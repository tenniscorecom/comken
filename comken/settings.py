r"""comken/settings.py — 社内固有の値をまとめる。

**社内の値を持つのはこのファイルだけ。** 共有フォルダの場所・組織の URL など、
公開リポジトリに実物を書けない値をここに集める。配置するときに実際の値へ書き換える。

**配置しても上書きされない。** `deploy.py` はこのファイルを配置先の既存のまま残すので、
comken を更新しても書き換えた値は消えない。

    from comken import settings

    settings.MASTER_PATH        # レポート管理表の場所

設定を ini にしない理由:

- **設定がコードと ini に散ると、どちらを見ればよいか分からなくなる。** 探す場所は1つにする
- Python の定数なら import した時点で解決するので、**クラス定数にも使える**
  （ini から読む形にすると、import した瞬間に設定ファイルが必要になる）
- 補完が効き、型も付く。書き間違いは import した時点で分かる

ここに書かないもの:

- **プロジェクトごとに変わる値**（入力フォルダ・出力先など）は各プロジェクトの config.ini へ。
  ここに書くのは「comken を1回配置したら、そのまま変わらない値」だけ
- **社内 RPA 基盤の import 名**（`comken/toolbox/rpa.py`）。import 文は文字列にできないため、
  あちらは直接書き換える。あのファイルも deploy で上書きされない
"""

from pathlib import Path

# ── Salesforce レポートの集約取得（comken.services.salesforce_downloader）────────
# レポート管理表（Excel）。非エンジニアが編集する。雛形は次のコマンドで作れる:
#     python -m comken.services.salesforce_downloader init レポート管理表.xlsx
MASTER_PATH = Path(r"\\server\share\tools\salesforce\レポート管理表.xlsx")

# ダウンロード履歴（CSV）。プログラムが追記する（人は編集しない）
HISTORY_PATH = Path(r"\\server\share\tools\salesforce\ダウンロード履歴.csv")


# ── Salesforce の組織（comken.toolbox.salesforce.sites）──────────────────────────
# Sandbox 組織の My Domain。「<組織>--<サンドボックス名>.sandbox」の形になる
SANDBOX_DOMAIN_URL = "https://example--sandbox.sandbox.my.salesforce.com"

# 認証情報のキー名の頭。DPAPI には sandbox_client_id / sandbox_client_secret で入る
SANDBOX_CREDENTIAL_PREFIX = "sandbox"

# Sandbox 組織のレポート ID（組織ごとに固有で、環境では変わらない）
SANDBOX_REPORT_案件一覧 = "00O000000000001"
