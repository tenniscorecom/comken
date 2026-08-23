r"""comken/services/salesforce_downloader/__init__.py — 後方互換用の re-export シェル。

実体は ``comken.internal.salesforce_downloader`` に移動済み。
旧パスからの import は引き続き動くが、新規コードは internal/ を使うこと。

    # 旧（動くが DeprecationWarning が出る）
    from comken.services.salesforce_downloader import cached_report, download_report

    # 新
    from comken.internal.salesforce_downloader import cached_report, download_report
"""

import warnings

from comken.internal.salesforce_downloader import (  # noqa: F401
    ReportEntry,
    ScheduleRule,
    cached_report,
    cli,
    download_report,
    download_scheduled,
    file_path_of,
    history,
    history_file_lock,
    load_master,
    master,
    provider,
    report_master,
    schedule,
    service,
    shared_report_ids,
)

warnings.warn(
    "comken.services.salesforce_downloader は非推奨です。"
    "comken.internal.salesforce_downloader を使用してください。",
    DeprecationWarning,
    stacklevel=2,
)
