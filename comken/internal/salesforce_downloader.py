"""comken/internal/salesforce_downloader.py — 既存 salesforce_downloader の薄いラッパー。

``comken.services.salesforce_downloader`` の主要 API を再エクスポートして、
``comken.internal`` 配下から Salesforce ダウンロードを使えるようにする。
既存 ``comken.services.salesforce_downloader`` は触らない
（ユーザー指示「現状のセールスフォースは触らないで残したまま」）。
"""

from comken.services.salesforce_downloader import (
    ReportEntry,
    ScheduleRule,
    download_report,
    download_scheduled,
    file_path_of,
    load_master,
    shared_report_ids,
)

__all__ = [
    "download_report",
    "download_scheduled",
    "file_path_of",
    "load_master",
    "ReportEntry",
    "ScheduleRule",
    "shared_report_ids",
]
