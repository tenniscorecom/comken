"""comken/core/files/ops.py — ファイルのコピー・移動、置き場所の取得、一時ファイル管理。"""

import logging
import shutil
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ...runtime import dry_run_log, is_dry_run
from ..timer import measure

logger = logging.getLogger(__name__)


def project_dir() -> Path:
    """実行したスクリプトが置かれているフォルダを返す。

    `python main.py` で動かしたときの `main.py` の場所、つまりプロジェクトの
    ルートを指す。`src/run.py` のような下の階層から呼んでも同じ場所を返す。

    利用側で `Path(__file__).parent` と書かなくて済むようにするためのもの。
    あの書き方はファイルを別の階層へ移した瞬間に指す先が変わるが、
    こちらは呼ぶ場所を選ばない。

    入力元・出力先は config.ini に書くのが基本なので、これが要るのは
    **プロジェクトに同梱したファイルを読む**ような場面に限られる。

    対話実行（REPL）や pytest から呼ぶと、その実行環境の場所を返す。
    バッチとして動かす前提の関数なので、そこは想定していない。

    Returns:
        実行スクリプトのあるフォルダ。
    """
    return Path(sys.argv[0]).resolve().parent


@measure
def copy_to_local_if_large(path: str | Path, threshold_mb: float) -> tuple[Path, Path | None]:
    """ファイルサイズが閾値を超えていればローカルへコピーして、そのパスを返す。

    NAS・ネットワークドライブ上のファイルを openpyxl や win32com が開くときに
    遅い・不安定になる事があり、社内ルールで許可されていればローカルへコピーして
    安定化させる。``threshold_mb=0`` を指定すればコピーせず元のまま返す
    （社内ルールでローカルコピーが禁止されている場合のオプトアウト）。

    返り値は ``(working_path, tmp_path_or_None)``。第2要素が ``None`` 以外の
    ときは呼び出し側がローカルコピーの所有者となり、不要になったら
    ``tmp_path.unlink(missing_ok=True)`` で削除する。
    ``local_copy`` のような ``with`` ブロックでの自動削除はしない
    （openpyxl / win32com は ``close()`` までパスを保持する必要があるため、
    スコープがクラス側に寄る）。

    この関数は ``__all__`` に入れない。利用者が直接呼ぶことは想定せず、
    ExcelBase / ExcelComHandler などクラス側の自動コピールーチンが使う。

    Args:
        path: 元のファイルパス。
        threshold_mb: この値（MB）を**超える**ファイルはコピーする。
                      0 を指定するとコピーしない。

    Returns:
        (working_path, tmp_path_or_None) のタプル。
        コピーしたときは ``(ローカルコピーへのPath, そのPath)``、
        コピーしなかったときは ``(元のパス, None)``。
    """
    src = Path(path)
    if not threshold_mb:
        return src, None
    if src.stat().st_size <= threshold_mb * 1024 * 1024:
        return src, None
    # クラス側に open できる名前（パス）が必要なので NamedTemporaryFile で
    # 名前だけ確保してすぐ閉じ、呼び出し側がパスから開ける状態にする。
    tmp = tempfile.NamedTemporaryFile(suffix=src.suffix, delete=False)  # noqa: SIM115
    tmp_path = Path(tmp.name)
    tmp.close()
    try:
        shutil.copy2(src, tmp_path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            logger.debug(
                "コピー失敗後の一時ファイルを削除できませんでした: %s", tmp_path, exc_info=True
            )
        raise
    return tmp_path, tmp_path


@contextmanager
def local_copy(path: str | Path) -> Iterator[Path]:
    """ネットワーク上のファイルをローカルにコピーし、処理後に自動削除する。

    NAS やネットワークドライブ上の大きなファイルを直接開くと遅い場合や、
    win32com（Excel COM）でネットワークファイルが不安定な場合に使う。

    テンポラリファイルの保存先: C:\\Users\\<ユーザー名>\\AppData\\Local\\Temp\\
    with ブロックを抜けると自動削除される（例外が発生した場合も削除される）。
    Args:
        path: コピー元のファイルパス（ネットワークパス・UNCパス・マップドドライブ）。

    Yields:
        ローカルのテンポラリファイルパス（Path）。
    """
    src = Path(path)
    # NOTE: 呼び出し側がパスから開くため、名前を確保して即座に閉じる。
    tmp = tempfile.NamedTemporaryFile(suffix=src.suffix, delete=False)  # noqa: SIM115
    tmp_path = Path(tmp.name)
    tmp.close()
    try:
        shutil.copy2(src, tmp_path)
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)


@measure
def move_file(src: str | Path, dst: str | Path) -> Path:
    """ファイルを移動する。

    shutil.move の分かりにくい点をなくしたラッパー:
        - dst が既存フォルダなら、その中に同名で移動する
        - それ以外はファイルパスとして扱う（親フォルダがなければ自動作成する）
        - 移動先に同名ファイルがあれば上書きする
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
    if target.exists() and src.samefile(target):
        return target
    try:
        src.replace(target)
    except OSError:
        # os.replace は同一ドライブ内で使うため、移動先と同じフォルダに一時ファイルを作る。
        # NOTE: shutil.copy2 で書くため、一時ファイル名を確保して即座に閉じる。
        tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
            dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False
        )
        tmp_path = Path(tmp.name)
        tmp.close()
        try:
            shutil.copy2(src, tmp_path)
            tmp_path.replace(target)
            src.unlink()
        finally:
            tmp_path.unlink(missing_ok=True)
    return target


@measure
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
    if target.exists() and src.samefile(target):
        return target
    shutil.copy2(src, target)
    return target


def cleanup_stale_tmp(target: str | Path, max_age_seconds: float = 3600) -> None:
    """アトミック書き込みで残った一時ファイルの残骸を削除する（ライブラリ内部用）。

    利用者が呼ぶものではないので `__all__` には入れない。ただし `_` も付けない。
    アトミック書き込みをする側（state / config のスタブ / 認証情報の保存）から
    モジュールを跨いで呼ばれるためで、`_` は「同じモジュールの中だけ」の印だから。
    2026-07-29 に一度 `_cleanup_stale_tmp` へ内部化したが、そのときの理由
    （呼ぶのは config のスタブだけ）は、呼び手が3つに増えた時点で失効した。


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
    # NOTE: ファイルの st_mtime と同じ基準で比較するため time.time() を使う。
    now = time.time()
    for tmp in target.parent.glob(f"{target.name}.*.tmp"):
        try:
            if now - tmp.stat().st_mtime > max_age_seconds:
                tmp.unlink()
        except OSError:
            logger.debug("一時ファイルを削除できませんでした: %s", tmp, exc_info=True)
