r"""comken/services/salesforce_downloader/__init__.py — Salesforce レポート管理表・履歴の共有契約。

**取得を実行する側（旧 `download_scheduled()`）は 2026-09 に comken の外
（`Salesforceレポートダウンローダー` リポジトリ）へ切り出した。** このパッケージに
残っているのは、取得を実行する側・取得済みを読む側の**両方が従う共有の形**——
管理表（Excel）の列定義、履歴（CSV）の列定義、保存先パスの組み立て——と、
**「取っておいたものを受け取る」読み取り側の実装**だけ。経緯は本ファイル末尾を参照。

    from comken.services.salesforce_downloader import cached_report

    CUSTOMER_LIST = "1001"        # プロジェクトごとに、意味の分かる名前を付ける

    by_code = cached_report(CUSTOMER_LIST).index("顧客コード")

**プロジェクトのコードに Salesforce の URL もレポート ID も書かない。** 書くのは
管理番号だけで、参照先の差し替えは管理表を直せば済む（コードは変えない）。

    cached_report         本日の定期取得キャッシュを CSV で返す（取りに行かない）
    cached_report_path    本日の定期取得キャッシュが置かれるパスを返す（中身は読まない）
    file_path_of          そのレポートが保存されるパス
    load_master           管理表を読む
    shared_report_ids     同じ Salesforce レポートを指している管理番号を返す
    ReportEntry           管理表の1行
    ReportEntry.create_template  管理表の雛形（Excel）を作る
    ScheduleRule          取得スケジュール管理表の1行
    write_latest_status   全レポートの最新実行結果を 1 つの Excel へ上書き生成する
    downloaded_today      指定した管理番号が今日すでに成功しているかを履歴から調べる

**「今すぐ取りに行く」関数はここには無い。** 取得の実行（`download_scheduled()`）は
`Salesforceレポートダウンローダー` リポジトリ側にある。急ぎの取得は権限を持つ人が
Salesforce から手動ダウンロードするか、そちらのプロジェクトで `download_scheduled()`
をスケジュール外で直接実行する。

管理表の検査はコマンドから呼べる（保守用。業務の定期実行ではない）:

    python -m comken sfdl check

---

**このパッケージと `Salesforceレポートダウンローダー` の分担は何度か変わっている。**
経緯は次のとおり（新しい方を先に書く）:

- **2026-09: 取得実行部分（旧 `service.py` / `download_scheduled()`）を再度
  comken の外（`Salesforceレポートダウンローダー`）へ切り出した。** 実際に
  `download_scheduled()`（管理表・履歴を読んで Salesforce へ取りに行き、
  履歴へ書く）を呼ぶプロジェクトは今のところこの1つだけで、しかもそこで
  完結している。「1つのプロジェクトだけが困っているなら、そのプロジェクトに
  書く」という下の判定基準に照らすと、単一消費者の実行部分を comken に
  置き続ける理由が無くなっていた。一方で、管理表・履歴の**形式そのもの**
  （列定義・読み取り関数）は、将来別プロジェクトが `cached_report()` で
  読みに来たときに毎回書き方を揃え直さずに済むよう、引き続き comken 側に
  置く。取得実行側は `paths.MASTER_PATH` / `history.HistoryRow` /
  `history.COLUMNS` / `history_file_lock.HistoryFileLock` /
  `provider.daily_cache_path_of` など、ここで定義する形式を import して使う
  （これらのモジュール・シンボルにアンダースコアを付けていないのは、この
  外部からの import を想定しているため）。
- 2026-08-30 に comken から分離し、外部の別リポジトリ
  （`comken-salesforce-downloader` → 最終的に `Salesforceレポートダウンローダー`）として
  運用していた
- 他のプロジェクトが呼び出すたびに comken 用とは別の `PYTHONPATH` / `pip install`
  設定が必要になる不便が判明したため、2026-08-31 に comken 本体へ再統合した
  （※ この時点では取得実行部分も含めて丸ごと comken 側にあった）

comken 本体側の共有例外（`ComkenError` / `SalesforceReportIDNotFoundError` など）は
引き続き `from comken.exceptions import ...` で読み込む。

---

**このファイルが持つもの:**
- Salesforce レポート管理表・履歴の「形式（列定義）」
- 取得済みを読み取る側の実装（`cached_report` など）

**ここに書かないもの:**
- 取得を実行する側（Salesforce への問い合わせ・保存・履歴書き込み） → `Salesforceレポート
  ダウンローダー`
- いつ取るか（毎日・平日・月末などのスケジュール判定） → 取得を実行する側のプロジェクト
- 取ったデータの加工・DB登録・帳票化 → 利用プロジェクト
- 取得成功時の通知（メール・チャット等） → 利用プロジェクト
- 「このプロジェクトのときはこうする」という業務ルール → 利用プロジェクト

**迷ったときの判定:**
- **1つのプロジェクトだけが困っているなら、そのプロジェクトに書く**
- **全プロジェクトが同じように困るなら、ここに書く**

迷ったら入れない。プロジェクト側に書いたものは後から共通へ引き上げられるが、
ここに入れたものは利用者が付いた後だと外せなくなるため（後から動かせる方向へ倒す）。

---

**`__init__.py` 経由の import で `openpyxl` 以外の重い依存を読み込ませない設計。**
取得実行部分（`requests` / `selenium` が要る）が外へ出たため、このパッケージ自体は
もう `requests` を必要としない。`__getattr__` (PEP 562) による遅延 import は、
`master.py`（Excel）だけで完結する軽い用途と `latest_status.py`（openpyxl の
スタイル操作まで使う）用途を分けておく目的で残してある。
"""

from comken.services.salesforce_downloader.master import (
    ReportEntry,
    load_master,
    shared_report_ids,
)
from comken.services.salesforce_downloader.schedule import ScheduleRule

__all__ = [
    "cached_report",
    "cached_report_path",
    "file_path_of",
    "load_master",
    "shared_report_ids",
    "write_latest_status",
    "downloaded_today",
    "ReportEntry",
    "ScheduleRule",
]

# 遅延 import する対象。値はその属性が定義されているサブモジュールの絶対パス。
_LAZY_TARGETS: dict[str, str] = {
    "cached_report": "comken.services.salesforce_downloader.provider",
    "cached_report_path": "comken.services.salesforce_downloader.provider",
    "file_path_of": "comken.services.salesforce_downloader.provider",
    "write_latest_status": "comken.services.salesforce_downloader.latest_status",
    "downloaded_today": "comken.services.salesforce_downloader.history",
}


def __getattr__(name: str) -> object:
    """`from ... import X` の X を必要になったタイミングでだけ import する。

    Raises:
        AttributeError: 定義されていない属性を要求したとき。
    """
    module_name = _LAZY_TARGETS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    # 2回目以降は module ロードをスキップして globals() から返す (PEP 562 の慣例)
    import importlib

    module = importlib.import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """`dir(comken.services.salesforce_downloader)` で遅延対象も返す。"""
    return sorted(set(__all__) | set(_LAZY_TARGETS))
