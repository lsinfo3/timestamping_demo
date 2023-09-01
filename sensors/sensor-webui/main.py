from nicegui import ui
from nicegui.elements import button as nge
from nicegui.events import ValueChangeEventArguments
import pandas as pd
from typing import Dict
import copy
import time
import subprocess
import sys
import os
import stat

from netmiko import ConnectHandler
from typing import List

from helpers import ShellFunctionButton, ShellToggleButton, NicePandas, RunningProcess



kontron_switch = {
        'device_type': 'cisco_ios',
        'host': '10.0.0.5',
        'username': 'admin',
        'password': 'kosinu5',
        'port': 22,
        'secret': ''
        }


columns = [
    {'name': 'Enabled', 'label': 'Enabled', 'field': 'Enabled'},
    {'name': 'QcE', 'label': 'QoS Control Entry', 'field': 'QcE'},
    {'name': 'PCP', 'label': 'Priority Code Point', 'field': 'PCP'},
    {'name': 'CoS', 'label': 'Class of Service', 'field': 'CoS'},
]
kontron_settings = [
    {'id': 0, 'Enabled': False, 'QcE': 1, 'PCP': 0, 'CoS':0},
    {'id': 1, 'Enabled': False, 'QcE': 2, 'PCP': 0, 'CoS':0},
    {'id': 2, 'Enabled': False, 'QcE': 3, 'PCP': 0, 'CoS':0},
    {'id': 3, 'Enabled': False, 'QcE': 4, 'PCP': 0, 'CoS':0},
    {'id': 4, 'Enabled': False, 'QcE': 5, 'PCP': 0, 'CoS':0},
    {'id': 5, 'Enabled': False, 'QcE': 6, 'PCP': 0, 'CoS':0},
    {'id': 6, 'Enabled': False, 'QcE': 7, 'PCP': 0, 'CoS':0},
    {'id': 7, 'Enabled': False, 'QcE': 8, 'PCP': 0, 'CoS':0},
]
rows_default = copy.deepcopy(kontron_settings)

PCP_options = list(range(0,8))
CoS_options = list(range(0,8))



ddf = pd.DataFrame(data={
    "Sensor": ["Humidity", "Temp", "PTC_Temp", "Light"],
    "Enabled": [True]*4,
    'Period (μs)': [20000]*4,
    'PCP': [0]*4,
    'Port': [1234,1235,1236,1237]
})










def table_data_to_ios_cmd():
    """
    convert data to qos cmds for the kontron switch
    """
    str_lst = []
    for r in kontron_settings:
        if r['Enabled']:
            str_lst.append(f"qos qce {r['QcE']} tag pcp {r['PCP']} action cos {r['CoS']}")
    return str_lst

def ios_reset_qce():
    str_lst = []
    for r in kontron_settings:
        str_lst.append(f"no qos qce {r['QcE']}")
    return str_lst


def set_qos():
    """
    send list of cmds to the kontron switch
    """
    print(table_data_to_ios_cmd())
    con = ConnectHandler(**kontron_switch)
    con.send_config_set(ios_reset_qce())
    ui.notify(f"Reset QoS control list configuration")
    output = con.send_config_set(table_data_to_ios_cmd())
    #ui.notify(f"New QoS control list: {table_data_to_ios_cmd()}")
    ui.notify(f"New QoS control list: >> {output}")

def kontron_update_settings(msg: Dict) -> None:
    """
    rename data according to fields in the webui
    """
    for row in kontron_settings:
        if row['id'] == msg['args']['id']:
            row['Enabled'] = msg['args']['Enabled']
            row['PCP'] = msg['args']['PCP']
            row['QcE'] = msg['args']['QcE']
            row['CoS'] = msg['args']['CoS']
    #print(kontron_settings)


