"""comken/services/salesforce_downloader/soql_reports/_registry.py — SOQLレポート登録の置き場所。

``__init__.py`` から ``runner`` を import するので、``runner`` から
``__init__.py`` を逆に import すると循環する。``SOQL_REPORTS`` は
``runner.download_soql_reports()`` が「``reports=None`` のときの既定値」
として参照するため、**循環を切れる別のモジュール**に置く。
"""

from comken.services.salesforce_downloader.soql_reports.base import SoqlReport

# 新しいレポートを追加したら、ここへ import してタプルへ足す。
# 例:
#   from ...soql_reports.large_sales_report import LargeSalesReport
#   SOQL_REPORTS: tuple[type[SoqlReport], ...] = (LargeSalesReport,)
SOQL_REPORTS: tuple[type[SoqlReport], ...] = ()
