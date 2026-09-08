r"""comken/services/salesforce_downloader/soql_reports/base.py — SOQLで取るレポートの基底クラス。

Report API（2000行上限）で取れない大きなレポートは、SOQL（`SalesforceBase.query()`、
上限なし）で取る。サブクラスは1レポート=1ファイルで書き、`__init__.py` の
``SOQL_REPORTS`` タプルへ明示的に登録する。**自動登録の仕組みは持たない**
（新しいレポートを増やすたびに1行タプルへ足す運用）。

    class LargeSalesReport(SoqlReport):
        KEY = "9001"
        SUMMARY = "売上明細（SOQL、2000件超）"
        URL = "https://example.my.salesforce.com"
        FOLDER = r"\\server\share\reports\売上明細"

        def soql(self) -> str:
            return "SELECT Id, Name, Amount FROM Opportunity WHERE ..."

Excel の「スケジュール」シートとは独立している。いつ呼ぶかは呼び出し側
（プロジェクトの定期実行）が決める。
"""

from __future__ import annotations

from typing import ClassVar


class SoqlReport:
    """Report API（2000行上限）で取れない大きなレポートを SOQL で取る基底クラス。

    サブクラスは ``KEY`` / ``SUMMARY`` / ``URL`` / ``FOLDER`` を上書きし、
    ``soql()`` を実装する。1レポート=1ファイルで ``__init__.py`` の
    ``SOQL_REPORTS`` タプルへ明示的に登録する（**自動登録の仕組みは持たない**）。

    Excel の「スケジュール」シートとは独立している。いつ呼ぶかは呼び出し側
    （プロジェクトの定期実行）が決める前提なので、この基底クラスには
    スケジュール判定を持たせない。

    Attributes:
        KEY: 管理番号。``download_scheduled()`` の ``ReportEntry.key`` と
            同じ意味で、社内で決める論理的な番号（前ゼロ・記号入りも可）。
            Salesforce のレポート ID ではない。
        SUMMARY: 人が読んで何のレポートか分かる説明。保存するファイル名にも使われる。
        URL: レポートを開いた組織の My Domain の URL。``site_for()`` で
            組織を解決するために使う（``ReportEntry.url`` と同じ運用）。
        FOLDER: 保存先フォルダの絶対パス／UNC 文字列。**フォルダが無いと
            エラーにする**（``_reserve_path()`` と同じ判断。書き間違いに
            気づけるよう、勝手には作らない）。
        ALLOW_EMPTY: ``True`` なら 0 件のときも空 CSV を保存して成功扱い、
            ``False`` なら 0 件を ``EmptyReportError`` として失敗扱いする
            （``ReportEntry.allow_empty`` と同じ運用）。
    """

    KEY: ClassVar[str] = ""
    SUMMARY: ClassVar[str] = ""
    URL: ClassVar[str] = ""
    FOLDER: ClassVar[str] = ""
    ALLOW_EMPTY: ClassVar[bool] = False

    def soql(self) -> str:
        """実行する SOQL クエリ文字列を返す。サブクラスで実装する。"""
        raise NotImplementedError
