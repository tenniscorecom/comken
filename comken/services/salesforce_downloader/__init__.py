r"""comken/services/salesforce_downloader/__init__.py — Salesforce レポートの集約取得。

各プロジェクトが個別に Salesforce からレポートを落としていると、**どのプロジェクトが
どのレポートを、どれくらいの頻度で取っているのか**が分からなくなる。取得をここに集約し、
何を取っているかは管理表（Excel）に、いつ何を取ったかは履歴（CSV）に集める。

    from comken.services.salesforce_downloader import download_report, get_scheduled_report

    CUSTOMER_LIST = 1001          # プロジェクトごとに、意味の分かる名前で定数にする
    SALES_RESULT = 1003

    path = download_report(CUSTOMER_LIST)        # 今すぐ取りに行く
    path = get_scheduled_report(SALES_RESULT)    # 定期取得しておいたものを受け取る

**プロジェクトのコードに Salesforce の URL もレポート ID も書かない。** 書くのは
管理番号だけで、参照先の差し替えは管理表を直せば済む（コードは変えない）。

    download_report      今すぐ Salesforce から取得して、保存したパスを返す
    get_scheduled_report 定期取得しておいたファイルのパスを返す（取りに行かない）
    download_scheduled   「定期」登録の全件を取得する（定期実行のプロジェクトが呼ぶ）
    file_path_of         そのレポートが保存されるパス
    load_master          管理表を読む
    shared_report_ids    同じ Salesforce レポートを指している管理番号を返す
    ReportEntry          管理表の1行
    create_master_template  管理表の雛形（Excel）を作る

管理表の雛形作成と検査はコマンドからも呼べる（保守用。業務の定期実行ではない）:

    python -m comken.services.salesforce_downloader init レポート管理表.xlsx
    python -m comken.services.salesforce_downloader check レポート管理表.xlsx
"""

from .master import ReportEntry, load_master, shared_report_ids
from .service import download_report, download_scheduled, file_path_of, get_scheduled_report
from .template import create_master_template

__all__ = [
    "download_report",
    "get_scheduled_report",
    "download_scheduled",
    "file_path_of",
    "load_master",
    "shared_report_ids",
    "ReportEntry",
    "create_master_template",
]
