"""
utils/files/archive.py — zip 圧縮・展開ユーティリティ

標準ライブラリのみで動く。Windows のエクスプローラーで作られた zip
（日本語ファイル名が cp932 で入っている）も文字化けせずに展開できる。

使い方:
    from comken.utils.files import unzip, zip_files, zip_folder

    # フォルダごと圧縮（出力先を省略すると隣に「フォルダ名.zip」）
    zip_folder(r"C:\\作業\\reports")                        # → C:\\作業\\reports.zip
    zip_folder(r"C:\\作業\\reports", r"C:\\作業\\backup.zip")

    # ファイルを選んで圧縮
    zip_files(["a.xlsx", "b.csv"], r"C:\\作業\\提出用.zip")

    # 展開（出力先を省略すると隣に同名フォルダ）
    unzip(r"C:\\作業\\data.zip")                            # → C:\\作業\\data\\
    unzip(r"C:\\作業\\data.zip", r"C:\\作業\\展開先")
"""

import logging
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path

from ..timer import measure

logger = logging.getLogger(__name__)

# zip エントリのファイル名が UTF-8 で格納されていることを示すフラグ（general purpose bit 11）
_ZIP_UTF8_FLAG = 0x800


@measure
def zip_folder(folder: str | Path, dst: str | Path | None = None) -> Path:
    """フォルダの中身をまるごと zip に圧縮する（サブフォルダも含む）。

    Args:
        folder: 圧縮するフォルダ。
        dst: 出力する zip のパス。省略するとフォルダの隣に「フォルダ名.zip」。
             親フォルダがなければ自動作成される。既存の zip は上書きされる。

    Returns:
        作成した zip のパス。

    Raises:
        FileNotFoundError: folder が存在しない場合。
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"フォルダが見つかりません: {folder}")
    dst = Path(dst) if dst else folder.parent / f"{folder.name}.zip"
    dst.parent.mkdir(parents=True, exist_ok=True)

    # NOTE: os.replace を確実に使えるよう、一時ファイルは出力先と同じフォルダに作る。
    # NOTE: アーカイバがパスへ書けるよう、名前を確保して即座に閉じる。
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
        dir=dst.parent, suffix=".tmp", delete=False
    )
    tmp_path = Path(tmp.name)
    tmp.close()
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(folder.rglob("*")):
                if (
                    path.is_file()
                    and path.resolve() != dst.resolve()
                    and path.resolve() != tmp_path.resolve()
                ):
                    zf.write(path, path.relative_to(folder))
        tmp_path.replace(dst)
    finally:
        tmp_path.unlink(missing_ok=True)
    return dst


def zip_files(files: Sequence[str | Path], dst: str | Path) -> Path:
    """ファイルを選んで zip に圧縮する（zip 内はフラットに並ぶ）。

    Args:
        files: 圧縮するファイルパスのリスト。
        dst: 出力する zip のパス。親フォルダがなければ自動作成される。

    Returns:
        作成した zip のパス。

    Raises:
        FileNotFoundError: files の中に存在しないファイルがある場合。
        ValueError: zip 内で同じ名前になるファイルが複数ある場合。
    """
    paths = [Path(file) for file in files]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"ファイルが見つかりません: {path}")

    names = [path.name.casefold() for path in paths]
    duplicated = sorted({path.name for path in paths if names.count(path.name.casefold()) > 1})
    if duplicated:
        raise ValueError(
            f"zip の中で同じ名前になるファイルが複数あります: {', '.join(duplicated)}\n"
            "そのまま圧縮すると片方が消えるため、ファイル名を変えるか、"
            "フォルダごと zip_folder で圧縮してください。"
        )

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    # NOTE: os.replace を確実に使えるよう、一時ファイルは出力先と同じフォルダに作る。
    # NOTE: アーカイバがパスへ書けるよう、名前を確保して即座に閉じる。
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
        dir=dst.parent, suffix=".tmp", delete=False
    )
    tmp_path = Path(tmp.name)
    tmp.close()
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in paths:
                zf.write(path, path.name)
        tmp_path.replace(dst)
    finally:
        tmp_path.unlink(missing_ok=True)
    return dst


@measure
def unzip(src: str | Path, dst: str | Path | None = None) -> Path:
    """zip を展開する。

    Windows のエクスプローラーで作られた zip（ファイル名が cp932）も
    文字化けせずに展開できる（UTF-8 の zip はそのまま正しく読まれる）。

    Args:
        src: 展開する zip のパス。
        dst: 展開先フォルダ。省略すると zip の隣に同名フォルダ（data.zip → data\\）。
             同名ファイルがあれば上書きされる。

    Returns:
        展開先フォルダのパス。
    """
    src = Path(src)
    dst = Path(dst) if dst else src.with_suffix("")
    dst.mkdir(parents=True, exist_ok=True)

    if sys.version_info >= (3, 11):
        # metadata_encoding は Python 3.11 で追加。
        # UTF-8 フラグのないエントリ（Windows 製 zip）にだけ効く
        with zipfile.ZipFile(src, metadata_encoding="cp932") as zf:
            zf.extractall(dst)
    else:
        # 3.10 以前は metadata_encoding が無いため、ファイル名を自前で cp932 に直して展開する
        _extract_cp932(src, dst)
    return dst


def _extract_cp932(src: Path, dst: Path) -> None:
    """Windows 製 zip（ファイル名が cp932）を Python 3.10 以前でも文字化けせず展開する。

    UTF-8 フラグのないエントリのファイル名は、zipfile が cp437 で復元して保持している。
    これを cp437 → cp932 に戻すと元の日本語名になる（metadata_encoding="cp932" と同じ結果）。
    """
    dst_resolved = dst.resolve()
    with zipfile.ZipFile(src) as zf:
        for info in zf.infolist():
            name = info.filename
            if not info.flag_bits & _ZIP_UTF8_FLAG:
                name = name.encode("cp437").decode("cp932", errors="replace")
            target = dst / name
            # Zip Slip 対策: 展開先フォルダの外を指すエントリはスキップする
            # （3.11+ の extractall は Python 側で無害化されるが、この自前展開では自分で守る）
            if not target.resolve().is_relative_to(dst_resolved):
                logger.warning("展開先の外を指すエントリをスキップしました: %s", info.filename)
                continue
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as fsrc, target.open("wb") as fdst:
                shutil.copyfileobj(fsrc, fdst)
