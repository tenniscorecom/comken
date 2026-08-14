"""comken/utils/files/finder.py — フォルダ内のファイル検索

使い方は docs/utils-files.md を参照。
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from ...constants import SortBy
from ..clock import today

# ファイル名に含まれる日付らしい数字（20260729 / 2026-07-29 / 2026_07_29 / 2026.07.29）。
# 前後を数字で挟まれたものは日付とみなさない（社員番号・伝票番号の一部を拾わないため）
_DATE_IN_NAME = re.compile(r"(?<!\d)([0-9]{4})([-_.]?)([0-9]{2})\2([0-9]{2})(?!\d)")


class FileFinder:
    """フォルダからファイルを探して取得する。

    見つからないときは既定で FileNotFoundError を投げる
    （業務スクリプトでは「ファイルがない＝処理を止める」がほとんどのため）。
    処理を続けたい場合は required=False を指定すると None または空リストを返す。
    """

    def __init__(self, folder: str | Path) -> None:
        self._folder = Path(folder)

    def today(
        self,
        pattern: str = "*.xlsx",
        date_format: str = "%Y%m%d",
        required: bool = True,
    ) -> Path | None:
        """ファイル名に今日の日付を含むファイルを返す。

        複数ある場合は更新日時が最も新しいもの。年月で探すなら date_format="%Y%m"。

        Raises:
            FileNotFoundError: required=True で該当ファイルがない場合。
        """
        today_text = today().strftime(date_format)
        matched = [p for p in self._folder.glob(pattern) if p.is_file() and today_text in p.name]
        if not matched:
            if required:
                raise FileNotFoundError(
                    f"今日の日付（{today_text}）を含むファイルが見つかりません: "
                    f"{self._folder}\\{pattern}"
                )
            return None
        return max(matched, key=lambda p: p.stat().st_mtime)

    def latest(
        self,
        pattern: str = "*.xlsx",
        by: str = SortBy.NAME,
        required: bool = True,
    ) -> Path | None:
        """最新のファイルを返す。既定はファイル名の辞書順で最後のもの。

        "20260711_売上.xlsx" のような日付プレフィックス命名を想定しており、
        コピーや再保存で更新日時が変わっても影響を受けない。

        注意: 文字列比較のため、ゼロ埋めしていない連番（report_9 と report_10）は
        9 の方が「最新」と判定される。連番命名なら by=SortBy.UPDATED を使うこと。

        Raises:
            FileNotFoundError: required=True で該当ファイルがない場合。
            ValueError: by に SortBy.NAME / SortBy.UPDATED 以外を指定した場合。
        """
        if by not in (SortBy.NAME, SortBy.UPDATED):
            raise ValueError(f"by には SortBy.NAME か SortBy.UPDATED を指定してください: {by}")

        files = [path for path in self._folder.glob(pattern) if path.is_file()]
        if not files:
            if required:
                raise FileNotFoundError(f"ファイルが見つかりません: {self._folder}\\{pattern}")
            return None
        if by == SortBy.UPDATED:
            return max(files, key=lambda p: p.stat().st_mtime)
        return max(files, key=lambda p: p.name)

    def dated(self, pattern: str = "*.xlsx", required: bool = True) -> list[Path]:
        """ファイル名に日付が入っているファイルを、日付の新しい順で返す。

        日付として認識するのは 20260729 / 2026-07-29 / 2026_07_29 / 2026.07.29。
        実在しない日付や、前後を数字で挟まれた数字（伝票番号の一部など）は対象外。
        同じ日付なら更新日時の新しい順。詳しくは date_in_name を参照。

        Raises:
            FileNotFoundError: required=True で該当ファイルがない場合。
        """
        dated_files = []
        for path in self._folder.glob(pattern):
            if not path.is_file():
                continue
            date = date_in_name(path.name)
            if date is not None:
                dated_files.append((date, path))

        if not dated_files:
            if required:
                raise FileNotFoundError(
                    f"日付が入ったファイルが見つかりません: {self._folder}\\{pattern}\n"
                    "ファイル名に 20260729 や 2026-07-29 のような日付が"
                    "含まれているか確認してください。"
                )
            return []

        dated_files.sort(key=lambda pair: (pair[0], pair[1].stat().st_mtime), reverse=True)
        return [path for _, path in dated_files]


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
