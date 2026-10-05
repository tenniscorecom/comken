"""examples/advanced/salesforce_query/run.py — query() と bulk_query() の使い分けサンプル。

Salesforce の商談 (Opportunity) を例に、``SalesforceBase.query()`` と
``SalesforceBase.bulk_query()`` をどう使い分けるかを示す。Salesforce 組織・
認証情報なしでも動くよう、``_fake_org.FakeOpportunityOrg`` が ``_send``
だけを差し替える。``query()`` / ``bulk_query()`` 本体のロジックは
差し替えず、本物と同じコードが動く。

実行方法:
    リポジトリのルートで ``python -m examples.advanced.salesforce_query.run``

---

## query() / bulk_query() の使い分け

| 場面 | メソッド | 理由 |
|---|---|---|
| 1件だけ引く | ``query()`` + ``LIMIT 1`` | 速くて十分。型 (``dict``) がそのまま使える |
| 集計 (``COUNT``・``GROUP BY``) | ``query()`` | bulk は集計関数・``GROUP BY`` を 400 で弾く |
| 大量データ | ``bulk_query()`` | サーバ側でジョブ実行・往復が少ない・定期取得向き |
| 値の型 | 型付き (``int``・``bool``・``None``) | bulk の値は **全て文字列** |
| 参照項目 (``Account.Name``) | 入れ子の ``dict`` | bulk は ``Account.Name`` の列が立つ (非平坦) |

bulk_query() の制約:
- 値は **全て文字列**（真偽値は ``"true"`` / ``"false"``、null は空文字、
  ``"0012"`` の先頭ゼロもそのまま）。``int`` / ``bool`` / ``Decimal``
  に変換するのは呼び出し側の責任。
- 参照項目 (``Account.Name``) は見出しの名前をそのまま列名にする
  （平坦化しない）。
- 集計関数・``GROUP BY``・``OFFSET``・親→子のサブクエリはジョブ作成時に
  400 で失敗する。集計や少量の対話的な取得は ``query()`` で取る。
"""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path

from comken.core.table import Table
from comken.toolbox.csv import CSV
from comken.toolbox.salesforce.client import SalesforceBase
from examples.advanced.salesforce_query._fake_org import FakeOpportunityOrg

HERE = Path(__file__).parent
OUTPUT_DIR = HERE / "output"
OPPORTUNITIES_CSV_NAME = "opportunities.csv"

# bulk_query() で取る SOQL。戻り値は **全て文字列**。
# 真偽値は "true" / "false"、null は空文字、"0012" の先頭ゼロもそのまま。
OPPORTUNITY_SOQL = (
    "SELECT Id, Name, Account.Name, Amount, IsWon, CloseDate "
    "FROM Opportunity "
    "WHERE CloseDate = LAST_N_DAYS:365"
)
# 集計 (GROUP BY) は bulk_query() では 400 になるため query() で取る。
STAGE_AGGREGATE_SOQL = "SELECT StageName, COUNT(Id) cnt FROM Opportunity GROUP BY StageName"

logger = logging.getLogger(__name__)


def export_opportunities(sf: SalesforceBase, path: Path) -> Table:
    """``bulk_query()`` で商談を大量に取得し、CSV へ保存する。

    bulk_query() の戻り値は **全て文字列**。書き出した CSV もそのまま
    ``"true"`` / ``"false"``・空文字 (null)・``"0012"`` のまま。
    ``Account.Name`` のような参照項目は CSV の列名に ``Account.Name`` の
    まま残る（平坦化しない）。
    """
    logger.info("bulk_query() で商談を取得します")
    table = sf.bulk_query(OPPORTUNITY_SOQL)

    # with CSV(...) as out: の形で保存（bulk_query() の Table をそのまま書く）
    with CSV(path) as out:
        out.replace(table)

    logger.info("CSV 出力: %s (%d 件)", path, len(table))
    return table


