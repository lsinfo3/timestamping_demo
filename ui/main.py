import numpy as np
from nicegui import ui, app, events
from matplotlib import pyplot as plt
import numpy as np
import plotly.graph_objects as go
import os
import io
import pandas as pd
from typing import List, Optional, Dict, Union, Tuple, Callable, Set, Mapping
import subprocess
import time
import tsncalc
import plotutils
from bidict import bidict
import math
import helpers, gridutils, colors, binutils, utils

PIPE_NAME: os.PathLike = os.path.expanduser("/tmp/tsn-pipe")
IFACES: List[str] = ["enp3s0f1", "enp3s0f0"]
PIPE: Optional[io.TextIOWrapper] = None
PIPE_IF1: Optional[io.TextIOWrapper] = None
PIPE_IF2: Optional[io.TextIOWrapper] = None
DATA: pd.DataFrame = pd.DataFrame(columns=["pcp","id", "ts_if1", "ts_if2", "flow_id", "ip_src", "ip_dst", "port_src", "port_dst", "proto", "size", "cummvol", "cummvol_flow"])
DATA_IF1: pd.DataFrame = pd.DataFrame(columns=["pcp", "id", "ts_if1", "ts_if2", "flow_id", "ip_src", "ip_dst", "port_src", "port_dst", "proto", "size", "cummvol", "cummvol_flow"])
DATA_IF2: pd.DataFrame = pd.DataFrame(columns=["pcp","id", "ts_if1", "ts_if2", "flow_id", "ip_src", "ip_dst", "port_src", "port_dst", "proto", "size", "cummvol", "cummvol_flow"])
CUMMVOL: Dict[int, List[int]] = {}
TIMEDELTA: int = int(10e9)
TIMEDELTA_DETECT_INPUT: Optional[ui.number] = None
RUNNING: bool = False
DETECTING: bool = True
TABLE_FLOWS: Optional[ui.table] = None
TABLE_ALERT_IF1: Optional[gridutils.GridHelper] = None
TABLE_ALERT_IF2: Optional[gridutils.GridHelper] = None
FIGURE: Optional[go.Figure] = None
FLOWIDS: Mapping[Tuple[str, int, str, int, str, int], int] = bidict()
FLOWIDS[("1.2.3.4", 5, "6.7.8.9", 10, 11, 0)] = -1                  # (src_ip, src_port, dst_ip, dst_port, proto, pcp) -> flow_idsst
CAPTURE_PROCESS: Optional[subprocess.Popen] = None
APP: str = os.path.abspath("./ts-bin/ts_ring_hw")
LINECACHE: str = ["" for _ in range(3)]
MAX_TS: List[int] = [0, 0]
LAST_TS: Dict[int, List[int]] = {}
REFRESH_TIMER: Optional[ui.timer] = None
WINDOW_CUMM_DATA: Dict[int, Tuple[int, int]] = dict() # flow_id -> (rate_if1, rate_if2)
BUCKETS: Dict[int, List[tsncalc.Bucket]] = dict()
ACTIVE_FLOWS: Set[int] = set()
WINDOW_TIMEDELTA: List[int] = [1, 1]
TABS: Optional[ui.tab] = None
START_TIME: Optional[int] = None
DELAY: int = 0
CALIBRATING: bool = False
BURST_SIZES: dict[int, int] = dict() # flow_id -> Burst Size in Bytes
RATES: dict[int, float] = dict() # flow_id -> Max. Rate in kbps

DELAY_BIN_BOUNDARIES=[6000,7000,9000,12000,16000,21000,30000,45000,60000,70000,90000,120000,160000,210000,300000,450000,6000000,700000,900000,1200000,1600000,2100000,3000000,4500000,6000000]
IAT_BIN_BOUNDARIES=[int(1e6), int(2e6), int(6e6), int(1e7), int(2e7), int(6e7)]
SIZE_BIN_BOUNDARIES=[128, 256, 512, 1024]
DELAY_BINS: Dict[int, binutils.Bins]={}
IAT_BINS: Dict[int, Tuple[binutils.Bins, binutils.Bins]]={}
SIZE_BINS: Dict[int, Tuple[binutils.Bins, binutils.Bins]]={}

