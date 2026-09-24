"""tools/build_release.py — リリース用のフォルダと zip を生成するツール。

git のタグで指定した時点のファイルだけを ``git archive`` で取り出し、共有サーバーの
**フォルダコピー（robocopy）** で配布できる形に整えて ``RELEASE.txt`` を添える。

このツールを動かすのは **git のある開発 PC** だけ。配布先（社内 BO・intranet
の共有サーバー）には git が入っていないため、``git archive`` の出力をそのまま
``robocopy /MIR`` でコピーする形になっている。コピーで上書きしてはいけない
**3ファイル**（``comken/toolbox/salesforce/sites/solution.py`` /
``solution_sandbox.py`` / ``comken/services/salesforce_downloader/paths.py``）
は、robocopy の ``/XF`` で送り元（配布用フォルダ）側のフルパスを指定して守る。

## 使い方

::

    python tools\\build_release.py --tag v1.0.0
    python tools\\build_release.py --tag v1.0.0 --dest .\\dist
    python tools\\build_release.py --tag v1.0.0 --server-path "\\\\filesv\\share\\tools\\comken"
    python tools\\build_release.py --force

``--tag`` を省略すると ``comken/__init__.py`` の ``__version__`` から
``v<version>`` を作る（例: ``v1.0.0``）。``--dest`` は既定で ``dist/``
（``.gitignore`` で除外済み）。

``git archive`` は **git が追跡しているファイルだけ** を出力するため、
未コミット・未追跡のファイルはリリース用フォルダにも zip にも入らない。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import io
import logging
import re
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

# スクリプト実行時に tools/ が sys.path 先頭に入る（pyproject.toml の
# pytest.ini_options / pyright.extraPaths 設定により、tools/ はパッケージ
# ルート扱い）。``comken/__init__.py`` を直接読んで既定タグを決めるので、
# リポジトリルートも入れて ``from comken import ...`` を使わずに済ませる
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)


# ── 配布時に上書きしない3ファイル ─────────────────────────────────────────
# git では ``git update-index --skip-worktree`` で守っていたものを、共有
# サーバーに git が無いので robocopy の ``/XF`` で送り元側のフルパスを
# 指定して守る。順不同で3つとも robocopy コマンドに並ぶ。
EXCLUDED_RELATIVE_PATHS: tuple[str, ...] = (
    "comken/toolbox/salesforce/sites/solution.py",
    "comken/toolbox/salesforce/sites/solution_sandbox.py",
    "comken/services/salesforce_downloader/paths.py",
)

# 既定の配布先プレースホルダ。実際に動かすときは ``--server-path`` で
# 共有サーバーのパスを指定する。UNC のバックスラッシュは raw 文字列で持つ
DEFAULT_SERVER_PATH: str = r"\\server\share\tools\comken"


class ReleaseBuildError(RuntimeError):
    """リリース用フォルダ生成で起きた失敗。

    メッセージに「何が起きたか」「次に何をすればよいか」を含める。
    """


@dataclass(frozen=True)
class ReleaseArtifacts:
    """``build_release()`` の戻り値。生成物と robocopy コマンドを束ねる。"""

    folder: Path  # ``dist/comken-<tag>/``
    zip_path: Path  # ``dist/comken-<tag>.zip``
    robocopy_command: str  # 標準出力に表示する配布コマンド
    commit: str  # タグが指すコミットハッシュ


# ── 公開関数 ─────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 引数を解釈する。テストからも ``parse_args([...])`` で呼べる。"""
    parser = argparse.ArgumentParser(
        description=(
            "タグ時点のファイルだけをリリース用フォルダと zip に出力し、"
            "robocopy の配布コマンドを表示する。"
        ),
    )
    parser.add_argument(
        "--tag",
        help=(
            "リリースタグ（例: v1.0.0）。省略時は comken/__init__.py の "
            "__version__ から v<version> を作る"
        ),
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path("dist"),
        help="出力先ディレクトリ（既定: dist）。配下に comken-<tag>/ と zip を作る",
    )
    parser.add_argument(
        "--server-path",
        default=DEFAULT_SERVER_PATH,
        help=(
            "配布先の共有サーバー側パス（UNC）。robocopy コマンドの宛先に使う。"
            f"既定: {DEFAULT_SERVER_PATH}"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存の出力先（comken-<tag>/ と zip）があれば消して作り直す",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
        help="git リポジトリのルート（既定: このツールの親の親）",
    )
    return parser.parse_args(argv)


def default_tag_from_version(repo_root: Path) -> str:
    """``comken/__init__.py`` の ``__version__`` から ``v<version>`` を作る。

    ファイルが見つからない / 値が読めない場合は ``ReleaseBuildError``。

    Args:
        repo_root: リポジトリルート。

    Returns:
        ``v`` プレフィクス付きのタグ名（例: ``v1.0.0``）。

    Raises:
        ReleaseBuildError: ``__version__`` が見つからない・読み取れないとき。
    """
    init_path = repo_root / "comken" / "__init__.py"
    try:
        text = init_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReleaseBuildError(
            f"{init_path} を読み込めません: {exc}リポジトリルートが合っているか確認してください。"
        ) from exc
    match = re.search(
        r"""__version__\s*=\s*['"]([^'"]+)['"]""",
        text,
    )
    if not match:
        raise ReleaseBuildError(
            f"{init_path} から __version__ が見つかりません。"
            "タグの既定値を決められないので --tag で明示してください。"
        )
    return f"v{match.group(1)}"


def build_release(
    *,
    tag: str,
    dest: Path,
    server_path: str,
    force: bool,
    repo_root: Path,
) -> ReleaseArtifacts:
    """タグ時点のファイルから ``dist/comken-<tag>/`` と zip を作るメイン処理。

    処理:

    1. ``git archive --format=tar <tag>`` を ``subprocess`` で実行し、tar の
       バイト列を取得する（``git archive`` は git 管理下のファイルだけ出力する）
    2. ``tarfile`` で読み、``dist/comken-<tag>/`` 配下に展開する
    3. ``RELEASE.txt`` にタグ・コミット・作成日時・``__version__`` を書く
    4. 同じ内容で ``dist/comken-<tag>.zip`` を作る
    5. robocopy コマンド（``/MIR`` + ``/XF`` で3ファイル除外）を組み立てて返す

    Args:
        tag: リリースタグ（例: ``v1.0.0``）。タグの存在と、
            タグ時点の ``__version__`` がタグ番号と一致することは呼び出し前に検証する
        dest: 出力先ディレクトリ（配下に ``comken-<tag>/`` と zip を作る）
        server_path: 配布先パス（robocopy の宛先に使う）
        force: ``True`` なら既存出力を削除して作り直す。``False`` なら既存がある
            時点で ``ReleaseBuildError``
        repo_root: ``git`` を実行するときの作業ディレクトリ

    Returns:
        生成物への参照（フォルダ・zip・robocopy コマンド・コミットハッシュ）。

    Raises:
        ReleaseBuildError: タグが存在しない、``__version__`` がタグ番号と食い違う、
            既存出力が ``--force`` なしにある、git の実行に失敗した、等。
    """
    ensure_git_available()
    repo_root = repo_root.resolve()

    # タグの存在確認（先にやると tar 取得で迷わない）
    tag_commit = tag_commit_for(tag, repo_root)
    tag_version = read_version_at_tag(tag, repo_root)
    expected_version = tag[len("v") :] if tag.startswith("v") else tag
    if tag_version != expected_version:
        raise ReleaseBuildError(
            f"タグ {tag} の __version__ が {tag_version!r} で、タグ番号"
            f" ({expected_version!r}) と一致しません。タグを打つ直前に"
            f" comken/__init__.py の __version__ を更新してから"
            " タグを打ち直してください。"
        )

    dest = dest.resolve()
    folder = dest / f"comken-{tag}"
    zip_path = dest / f"comken-{tag}.zip"
    _check_destinations(folder, zip_path, force=force, dest=dest)

    folder.parent.mkdir(parents=True, exist_ok=True)

    # 1. git archive --format=tar の出力を取得
    archive_bytes = _run_git_bytes("archive", "--format=tar", tag, repo_root=repo_root)

    # 2. tarfile で展開する
    _extract_archive(archive_bytes, folder)

    # 3. RELEASE.txt を書く
    _write_release_txt(
        folder,
        tag=tag,
        commit=tag_commit,
        version=tag_version,
    )

    # 4. zip を作る
    _build_zip(folder, zip_path)

    # 5. robocopy コマンドを組み立てる
    robocopy_command = _build_robocopy_command(folder, server_path)

    return ReleaseArtifacts(
        folder=folder,
        zip_path=zip_path,
        robocopy_command=robocopy_command,
        commit=tag_commit,
    )


def ensure_git_available() -> None:
    """``git --version`` が動くか確認する。無い環境では手元でツールを起動できない。"""
    try:
        subprocess.run(
            ["git", "--version"],
            capture_output=True,
            check=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise ReleaseBuildError(
            "git が見つからないか実行できません。このツールは git の"
            " ある開発 PC で動かす前提です。配布先（共有サーバー）で"
            " 動かすものではありません。"
        ) from exc


def tag_commit_for(tag: str, repo_root: Path) -> str:
    """タグが指すコミットハッシュを返す。タグが無ければ ``ReleaseBuildError``。"""
    try:
        return _run_git(
            "rev-parse", "--verify", "refs/tags/" + tag + "^{}", repo_root=repo_root
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise ReleaseBuildError(
            f"タグ {tag} が見つかりません。git tag -l で存在するタグを 確認してください。"
        ) from exc


def read_version_at_tag(tag: str, repo_root: Path) -> str:
    """タグ時点の ``comken/__init__.py`` から ``__version__`` を読み取る。

    Args:
        tag: タグ名（例: ``v1.0.0``）。
        repo_root: リポジトリルート。

    Returns:
        ``__version__`` の文字列（例: ``"1.0.0"``）。

    Raises:
        ReleaseBuildError: タグが見つからない、またはファイルが読めないとき。
    """
    try:
        content = _run_git(
            "show",
            f"{tag}:comken/__init__.py",
            repo_root=repo_root,
        )
    except subprocess.CalledProcessError as exc:
        raise ReleaseBuildError(
            f"タグ {tag} が見つかりません。git tag -l で存在するタグを 確認してください。"
        ) from exc
    match = re.search(r"""__version__\s*=\s*['"]([^'"]+)['"]""", content)
    if not match:
        raise ReleaseBuildError(
            f"タグ {tag} の comken/__init__.py から __version__ が見つかりません。"
        )
    return match.group(1)


# ── 内部ヘルパー（テストから monkeypatch で差し替えて壊した動作を検証する）


def _run_git(*args: str, repo_root: Path) -> str:
    """git を実行して ``stdout`` の文字列を返す。失敗時は ``CalledProcessError``。

    出力には UTF-8 の日本語を含むため、エンコーディングを明示する
    （Windows 既定の cp932 でデコードに失敗するのを防ぐ）。
    """
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout


def _run_git_bytes(*args: str, repo_root: Path) -> bytes:
    """``git archive`` のようにバイナリ出力を返す git コマンド用。"""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    return result.stdout


def _check_destinations(
    folder: Path,
    zip_path: Path,
    *,
    force: bool,
    dest: Path,
) -> None:
    """出力先が既にあれば止める。``force`` なら ``dest`` の下だけ削除する。

    ``dest`` の外は触らない（共有サーバー上の同名のフォルダを誤って消さないため）。
    """
    if not folder.exists() and not zip_path.exists():
        return
    if not force:
        raise ReleaseBuildError(
            f"{folder} または {zip_path} が既に存在します。"
            " 上書きせずに失敗しました。再生成する場合は --force を"
            " 付けてください（このオプションは dest/ の下だけ消します）。"
        )
    # force: dest の下だけ削除。万一 dest と同じパスが万一渡されても
    # 誤って環境を壊さないよう、dest 自身は消さない
    for target in (folder, zip_path):
        if target.exists() and target.is_relative_to(dest):
            if target.is_dir():
                _rmtree(target)
            else:
                target.unlink()


def _rmtree(path: Path) -> None:
    """``shutil.rmtree`` の薄いラッパー（onerror を明示するため独立）。"""
    import shutil

    shutil.rmtree(path)


def _extract_archive(archive_bytes: bytes, target: Path) -> None:
    """tar のバイト列を ``target`` 配下に展開する。

    Python 3.11 の ``tarfile`` には ``filter="data"`` が無いので、
    ディレクトリトラバーサルを自分で防ぐ。
    """
    target.mkdir(parents=True, exist_ok=False)
    target_resolved = target.resolve()
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as tar:
        for member in tar.getmembers():
            member_path = (target_resolved / member.name).resolve()
            # Windows でも区切りは forward slash で来る（tarfile の仕様）
            if (
                not str(member_path).startswith(str(target_resolved) + "\\")
                and member_path != target_resolved
            ):
                raise ReleaseBuildError(f"アーカイブに不正なパスが含まれています: {member.name}")
        tar.extractall(path=target)


def _write_release_txt(
    target: Path,
    *,
    tag: str,
    commit: str,
    version: str,
) -> None:
    """``RELEASE.txt`` にタグ・コミット・作成日時・``__version__`` を書く。

    配った先で「どの版か」が分かるようにするための正本。
    """
    # 業務日時のため、ローカルタイムゾーン付きで書く（CONVENTIONS.md §17）。
    # ``now()`` は naive を返し、``astimezone()`` を付けるとシステムの
    # ローカルタイムゾーンが乗る
    now_value = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    body = f"tag: {tag}\ncommit: {commit}\nbuilt_at: {now_value}\n__version__: {version}\n"
    (target / "RELEASE.txt").write_text(body, encoding="utf-8")


def _build_zip(folder: Path, zip_path: Path) -> None:
    """``folder`` の中身（``RELEASE.txt`` 含む）を zip に詰める。"""
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                arcname = path.relative_to(folder).as_posix()
                zf.write(path, arcname=arcname)


def _build_robocopy_command(source: Path, server_path: str) -> str:
    """robocopy の配布コマンドを組み立てる。

    ``/MIR`` で宛先を完全同期し、3ファイルを ``/XF`` で除外する。

    **``/XF`` に渡すのは、送り元（配布用フォルダ）側のフルパス。** robocopy は ``/XF`` の
    パスを送り元のファイルと照合するため、宛先（共有サーバー）側のフルパスで書くと
    一致せず、共有サーバーの値がダミー値で上書きされる（2026-09-24 に実際に robocopy で確認）。
    ファイル名だけの指定は、同名の別ファイル（``browser/sites/salesforce/solution.py`` など）
    まで更新されなくなるので使わない。送り元に存在する3ファイルは ``/MIR`` の削除対象にもならず、
    宛先の値のまま残る。
    Windows のパスなので、区切りの ``/`` はバックスラッシュに正規化する。
    """
    source_text = str(source).rstrip("\\").rstrip("/")
    server_text = server_path.rstrip("\\").rstrip("/").replace("/", "\\")
    # f-string 内で ``\`` が使えない（Python 3.11）ため、連結で組み立てる
    excluded_full = [
        '"' + source_text + "\\" + relative.replace("/", "\\") + '"'
        for relative in EXCLUDED_RELATIVE_PATHS
    ]
    parts = [
        "robocopy",
        '"' + source_text + '"',
        '"' + server_text + '"',
        "/MIR",
        "/XF",
        *excluded_full,
    ]
    return " ".join(parts)


# ── main ─────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。タグ指定 → フォルダ/zip 生成 → robocopy コマンド表示。

    配布コマンドと注意事項は ``logger.warning`` で出す（CLI では
    ``logging.basicConfig`` を INFO で初期化するのでコンソールに出る）。
    """
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    tag = args.tag or default_tag_from_version(args.repo_root)

    artifacts = build_release(
        tag=tag,
        dest=args.dest,
        server_path=args.server_path,
        force=args.force,
        repo_root=args.repo_root,
    )

    logger.warning("=" * 70)
    logger.warning("リリース用フォルダを作成しました")
    logger.warning("=" * 70)
    logger.warning("  フォルダ    : %s", artifacts.folder)
    logger.warning("  zip         : %s", artifacts.zip_path)
    logger.warning("  タグ        : %s", tag)
    logger.warning("  コミット    : %s", artifacts.commit)
    logger.warning("")
    logger.warning("配布コマンド（BO 用と intranet 用の両方の共有サーバーで実行）:")
    logger.warning("  > %s", artifacts.robocopy_command)
    logger.warning("")
    logger.warning("注意:")
    logger.warning("  - 利用中でない時間帯に行う")
    logger.warning("  - /MIR は宛先にしか無いファイルを削除する")
    logger.warning("    （除外指定した3ファイルは削除されない）")
    logger.warning("  - 除外した3ファイルは各サーバー側の値のまま残る")
    logger.warning("  - ロールバックは旧タグのフォルダ/zip を同じ手順でコピーする")
    logger.warning("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
