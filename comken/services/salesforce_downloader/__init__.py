r"""comken/services/salesforce_downloader/__init__.py — Salesforce レポートの集約取得。

各プロジェクトが個別に Salesforce からレポートを落としていると、**どのプロジェクトが
どのレポートを、どれくらいの頻度で取っているのか**が分からなくなる。取得をここに集約し、
何を取っているかは管理表（Excel）に、いつ何を取ったかは履歴（CSV）に集める。

    from comken.services.salesforce_downloader import download_report, get_scheduled_report

    CUSTOMER_LIST = 1001          # プロジェクトごとに、意味の分かる名前で定数にする
    SALES_RESULT = 1003

    rows = download_report(CUSTOMER_LIST).read_rows()                  # 今すぐ取りに行く
    by_code = get_scheduled_report(SALES_RESULT).index("顧客コード")    # 定期取得済みを受け取る

**プロジェクトのコードに Salesforce の URL もレポート ID も書かない。** 書くのは
管理番号だけで、参照先の差し替えは管理表を直せば済む（コードは変えない）。

    download_report      今すぐ Salesforce から取得して、ファイルを CsvReader で返す
    get_scheduled_report 定期取得しておいたファイルを CsvReader で返す（取りに行かない）
    download_scheduled   「定期」登録の全件を取得する（定期実行のプロジェクトが呼ぶ）
    file_path_of         そのレポートが保存されるパス
    load_master          管理表を読む
    shared_report_ids    同じ Salesforce レポートを指している管理番号を返す
    ReportEntry          管理表の1行
    ReportEntry.create_template  管理表の雛形（Excel）を作る

管理表の雛形作成と検査はコマンドからも呼べる（保守用。業務の定期実行ではない）:

    python -m comken.services.salesforce_downloader init レポート管理表.xlsx
    python -m comken.services.salesforce_downloader check レポート管理表.xlsx

---

このファイルが持つもの:
- Salesforce レポートの「定義（管理表）・取得・保存・履歴」

ここに書かないもの:
- いつ取るか（毎日・平日・月末などのスケジュール判定） → 呼び出す側のプロジェクト
- 取ったデータの加工・DB登録・帳票化 → 利用プロジェクト
- 取得成功時の通知（メール・チャット等） → 利用プロジェクト
- 「このプロジェクトのときはこうする」という業務ルール → 利用プロジェクト

迷ったときの判定:
- **1つのプロジェクトだけが困っているなら、そのプロジェクトに書く**
- **全プロジェクトが同じように困るなら、ここに書く**

迷ったら入れない。プロジェクト側に書いたものは後から共通へ引き上げられるが、
ここに入れたものは利用者が付いた後だと外せなくなるため（後から動かせる方向へ倒す）。
"""

from .master import ReportEntry, load_master, shared_report_ids
from .service import download_report, download_scheduled, file_path_of, get_scheduled_report

__all__ = [
    "download_report",
    "get_scheduled_report",
    "download_scheduled",
    "file_path_of",
    "load_master",
    "shared_report_ids",
    "ReportEntry",
]
