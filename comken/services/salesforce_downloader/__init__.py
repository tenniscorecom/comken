r"""comken/services/salesforce_downloader/__init__.py — Salesforce レポートの履歴と読取。

**2026-09 に「取る側」と「読む側」をはっきり分けた。**

- **取る側**（管理表・スケジュール・SOQL レポート・取得の実行）は
  `Salesforceレポートダウンローダー` リポジトリ（`src/`）。管理表を
  読み、スケジュールを判定し、Salesforce から取り、保存し、履歴へ書く
  `download_scheduled()` まで全部こちらにある
- **comken に残ったもの**は、履歴の**形式**（`COLUMNS` / `HistoryRow`）と、
  **管理番号だけで取得済みレポートを引く読み取り関数**だけ
  （`latest_report_path` / `latest_report` / `today_report` / `has_today_report`）
- 境界を**履歴（ダウンロード履歴.csv）**にしたので、管理表を変えても
  comken は変えなくてよい

    from comken.services.salesforce_downloader import has_today_report, latest_report

    CUSTOMER_LIST = "1001"        # プロジェクトごとに、意味の分かる名前を付ける

    by_code = latest_report(CUSTOMER_LIST).index("顧客コード")
    if not has_today_report(CUSTOMER_LIST):
        # 定期取得が動いていない可能性 — 履歴の「成功」記録がない
        ...

**プロジェクトのコードに Salesforce の URL もレポート ID も書かない。** 書くのは
管理番号だけで、参照先の差し替えはダウンローダー側の管理表を直せば済む（コードは変えない）。

    latest_report_path    最も新しい成功履歴が指すパスを返す（中身は読まない）
    latest_report         最も新しい成功履歴の中身を ``Table`` で返す
    today_report          今日成功した履歴のうち最も新しい中身を ``Table`` で返す
    has_today_report      今日成功した履歴があり実ファイルも残っていれば True
    downloaded_today      指定した管理番号が今日すでに成功しているかを履歴から調べる
    read_history          履歴 CSV を全件 ``Table`` で返す（フィルタはしない）
    append_history        履歴を1行追記する（ダウンローダー側から呼ばれる共有書き込み）
    HistoryRow            履歴1行の形（呼び出し側で ``Mapping`` を組み立てるための参考）
    COLUMNS               履歴の列順と列名

**「今すぐ取りに行く」関数はここには無い。** 取得の実行（`download_scheduled()`）は
`Salesforceレポートダウンローダー` リポジトリ側にある。急ぎの取得は権限を持つ人が
Salesforce から手動ダウンロードするか、そちらのプロジェクトで `download_scheduled()`
をスケジュール外で直接実行する。

分担が変わってきた経緯は `docs/HISTORY.md`（6 章・15 章）を参照。

comken 本体側の共有例外（`ComkenError` / `HistoryWriteError` /
`ReportNotDownloadedError` など）は `from comken.exceptions import ...` で読み込む。

---

**このファイルが持つもの:**
- 履歴CSVの形式（列定義 `COLUMNS` / 行の形 `HistoryRow`）
- 取得済みを読み取る側の実装（`latest_report` / `today_report` / `has_today_report`）
- 履歴書き込み（`append_history`）
- 履歴の置き場所（`paths.HISTORY_PATH`）

**ここに書かないもの:**
- 取得を実行する側（Salesforce への問い合わせ・保存・履歴に書く値の組み立て） →
  `Salesforceレポートダウンローダー`
- 管理表・スケジュール・設定・SOQL レポート → `Salesforceレポートダウンローダー`
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

**`__init__.py` 経由の import で重い依存を読み込ませない設計。**
`requests` などを必要としないため、このパッケージ単体では何も追加で import
しない。`__getattr__` (PEP 562) による遅延 import は、読み取り関数の入口を
1 か所に集約する目的だけに残してある
（`from comken.services.salesforce_downloader import latest_report` が動くように）。
"""

from typing import TYPE_CHECKING

from comken.services.salesforce_downloader.history import COLUMNS, HistoryRow

if TYPE_CHECKING:
    from comken.services.salesforce_downloader.history import (
        append_history,
        downloaded_today,
        has_today_report,
        latest_report,
        latest_report_path,
        read_history,
        today_report,
    )

__all__ = [
    "latest_report_path",
    "latest_report",
    "today_report",
    "has_today_report",
    "downloaded_today",
    "read_history",
    "append_history",
    "HistoryRow",
    "COLUMNS",
]

# 遅延 import する対象。値はその属性が定義されているサブモジュールの絶対パス。
_LAZY_TARGETS: dict[str, str] = {
    "append_history": "comken.services.salesforce_downloader.history",
    "downloaded_today": "comken.services.salesforce_downloader.history",
    "has_today_report": "comken.services.salesforce_downloader.history",
    "latest_report": "comken.services.salesforce_downloader.history",
    "latest_report_path": "comken.services.salesforce_downloader.history",
    "read_history": "comken.services.salesforce_downloader.history",
    "today_report": "comken.services.salesforce_downloader.history",
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
