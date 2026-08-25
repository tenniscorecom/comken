"""comken/core/files/finder.py — フォルダ内のファイル検索

使い方は docs/core.md を参照。
"""

import datetime
import logging
import re
from pathlib import Path

from comken.core.clock import today
from comken.core.timer import measure
from comken.exceptions import FileSuffixMissingError

logger = logging.getLogger(__name__)

# ファイル名に含まれる日付らしい数字（20260729 / 2026-07-29 / 2026_07_29 / 2026.07.29）。
# 前後を数字で挟まれたものは日付とみなさない（社員番号・伝票番号の一部を拾わないため）
_DATE_IN_NAME = re.compile(r"(?<!\d)([0-9]{4})([-_.]?)([0-9]{2})\2([0-9]{2})(?!\d)")


class DateFileFinder:
    """指定した名前と日付を持つファイルを探す。

    探す名前に **拡張子を含める**（例: ``"売上レポート.csv"``）。拡張子無しの名前を
    渡すと ``FileSuffixMissingError`` で止める。

    **注意: ``prefix()`` / ``dated()`` は呼ぶたびにフォルダを走査する**。 同じ結果を
    何度も使うなら変数に受けること（業務時間中に新しいファイルが降ってくる前提の
    道具なので、 敢えてキャッシュしていない）。
    """

    def __init__(self, folder: str | Path, for_date: datetime.date | None = None) -> None:
        self._folder = Path(folder)
        self._date = for_date or today()

    @measure
    def prefix(
        self,
        name: str,
        required: bool = True,
    ) -> Path | None:
        """``prefix + 日付 + 拡張子`` に一致するファイルを返す。

        ``name`` に ``{:%Y-%m-%d}`` のような日付書式があれば、その位置へ日付を
        入れる。書式がなければ末尾へ ``YYYYMMDD`` を付ける。日付は **拡張子の手前** に入る。
        """
        stem, extension = _split_suffix(name)
        dated_name = (
            name.format(self._date) if "{:" in name else f"{stem}{self._date:%Y%m%d}{extension}"
        )
        logger.debug(
            "日付付きファイル検索開始: フォルダ=%s ファイル名=%s", self._folder, dated_name
        )
        matches = [
            path for path in self._folder.iterdir() if path.is_file() and path.name == dated_name
        ]
        if matches:
            logger.debug("日付付きファイル検索完了: 件数=%d", len(matches))
            return matches[0]
        logger.debug("日付付きファイル検索完了: 件数=0")
        if required:
            raise FileNotFoundError(
                f"日付付きファイルが見つかりません: {self._folder / dated_name}"
            )
        return None

    @measure
    def dated(
        self,
        prefix: str,
    ) -> list[Path]:
        """``prefix`` で始まり日付を含むファイルを全件、日付の新しい順で返す。

        ``prefix`` には **拡張子を含む完全なファイル名の一部** を渡す（例:
        ``"売上レポート.csv"`` — 拡張子は必須）。フォルダ内のファイル名から
        ``date_in_name`` で日付を取り出し、**日付の新しい順** に並べる。同じ日付の
        ときは更新日時が新しい方を先にする。該当するファイルが無ければ空リストを
        返す（例外は出さない）。

        ``prefix()`` との違い:

        - ``prefix`` 内の日付書式（``{:%Y-%m-%d}`` 等）は解釈せず、文字どおりの前方一致だけを行う。
        - コンストラクタの ``for_date`` は使わない。フォルダ内の全件が対象になる。
        - 見つからないときに例外を上げず、空リストを返す（``required`` 相当の引数も無い）。

        Args:
            prefix: ファイル名の先頭（この通りの前方一致。日付書式は解釈しない）。
                拡張子は必須。

        Returns:
            日付の新しい順に並んだ ``Path`` のリスト。同じ日付のときは更新日時が新しい順。
            該当するファイルが無ければ空リスト。

        Raises:
            FileSuffixMissingError: ``prefix`` に拡張子が含まれていないとき。
        """
        _, extension = _split_suffix(prefix)
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
            # ``prefix`` に拡張子を含めて渡されたケースも、ファイル名の先頭一致としては
            # 拡張子を除いた stem 部分で照合する（"売上_.xlsx" を渡したら "売上_" で始まるファイル）
            if not path.name.startswith(prefix[: -len(extension)]):
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


def _split_suffix(name: str) -> tuple[str, str]:
    """ファイル名（または ``prefix``）を ``stem`` と拡張子に分ける。拡張子無ければ例外。

    Raises:
        FileSuffixMissingError: 拡張子が無いとき。
    """
    parsed = Path(name)
    extension = parsed.suffix
    if not extension:
        raise FileSuffixMissingError(name)
    return parsed.stem, extension
