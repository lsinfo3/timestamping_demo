#!/usr/bin/env python3
import abc
from nicegui import ui
import pandas as pd
from typing import List, Tuple, Dict, Set
from plotly import graph_objects as go
import colors, binutils, utils
pd.options.mode.chained_assignment = None

class PlotGenerator(abc.ABC):
    plot_wrappers: List[ui.plotly]
    plots: List[go.Figure]
    labels: List[Tuple[str, str]]

    def __init__(self):
        self.plot_wrappers = []
        self.plots = []

    def _generate(self, labels: List[Tuple[str, str]], vw: int, vh: int) -> None:
        self.labels = labels
        with ui.row():
            for xlabel, ylabel in labels:
                self.plots.append(plot := go.Figure(go.Scatter(x = [], y = [], uid="-1", showlegend=False)))
                plot.update()
                plot.update_xaxes(title_text=xlabel)
                plot.update_yaxes(title_text=ylabel)
                self.plot_wrappers.append(ui.plotly(plot).style(f"width: {vw / len(labels)}vw; height: {vh}vh"))


    def _update(self, xseries: List[Dict[int, pd.Series]], yseries: List[Dict[int, pd.Series]]) -> None:
        for plot, plot_wrapper, xser, yser in zip(self.plots, self.plot_wrappers, xseries, yseries):
            for uid in xser.keys():
                # print(uid)
                plot.update_traces(selector={'uid': str(uid)}, x=xser[uid], y=yser[uid], marker={"color": colors.Colors[uid]})
                # print(plot)
            plot_wrapper.update()

    @abc.abstractmethod
    def generate(self, vw: int, vh:int) -> None:
        """Should use self._generate() to generate plot layout."""

    @abc.abstractmethod
    def update(self, dfs: Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame], bins: Tuple[binutils.Bins, Tuple[binutils.Bins, binutils.Bins], Tuple[binutils.Bins, binutils.Bins]], flowids: Set[int]) -> None:
        """Updates the plot with the value of the DataFrame"""

    def start(self, flowids: Set[int]) -> None:
        for index, ((xlabel, ylabel), plot_wrapper) in enumerate(zip(self.labels, self.plot_wrappers)):
            self.plots[index] = go.Figure()
            self.plots[index].update_xaxes(title_text=xlabel)
            self.plots[index].update_yaxes(title_text=ylabel)
            self.plots[index].add_traces([go.Scatter(x=[], y=[], uid=str(flowid), showlegend=False) for flowid in flowids])
            plot_wrapper.update_figure(self.plots[index])



class DelayHistoGenerator(PlotGenerator):
    def generate(self, vw: int, vh: int):
        self._generate([("Bins [s]", "Count")], vw, vh)

    def update(self, dfs: Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame], bins: Tuple[binutils.Bins, Tuple[binutils.Bins, binutils.Bins], Tuple[binutils.Bins, binutils.Bins]], flowids: Set[int]) -> None:
        xseries = [{flowid: [f"<{utils.format_timestamps(bins[0][0].bin_boundaries[0])}"] + [f"{utils.format_timestamps(bins[0][0].bin_boundaries[i])}-{utils.format_timestamps(bins[0][0].bin_boundaries[i+1])}" for i in range(len(bins[0][0].bin_boundaries)-1)] + [f"-{utils.format_timestamps(bins[0][0].bin_boundaries[-1])}"] for flowid in flowids}]
        yseries = [dict()]

        for flowid in flowids:
            flowbin = bins[0][flowid]
            yseries[0][flowid] = sum(flowbin.bin_fills)
        self._update(xseries, yseries)

class DelayPlotGenerator(PlotGenerator):
    def generate(self, vw:int, vh:int):
        self._generate([("Time at IF2 [s]", "Delay [ns]")], vw=vw, vh=vh)


    def update(self, dfs: Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame], bins: Tuple[binutils.Bins, Tuple[binutils.Bins, binutils.Bins], Tuple[binutils.Bins, binutils.Bins]], flowids: Set[int]) -> None:
        xseries: List[Dict[int, pd.Series]] = [dict()]
        yseries: List[Dict[int, pd.Series]] = [dict()]

        for flowid in flowids:
            if flowid == 0:
                temp: pd.DataFrame = dfs[0]
            else:
                temp = dfs[0][dfs[0]['flow_id'] == flowid]
            xseries[0][flowid] = temp['ts_if2'] / int(1e9)
            yseries[0][flowid] = temp['ts_if2'] - temp['ts_if1']

        self._update(xseries, yseries)

class CummDataPlotGenerator(PlotGenerator):
    def generate(self, vw: int, vh: int) -> None:
        self._generate([(f"Time at IF{i} [s]", f"Cumulative Data at IF{i} [B]") for i in (1,2)], vw=vw, vh=vh)

    def update(self, dfs: Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame], bins: Tuple[binutils.Bins, Tuple[binutils.Bins, binutils.Bins], Tuple[binutils.Bins, binutils.Bins]], flowids: Set[int]) -> None:
        xseries: List[Dict[pd.Series]] = [dict(), dict()]
        yseries: List[Dict[pd.Series]] = [dict(), dict()]

        for flowid in flowids:
            if flowid not in self.cumsum.keys():
                self.cumsum[flowid] = [0,0]
            for iface in (1, 2):
                if flowid != 0:
                    temp: pd.DataFrame = dfs[iface][dfs[iface]['flow_id'] == flowid]
                else:
                    temp = dfs[iface]
                temp.sort_values(by=f'ts_if{iface}', inplace=True, kind='stable')
                xseries[iface - 1][flowid] = temp[f'ts_if{iface}'] / 1e9
                if flowid != 0:
                    yseries[iface - 1][flowid] = temp['cummvol_flow']
                else:
                    yseries[iface - 1][flowid] = temp['cummvol']
            self.cumsum[flowid] = [yseries[0][flowid].max(), yseries[1][flowid].max()]
        self._update(xseries, yseries)

    def start(self, flowids: Set[int]) -> None:
        self.cumsum = dict()
        super().start(flowids)

