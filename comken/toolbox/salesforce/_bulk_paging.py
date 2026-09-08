"""comken/toolbox/salesforce/_bulk_paging.py — Bulk API 2.0 のページング共通処理。

``_`` プレフィックスは salesforce パッケージ内部専用（外部公開しない）の
意図。Bulk Query の結果取得と Bulk Ingest の成功/失敗結果取得で重複していた
「``Sforce-Locator`` でページングしながら結果CSVを取得し、一時ファイルへ
ページ単位で書き込みながら ``Table`` に変換する」処理を一箇所にまとめる。

**本物の Salesforce 組織に対して未検証。** ページ境界のヘッダー行の扱いや
0件判定などの前提は呼び出し元から受け取ったそのままを保ち、ロジックの意味を
変えないようにしている。
"""

from __future__ import annotations

import logging
import tempfile
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING

from comken.core.table import Table
from comken.toolbox.csv import CSV

if TYPE_CHECKING:  # 実行時は import しない（client と相互参照になるため）
    from comken.toolbox.salesforce.client import SalesforceBase

logger = logging.getLogger(__name__)

__all__ = ["NO_MORE_PAGES_LOCATOR", "fetch_paged_csv_as_table"]

# 結果取得の ``Sforce-Locator`` ヘッダーが無い・次ページ無しのマーカー。
# 公式リファレンスでは「次ページが無いときは null 文字列」と書かれており、
# 実際の振る舞いは本物の組織で未検証。
NO_MORE_PAGES_LOCATOR = "null"


def fetch_paged_csv_as_table(
    client: SalesforceBase,
    path: str,
    component: str,
    tmp_filename: str,
) -> Table:
    """Sforce-Locator でページングされた結果CSVを取得し、一時ファイルへ
    ページ単位で書き込みながら ``Table`` に変換する。

    Bulk Query の結果取得・Bulk Ingest の成功/失敗結果取得の両方で使う
    共通処理。1ページ目は ``Sforce-Locator`` ヘッダーが ``"null"`` か
    空なら最終ページ。値があれば ``?locator=<値>`` を付けて同じ結果
    取得 URL を呼ぶ。2ページ目以降にもヘッダー行が含まれる前提で、
    1行目を捨てて連結する（本物の組織で未検証の前提）。

    Args:
        client: この Bulk API を使う Salesforce クライアント。
        path: 結果取得のパス（``"/services/data/..."`` から始まる、
            locator クエリパラメータを含まないベースの形）。
        component: 計測での呼び出し元の区別。
        tmp_filename: 一時ファイルの名前（呼び出し元ごとに変えて衝突を
            避ける、例: ``"bulk_query_result.csv"`` /
            ``"bulk_ingest_result.csv"``）。
    """
    text, headers = client.request_csv("GET", path, component=component)
    lines = text.splitlines()
    locator = headers.get("Sforce-Locator", "")
    if not lines and (not locator or locator == NO_MORE_PAGES_LOCATOR):
        # 1ページ目が完全に空で、次ページも無い → 真の0件
        return Table([], [])
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / tmp_filename
        # 1ページ目（ヘッダー込み）を書き出す。``splitlines`` で末尾改行を
        # 落としているので、追記時に ``\n`` を足してもページ間に空行が
        # 挟まらない（``csv.DictReader`` の行解釈がずれないように）。
        tmp_path.write_text("\n".join(lines), encoding="utf-8")
        while locator and locator != NO_MORE_PAGES_LOCATOR:
            next_path = f"{path}?locator={urllib.parse.quote(locator, safe='')}"
            next_text, next_headers = client.request_csv("GET", next_path, component=component)
            next_lines = next_text.splitlines()
            # 2ページ目以降のヘッダー行を除いて追記（未検証の前提）
            with tmp_path.open("a", encoding="utf-8", newline="") as f:
                if next_lines[1:]:
                    f.write("\n")
                    f.write("\n".join(next_lines[1:]))
            locator = next_headers.get("Sforce-Locator", "")
        with CSV(tmp_path, read_only=True) as csv_file:
            return csv_file.read()
