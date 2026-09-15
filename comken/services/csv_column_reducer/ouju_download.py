"""comken/services/csv_column_reducer/ouju_download.py — 応需CSVのダウンロード＋列削減（雛形）。

「ブラウザでダウンロードする」（toolbox）と「列を削減する」（services、この
パッケージ）を1つにまとめる置き場所。toolbox は services に依存できない
設計ルール（下の層だけを import する）のため、この組み合わせは
services 側に置く（逆に services が toolbox を使うのは問題ない）。
"""

from __future__ import annotations

from pathlib import Path

from comken.services.csv_column_reducer.file_ops import reduce_ouju_csv_file
from comken.toolbox.browser.sites.ouju import Ouju


def download_and_reduce_ouju_csv(ouju: Ouju, *, columns: list[str] | None = None) -> Path:
    """ログイン済みの Ouju で CSV帳票をダウンロードし、列を削減して返す。

    新ロールでは列数が255を超えてAccessへ取り込めないため、既定では
    旧ロール相当の列だけに絞る。columns を渡すと絞る列を上書きできる。

        with Ouju() as ouju:
            ouju.go_login().login(username, password)
            path = download_and_reduce_ouju_csv(ouju)

    Returns:
        列を削減した後のCSVのパス（ダウンロードされた場所・ファイル名のまま）。
    """
    downloaded_path = ouju.go_csv_report().download_csv()
    reduce_ouju_csv_file(downloaded_path, columns=columns)
    return downloaded_path
