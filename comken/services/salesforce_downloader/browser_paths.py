r"""comken/services/salesforce_downloader/browser_paths.py — ブラウザ版exportの保存先組み立て。

グループごとに保存先のベースパスが変わる運用に合わせて、
``base/担当者/概要/レポート名.拡張子`` の形で保存先を組み立てる。
``comken.toolbox.browser.sites.salesforce.Salesforce.export_reports()`` の
``reports: Mapping[URL, 保存先パス]`` を作るときに使う。

    from comken.services.salesforce_downloader.browser_paths import build_destination

    base_by_group = {"営業部": r"\\server\share\営業部", "経理部": r"\\server\share\経理部"}
    dest = build_destination(base_by_group, "営業部", "山田", "顧客一覧", "月次顧客一覧")
    # → \\server\share\営業部\山田\顧客一覧\月次顧客一覧.csv
"""

from collections.abc import Mapping
from pathlib import Path

# ファイル名・フォルダ名に使えない文字
_FORBIDDEN_IN_NAME = '\\/:*?"<>|'


def build_destination(
    base_by_group: Mapping[str, str | Path],
    group_name: str,
    assignee: str,
    summary: str,
    report_name: str,
    *,
    export_format: str = "csv",
) -> Path:
    """保存先を ``base/担当者/概要/レポート名.拡張子`` の形で組み立てる。

    ベースパスはグループごとに変わる運用のため、呼び出し側が
    ``{グループ名: ベースパス}`` の対応表を渡す。

    Args:
        base_by_group: ``{グループ名: 保存先のベースパス}`` の対応表。
        group_name: 保存先のベースを決めるグループ名。
        assignee: 担当者名。フォルダ名になる。
        summary: レポートの概要。フォルダ名になる。
        report_name: レポート名。ファイル名になる（拡張子は付けない）。
        export_format: ファイルの拡張子。既定は "csv"。

    Returns:
        組み立てた保存先パス（``pathlib.Path``）。

    Raises:
        ValueError: ``group_name`` が ``base_by_group`` に登録されていない場合。
    """
    if group_name not in base_by_group:
        known = "、".join(base_by_group) or "（登録なし）"
        raise ValueError(
            f"グループ「{group_name}」のベースパスが登録されていません。登録済みのグループ: {known}"
        )
    base = Path(base_by_group[group_name])
    return (
        base
        / _safe_name(assignee)
        / _safe_name(summary)
        / f"{_safe_name(report_name)}.{export_format}"
    )


def _safe_name(name: str) -> str:
    """フォルダ名・ファイル名に使えない文字を落とす。"""
    cleaned = "".join(char for char in name if char not in _FORBIDDEN_IN_NAME).strip()
    return cleaned or "名称未設定"
