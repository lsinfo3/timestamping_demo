#!/usr/bin/env python3

import plotly

class Colors:
    def __getitem__(self, i):
        color_list = [
            plotly.colors.qualitative.Plotly,
            plotly.colors.qualitative.D3,
            plotly.colors.qualitative.G10,
            plotly.colors.qualitative.T10,
            plotly.colors.qualitative.Alphabet,
            plotly.colors.qualitative.Dark24,
            plotly.colors.qualitative.Light24,
        ]
        it = iter(color_list)
        ne = next(it)
        while i >= len(ne):
            i -= len(ne)
            try:
                ne = next(it)
            except StopIteration:
                it = iter(color_list)
                ne = next(it)
        return ne[i]

Colors = Colors()
