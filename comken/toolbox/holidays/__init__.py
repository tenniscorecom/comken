"""comken/toolbox/holidays/__init__.py — 内閣府 CSV ダウンローダの facade。

祝日計算ロジック本体は ``comken.core.holidays`` 配下にある
（標準ライブラリのみで動くため ``core`` 層に置いている）。
toolbox 側には ``requests`` に依存する内閣府 CSV ダウンローダ
（``CabinetOfficeCSVSource``）だけを残し、ここから再エクスポートする。

``HolidayCalendar`` / ``is_business_day`` / ``ComputedHolidaySource`` などの
純粋計算の API は ``comken.core.holidays`` から直接 import すること。
"""

from comken.toolbox.holidays.sources.cabinet_office import CabinetOfficeCSVSource

__all__ = ["CabinetOfficeCSVSource"]
