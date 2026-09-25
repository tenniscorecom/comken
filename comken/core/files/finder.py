"""comken/core/files/finder.py — フォルダ内のファイル検索

使い方は docs/機能/core.md を参照。
"""

import datetime
import logging
import re
from pathlib import Path

from comken.core.dates import today
from comken.core.files.name import _split_suffix
from comken.core.timer import measure
from comken.exceptions import ComkenFileNotFoundError

logger = logging.getLogger(__name__)

# ファイル名に含まれる日付らしい数字（20260729 / 2026-07-29 / 2026_07_29 / 2026.07.29）。
# 前後を数字で挟まれたものは日付とみなさない（社員番号・伝票番号の一部を拾わないため）
_DATE_IN_NAME = re.compile(r"(?<!\d)([0-9]{4})([-_.]?)([0-9]{2})\2([0-9]{2})(?!\d)")


class DateFileFinder:
    """指定した名前と日付を持つファイルを探す。

    探す名前に **拡張子を含める**（例: ``"売上レポート.csv"``）。拡張子無しの名前を
    渡すと ``FileSuffixMissingError`` で止める。

    **注意: ``find()`` / ``find_all()`` は呼ぶたびにフォルダを走査する。** 同じ結果を
    何度も使うなら変数に受けること（業務時間中に新しいファイルが降ってくる前提の
    道具なので、 敢えてキャッシュしていない）。

    判定の規則:

    - 「名前を含む」: ``name`` の拡張子を除いた本体部分が、ファイル名の本体部分に
      **含まれている**（部分一致）。同じ拡張子（大文字小文字は区別しない）のファイル
      だけが対象。日付の位置や書式（``20260711`` / ``2026-07-11`` / ``2026_07_11`` /
      ``2026.07.11``）は問わない
    - ``find(name)``: 上の条件に加えて、ファイル名の日付の中に ``for_date``
      （コンストラクタで指定。省略時は今日）が **含まれる** ファイルだけが対象。
      複数見つかったときは **更新日時（mtime）が新しい方** を返す。
      1つも無ければ ``ComkenFileNotFoundError``
    - ``find_all(name)``: 上の名前の条件に加えて、ファイル名に日付が 1 つ以上ある
      ファイルだけが対象。**``for_date`` は使わない**。並び順は ``date_in_name``
      の日付の降順、同じ日付なら mtime の降順。該当するファイルが無ければ
      空リスト（例外は出さない）
    """

    def __init__(self, folder: str | Path, for_date: datetime.date | None = None) -> None:
        self._folder = Path(folder)
        self._date = for_date or today()

    @measure
    def find(self, name: str) -> Path:
        """名前を含み、ファイル名の日付が ``for_date`` のファイルを返す。

        同じ拡張子（大文字小文字は区別しない）で、``name`` の拡張子を除いた本体部分が
        ファイル名の本体部分に **含まれている** ファイルのうち、ファイル名から
        ``dates_in_name`` で取り出した日付リストの中に ``for_date`` が含まれるもの
        を返す。日付の位置・書式は問わない。

        候補が複数見つかったときは **更新日時（mtime）が新しい方** を返す。
        1 つも無ければ ``ComkenFileNotFoundError``
        （``FileNotFoundError`` としても送出される）。

        Args:
            name: 探すファイル名。**拡張子を含める**（例: ``"売上レポート.csv"``）。

        Returns:
            条件に合うファイルのうち mtime が最新の ``Path``。

        Raises:
            FileSuffixMissingError: ``name`` に拡張子が含まれていないとき。
            ComkenFileNotFoundError: フォルダが存在しない／フォルダではない、
                もしくは条件に合うファイルが無いとき。
        """
        stem, extension = _split_suffix(name)
        folder = self._resolve_folder()
        logger.debug(
            "日付付きファイル検索開始: フォルダ=%s 名前=%s 対象日=%s",
            folder,
            name,
            self._date,
        )
        matches: list[tuple[float, Path]] = []
        for path in folder.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() != extension.lower():
                continue
            if stem not in path.stem:
                continue
            if self._date not in dates_in_name(path.name):
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
            folder / name,
            hint=(
                f"探した日付: {self._date}\n"
                f"フォルダに『日付が今日のファイル』が置かれているか、"
                "名前（拡張子を含む）を確認してください。"
            ),
        )

    @measure
    def find_all(self, name: str) -> list[Path]:
        """名前を含み、日付を含むファイルを全部、新しい日付順で返す。

        ``name`` の拡張子を除いた本体部分がファイル名の本体部分に **含まれている**
        （部分一致）ファイルのうち、ファイル名から取り出した日付が 1 つ以上ある
        ファイルだけを返す。日付の位置・書式は問わない。

        並び順は ``dates_in_name`` の先頭日付の降順、同じ日付なら mtime の降順。
        ``for_date`` は使わない（フォルダ内の全件が対象）。
        該当するファイルが無ければ空リストを返す（例外は出さない）。

        Args:
            name: 探すファイル名。**拡張子を含める**（例: ``"売上レポート.csv"``）。

        Returns:
            条件に合うファイルの ``Path`` リスト。新しい日付順。

        Raises:
            FileSuffixMissingError: ``name`` に拡張子が含まれていないとき。
            ComkenFileNotFoundError: フォルダが存在しない／フォルダではないとき。
        """
        stem, extension = _split_suffix(name)
        folder = self._resolve_folder()
        logger.debug(
            "日付付きファイル全件検索開始: フォルダ=%s 名前=%s",
            folder,
            name,
        )
        dated_paths: list[tuple[datetime.date, float, Path]] = []
        for path in folder.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() != extension.lower():
                continue
            if stem not in path.stem:
                continue
            file_date = date_in_name(path.name)
            if file_date is None:
                continue
            dated_paths.append((file_date, path.stat().st_mtime, path))
        # 先頭日付の降順 → 同じ日付なら mtime の降順
        dated_paths.sort(key=lambda item: (item[0], item[1]), reverse=True)
        matches = [path for _, _, path in dated_paths]
        logger.debug("日付付きファイル全件検索完了: 件数=%d", len(matches))
        return matches

    def _resolve_folder(self) -> Path:
        """フォルダが存在してディレクトリであることを確認し、``Path`` を返す。

        Raises:
            ComkenFileNotFoundError: フォルダが無い／フォルダではないとき。
        """
        if not self._folder.exists() or not self._folder.is_dir():
            raise ComkenFileNotFoundError(
                "フォルダ",
                self._folder,
                hint="指定したパスがフォルダとして存在するか確認してください。",
            )
        return self._folder


def date_in_name(name: str) -> datetime.date | None:
    """ファイル名に含まれる **最初の日付** を返す。日付が無ければ None。

    1つのファイル名に日付が複数あるときは、先に出てくる方を使う。
    ファイル名の日付とファイル内容の日付を突き合わせる業務で使うため公開している。
    すべての日付が要るときは ``dates_in_name`` を使う。
    """
    dates = dates_in_name(name)
    return dates[0] if dates else None


def dates_in_name(name: str) -> list[datetime.date]:
    """ファイル名に含まれる日付を **すべて** 出現順で返す。無ければ空リスト。

    ``_DATE_IN_NAME`` 正規表現で日付らしい数字（``20260729`` / ``2026-07-29`` /
    ``2026_07_29`` / ``2026.07.29``）を抜き出し、``date`` に変換できたものだけを
    順番に並べる。``20261345`` のように数字は揃っていても日付として成立しないものは
    結果に含まない。
    """
    results: list[datetime.date] = []
    for match in _DATE_IN_NAME.finditer(name):
        year, _, month, day = match.groups()
        try:
            results.append(datetime.date(int(year), int(month), int(day)))
        except ValueError:
            continue  # 20261345 のように数字は揃っていても日付として成立しないもの
    return results
