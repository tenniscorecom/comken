"""
utils/file.py — ファイル操作ユーティリティ

使い方:
    from comken.utils import FileFinder, local_copy

    # NAS ファイルのローカルコピー
    with local_copy(r"\\\\nas-server\\share\\data.xlsx") as path:
        with ExcelFile(path) as f:
            rows = f.read_rows_as_dicts("Sheet1")

    # フォルダからファイルを取得
    FileFinder(r"\\\\nas\\share").today()      # → 今日の日付を含むファイル
    FileFinder(r"\\\\nas\\share").latest()     # → 最も新しい .xlsx ファイル

"""

import datetime
import logging
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from ..const import SortBy
from ..runtime import dry_run_log, is_dry_run

logger = logging.getLogger(__name__)


class Paths:
    """よく使うフォルダのパスを返すユーティリティ。インスタンス化せず静的メソッドで使う。

    Desktop / Downloads は OneDrive の「既知のフォルダーの移動」で
    C:\\Users\\xxx 直下にないことがあるため、レジストリから実際の場所を取得する。

    使い方:
        from comken.utils import Paths

        Paths.downloads()   # → C:\\Users\\xxx\\Downloads
        Paths.desktop()     # → C:\\Users\\xxx\\OneDrive\\Desktop（リダイレクトされている場合）
        Paths.temp_dir()    # → C:\\Users\\xxx\\AppData\\Local\\Temp
    """

    @staticmethod
    def downloads() -> Path:
        """ダウンロードフォルダのパスを返す。"""
        return _shell_folder(_DOWNLOADS_GUID, Path.home() / "Downloads")

    @staticmethod
    def desktop() -> Path:
        """デスクトップのパスを返す（OneDrive リダイレクトにも追従する）。"""
        return _shell_folder("Desktop", Path.home() / "Desktop")

    @staticmethod
    def temp_dir() -> Path:
        """システムの一時フォルダのパスを返す。"""
        return Path(tempfile.gettempdir())


@contextmanager
def local_copy(path: str | Path):
    """ネットワーク上のファイルをローカルにコピーし、処理後に自動削除する。

    NAS やネットワークドライブ上の大きなファイルを直接開くと遅い場合や、
    win32com（Excel COM）でネットワークファイルが不安定な場合に使う。

    テンポラリファイルの保存先: C:\\Users\\<ユーザー名>\\AppData\\Local\\Temp\\
    with ブロックを抜けると自動削除される（例外が発生した場合も削除される）。

    使い方:
        with local_copy(r"\\\\nas-server\\share\\data.xlsx") as local_path:
            with ExcelFile(local_path) as f:
                rows = f.read_rows_as_dicts("Sheet1")

    Args:
        path: コピー元のファイルパス（ネットワークパス・UNCパス・マップドドライブ）。

    Yields:
        ローカルのテンポラリファイルパス（Path）。
    """
    src = Path(path)
    tmp = tempfile.NamedTemporaryFile(suffix=src.suffix, delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    try:
        shutil.copy2(src, tmp_path)
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)


def move_file(src: str | Path, dst: str | Path) -> Path:
    """ファイルを移動する。

    shutil.move の分かりにくい点をなくしたラッパー:
        - dst が既存フォルダなら、その中に同名で移動する
        - それ以外はファイルパスとして扱う（親フォルダがなければ自動作成する）
        - 移動先に同名ファイルがあれば上書きする

    使い方:
        move_file("report.xlsx", r"C:\\作業\\output")               # フォルダの中へ
        move_file("report.xlsx", r"C:\\作業\\output\\売上.xlsx")     # 名前を変えて移動

    Args:
        src: 移動するファイルのパス。
        dst: 移動先（フォルダ、またはファイルパス）。

    Returns:
        移動後のファイルパス。
    """
    src = Path(src)
    dst = Path(dst)
    target = dst / src.name if dst.is_dir() else dst
    if is_dry_run():
        dry_run_log("ファイルを移動: %s → %s", src, target)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    shutil.move(str(src), str(target))
    return target


def copy_file(src: str | Path, dst: str | Path) -> Path:
    """ファイルをコピーする（更新日時などの属性も保持する）。

    ルールは move_file と同じ:
        - dst が既存フォルダなら、その中に同名でコピーする
        - それ以外はファイルパスとして扱う（親フォルダがなければ自動作成する）
        - コピー先に同名ファイルがあれば上書きする

    Args:
        src: コピーするファイルのパス。
        dst: コピー先（フォルダ、またはファイルパス）。

    Returns:
        コピー後のファイルパス。
    """
    src = Path(src)
    dst = Path(dst)
    target = dst / src.name if dst.is_dir() else dst
    if is_dry_run():
        dry_run_log("ファイルをコピー: %s → %s", src, target)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    return target


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
        matched = [p for p in self._folder.glob(pattern) if today in p.name]
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

        files = list(self._folder.glob(pattern))
        if not files:
            if required:
                raise FileNotFoundError(f"ファイルが見つかりません: {self._folder}\\{pattern}")
            return None
        if by == SortBy.UPDATED:
            return max(files, key=lambda p: p.stat().st_mtime)
        return max(files, key=lambda p: p.name)


# ── 内部ヘルパー ──────────────────────────────────────────────────────────────


def cleanup_stale_tmp(target: str | Path, max_age_seconds: float = 3600) -> None:
    """アトミック書き込みで残った一時ファイルの残骸を削除する（ライブラリ内部用）。

    アトミック書き込み（一時ファイル + os.replace）は、置換直前にプロセスが
    強制終了すると「target名.<PID>.tmp」が残ることがある。
    次回の書き込み時にこれを呼んで、古い残骸だけ片付ける。

    max_age_seconds より新しいものは、並行実行中の別プロセスが
    書き込み中の可能性があるため消さない（一時ファイルの寿命はミリ秒単位なので、
    1時間残っていれば確実にクラッシュの残骸）。

    Args:
        target: アトミック書き込みの対象ファイル（例: src/config.pyi）。
        max_age_seconds: これより古い一時ファイルだけ削除する（デフォルト: 1時間）。
    """
    target = Path(target)
    now = time.time()
    for tmp in target.parent.glob(f"{target.name}.*.tmp"):
        try:
            if now - tmp.stat().st_mtime > max_age_seconds:
                tmp.unlink()
        except OSError:
            pass  # 他プロセスが使用中・権限なし等。次回の実行でまた試みる


# レジストリ「User Shell Folders」の Downloads の値名（固定 GUID）
_DOWNLOADS_GUID = "{374DE290-123F-4565-9164-39C4925E467B}"


def _shell_folder(value_name: str, default: Path) -> Path:
    """Windows の特殊フォルダの実際の場所をレジストリから取得する。

    OneDrive の「既知のフォルダーの移動」やユーザーによる場所変更で
    Desktop / Downloads が C:\\Users\\xxx 直下にないことがあるため、
    Path.home() 決め打ちではなくレジストリを見る。取得できなければ default を返す。
    """
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            raw, _ = winreg.QueryValueEx(key, value_name)
        return Path(os.path.expandvars(raw))
    except (OSError, ImportError):
        return default
