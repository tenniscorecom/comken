"""comken/services/salesforce_downloader/soql_reports/__init__.py — SOQLレポートの登録一覧。

``SalesforceBase.query()`` で取るレポートを 1 レポート=1ファイルで定義し、
ここへ明示的にタプル登録する。**自動登録の仕組みは持たない**
（``comken/toolbox/salesforce/sites/__init__.py`` の ``SITES`` と同じ運用。
新しいレポートを増やすたびに1行タプルへ足すこと）。

``download_soql_reports()`` を呼ぶと ``SOQL_REPORTS`` の中身を取りに行く。
空タプルのままなら何もしない（テストでは ``reports`` 引数で差し替える）。

``SOQL_REPORTS`` は ``_registry.py`` に置く。``__init__.py`` が ``runner`` を
import する関係で、``runner`` から ``__init__.py`` を import すると循環するため。
"""

from comken.services.salesforce_downloader.soql_reports._registry import SOQL_REPORTS
from comken.services.salesforce_downloader.soql_reports.base import SoqlReport
from comken.services.salesforce_downloader.soql_reports.runner import download_soql_reports

__all__ = ["SoqlReport", "SOQL_REPORTS", "download_soql_reports"]