class SizeHistoPlotGenerator(PlotGenerator):
    def generate(self, vw: int, vh: int) -> None:
        self._generate([(f"Size at IF{i} [B]", f"Count") for i in (1,2)], vw=vw, vh=vh)

    def update(self, dfs: Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame], bins: Tuple[binutils.Bins, Tuple[binutils.Bins, binutils.Bins], Tuple[binutils.Bins, binutils.Bins]], flowids: Set[int]) -> None:
        xseries = [{flowid: [f"<{bins[2][0][0].bin_boundaries[0]}"] + [f"{bins[2][0][0].bin_boundaries[i]}<...<{bins[2][0][0].bin_boundaries[i+1]}" for i in range(len(bins[2][0][0].bin_boundaries)-1)] + [f">{bins[2][0][0].bin_boundaries[-1]}"] for flowid in flowids} for _ in range(2)]
        yseries = [dict(), dict()]

        for flowid in flowids:
            for iface in (1,2):
                flowbin = bins[2][flowid][iface-1]
                yseries[iface - 1][flowid] = sum(flowbin.bin_fills)
        self._update(xseries, yseries)


class IATHistoPlotGenerator(PlotGenerator):
    def generate(self, vw: int, vh: int) -> None:
        self._generate([(f"IAT at IF{i} [s]", f"Count") for i in (1,2)], vw=vw, vh=vh)

    def update(self, dfs: Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame], bins: Tuple[binutils.Bins, Tuple[binutils.Bins, binutils.Bins], Tuple[binutils.Bins, binutils.Bins]], flowids: Set[int]) -> None:
        xseries = [{flowid: [f"<{utils.format_timestamps(bins[1][0][0].bin_boundaries[0])}"] + [f"{utils.format_timestamps(bins[1][0][0].bin_boundaries[i])}-{utils.format_timestamps(bins[1][0][0].bin_boundaries[i+1])}" for i in range(len(bins[1][0][0].bin_boundaries)-1)] + [f">{utils.format_timestamps(bins[1][0][0].bin_boundaries[-1])}"] for flowid in flowids} for _ in range(2)]
        yseries = [dict(), dict()]

        for flowid in flowids:
            for iface in (1,2):
                flowbin = bins[1][flowid][iface-1]
                yseries[iface - 1][flowid] = sum(flowbin.bin_fills)
        self._update(xseries, yseries)





class IatPlotGenerator(PlotGenerator):
    last_ts: List[Dict[int, int]]

    def __init__(self):
        super().__init__()
        self.last_ts = [dict(), dict()]

    def generate(self, vw: int, vh:int) -> None:
        self._generate([(f"Time at IF{i} [s]", f"IAT at IF{i} [ns]") for i in (1,2)], vw=vw, vh=vh)

    def update(self, dfs: Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame], bins: Tuple[binutils.Bins, Tuple[binutils.Bins, binutils.Bins], Tuple[binutils.Bins, binutils.Bins]], flowids: Set[int]) -> None:
        xseries: List[Dict[pd.Series]] = [dict(), dict()]
        yseries: List[Dict[pd.Series]] = [dict(), dict()]

        for flowid in flowids:
            for iface in (1, 2):
                if flowid != 0:
                    temp: pd.DataFrame = dfs[iface][dfs[iface]['flow_id'] == flowid]
                else:
                    temp = dfs[iface]
                if flowid not in self.last_ts[iface - 1].keys():
                    self.last_ts[iface - 1][flowid] = 0
                temp.sort_values(by=f'ts_if{iface}', inplace=True, kind='stable', ascending=True)
                xseries[iface - 1][flowid] = (temp[f'ts_if{iface}'] / 1e9)[1:]
                yseries[iface - 1][flowid] = temp[f'ts_if{iface}'].diff()[1:]
                # yseries[iface - 1][flowid] = pd.concat([pd.Series(self.last_ts[iface - 1][flowid]), temp[f'ts_if{iface}']]).diff()[1:]
                # print(pd.concat([pd.Series(self.last_ts[iface - 1][flowid]), temp[f'ts_if{iface}']]))
                # self.last_ts[iface - 1][flowid] = temp[f'ts_if{iface}'].max()
        self._update(xseries, yseries)

    def start(self, flowids: Set[int]) -> None:
        self.last_ts = [dict(), dict()]
        super().start(flowids)

FUNCTIONS: Dict[str, PlotGenerator] = {
    'Delay': DelayPlotGenerator(),
    'Cummulative Data Volume': CummDataPlotGenerator(),
    'Inter Arrival Times': IatPlotGenerator(),
    'Delay Bins': DelayHistoGenerator(),
    "IAT Bins": IATHistoPlotGenerator(),
    "Size Bins": SizeHistoPlotGenerator()
}
