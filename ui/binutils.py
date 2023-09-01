#!/usr/bin/env python3

import dataclasses, numpy as np, typing

@dataclasses.dataclass
class Bins:
    bin_boundaries: typing.List[int]
    bin_fills: typing.List[np.ndarray] = dataclasses.field(default_factory=list)
    first_tss: typing.List[int] = dataclasses.field(default_factory=list)

    def first_ts(self) -> float:
        return self.first_tss[0]/1e9

    def push_ts(self, ts: int) -> None:
        print(self.bin_boundaries)
        self.first_tss.append(ts)
        self.bin_fills.append(np.array([0 for _ in range(len(self.bin_boundaries) + 1)]))

    def push(self, val) -> None:
        i_min = 0
        i_max = len(self.bin_boundaries)

        while i_max - i_min > 0:
                if val < self.bin_boundaries[(i_max + i_min) // 2]:
                    i_max = (i_max + i_min) // 2
                elif val > self.bin_boundaries[(i_max + i_min) // 2]:
                    i_min = (i_max + i_min) // 2 + 1
                else:
                    i_min = i_max = (i_max + i_min) // 2
                    break
        self.bin_fills[-1][i_min] += 1

    def drop_older_than(self, ts: int) -> None:
        to_drop: int = sum(1 for _ in filter(lambda t: t < ts, self.first_tss))
        self.bin_fills = self.bin_fills[to_drop:]
        self.first_tss = self.first_tss[to_drop:]
