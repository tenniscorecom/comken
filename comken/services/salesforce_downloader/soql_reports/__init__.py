"""comken/services/salesforce_downloader/soql_reports/__init__.py — SOQLレポートの登録一覧。

``SalesforceBase.query()`` で取るレポートを 1 レポート=1ファイルで定義し、
ここへ明示的にタプル登録する。**自動登録の仕組みは持たない**
（``comken/toolbox/salesforce/sites/__init__.py`` の ``SITES`` と同じ運用。
新しいレポートを増やすたびに1行タプルへ足すこと）。

``download_soql_reports()`` を呼ぶと ``SOQL_REPORTS`` の中身を取りに行く。
空タプルのままなら何もしない（テストでは ``reports`` 引数で差し替える）。

管理表の「SOQL」列（``ReportEntry.use_soql``）が「○」の行は、取得実行側
（Salesforceレポートダウンローダー の ``service.py``）が ``soql_report_for()``
で管理番号から ``SoqlReport`` を引く。``site_for()``（``toolbox.salesforce.sites``）
と同じ「URL・管理番号から対応クラスを探す」役割。

``SOQL_REPORTS`` は ``_registry.py`` に置く。``__init__.py`` が ``runner`` を
import する関係で、``runner`` から ``__init__.py`` を import すると循環するため。
"""

from comken.exceptions import SoqlReportNotRegisteredError
from comken.services.salesforce_downloader.soql_reports import _registry
from comken.services.salesforce_downloader.soql_reports._registry import SOQL_REPORTS
from comken.services.salesforce_downloader.soql_reports.base import SoqlReport
from comken.services.salesforce_downloader.soql_reports.runner import download_soql_reports

__all__ = ["SoqlReport", "SOQL_REPORTS", "download_soql_reports", "soql_report_for"]


def soql_report_for(key: str) -> type[SoqlReport]:
    """管理番号（``ReportEntry.key`` と同じ値）から ``SoqlReport`` サブクラスを引く。

    管理表の「SOQL」列が「○」の行を取得実行側が処理するときに使う想定。

    Args:
        key: 管理番号。``SoqlReport.KEY`` と一致するものを探す。

    Returns:
        該当する ``SoqlReport`` サブクラス。

    Raises:
        SoqlReportNotRegisteredError: ``SOQL_REPORTS`` に該当する ``KEY`` が無い場合
            （管理表の「SOQL」列を「○」にしたのに登録を忘れている設定ミス）。
    """
    # ``_registry`` モジュール経由で読む（``download_soql_reports()`` と同じ理由）。
    # ``from ... import SOQL_REPORTS`` だとこのモジュールの import 時点のスナップ
    # ショットに固定され、テストでの `_registry.SOQL_REPORTS` 差し替えを拾えない
    for report_cls in _registry.SOQL_REPORTS:
        if key == report_cls.KEY:
            return report_cls
    raise SoqlReportNotRegisteredError(
        key, [report_cls.KEY for report_cls in _registry.SOQL_REPORTS]
    )
