"""comken/services/salesforce_downloader/paths.py — 管理表・履歴の置き場所。

`provider.py`（読み取る側）や、外部プロジェクト（Salesforceレポートダウンローダー）の
取得実行側の両方が読む定数を、依存関係を持ち込まない形で共有する。
`comken.toolbox.salesforce` を経由しないため、`requests` なしで import できる。

**アンダースコア無しの名前にしてある。** 取得実行部分（旧 `service.py`）は
2026-09 に comken の外（Salesforceレポートダウンローダー）へ切り出したため、
この定数はもう同一パッケージ内だけでなく、外部プロジェクトからも直接
import される（詳しくは `__init__.py` の履歴メモを参照）。

配置するときに実際の場所へ書き換える（公開リポジトリなので仮名にしてある）。
"""

from pathlib import Path

# レポート管理表（Excel）。非エンジニアが編集する。編集後は次のコマンドで検査できる:
#     python -m comken sfdl check
# 雛形が必要な場合は `ReportEntry.create_template()` を Python から直接呼ぶ
# （雛形自動生成の CLI は非エンジニア運用の方針により廃止済み）。
# **config ファイルへは外出ししない。** 利用側がパスを渡せるようにすると、
# プロジェクト側に定数を持たせて管理表と食い違う事故が起きる（場所を変えるなら
# ここ1か所を変える）。設定ファイルに集約する案は試して戻した
# （仕様書 8章「配置時に書き換える3ファイル」）。

# 管理表と履歴は同じフォルダに置く。フォルダだけ変えたい／ファイル名だけ
# 変えたいときに 1 本の文字列だと切り分けにくいので、フォルダ定数とファイル名
# 定数を分けて、 下の 2 つのパス定数で組み立てる。
SALESFORCE_DOWNLOADER_FOLDER = Path(r"\\server\share\tools\salesforce")

MASTER_FILENAME = "レポート管理表.xlsx"
HISTORY_FILENAME = "ダウンロード履歴.csv"

MASTER_PATH = SALESFORCE_DOWNLOADER_FOLDER / MASTER_FILENAME

# ダウンロード履歴（CSV）。プログラムが追記する（人は編集しない）
HISTORY_PATH = SALESFORCE_DOWNLOADER_FOLDER / HISTORY_FILENAME
