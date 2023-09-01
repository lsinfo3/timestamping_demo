#!/usr/bin/env python3
import json, subprocess, typing, time

LAST_TS: typing.Dict[str, float] = {}
LAST_RX_BYTES: typing.Dict[str, int] = {}


def get_bytes_by_interface(iface: str) -> int:
    if_json: typing.Dict = json.loads(subprocess.run(["ip", "-j", "-s", "a", "show", "dev", iface], stdout=subprocess.PIPE).stdout)
    return int(if_json[0]["stats64"]["rx"]["bytes"])

def get_rate_by_interface(iface: str) -> typing.Optional[float]:
    global LAST_TS, LAST_RX_BYTES
    rx_bytes: int = get_bytes_by_interface(iface)
    ts: float = time.time()
    if iface in LAST_RX_BYTES.keys() and iface in LAST_RX_BYTES.keys():
        result: float = 8*(rx_bytes - LAST_RX_BYTES[iface])/(ts - LAST_TS[iface])
    else:
        result = None
    LAST_RX_BYTES[iface] = rx_bytes
    LAST_TS[iface] = ts
    return result

def iface_captured(iface: str) -> bool:
    return iface in LAST_RX_BYTES.keys() and iface in LAST_TS.keys()


def format_timestamps(ns: int) -> str:
    val: float
    unit: str
    if abs(ns) < 1e3:
        unit = "n"
        val = ns
    elif abs(ns) < 1e6:
        unit = "\u03bc"
        val = ns / 1e3
    elif abs(ns) < 1e9:
        unit = "m"
        val = ns / 1e6
    else:
        val = ns / 1e9
        unit = ""

    if val < 1e1:
        val = round(val, 2)
    elif val < 1e2:
        val = round(val, 1)
    else:
        val = round(val)

    return f"{val}{unit}"
