"""comken/core/holidays/sources/__init__.py — 祝日ソースの実装を置く場所。

``HolidaySource`` Protocol を実装するクラスを集める。
``comken.core.holidays`` の facade からは直接は読まれず、
利用側が ``HolidayCalendar.from_sources([...])`` に渡して使う。
"""
