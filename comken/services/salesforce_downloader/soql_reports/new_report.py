"""comken/services/salesforce_downloader/soql_reports/new_report.py — SOQLレポートの雛形（未使用）。

**このファイルはプレースホルダー。** 値が決まったら埋めて、ファイル名・クラス名を
実際のレポートに合わせてリネームし、`_registry.py` の `SOQL_REPORTS` へ登録する
（登録するまでは `download_soql_reports()` から呼ばれない）。書き方は
`base.py` のモジュール docstring、詳しい手順は docs/機能/salesforce-downloader.md の
「SOQLレポート（2000件超のレポートを移行する）」を参照。
"""

from comken.services.salesforce_downloader.soql_reports.base import SoqlReport


class NewReport(SoqlReport):
    """TODO: レポートの説明に書き換える（登録前にファイル名・クラス名もリネーム）。"""

    KEY = ""  # TODO: 社内で決める管理番号（例: "9001"）
    SUMMARY = ""  # TODO: 人が読んで分かる説明（保存するファイル名にも使われる）
    URL = ""  # TODO: 接続先組織のMy Domain URL（site_for()が組織を解決する）
    FOLDER = r""  # TODO: 保存先フォルダの絶対パス／UNC（存在しないとエラー。勝手に作らない）
    ALLOW_EMPTY = False  # TODO: 0件を失敗として扱うか（普段データがあるなら False のまま）

    def soql(self) -> str:
        """TODO: 実行する SOQL クエリ文字列を返す。"""
        raise NotImplementedError("TODO: SOQL文をここに書く")
