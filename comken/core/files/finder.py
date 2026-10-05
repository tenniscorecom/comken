"""comken/core/files/finder.py — フォルダ内のファイル検索

使い方は docs/機能/core.md を参照。
"""

import datetime
import logging
from pathlib import Path

from comken.core.dates import today
from comken.core.dates.parse import dates_in_name
from comken.core.timer import measure
from comken.exceptions import ComkenFileNotFoundError, FileSuffixMissingError

logger = logging.getLogger(__name__)


@measure
def find_dated_file(
    folder: str | Path,
    name: str,
    for_date: datetime.date | None = None,
) -> Path:
    """指定した名前と日付を持つファイルを 1 件返す。

    探す名前に **拡張子を含める**（例: ``"売上レポート.csv"``）。拡張子無しの名前を
    渡すと ``FileSuffixMissingError`` で止める。

    **注意: 呼ぶたびにフォルダを走査する。** 同じ結果を何度も使うなら変数に受けること
    （業務時間中に新しいファイルが降ってくる前提の道具なので、敢えてキャッシュしていない）。

    判定の規則:

    - 「名前を含む」: ``name`` の拡張子を除いた本体部分が、ファイル名の本体部分に
      **含まれている**（部分一致）。同じ拡張子（大文字小文字は区別しない）のファイル
      だけが対象。日付の位置や書式（``20260711`` / ``2026-07-11`` / ``2026_07_11`` /
      ``2026.07.11``）は問わない
    - ファイル名から ``dates_in_name`` で取り出した日付リストの中に ``for_date``
      （省略時は今日）が **含まれる** ファイルだけが対象。
      複数見つかったときは **更新日時（mtime）が新しい方** を返す。
      1 つも無ければ ``ComkenFileNotFoundError``

    Args:
        folder: 探すフォルダ。
        name: 探すファイル名。**拡張子を含める**（例: ``"売上レポート.csv"``）。
        for_date: ファイル名から取り出した日付のどれかと一致する対象日。
            ``None``（既定）なら呼んだ時点の ``today()``。

    Returns:
        条件に合うファイルのうち mtime が最新の ``Path``。

    Raises:
        FileSuffixMissingError: ``name`` に拡張子が含まれていないとき。
        ComkenFileNotFoundError: フォルダが存在しない／フォルダではない、
            もしくは条件に合うファイルが無いとき。
    """
    stem, extension = _split_suffix(name)
    folder_path = _resolve_folder(Path(folder))
    target_date = for_date or today()
    logger.debug(
        "日付付きファイル検索開始: フォルダ=%s 名前=%s 対象日=%s",
        folder_path,
        name,
        target_date,
    )
    matches: list[tuple[float, Path]] = []
    for path in folder_path.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() != extension.lower():
            continue
        if stem not in path.stem:
            continue
        if target_date not in dates_in_name(path.name):
            continue
        matches.append((path.stat().st_mtime, path))
    if matches:
        matches.sort(key=lambda item: item[0], reverse=True)
        chosen = matches[0][1]
        logger.debug("日付付きファイル検索完了: 件数=%d 採用=%s", len(matches), chosen.name)
        return chosen
    logger.debug("日付付きファイル検索完了: 件数=0")
    raise ComkenFileNotFoundError(
        "日付付きファイル",
        folder_path / name,
        hint=(
            f"探した日付: {target_date}\n"
            f"フォルダに『日付が今日のファイル』が置かれているか、"
            "名前（拡張子を含む）を確認してください。"
        ),
    )


def _split_suffix(name: str) -> tuple[str, str]:
    """ファイル名を ``stem`` と拡張子（``".xlsx"`` 等）に分ける。

    ``pathlib.Path`` の規則に従う:

    - ``"売上.xlsx"`` → ``("売上", ".xlsx")``
    - ``"売上"`` → ``FileSuffixMissingError``
    - ``"data.tar.gz"`` → ``("data.tar", ".gz")``（最後のドット以降を拡張子とみなす）
    - ``".hidden"`` → ``FileSuffixMissingError``（ドット始まりのファイル名は不可）

    Raises:
        FileSuffixMissingError: 拡張子が無いとき。
    """
    parsed = Path(name)
    extension = parsed.suffix
    if not extension:
        logger.debug("_split_suffix 失敗: 拡張子なし: %s", name)
        raise FileSuffixMissingError(name)
    return parsed.stem, extension


def _resolve_folder(folder: Path) -> Path:
    """フォルダが存在してディレクトリであることを確認し、``Path`` を返す。

    Raises:
        ComkenFileNotFoundError: フォルダが無い／フォルダではないとき。
    """
    if not folder.exists() or not folder.is_dir():
        raise ComkenFileNotFoundError(
            "フォルダ",
            folder,
            hint="指定したパスがフォルダとして存在するか確認してください。",
        )
    return folder