def make_table_switch()-> None:
    """
    creates a new table for qos data
    """
    container.clear()
    with container:
        table = ui.table(columns=columns, rows=kontron_settings, row_key='QcE').classes('w-full bg-gray-100')
        table.add_slot('body', r'''
            <q-tr :props="props">
                <q-td key="Enabled" :props="props">
                    <q-checkbox
                        v-model="props.row.Enabled"
                        @update:model-value="() => $parent.$emit('rename', props.row)"
                    />
                </q-td>
                <q-td key="QcE" :props="props">
                    {{ props.row.QcE }}
                </q-td>
                <q-td key="PCP" :props="props">
                    <q-select
                        v-model="props.row.PCP"
                        :options="''' + str(PCP_options) + r'''"
                        @update:model-value="() => $parent.$emit('rename', props.row)"
                    />
                </q-td>
                <q-td key="CoS" :props="props">
                    <q-select
                        v-model="props.row.CoS"
                        :options="''' + str(CoS_options) + r'''"
                        @update:model-value="() => $parent.$emit('rename', props.row)"
                    />
                </q-td>
            </q-tr>
        ''')
        table.classes("text-xl/8")
        # table.style("font-size: 200% !important")
        table.on('rename', kontron_update_settings)

def reset_rows():
    """
    reset qos table in the webui
    """
    global kontron_settings
    kontron_settings = copy.deepcopy(rows_default)
    print(kontron_settings)
    make_table_switch()


with ui.tabs() as tabs:
    tabs.tailwind.text_color("blue-600").margin("m-2")
    t1 = ui.tab('Traffic', icon='mediation')
    t1.tooltip("configure traffic")
    t2 = ui.tab('Switch', icon='sync_alt')
    t2.tooltip("configure switch priorities")
    t2.tailwind.font_size("2xl")
    t2.props("font-size: 200%")

class NumberClass:
    def __init__(self) -> None:
        self.number = 0


