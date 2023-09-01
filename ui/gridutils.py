#!/usr/bin/env python3

import pandas as pd, typing, enum
from nicegui import ui

class ColumnTypes(enum.Enum):
    label = ui.label
    input = ui.input
    number = ui.number
    checkbox = ui.checkbox
    icon = ui.icon

class GridHelper:
    df: pd.DataFrame
    columns: typing.List[str]
    column_names: typing.Dict[str, str]
    column_format: typing.Dict[str, ColumnTypes]
    grid: ui.grid
    selector_column: typing.Optional[str]

    def __init__(self, df: pd.DataFrame, columns: typing.List[str], column_format: typing.Dict[str, ColumnTypes], column_names: typing.Dict[str, str], selector_column: typing.Optional[str] = None, min_width: str = "auto"):
        self.df = df
        self.column_format = column_format
        self.columns = columns
        self.column_names = column_names
        print(len(self.columns))
        with ui.element('q-scroll-area').classes("w-full h-full"):
                self.grid = ui.grid(columns=len(self.columns)+sum([1 if col in {ColumnTypes.number, ColumnTypes.input} else 0 for col in self.column_format.values()])).classes('gap-0').style(add=f"min-width: {min_width}")
        self.selector_column = selector_column
        if not set(columns) <= set(df.columns):
            raise ValueError("Column list must be subset of DataFrame columns!")
        if selector_column is not None and not (selector_column in df.columns and selector_column in columns and column_format[selector_column] == ColumnTypes.checkbox):
            raise ValueError("The selector has to be a shown checkbox!")
        self.make_grid()

    def make_grid(self):
        with self.grid:
            self.grid.clear()
            self.grid.classes("rounded-xl p-0 bg-gray-100 shadow-xl item-center")
            for columnname in self.columns:
                ch = ui.label(self.column_names[columnname]).classes('font-bold m-0 pt-8 h-20 text-center')
                if columnname in self.column_format.keys() and self.column_format[columnname] in {ColumnTypes.input, ColumnTypes.number}:
                    ch.classes(add="col-span-2")
            for row in self.df.iloc:
                for field in self.columns:
                    def save_value(x, c=field, r=row.name): self.df[c][r] = x.value
                    if field in self.column_format.keys() and self.column_format[field] in {ColumnTypes.checkbox, ColumnTypes.input, ColumnTypes.number}:
                        cls = self.column_format[field].value(value=row[field], on_change=save_value)
                    elif field in self.column_format.keys() and self.column_format[field] == ColumnTypes.icon:
                        cls = ui.icon(row[field][0], color=row[field][1])
                        cls.style(add="padding-top: 17.5px")
                    else:
                        cls = ui.label(row[field])
                        cls.style(add="padding-top: 17.5px")
                    cls.classes("px-8 py-2 border-solid m-0 border-x-0 border-b-0 border-t-2 border-gray-300 text-center")
                    if field in self.column_format.keys() and self.column_format[field] in {ColumnTypes.input, ColumnTypes.number}:
                        cls.classes(add="col-span-2")
                    cls.style(add="border-top-width: 1.0px")



    def update(self, df: pd.DataFrame):
        if not set(self.columns) <= set(df.columns):
            raise ValueError("Column list must be subset of DataFrame columns!")
        if self.selector_column is not None and not (self.selector_column in df.columns):
            raise ValueError("The selector has to be a shown checkbox!")
        self.df = df
        self.make_grid()

    def selected(self) -> pd.DataFrame:
        if self.selector_column is None:
            return self.df
        else:
            print(self.df)
            return self.df.query(f"{self.selector_column}", inplace=False)