def generate_layout() -> None:
    global TABLE_FLOWS, TABLE_ALERT_IF1, TABLE_ALERT_IF2, FIGURE, REFRESH_TIMER, TIMEDELTA_DETECT_INPUT, TABS
    columns = [
        "active", "icon", "pcp", "ip_src", "port_src", "ip_dst", "port_dst", "proto", "rate", "burst_size"
    ]
    column_types = {
        "active": gridutils.ColumnTypes.checkbox,
        "icon": gridutils.ColumnTypes.icon,
        "rate": gridutils.ColumnTypes.number,
        "burst_size": gridutils.ColumnTypes.number
    }
    column_names = {
        "active": "",
        "pcp": "PCP",
        "icon": "Color",
        "ip_src": "Source IP",
        "ip_dst": "Destination IP",
        "port_src": "Source Port",
        "port_dst": "Destination Port",
        "proto": "Protocol",
        "burst_size": "Burst Size [B]",
        "rate": "Rate [kbps]"
    }

    rows = [
        {"flow_id": -2, "ip_src": "10.0.0.1", "port_src": 61234, "ip_dst": "10.0.0.2", "port_dst": 80, "proto": "TCP"},
        {"flow_id": -3, "ip_src": "10.0.0.1", "port_src": 62345, "ip_dst": "10.0.0.2", "port_dst": 80, "proto": "TCP"},
    ]

    columns_alert_tables: List[Dict[str, any]] = [
        {"name": "flow_id", "label": "Flow", "field": "flow_id", "required": True, "align": "left"},
        {"name": "burst", "label": "Burst", "field": "burst", "required": True},
        {"name": "rate", "label": "Rate", "field": "rate", "required": True},
        {"name": "burst_alert", "label": "Alert", "field": "burst_alert"}
    ]
    columns_alert_tables = ["icon", "burst", "rate", "burst_alert"]
    column_types_alert_table = {
        "burst_alert": gridutils.ColumnTypes.icon,
        "icon": gridutils.ColumnTypes.icon,
    }
    column_names_alert_table = {
        "icon": "Color",
        "burst": "Burst [B]",
        "rate": "Rate [L2]",
        "burst_alert": "Alert"
    }

    FIGURE = go.Figure(go.Scatter(x=[1, 2, 3, 4], y=[1, 2, 3, 2.5], uid="-2"))
    FIGURE.update_layout(margin=dict(l=0, r=0, t=0, b=0))
    REFRESH_TIMER = ui.timer(interval=1, callback=refresh)
    app.on_startup(startup)
    app.on_shutdown(shutdown)


    with ui.column():
        with ui.row():
            TIMEDELTA_DETECT_INPUT = ui.number(label="Detect Time", value=5, step=1)
            ui.button("Detect", on_click=detect)
            ui.button("Calibrate", on_click=start_calibration)
            ui.button("Start", on_click=start_plot)
            ui.button("Stop", on_click=stop_plot)
            ui.number(label="Refresh Time", value=1, step=0.1, on_change=lambda vce: update_refresh_timer(vce.value))
            timedelta_input = ui.number(label="Deletion Time", value=10, step=1)
            ui.button(text="Apply", on_click=lambda: update_timedelta(timedelta_input.value))
        with ui.row():
            with ui.column().style(add="height: 90vh; width: 33vw"):
                with ui.card().style(add="height: 35%; width: 100%"):
                    TABLE_FLOWS = gridutils.GridHelper(df=pd.DataFrame(columns=columns + ['flow_id']), columns=columns, column_format=column_types, column_names=column_names, selector_column="active", min_width="1100px")
                with ui.card().style(add="height: 30%; width: 100%"):
                    TABLE_ALERT_IF1 = gridutils.GridHelper(df=pd.DataFrame(columns=columns_alert_tables), columns=columns_alert_tables, column_format=column_types_alert_table, column_names=column_names_alert_table, min_width="500px")
                with ui.card().style(add="height: 30%; width: 100%"):
                    TABLE_ALERT_IF2 = gridutils.GridHelper(df=pd.DataFrame(columns=columns_alert_tables), columns=columns_alert_tables, column_format=column_types_alert_table, column_names=column_names_alert_table, min_width="500px")
            with ui.card().style(add="height: 90vh; width: 60vw"):
                with ui.tabs().style(add="width: 100%") as TABS:
                    for function in plotutils.FUNCTIONS.keys():
                        ui.tab(function)
                with ui.tab_panels(TABS, value=next(iter(plotutils.FUNCTIONS.keys()))) as tab_panels:
                    for function_name, function_class in plotutils.FUNCTIONS.items():
                        with ui.tab_panel(function_name):
                            function_class.generate(vh=70, vw=55)


