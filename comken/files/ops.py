"""ファイルのコピー・移動と一時ファイル管理。

使い方:
    from comken.files import local_copy

    # NAS ファイルのローカルコピー
    with local_copy(r"\\\\nas-server\\share\\data.xlsx") as path:
        with ExcelFile(path) as f:
            rows = f.read_rows_as_dicts("Sheet1")
"""

import logging
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from ..runtime import dry_run_log, is_dry_run

logger = logging.getLogger(__name__)


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