with ui.tab_panels(tabs, value='Traffic').classes("w-full"):
    with ui.tab_panel('Traffic') as tp:
        pandas_table = NicePandas(ddf)
        with ui.row() as r:
            r.tailwind.margin("m-2 mt-4")
            r.classes("item-center items-center justify-items-center")
            sensors_bin = RunningProcess(exe="/home/demo/sensors/query-sensors/sensor-query --interface end0.16", df=pandas_table.df)
            def sensors_send():
                #sensors_bin.df = pandas_table.df.copy(deep=True)
                sensors_bin.construct_params()
                sensors_bin.restart()
            ui.button("(Re)start", on_click=sensors_send)
            ui.button("Stop", on_click=sensors_bin.stop)
            #ui.label("False").bind_text_from(sensors_bin, "running")
            ui.html("").bind_content_from(sensors_bin, "running_html")
            sensor_rate_label=ui.html("").bind_content_from(sensors_bin, "rate_html")
            # BUG: why the f is the tooltip not working!?
            sensor_rate_label.tooltip("L2 including FCS")
            with sensor_rate_label:
                ui.tooltip("L2 including FCS")
        with ui.row() as r:
            r.tailwind.margin("m-2")
            ui.button("Reset settings", on_click=pandas_table.reset)

        with ui.row() as r:
            r.tailwind.margin("m-2 mt-6")
            synctraffic_toggle_button = ShellToggleButton(
                    "Sinus curve synthetic traffic",
                    cmd_on= lambda : {"cmd":f"sudo nohup tcpreplay -K -l 0 --pps={synctraffic_toggle_button.data} -i end0.16 ~/pcaps/syc-50.pcap </dev/null 1>/dev/null 2>&1 &","value":synctraffic_toggle_button.data},
                    cmd_off= lambda : {"cmd":"sudo killall tcpreplay","value":0},
                    start_value=0,
                    data=500
                    )
            synctraffic_toggle_button.callback = lambda : [f"<div class=\"bg-gray-200 p-2 rounded\">PPS: {synctraffic_toggle_button.value}</div>",f"<div class=\"bg-gray-200 p-2 rounded\">Rate(L2): {synctraffic_toggle_button.value * 68*8.0}bps</div>"]
            ui.html("").bind_content_from(synctraffic_toggle_button, "state")
            ui.html("").bind_content_from(synctraffic_toggle_button, "call", backward=lambda t : t[0])
            ui.html("").bind_content_from(synctraffic_toggle_button, "call", backward=lambda t : t[1])
            ui.number(label="PPS", value=500, min=2, max=2000).bind_value(synctraffic_toggle_button, "data").style(add="margin-top: -1rem;")

        with ui.row() as r:
            # Compensate -1 from ui.number input
            r.tailwind.margin("m-2 mt-7")
            shaping_toggle_button = ShellToggleButton(
                    "Shaping",
                    cmd_on= lambda : {"cmd": f"sudo tc qdisc add dev end0.16 root tbf rate {int(sensors_bin.rate +synctraffic_toggle_button.value*68 *8)} mpu {68} latency 1000ms burst {68} minburst 1500", "value":int(sensors_bin.rate +synctraffic_toggle_button.value*68*8)},
                    cmd_off=lambda : {"cmd": f"sudo tc qdisc del dev end0.16 root", "value":0},
                    start_value=0
                    )
            shaping_toggle_button.callback = lambda : f"<div class=\"bg-gray-200 p-2 rounded\">Rate(L2): {shaping_toggle_button.value}bps</div>"
            ui.html("").bind_content_from(shaping_toggle_button, "state")
            ui.html("").bind_content_from(shaping_toggle_button, "call")

        with ui.row() as r:
            r.tailwind.margin("m-2 mt-12")
            xtraffic_toggle_button = ShellToggleButton(
                    "Cross Traffic RPi4/5",
                    # nohup and running in background seems to fix the issue
                    cmd_on= lambda : {"cmd":f"ssh Demo4 'sudo nohup tcpreplay -K --topspeed --loop=0 -i end0.16 ~/iperf-novlan.pcap </dev/null >/dev/null 2>&1 &'; ssh Demo5 'sudo nohup tcpreplay -K --topspeed --loop=0 -i end0.16 ~/iperf-novlan.pcap </dev/null >/dev/null 2>&1 &'"},
                    cmd_off= lambda : {"cmd":f"ssh Demo4 sudo killall tcpreplay; ssh Demo5 sudo killall tcpreplay"}
                    )
            ui.html("").bind_content_from(xtraffic_toggle_button, "state")

        with ui.row() as r:
            r.tailwind.margin("m-2 mt-6")
            xtraffic_toggle_button = ShellToggleButton(
                    "Cross Traffic local",
                    # nohup and running in background seems to fix the issue
                    # HACK: tcpreplay-clone is just a symlink to tcpreplay! fix for killall tcpreplay: crosstraffic & sinus curve
                    cmd_on= lambda : {"cmd":f"sudo nohup tcpreplay-clone -K --topspeed --loop=0 -i end0.17 ~/pcaps/iperf-novlan.pcap </dev/null >/dev/null 2>&1 &"},
                    cmd_off= lambda : {"cmd":f"sudo killall tcpreplay-clone"}
                    )
            ui.html("").bind_content_from(xtraffic_toggle_button, "state")

    with ui.tab_panel('Switch') as tp:
        container = ui.column()
        make_table_switch()
        with ui.row() as r:
            r.tailwind.margin("m-2")
            ui.button('Save', on_click=set_qos)
            ui.button('Reset', on_click=reset_rows)

"""
- row:
    select:
      value: [a,b,c,d,e]
    slider:
      value: [0,100]
      bindid: 1234
    label:
      value: text
    checkbox:
      value: ??
    number:
      value: ??
      bindid: 1234
- row:
    select:
      [a,b,c]
"""


ui.run(show=False, reload=True, port=8080)