def start_calibration() -> None:
    global CALIBRATING
    # TODO Start Lukas' app
    CALIBRATING = True
    ui.timer(interval=TIMEDELTA_DETECT_INPUT.value, callback=stop_calibration, once=True)

def stop_calibration() -> None:
    global CALIBRATING, DELAY, DATA
    CALIBRATING = False
    DELAY += DATA['ts_if2'].mean() - DATA['ts_if1'].mean()


def update_refresh_timer(inpt: int) -> None:
    global REFRESH_TIMER
    if inpt > 0:
        REFRESH_TIMER.interval = inpt

def update_timedelta(inpt: int) -> None:
    global TIMEDELTA
    TIMEDELTA = inpt * int(1e9)

def startup() -> None:
    """
    Opens the named PIPE on startup. All actions that should be done once on startup should be placed here.
    :return: None
    """
    global PIPE, PIPE_IF1, PIPE_IF2
    os.system(f"killall -9 ts_ring_hw")
    if not os.path.exists(PIPE_NAME):
        os.mkfifo(PIPE_NAME)
    if not os.path.exists(f"{PIPE_NAME}-1"):
        os.mkfifo(f"{PIPE_NAME}-1")
    if not os.path.exists(f"{PIPE_NAME}-2"):
        os.mkfifo(f"{PIPE_NAME}-2")
    if CAPTURE_PROCESS is not None:
        stop_plot()
    PIPE = os.fdopen(os.open(PIPE_NAME, os.O_RDONLY | os.O_NONBLOCK), "r")
    PIPE_IF1 = os.fdopen(os.open(f"{PIPE_NAME}-1", os.O_RDONLY | os.O_NONBLOCK), "r")
    PIPE_IF2 = os.fdopen(os.open(f"{PIPE_NAME}-2", os.O_RDONLY | os.O_NONBLOCK), "r")
    create_flow("0.0.0.0", 0, "0.0.0.0", 0, 0, 0 )

    detect()

def shutdown() -> None:
    """
    All things that should be done once on UI application stop should be placed here.
    :return: None
    """
    global PIPE, CAPTURE_PROCESS
    print("Shutdown started...")
    os.system(f"killall -9 ts_ring_hw")
    print("...and shutdown completed!")

