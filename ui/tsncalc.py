import pandas as pd
import numpy as np
from collections import namedtuple

from typing import NamedTuple
from dataclasses import dataclass, asdict

import time

SFD = 8         # preamble + start frame delimiter
IPG = 12        # interpacket gap
FCS = 4         # frame check sequence
FRAMESPACING_L1 = SFD + IPG + FCS
FRAMESPACING_L2 = FCS

@dataclass
class Bucket:
    filllevel: float
    size: int|float
    lastts: int



def validate_envelope_bucket(df: pd.DataFrame, rate: int|float, bkt: Bucket = Bucket(0,0,0)) -> Bucket:
    """
    token bucket algorithm for determining min burst size
    requires DataFrame with "TS" and "Size" columns
    TS should be in ns resolution (and be normalised to start at 0?)
    Size should be the size including FCS but without interframegap,etc
    """
    df = df[["ts","size"]]
    np_arr = df.to_numpy()
    # TODO: sort numpy matrix so ts are in ascending order
    return validate_envelope_bucket_calc(np_arr, rate, bkt, L1=False,NO_FCS=True)

def validate_envelope_bucket_calc(data: np.ndarray, rate: int|float, bkt: Bucket = Bucket(0,0,0), L1=False, NO_FCS=True) -> Bucket:
    """ token bucket algorithm for determining min burst size """
    # Bucket starts full but with size 0
    # When more tokens are needed than the bucket can offer,
    # correct the bucket size (and thereby the fill level) retroactively
    # The bucket is filled with a specified rate, however the level is limited by bucket size
    # The final bucket size is the minimal burst size
    # To allow for continouus processing the complete bucket state is returned
    rate = rate/1e9

    if L1:
        FRAMESPACING = FRAMESPACING_L1
    else:
        if NO_FCS:
            FRAMESPACING = 0
        else:
            FRAMESPACING = FRAMESPACING_L2
    bucket = bkt.filllevel
    size = bkt.size
    lastts = bkt.lastts
    for i in range(data[:,0].size):
        if data[i][0] < lastts:
            raise ValueError(f"Invalid change in bucket level. Timestamps might not be in the correct order: lastts: {lastts}; currentts: {data[i][0]}")
        bucket = bucket + rate * (data[i][0]-lastts)
        if bucket > size:
            bucket = size
        bucket = bucket - (data[i][1]+FRAMESPACING) * 8
        if bucket < 0:
            diff = np.ceil(np.abs(bucket))
            bucket = bucket + diff
            size = size + diff
        lastts = data[i][0]

    return Bucket(size=size, filllevel=bucket, lastts=lastts)


def get_conflicts(df: pd.DataFrame, rate, bkt: Bucket):
    """
    given a set of parameters, construct information about conflicts for plotting
    """
    df = df[["ts","size"]]
    np_arr = df.to_numpy()
    return get_conflicts_calc(np_arr, rate, bkt)

def get_conflicts_calc(data: np.ndarray, rate: int|float, bkt: Bucket):
    """
    WIP!!
    """
    bucket = bkt.filllevel
    size = bkt.size
    lastts = bkt.lastts
    collisions = []

    for i in range(data[:,0].size):
        if data[i][0] < lastts:
            raise ValueError(f"Invalid change in bucket level. Timestamps might not be in the correct order: lastts: {lastts}; currentts: {data[i][0]}")
        bucket = bucket + rate * (data[i][0]-lastts)
        if bucket > size:
            bucket = size
        bucket = bucket - (data[i][1]+20) * 8
        if bucket < 0:
            np.array([])
            # diff = np.ceil(np.abs(bucket))
            # bucket = bucket + diff
            # size = size + diff
        lastts = data[i][0]

    return
