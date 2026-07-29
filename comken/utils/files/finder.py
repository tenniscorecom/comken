"""フォルダ内のファイル検索。

使い方:
    from comken.utils.files import FileFinder

    FileFinder(r"\\\\nas\\share").today()      # → 今日の日付を含むファイル
    FileFinder(r"\\\\nas\\share").latest()     # → 最も新しい .xlsx ファイル
"""

import datetime
from pathlib import Path

from ...constants import SortBy


class FileFinder:
    """フォルダからファイルを探して取得する。

    見つからない場合はデフォルトで FileNotFoundError を投げる
    （業務スクリプトでは「ファイルがない＝処理を止める」がほとんどのため）。
    「なければ None で続行したい」場合は required=False を指定する。

    使い方:
        path = FileFinder(r"\\\\nas\\share").today()          # 今日の日付を含むファイル
        path = FileFinder(r"\\\\nas\\share").latest("*.csv")  # 最新の CSV

        # 見つからなくても処理を続けたい場合
        path = FileFinder(r"\\\\nas\\share").today(required=False)
        if path is None:
            ...  # スキップ処理など
    """

    def __init__(self, folder: str | Path) -> None:
        """
        Args:
            folder: 検索するフォルダのパス。
        """
        self._folder = Path(folder)

    def today(
        self,
        pattern: str = "*.xlsx",
        date_format: str = "%Y%m%d",
        required: bool = True,
    ) -> Path | None:
        """ファイル名に今日の日付を含むファイルを返す。

        該当ファイルが複数ある場合は更新日時が最も新しいものを返す。

        Args:
            pattern: ファイルのパターン（デフォルト: "*.xlsx"）。
            date_format: 日付フォーマット（デフォルト: "%Y%m%d"。年月で探すなら "%Y%m"）。
            required: True（デフォルト）なら見つからないとき FileNotFoundError。
                      False なら None を返す。

        Raises:
            FileNotFoundError: required=True で該当ファイルがない場合。
        """
        today = datetime.date.today().strftime(date_format)
        matched = [p for p in self._folder.glob(pattern) if p.is_file() and today in p.name]
        if not matched:
            if required:
                raise FileNotFoundError(
                    f"今日の日付（{today}）を含むファイルが見つかりません: "
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
        """最新のファイルを返す。

        デフォルトは**ファイル名の辞書順で最後**のもの
        （"20260711_売上.xlsx" のような日付プレフィックス命名で「名前上の最新」を取る用途）。
        コピーや再保存で更新日時が変わっていても影響を受けない。
        更新日時で選びたい場合は by=SortBy.UPDATED を指定する。

        注意: 文字列比較のため、ゼロ埋めしていない連番（report_9.xlsx と report_10.xlsx）は
        9 の方が「最新」と判定される。連番命名なら by=SortBy.UPDATED を使うこと。

        Args:
            pattern: ファイルのパターン（デフォルト: "*.xlsx"）。
            by: SortBy.NAME（ファイル名順・デフォルト）または SortBy.UPDATED（更新日時順）。
            required: True（デフォルト）なら見つからないとき FileNotFoundError。
                      False なら None を返す。

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