def won_total(table: Table) -> Decimal:
    """成約 (``IsWon=true``) 案件の Amount 合計を ``Decimal`` で返す。

    bulk_query() の値は **全て文字列** なので ``Decimal`` に変換して足す。

    注意: ``if row["IsWon"]:`` と書くと **"false" も真と判定される**。
    空文字・``"false"`` いずれも Python では falsy ではないため、
    ``"true"`` と明示比較する。``Amount`` が空文字 (null) のときも
    ``Decimal("")`` はエラーになるため、 ``!= ""`` で先に除く。
    """
    total = Decimal("0")
    for row in table:
        if row["IsWon"] != "true":
            continue
        if row["Amount"] == "":
            continue
        total += Decimal(row["Amount"])
    return total


def count_by_stage(sf: SalesforceBase) -> dict[str, int]:
    """ステージ別の商談件数を集計する。

    bulk_query() は集計関数 / ``GROUP BY`` を受け付けない (400) ため、
    ``query()`` を使う。戻り値の ``cnt`` は int で返る
    （集計結果は Salesforce 側でカウント済みの整数として届く）。
    """
    logger.info("query() でステージ別件数を集計します")
    table = sf.query(STAGE_AGGREGATE_SOQL)
    return {row["StageName"]: int(row["cnt"]) for row in table}


def _soql_quote(value: str) -> str:
    """SOQL の文字列リテラル用に ``\\`` と ``'`` をエスケープして返す。

    利用者入力を SOQL に埋める前に通す。SOQL の文字列リテラルでは ``\\`` が
    エスケープ文字として解釈されるため、**先に ``\\`` を ``\\\\`` に増やしてから**
    ``'`` を ``\\'`` に置き換える（逆順だと ``\\'`` がもう一度 ``\\'`` 扱いされて
    しまう）。``'`` を含む社名（例: ``O'Brien & Sons``）が渡されたときに
    ``WHERE Name = 'O'Brien & Sons'`` のような壊れたクエリになるのを防ぐ。
    """
    return value.replace("\\", "\\\\").replace("'", "\\'")


def find_account(sf: SalesforceBase, name: str) -> dict | None:
    """アカウント名で 1 件だけ取得する。

    1件だけ欲しいときは ``query()`` + ``LIMIT 1`` で十分で、bulk を
    立てるほどではない。``bulk_query()`` はジョブ作成と完了待ちで
    1件取得でも数秒かかるため、対話的な引き方では無駄が大きい。
    """
    logger.info("query() でアカウントを 1 件取得: %s", name)
    soql = f"SELECT Id, Name FROM Account WHERE Name = '{_soql_quote(name)}' LIMIT 1"
    table = sf.query(soql)
    rows = list(table)
    return rows[0] if rows else None


def main() -> None:
    """疑似組織で 4 つの取得パターンを順に実行する。"""
    # ログを画面に出すための最小設定。``logs/`` ディレクトリは作らない
    # （``comken.core.logger`` の ``setup_local_logging`` を使うと
    # ``logs/local-YYYY-MM-DD.log`` を生成するため、サンプルの
    # ``output/`` 以外にはファイルを残さない方針に合わない）
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sf = FakeOpportunityOrg()
    try:
        # 1. bulk_query() で大量取得 → CSV へ保存
        # CSV パスは OUTPUT_DIR の差し替えに追随するため main() 内で組み立てる
        table = export_opportunities(sf, OUTPUT_DIR / OPPORTUNITIES_CSV_NAME)

        # 2. 成約案件の合計金額。値は全部文字列なので Decimal に変換して足す
        total = won_total(table)
        logger.info("成約案件の合計金額: %s 円", f"{total:,}")

        # 3. ステージ別件数は集計なので query() 側で取る。値は int で返る
        counts = count_by_stage(sf)
        logger.info("ステージ別件数:")
        for stage, count in counts.items():
            logger.info("  %s: %d 件", stage, count)

        # 4. 1件だけ引くなら query() + LIMIT 1
        account = find_account(sf, "株式会社アルファ")
        logger.info("アカウント検索結果: %s", account)
    finally:
        sf.close()


if __name__ == "__main__":
    main()
