"""comken/services/salesforce_downloader/paths.py — 履歴の置き場所。

取る側（Salesforceレポートダウンローダー）もこの定数を import して書き込むため、
書き換えるのはここ1か所だけでよい。`comken.toolbox.salesforce` を経由しないので
`requests` なしで import できる。

**アンダースコア無しの名前にしてある。** 取得実行部分（外部プロジェクト）と
comken 側の読み取り側の両方が直接 import する（外部プロジェクトの参照は
`__init__.py` の履歴メモを参照）。

配置するときに実際の場所へ書き換える（公開リポジトリなので仮名にしてある）。
"""

from pathlib import Path

# ダウンロード履歴（CSV）。プログラムが追記する（人は編集しない）。
# **管理表の場所（`MASTER_PATH`）は 2026-09 にダウンロード側へ移した** —
# comken 側は履歴だけを見る。取る側のプロジェクトが管理表の置き場所を
# 決めるので、ここでは触らない（境界を履歴にしたため）。
#
# **config ファイルへは外出ししない。** 利用側がパスを渡せるようにすると、
# プロジェクト側に定数を持たせて管理表・履歴と食い違う事故が起きる
# （場所を変えるならここ1か所を変える）。設定ファイルに集約する案は試して
# 戻した（docs/ARCHITECTURE.md「配置時に書き換える3ファイル」）。
SALESFORCE_DOWNLOADER_FOLDER = Path(r"\\server\share\tools\salesforce")
HISTORY_FILENAME = "ダウンロード履歴.csv"

HISTORY_PATH = SALESFORCE_DOWNLOADER_FOLDER / HISTORY_FILENAME
