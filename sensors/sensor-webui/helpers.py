import nicegui as ng
from nicegui import ui
import time

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

import subprocess
import psutil
from typing import Callable


SFD = 8         # preamble + start frame delimiter
IPG = 12        # interpacket gap
FCS = 4         # frame check sequence
FRAMESPACING_L1 = SFD + IPG + FCS
FRAMESPACING_L2 = FCS



def kill(proc_pid):
    process = psutil.Process(proc_pid)
    for proc in process.children(recursive=True):
        proc.kill()
    process.kill()


class ShellFunctionButton(ng.elements.button.Button):
    """
    A nicegui button which launches a shell function via subprocess.Popen
    """
    def __init__(self, label:str, cmd: str) -> None:
        super().__init__(label,on_click= self.run)
        self.cmd = cmd
        #super().on_click = self.run()

    def run(self):
        subprocess.Popen(self.cmd, shell=True).wait()

class ShellToggleButton(ng.elements.button.Button):
    """
    A nicegui button which launches a shell function via subprocess.Popen
    """
    def __init__(self, label:str, cmd_on: Callable, cmd_off: Callable, data=None, start_value=None, callback: Callable = None) -> None:
        super().__init__(label,on_click= self.run)
        self.cmd_on = cmd_on
        self.cmd_off = cmd_off
        self.on = False
        self.data = data
        self.callback = callback
        self.value = start_value

    @property
    def call(self):
        return self.callback()

    @property
    def state(self):
        if self.on:
            return f"<div class=\"bg-green-500 p-2 rounded \">On</div>"
        else:
            return f"<div class=\"bg-red-500 p-2 rounded\">Off</div>"

    def run(self):
        if self.on:
            cmd_off = self.cmd_off()
            if "value" in cmd_off.keys():
                self.value = cmd_off["value"]
            cmd_off = cmd_off["cmd"]
            print(cmd_off)
            ui.notify(cmd_off)
            subprocess.Popen(cmd_off, shell=True).wait()
            self.classes('bg-red-100')
        else:
            cmd_on = self.cmd_on()
            if "value" in cmd_on.keys():
                self.value = cmd_on["value"]
            cmd_on = cmd_on["cmd"]
            ui.notify(cmd_on)
            print(cmd_on)
            subprocess.Popen(cmd_on, shell=True).wait()
            self.classes('bg-green-100')
        self.on = not self.on



class RunningProcess():
    """
    takes a full path to a binary and a set of parameter, each as single strings
    """
    def __init__(self, exe, df):
        self.exe = f"{exe}"
        self.popen = None
        self.df = df
        self.params = self.construct_params()
        self.rate = 0
        self.aggregate = 1

    @property
    def running_html(self):
        if self.popen == None:
            return f"<div class=\"bg-red-500 p-2 rounded\">Off</div>"
        else:
            return f"<div class=\"bg-green-500 p-2 rounded \">On</div>"

    @property
    def cmd(self):
        if self.params:
            return self.exe + " " + self.params
        else:
            return self.exe

    def construct_params(self):
        ss = "bin "
        flags = []
        translations = {
                "Humidity":"hum",
                "Light":"lig",
                "Temp":"tem",
                "PTC_Temp":"ptc"
                }
        for _, row in self.df.iterrows():
            if row["Enabled"]:
                sensortype = translations[str(row["Sensor"])]
                flags.append(f"--sensor_{sensortype}_delay {row['Period (μs)']}")
                flags.append(f"--sensor_{sensortype}_pcp {row['PCP']}")
                flags.append(f"--sensor_{sensortype}_port {row['Port']}")
        params = " ".join(flags)
        self.params = params

    def calc_rate(self):
        """
        calculate L2 (NO FCS) rate in bps
        """
        total_rate = 0
        for _, row in self.df.iterrows():
            if row["Enabled"]:
                # payload = 12 bytes * 8 = 96 bits
                # WARN: payload_size/self.aggregate ist grade wilder blödsinn!
                pps = ( 1e6 / row['Period (μs)']) / self.aggregate
                payload_size = 12 * self.aggregate
                pkt_size = max(68,payload_size) * 8
                total_rate += pps * pkt_size
        self.rate = total_rate

    @property
    def rate_html(self):
        return f"<div class=\"bg-gray-200 p-2 rounded\">Rate(L2): {self.rate:.1f}bps</div>"

    def start(self):
        print(self.cmd)
        print()

        try:
            self.popen.wait(0)
        except:
            pass
        try:
            self.popen = subprocess.Popen(self.cmd, shell=True)
            self.calc_rate()
        except:
            pass

    def stop(self):
        # subprocess.Popen(f"killall {self.exe}", shell=True).wait()

        if not self.popen is None:
            kill(self.popen.pid)
            self.rate = 0
            self.popen = None

        time.sleep(0.2)
        subprocess.Popen(f"sudo killall sensor-query", shell=True).wait()
        # if self.popen:
        #     self.popen.terminate()
        #     #time.sleep(2)
        #     #if self.popen.poll():
        #     #    print("Process didn't close in time, killing!", file=sys.stderr)
        #     #    self.popen.kill()
        # else:
        #     raise TypeError("Process has not been started!")

    def restart(self, params = None):
        if params:
            self.params = params
        self.stop()
        self.start()


class NicePandas():
    """
    Create a table from a pandas dataframe with editable fields.
    Asume non-bool non-numeric values are labels and not supposed to be editable.
    """
    def __init__(self, dataframe: pd.DataFrame) -> None:
        self.df = dataframe
        self.grid = ui.grid(rows=len(self.df.index) * 1+1).classes('grid-flow-col gap-0')
        self.org_df = dataframe.copy(deep=True)
        self.make_grid()

    def make_grid(self):
        with self.grid:
            self.grid.clear()
            self.grid.classes('rounded-xl p-0 bg-gray-100 shadow-xl item-center')
            for c, col in enumerate(self.df.columns):
                label = ui.label(col)
                label.classes('font-bold m-0 px-8 pt-8 h-16')
                for r, row in enumerate(self.df.loc[:, col]):
                    if is_bool_dtype(self.df[col].dtype):
                        cls = ui.checkbox(value=row, on_change=lambda event, r=r, c=c: self.update(r=r, c=c, value=event.value))
                    elif is_numeric_dtype(self.df[col].dtype):
                        cls = ui.number(value=row, on_change=lambda event, r=r, c=c: self.update(r=r, c=c, value=event.value))
                    else:
                        cls = ui.label(row)
                        # for some reason, labels have the wrong size so padding is adjusted to center them
                        cls.style(add="padding-top: 25px;")
                    cls.classes("px-8 py-2 m-0 h-fit border-solid border-x-0 border-b-0 border-t-2 border-gray-300")
                    cls.style(add="border-top-width: 1.0px;")


    def update(self, *, r: int, c: int, value):
        self.df.iat[r, c] = value
        # print(self.df)

    def reset(self):
        self.df = self.org_df.copy(deep=True)
        self.make_grid()
        print(self.df)







