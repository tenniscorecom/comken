"""comken/core/files/finder.py — フォルダ内のファイル検索

使い方は docs/core.md を参照。
"""

import datetime
import logging
import re
from pathlib import Path

from comken.core.clock import today
from comken.core.timer import measure

logger = logging.getLogger(__name__)

# ファイル名に含まれる日付らしい数字（20260729 / 2026-07-29 / 2026_07_29 / 2026.07.29）。
# 前後を数字で挟まれたものは日付とみなさない（社員番号・伝票番号の一部を拾わないため）
_DATE_IN_NAME = re.compile(r"(?<!\d)([0-9]{4})([-_.]?)([0-9]{2})\2([0-9]{2})(?!\d)")


class DateFileFinder:
    """指定した名前と日付を持つファイルを探す。"""

    def __init__(self, folder: str | Path, for_date: datetime.date | None = None) -> None:
        self._folder = Path(folder)
        self._date = for_date or today()

    @measure
    def prefix(
        self,
        prefix: str,
        extension: str = ".xlsx",
        required: bool = True,
    ) -> Path | None:
        """``prefix + YYYYMMDD + 拡張子`` に一致するファイルを返す。

        prefix に ``{:%Y-%m-%d}`` のような日付書式があれば、その位置へ日付を
        入れる。書式がなければ末尾へ ``YYYYMMDD`` を付ける。
        """
        extension = extension if extension.startswith(".") else f".{extension}"
        dated_prefix = (
            prefix.format(self._date) if "{:" in prefix else f"{prefix}{self._date:%Y%m%d}"
        )
        expected_name = f"{dated_prefix}{extension}"
        logger.debug(
            "日付付きファイル検索開始: フォルダ=%s ファイル名=%s", self._folder, expected_name
        )
        matches = [
            path for path in self._folder.iterdir() if path.is_file() and path.name == expected_name
        ]
        if matches:
            logger.debug("日付付きファイル検索完了: 件数=%d", len(matches))
            return matches[0]
        logger.debug("日付付きファイル検索完了: 件数=0")
        if required:
            raise FileNotFoundError(
                f"日付付きファイルが見つかりません: {self._folder / expected_name}"
            )
        return None

    @measure
    def dated(
        self,
        prefix: str,
        extension: str = ".xlsx",
    ) -> list[Path]:
        """``prefix`` で始まり ``extension`` で終わる、日付を含むファイルを全件返す。

        フォルダ内のファイル名から ``date_in_name`` で日付を取り出し、**日付の新しい順**に
        並べる。同じ日付のときは更新日時が新しい方を先にする。該当するファイルが無ければ
        空リストを返す（例外は出さない）。

        ``prefix()`` との違い:

        - ``prefix`` 内の日付書式（``{:%Y-%m-%d}`` 等）は解釈せず、文字どおりの前方一致だけを行う。
        - コンストラクタの ``for_date`` は使わない。フォルダ内の全件が対象になる。
        - 見つからないときに例外を上げず、空リストを返す（``required`` 相当の引数も無い）。

        Args:
            prefix: ファイル名の先頭（この通りの前方一致。日付書式は解釈しない）。
            extension: 拡張子。先頭が ``.`` でなければ補う（``xlsx`` も ``.xlsx`` も OK）。

        Returns:
            日付の新しい順に並んだ ``Path`` のリスト。同じ日付のときは更新日時が新しい順。
            該当するファイルが無ければ空リスト。
        """
        extension = extension if extension.startswith(".") else f".{extension}"
        logger.debug(
            "日付付きファイル全件検索開始: フォルダ=%s 接頭辞=%s 拡張子=%s",
            self._folder,
            prefix,
            extension,
        )
        dated_paths: list[tuple[datetime.date, float, Path]] = []
        for path in self._folder.iterdir():
            if not path.is_file():
                continue
            if not path.name.startswith(prefix):
                continue
            if not path.name.endswith(extension):
                continue
            file_date = date_in_name(path.name)
            if file_date is None:
                continue
            dated_paths.append((file_date, path.stat().st_mtime, path))
        # 日付の降順 → 同じ日付なら更新日時が新しい方（mtime 降順）
        dated_paths.sort(key=lambda item: (item[0], item[1]), reverse=True)
        matches = [path for _, _, path in dated_paths]
        logger.debug("日付付きファイル全件検索完了: 件数=%d", len(matches))
        return matches


def date_in_name(name: str) -> datetime.date | None:
    """ファイル名に含まれる最初の日付を返す。日付が無ければ None。

    1つのファイル名に日付が複数あるときは、先に出てくる方を使う。
    ファイル名の日付とファイル内容の日付を突き合わせる業務で使うため公開している。
    """
    for match in _DATE_IN_NAME.finditer(name):
        year, _, month, day = match.groups()
        try:
            return datetime.date(int(year), int(month), int(day))
        except ValueError:
            continue  # 20261345 のように数字は揃っていても日付として成立しないもの
    return None
