"""comken/toolbox/csv/writer.py — CSV 書き込みユーティリティ

CsvWriter クラスを通じて CSV ファイルへの書き込みを行う。
"""

import csv
import io
import logging
import tempfile
from pathlib import Path

from comken.constants import Encoding
from comken.core.timer import measure
from comken.runtime import dry_run_log, is_dry_run
from comken.toolbox.csv.base import CsvBase

logger = logging.getLogger(__name__)


def _needs_header(path: Path) -> bool:
    """追記の前に見出し行を書く必要があるか返す。

    ファイルが無いときだけでなく、中身が空のときも見出しが要る。
    前回の実行が途中で落ちて0バイトのファイルが残ると、
    見出しの無い CSV に追記され、後で読んだときに1行目がデータ扱いになる。
    """
    return not path.exists() or path.stat().st_size == 0


class CsvWriter(CsvBase):
    """CSV ファイルへの書き込みユーティリティ。"""

    def __init__(
        self,
        path: str | Path,
        fieldnames: list[str],
        encoding: str = Encoding.UTF8_SIG,
    ) -> None:
        """
        Args:
            path: 書き込み先の CSV ファイルパス。親フォルダがなければ書き込み時に自動作成される。
            fieldnames: ヘッダー行の列名リスト。書き込み順に影響する。
            encoding: 文字コード。Excel で開く場合は Encoding.UTF8_SIG（デフォルト）。
                      Shift-JIS が必要な場合は Encoding.CP932 を指定する。
                      Encoding.AUTO は自動判定できない（読み込み専用）ため UTF8_SIG として扱う。
        """
        # AUTO は読み込み時の自動判定用。書き込みではデフォルトの UTF8_SIG に揃える
        # （CsvReader と同じ定数を渡し回しても落ちないようにする）
        if encoding == Encoding.AUTO:
            encoding = Encoding.UTF8_SIG
        super().__init__(path, encoding)
        self._fieldnames = fieldnames

    def _open(self, mode: str):
        """親フォルダを作ってからファイルを開く（ExcelWriter.save と挙動を揃える）。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        return self._path.open(mode, encoding=self._encoding, newline="")

    def _warn_unknown_keys(self, rows: list[dict]) -> None:
        """fieldnames にないキーがあれば警告する（黙って列が欠落するのを防ぐ）。

        extrasaction="ignore" は fieldnames 外のキーを無言で捨てるため、
        列名の typo やソース変更に気づけるよう1回だけ警告を出す。
        """
        known = set(self._fieldnames)
        for row in rows:
            unknown = [k for k in row if k not in known]
            if unknown:
                logger.warning(
                    "fieldnames にないキーは書き込まれません: %s（fieldnames: %s）",
                    unknown,
                    self._fieldnames,
                )
                return  # 全行で同じ構造のことが多いので1回警告すれば十分

    def _validate_encoding(self, rows: list[dict]) -> None:
        """追記内容を対象文字コードへ変換できることをファイル操作前に確認する。"""
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=self._fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        buffer.getvalue().encode(self._encoding)

    @measure
    def write_rows(self, rows: list[dict]) -> None:
        """ファイルを新規作成（または上書き）して全行を書き込む。

        既存ファイルがある場合は上書きされる。

        Args:
            rows: 書き込む行のリスト（辞書のリスト）。
        """
        self._warn_unknown_keys(rows)
        logger.debug("CSV書き込み開始: %s 件数=%d", self._path, len(rows))
        if is_dry_run():
            dry_run_log("CSV に %d 行書き込み（上書き）: %s", len(rows), self._path)
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # os.replace は同一ドライブ内で使うため、出力先と同じフォルダに一時ファイルを作る。
        # NOTE: CSV を別の open で書くため、一時ファイル名を確保して即座に閉じる。
        tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
            dir=self._path.parent, prefix=f".{self._path.name}.", suffix=".tmp", delete=False
        )
        tmp_path = Path(tmp.name)
        tmp.close()
        try:
            with tmp_path.open("w", encoding=self._encoding, newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self._fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            tmp_path.replace(self._path)
            logger.debug("CSV書き込み完了: %s 件数=%d", self._path, len(rows))
        finally:
            tmp_path.unlink(missing_ok=True)

    @measure
    def append_row(self, row: dict) -> None:
        """既存ファイルの末尾に1行追記する。

        ファイルが存在しない場合はヘッダー付きで新規作成する。

        Args:
            row: 追記する行の辞書。

        Notes:
            複数の PC から同じ CSV へ同時に追記する使い方は想定していない。
        """
        self._warn_unknown_keys([row])
        if is_dry_run():
            dry_run_log("CSV に 1 行追記: %s", self._path)
            return
        self._validate_encoding([row])
        is_new = _needs_header(self._path)
        with self._open("a") as f:
            writer = csv.DictWriter(f, fieldnames=self._fieldnames, extrasaction="ignore")
            if is_new:
                writer.writeheader()
            writer.writerow(row)

    @measure
    def append_rows(self, rows: list[dict]) -> None:
        """既存ファイルの末尾に複数行追記する。

        ファイルが存在しない場合はヘッダー付きで新規作成する。

        Args:
            rows: 追記する行のリスト（辞書のリスト）。

        Notes:
            複数の PC から同じ CSV へ同時に追記する使い方は想定していない。
        """
        self._warn_unknown_keys(rows)
        if is_dry_run():
            dry_run_log("CSV に %d 行追記: %s", len(rows), self._path)
            return
        self._validate_encoding(rows)
        is_new = _needs_header(self._path)
        with self._open("a") as f:
            writer = csv.DictWriter(f, fieldnames=self._fieldnames, extrasaction="ignore")
            if is_new:
                writer.writeheader()
            writer.writerows(rows)