def evaluate_pipe(pipe: io.TextIOWrapper, df: pd.DataFrame, interface: int = 0) -> Tuple[pd.DataFrame, str]:
    """
    Routine called periodically to read the named pipe and process the input
    :return: Appended Data
    """
    global LINECACHE, MAX_TS, ACTIVE_FLOWS, WINDOW_TIMEDELTA, START_TIME, DELAY
    lines: List[str] = pipe.readlines()
    ids: List[int] = []
    tss_if1: List[int] = []
    tss_if2: List[int] = []
    ips_src: List[str] = []
    ips_dst: List[str] = []
    ports_src: List[int] = []
    ports_dst: List[int] = []
    protos: List[str] = []
    sizes: List[int] = []
    flowids: List[int] = []
    pcps: List[int] = []
    cumvols: List[int] = []
    cumvol_flow: List[int] =[]
    ts_written_to_bin: bool = False
    if len(lines) > 0:
        lines[0] = LINECACHE[interface] + lines[0]
        LINECACHE[interface] = lines.pop()
    for line in lines:
        line = line.replace("\n", "")
        #TODO append pcp instead of 0
        for index in range(len(splitline:=line.split(", ")) // 10):
            [id, ts_if1, ts_if2, ip_src, ip_dst, port_src, port_dst, proto, size, pcp] = splitline[10*index : 10*(index+1)]
            if START_TIME is None:
                START_TIME = int(ts_if1) if int(ts_if1) != 0 else int(ts_if2)
            ids.append(int(id))
            tss_if1.append(ts_if1_clean := int(ts_if1)-START_TIME)
            tss_if2.append(ts_if2_clean := int(ts_if2)-START_TIME-DELAY)
            ips_src.append(ip_src)
            ips_dst.append(ip_dst)
            ports_src.append(int(port_src))
            ports_dst.append(int(port_dst))
            protos.append(int(proto))
            sizes.append(int(size) + tsncalc.FCS)
            pcps.append(int(pcp))
            if (ip_src, port_src, ip_dst, port_dst, proto, pcp) not in FLOWIDS.keys():
                create_flow(ip_src, port_src, ip_dst, port_dst, proto, pcp)
            flowids.append(flowid := FLOWIDS[ip_src, port_src, ip_dst, port_dst, proto, pcp])
            CUMMVOL[flowid][interface] += int(size)
            CUMMVOL[0][interface] += int(size)
            cumvols.append(CUMMVOL[0][interface])
            cumvol_flow.append(CUMMVOL[flowid][interface])
            if interface > 0:
                WINDOW_CUMM_DATA[flowid][interface - 1] += int(size) + tsncalc.FCS
                WINDOW_CUMM_DATA[0][interface - 1] += int(size) + tsncalc.FCS
                if not ts_written_to_bin:
                    for flw in ACTIVE_FLOWS:
                        print(IAT_BINS[flw])
                        IAT_BINS[flw][interface - 1].push_ts(ts_if1_clean if interface == 1 else ts_if2_clean)
                        SIZE_BINS[flw][interface - 1].push_ts(ts_if1_clean if interface == 1 else ts_if2_clean)
                    ts_written_to_bin = True
                if flowid in ACTIVE_FLOWS:
                    SIZE_BINS[flowid][interface - 1].push(int(size))
                    if 0 in ACTIVE_FLOWS: SIZE_BINS[0][interface - 1].push(int(size))
                if LAST_TS[flowid][interface - 1] > -1 and flowid in ACTIVE_FLOWS:
                    IAT_BINS[flowid][interface - 1].push((ts_if1_clean if interface == 1 else ts_if2_clean) - LAST_TS[flowid][interface - 1])
                    if 0 in ACTIVE_FLOWS: IAT_BINS[0][interface - 1].push((ts_if1_clean if interface == 1 else ts_if2_clean) - LAST_TS[0][interface - 1])
                LAST_TS[flowid][interface - 1] = ts_if1_clean if interface == 1 else ts_if2_clean
                LAST_TS[0][interface - 1] = ts_if1_clean if interface == 1 else ts_if2_clean
            else:
                if not ts_written_to_bin:
                    for flw in ACTIVE_FLOWS:
                        DELAY_BINS[flw].push_ts(ts_if1_clean)
                    ts_written_to_bin = True
                if flowid in ACTIVE_FLOWS:
                    DELAY_BINS[flowid].push(ts_if2_clean - ts_if1_clean)
                    if 0 in ACTIVE_FLOWS: DELAY_BINS[0].push(ts_if2_clean - ts_if1_clean)


                
    df = pd.concat([df, appended_data := pd.DataFrame({
        "id": ids,
        "ts_if1": tss_if1,
        "ts_if2": tss_if2,
        "ip_src": ips_src,
        "ip_dst": ips_dst,
        "port_src": ports_src,
        "port_dst": ports_dst,
        "proto": protos,
        "size": sizes,
        "flow_id": flowids,
        "pcp": pcps,
        "cummvol": cumvols,
        "cummvol_flow": cumvol_flow
    })])

    if interface > 0:
        MAX_TS[interface - 1] =  df[f"ts_if{interface}"].max()
        WINDOW_TIMEDELTA[interface - 1] = MAX_TS[interface - 1] - df[f"ts_if{interface}"].min()
        min_ts = MAX_TS[interface - 1] - TIMEDELTA
    else:
        min_ts = df["ts_if2"].max() - TIMEDELTA
    for flowid in ACTIVE_FLOWS :
        # FCS is not subtracted as it is saved in the size column of DATA
        if flowid != 0: query: pd.DataFrame = df.query(f"ts_if{max(interface,1)} < @min_ts and flow_id == @flowid", inplace=False)['size']
        else: query = df.query(f"ts_if{max(interface,1)} < @min_ts", inplace=False)['size']
        if interface > 0:
            WINDOW_CUMM_DATA[flowid][interface - 1] -= query.sum()
            IAT_BINS[flowid][interface - 1].drop_older_than(min_ts)
            SIZE_BINS[flowid][interface - 1].drop_older_than(min_ts)
        else:
            DELAY_BINS[flowid].drop_older_than(min_ts)
    df.query(f"ts_if{max(interface,1)} >= @min_ts", inplace=True)

    return df, appended_data

def create_flow(ip_src: str, port_src: int, ip_dst: str, port_dst: int, proto: int, pcp: int) -> None:
    global FLOWIDS, WINDOW_CUMM_DATA, RATES, BUCKETS, BURST_SIZES
    flowid = FLOWIDS[ip_src, port_src, ip_dst, port_dst, proto, pcp] = max(FLOWIDS.values()) + 1
    WINDOW_CUMM_DATA[flowid] = [0, 0]
    BUCKETS[flowid] = [tsncalc.Bucket(0, 0, 0), tsncalc.Bucket(0,0,0)]
    RATES[flowid] = 7000.0
    BURST_SIZES[flowid] = 68
    SIZE_BINS[flowid] = [binutils.Bins(SIZE_BIN_BOUNDARIES) for _ in range(2)]
    IAT_BINS[flowid] = [binutils.Bins(IAT_BIN_BOUNDARIES) for _ in range(2)]
    DELAY_BINS[flowid] = binutils.Bins(DELAY_BIN_BOUNDARIES)
    LAST_TS[flowid] = [-1,-1]
    CUMMVOL[flowid] = [0,0,0]

def reset_flow(flowid: int) -> None:
    """
    Deletes all flow-specific data. Should be called on (re-)start
    :param: flowid: int: Unique idetifier of the flow
    :return: None
    """
    global WINDOW_CUMM_DATA, BUCKETS
    print(f"Flow {flowid} resetted!")
    WINDOW_CUMM_DATA[flowid] = [0, 0]
    BUCKETS[flowid] = [tsncalc.Bucket(0, 0, 0), tsncalc.Bucket(0, 0, 0)]

def drop_data() -> None:
    """
    Deletes all (temporary) data. Should be called on (re-)start
    :retrn: None
    """
    global DATA, DATA_IF1, DATA_IF2, CUMMVOL, LINECACHE, ACTIVE_FLOWS, START_TIME, DELAY_BINS, SIZE_BINS, IAT_BINS, LAST_TS
    START_TIME = None
    LINECACHE = ["" for _ in range(3)]
    DATA = pd.DataFrame(columns=["cummvol", "cummvol_flow", "id", "pcp", "ts_if1", "ts_if2", "flow_id", "ip_src", "ip_dst", "port_src", "port_dst", "proto", "size"])
    DATA_IF1 = pd.DataFrame(columns=["cummvol", "cummvol_flow", "id", "pcp", "ts_if1", "ts_if2", "flow_id", "ip_src", "ip_dst", "port_src", "port_dst", "proto", "size"])
    DATA_IF2 = pd.DataFrame(columns=["cummvol", "cummvol_flow", "id", "pcp", "ts_if1", "ts_if2", "flow_id", "ip_src", "ip_dst", "port_src", "port_dst", "proto", "size"])
    for flowid in FLOWIDS.values():
        reset_flow(flowid)
    for function in plotutils.FUNCTIONS.values():
        function.start(ACTIVE_FLOWS)
    DELAY_BINS={key: binutils.Bins(DELAY_BIN_BOUNDARIES) for key in DELAY_BINS.keys()}
    IAT_BINS={key: [binutils.Bins(IAT_BIN_BOUNDARIES) for _ in range(2)] for key in IAT_BINS.keys()}
    SIZE_BINS={key: [binutils.Bins(SIZE_BIN_BOUNDARIES) for _ in range(2)] for key in SIZE_BINS.keys()}
    LAST_TS={key: [-1,-1] for key in LAST_TS.keys()}
    CUMMVOL={key: [0,0,0] for key in CUMMVOL.keys()}



def refresh() -> None:
    """
    This method is looped. All methods that should be calles frequently can be placed here, especially if they should be called before or after another specific mehtod is started or has stopped
    :return: None
    """
    global DETECTING, RUNNING, CALIBRATING, DATA, DATA_IF1, DATA_IF2
    if DETECTING or CALIBRATING:
        DATA, _ = evaluate_pipe(pipe=PIPE, df=DATA)
    if RUNNING:
        DATA, appended_data = evaluate_pipe(pipe=PIPE, df=DATA)
        DATA_IF1, appended_data_if1 = evaluate_pipe(pipe=PIPE_IF1, df=DATA_IF1, interface=1)
        DATA_IF2, appended_data_if2 = evaluate_pipe(pipe=PIPE_IF2, df=DATA_IF2, interface=2)
        refresh_buckets(appended_data_if1, appended_data_if2)
        refresh_alert_tables()
        refresh_plot()


def refresh_buckets(appended_data_if1: pd.DataFrame, appended_data_if2: pd.DataFrame) -> None:
    """
    Updates the Buckes state. Note: The timestamps should be passed ordered to tsncalc
    :return: None
    """
    global BUCKETS, RATES
    for flowid in ACTIVE_FLOWS:
        for i, appended_data in enumerate((appended_data_if1, appended_data_if2)):
            if flowid == 0:
                data: pd.DataFrame = appended_data
            else:
                data = appended_data.query("@flowid == flow_id")
            BUCKETS[flowid][i] = tsncalc.validate_envelope_bucket(data[[f"ts_if{ i + 1 }", "size"]].rename(columns={f"ts_if{ i + 1 }": "ts"}).sort_values(by="ts", inplace=False, kind='stable'), RATES[flowid], BUCKETS[flowid][i])


def refresh_alert_tables() -> None:
    global TABLE_ALERT_IF1, TABLE_ALERT_IF2, BUCKETS, ACTIVE_FLOWS, WINDOW_CUMM_DATA, RATES, BURST_SIZES
    for i, (alerttable, iface) in enumerate(zip((TABLE_ALERT_IF1, TABLE_ALERT_IF2), IFACES)):

        flow_ids: List[int] = list(ACTIVE_FLOWS)
        icon = [("circle", colors.Colors[flow_id]) for flow_id in flow_ids]
        rates: List[str] = [calculate_rate_with_unit(WINDOW_CUMM_DATA[flow_id][i], WINDOW_TIMEDELTA[i]) for flow_id in flow_ids]
        bursts: List[Optional[int,str]] = [math.ceil(BUCKETS[flow_id][i].size / 8) for flow_id in flow_ids]
        alerts: List[Tuple[str, str]] = [("warning", "#ff0000") if BUCKETS[flow_id][i].size / 8 > BURST_SIZES[flow_id] or WINDOW_CUMM_DATA[flow_id][i]*8e9/WINDOW_TIMEDELTA[i] >RATES[flow_id] else ("circle", "#000000") for flow_id in flow_ids]
        icon += [("","")]
        rates += [(add_unit_to_rate(utils.get_rate_by_interface(iface)))]
        bursts += [""]
        alerts += [("","")]
        alerttable.update(pd.DataFrame(dict(icon=icon, rate=rates, burst=bursts, burst_alert=alerts)))



def calculate_rate_with_unit(data: int, time: int) -> str:
    """
    Takes amount of data in bytes and time in nanoseconds
    """
    rate: float = data * 8 / (time * 1e-9)
    return add_unit_to_rate(rate)

def add_unit_to_rate(rate: float) -> str:
    prefix: str = ""
    if rate < 1e3:
        pass
    elif rate < 1e6:
        rate /= 1e3
        prefix = 'k'
    elif rate < 1e9:
        rate /= 1e6
        prefix = 'M'
    else:
        rate /= 1e9
        prefix = 'G'

    if rate < 1e1:
        rate = round(rate, 2)
    elif rate < 1e2:
        rate = round(rate, 1)
    # TODO: why is rate here sometimes NaN?
    else: rate =  round(rate)

    return f"{rate}{prefix}bps"


def detect() -> None:
    """
    Executed on click of the detect button. Refreshes the stream list.
    :return: None
    """
    global DETECTING, CAPTURE_PROCESS, APP, PIPE, PIPE_IF1, PIPE_IF2
    global TIMEDELTA_DETECT_INPUT
    RUNNING = True

    if CAPTURE_PROCESS is not None:
        helpers.kill(CAPTURE_PROCESS.pid)
        CAPTURE_PROCESS.wait()
        CAPTURE_PROCESS = None

    CAPTURE_PROCESS = subprocess.Popen(APP)
    DETECTING = True
    ui.timer(interval=TIMEDELTA_DETECT_INPUT.value, callback=stop_detecting, once=True)

def stop_detecting() -> None:
    """
    Scheduled at the End of the Detecting Routine
    """
    global DETECTING, CAPTURE_PROCESS, PIPE
    DETECTING = False
    # PIPE.close()
    # PIPE = None
    if CAPTURE_PROCESS is not None:
        helpers.kill(CAPTURE_PROCESS.pid)
        CAPTURE_PROCESS.wait()
        CAPTURE_PROCESS = None

    CAPTURE_PROCESS = None
    RUNNING = False
    refresh_table()

def refresh_table() -> None:
    global TABLE_FLOWS, DATA, BURST_SIZES, RATES, TABLE_FLOWS
    RATES.update({row['flow_id']: row['rate']*1000 for row in TABLE_FLOWS.df.iloc})
    BURST_SIZES.update({row['flow_id']: row['burst_size'] for row in TABLE_FLOWS.df.iloc})
    locdata: pd.DataFrame = pd.concat([
        DATA[["pcp", "flow_id", "ip_src", "port_src", "ip_dst", "port_dst", "proto"]].drop_duplicates(),
        pd.DataFrame(dict(pcp=[""], flow_id=[0], ip_src=[""], port_src=[""], ip_dst=[""], port_dst=[""], proto=[""]))
    ], ignore_index=True)
    is_active = lambda flow_id: (TABLE_FLOWS.df['flow_id'] == flow_id).any() and TABLE_FLOWS.df[TABLE_FLOWS.df['flow_id'] == flow_id].iloc[0]['active']
    locdata["active"] = [is_active(flow_id) for flow_id in locdata["flow_id"]]
    locdata["icon"] = [("circle", colors.Colors[flow_id]) for flow_id in locdata["flow_id"]]
    locdata["burst_size"] = [BURST_SIZES[flow_id] for flow_id in locdata["flow_id"]]
    locdata["rate"] = [RATES[flow_id]/1000 for flow_id in locdata["flow_id"]]
    locdata.sort_values("flow_id", inplace=True)
    TABLE_FLOWS.update(locdata)

def refresh_plot() -> None:
    global DATA, ACTIVE_FLOWS
    data = (DATA, DATA_IF1, DATA_IF2)
    bins = (DELAY_BINS, IAT_BINS, SIZE_BINS)
    plotutils.FUNCTIONS[TABS.value].update(data, bins, ACTIVE_FLOWS)


def start_plot() -> None:
    """
    Triggered by "Start" button
    :return: None
    """
    global RUNNING, ACTIVE_FLOWS, CAPTURE_PROCESS, APP, FLOWIDS, TABLE_FLOWS, DELAY_BINS, SIZE_BINS, IAT_BINS
    if RUNNING:
        stop_plot()
    RATES.update({row['flow_id']: row['rate']*1000 for row in TABLE_FLOWS.df.iloc})
    BURST_SIZES.update({row['flow_id']: row['burst_size'] for row in TABLE_FLOWS.df.iloc})
    ACTIVE_FLOWS = set(TABLE_FLOWS.selected()['flow_id'])
    drop_data()
    arg = ""
    for flowid in ACTIVE_FLOWS:
        if flowid != 0:
            flow = FLOWIDS.inv[flowid]
            arg += f"(src {flow[0]} and src port {flow[1]} and dst {flow[2]} and dst port {flow[3]} and proto {flow[4]}) or "
    os.system(f"killall -9 ts_ring_hw")
    CAPTURE_PROCESS = subprocess.Popen([APP, "-l", "EN10MB", "-r", "-b", arg[:-4]])
    # PIPE = open(PIPE_NAME, "r")
    RUNNING = True


def stop_plot() -> None:
    """
    Triggered by "Stop" button
    :return: None
    """
    global RUNNING, CAPTURE_PROCESS, PIPE
    RUNNING = False
    # PIPE.close()
    # PIPE = None
    if CAPTURE_PROCESS is not None:
        helpers.kill(CAPTURE_PROCESS.pid)
        CAPTURE_PROCESS.wait()
        CAPTURE_PROCESS = None
    os.system(f"killall -9 ts_ring_hw")
    CAPTURE_PROCESS = None


def main() -> None:
    generate_layout()
    ui.run(port=8080)
    # refresh_table()

if __name__ in {"__main__", "__mp_main__"}:
    main()
