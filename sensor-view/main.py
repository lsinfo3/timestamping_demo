import socket
import struct
import sys
import math
from datetime import datetime
from nicegui import ui
import time
import multiprocessing
import queue
import logging
logger = logging.getLogger("sensor-view")
log_formater = logging.Formatter(fmt=f"%(asctime)s [%(levelname)-8s] %(message)s", datefmt="[%H:%M:%S]")
log_streamhandler = logging.StreamHandler()
log_streamhandler.setFormatter(log_formater)
logger.handlers.clear()
logger.addHandler(log_streamhandler)
logger.setLevel(logging.INFO)


UDP_IP = "10.1.1.2"
UDP_PORTS = [1233,1234,1235,1236,1237]
UDP_PORTS = list(range(1200,1250))

"""
Start a range of processes
Each process listens (blocking) on a port
When the first packet is received, read the id and get the corresponding queue from a dict

"""



""" when adding synthetic traffic, just invent a sensor_id """
SENSOR_MAP = {
        "ZSE":"Temperature",
        "23pL":"Industrial PTC Temp",
        "25AR":"Ambient Light",
        "TsB":"Humidity",
        "SYC": "Sinus",
        }
SENSOR_LEGEND = {
        "ZSE":"temp °C",
        "23pL":"temp °C",
        "25AR":"ambient light lx",
        "TsB":"relative humidity %",
        "SYC":"sinus",
        }

sensor_queues = {}
sensor_processes = {}
tabs_map = {}
sockets = {}


def get_sensor_id_q_from_pkt(sock: socket.socket) -> multiprocessing.Queue:
    """
    Get sensor id and corresponding queue from the first packet
    """
    # INFO: keep blocking mode, inactive threads will just idle
    data, _ = sock.recvfrom(512)
    logger.info(f"Starting process after receiving packet: {data}")
    unpacked = struct.unpack("!4s2l",data)
    sensor_id = unpacked[0].decode('utf-8').replace('\x00','')
    return sensor_queues[sensor_id]

def get_values(port:int):
    """
    Process which recieves data and puts it into a queue
    """
    sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    sock.bind((UDP_IP,port))
    q = get_sensor_id_q_from_pkt(sock)

    while True:
        data, _ = sock.recvfrom(512)
        unpacked = struct.unpack("!4s2l",data)
        #sensor_id = unpacked[0].decode('utf-8').replace('\x00','')
        sensor_value = unpacked[1]
        #sensor_sequence = unpacked[2]
        q.put((sensor_value,datetime.now()))


def update_line_plot(line_plot,q,quota=1) -> None:
    """
    Get all values from the queue until empty.
    This function gets called to update a plot.
    """
    x = []
    y = []
    i = 0
    while True:
        try:
            value = q.get_nowait()
        except queue.Empty:
            break
        if i % quota == 0:
            y.append(value[0]/100)
            x.append(value[1])
            logger.debug(f"Putting data:{line_plot}\t{value[0]}")
        i+=1
    if len(x) > 0 and len(x) == len(y):
        y = [y]
        if not line_plot.visible:
            # Only update internal data and don't update plot. Otherwise ui might freeze for a couple of sec when reading values
            logger.debug(f"Skipping plotupdate for {line_plot}")
            line_plot.x = [*line_plot.x, *x][line_plot.slice]
            for i in range(len(line_plot.lines)):
                line_plot.Y[i] = [*line_plot.Y[i], *y[i]][line_plot.slice]
        else:
            line_plot.push(x, y)



""" define queues in dict """
for k in SENSOR_MAP:
    sensor_queues[k] = multiprocessing.Queue()

""" create all processes """
for port in UDP_PORTS:
    sensor_processes[port] = multiprocessing.Process(target=get_values, args=(port,))
""" and start them """
for p in sensor_processes.values():
    p.start()


toprow = ui.row()
plot_container = {}
plots = {}
timer = {}


def tab_focus_callback(s:str):
    """
    get string of the newly focused tab
    set all other plots to invisible
    """
    logger.info(f"Tabs change focus: {s}")
    for k,v in plots.items():
        assert(isinstance(v,ui.line_plot))
        if SENSOR_MAP[k] == s:
            v.visible = True
        else:
            v.visible = False


# WARN: tabs is globally defined and the lambda needs this global scope for this implementation
with ui.tabs(on_change=lambda : tab_focus_callback(tabs.value)) as tabs:
    tabs.tailwind.text_color("blue-600").margin("m-2")
    for k,v in SENSOR_MAP.items():
        t1 = ui.tab(v, icon='insights')
        t1.tooltip(f"{v} plot")
        tabs_map[k]=t1


""" create container and select the first one """
with ui.tab_panels(tabs,value=list(SENSOR_MAP.values())[0]).classes("w-full") as tps:
    tps.on_value_change(lambda : print(f"Value change: {tps.value}\t{tps.visible}"))
    tps.on(type="before-transition", handler=lambda : print(f"Value change: {tps.value}\t{tps.visible}"))
    for k,v in SENSOR_MAP.items():
        with ui.tab_panel(v) as tp:
            with ui.row() as r:
                plot_container[k]=r


def create_plots(ui_timer_period=1, limit_data:int=120, quota=1):
    """
    Create tabs and plots in corresponding tabs
    """
    logger.info(f"(Re)setting plots: period:{ui_timer_period}, data points:{limit_data}")
    for k,v in plot_container.items():
        if k in plots.keys():
            logger.info(f"Cleaning plot for sensor {k}")
            assert(isinstance(plots[k],ui.line_plot) )
            plots[k].clear()
            plots[k].slice = slice(-limit_data,None) # sets the limit in the line plot
            assert(isinstance(timer[k],ui.timer) )
            timer[k].callback = lambda line_plot=plots[k], id=k : update_line_plot(line_plot, sensor_queues[id],quota)
            timer[k].interval = ui_timer_period
        else:
            with v:
                id = k
                line_plot = ui.line_plot(n=1, limit=limit_data, figsize=(18,6), update_every=1, close=False) \
                        .with_legend([SENSOR_LEGEND[id]], loc="upper center", ncol=1)
                plots[k]=line_plot
                line_plot_timer = ui.timer(ui_timer_period, lambda line_plot=line_plot, id=id : update_line_plot(line_plot, sensor_queues[id],quota), active=True)
                timer[k]=line_plot_timer

limit_data = 120 # store up to $limit_data data points
quota = 1       # take only 1 out of $quota data points
ui_timer_period = 1 # update every $ui_timer_period seconds


create_plots(ui_timer_period,limit_data,quota)

with toprow:
    ui.button('Reload Plots', on_click=lambda : create_plots(ui_timer_period=ui_timer_period, limit_data=int(limit_data), quota=quota))
    ui.number(label="Update period", value=1.0, format="%.1f",min=0.1, step=0.1).bind_value(globals(), 'ui_timer_period').style(add="margin-top: -1rem;")
    ui.number(label="Data points", value=60, format="%.0f",min=10, step=5).bind_value(globals(), 'limit_data').style(add="margin-top: -1rem;")





ui.run(show=False, reload=False, port=8080)











