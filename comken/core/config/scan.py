"""comken/core/config/scan.py — プロジェクト側のソースから config の参照を集める。

``python -m comken config --check`` から呼ばれる補助モジュール。
「``main.py`` の ``config.require()`` と ``src/**/*.py`` の ``config.SECTION.KEY``
と ``config.ini`` が食い違っていないか」を **AST で** 静的に突き合わせるための
検出器。**コードを実行しない（副作用なし）**。

防いでいる事故:

| 事故 | 何が起きるか |
|---|---|
| ``config.X.Y`` を追加したが ini に書き忘れた | 実行時に ``ConfigKeyNotFoundError`` |
| ini からセクションを消した | 実行時に遠いところで ``ConfigSectionNotFoundError`` |
| ``require()`` のリストが古い | 足りない項目でも起動時に止まらない |
| セクション名・キー名を **使う側で書き間違えた** | 実行時まで気付かない |

**動的アクセスは拾えない。** ``getattr(config, "FOO")`` のように名前を実行時に
組み立てる書き方は AST からは追えない。``config.ini`` の項目数は数十個に
収まる想定で、動的アクセスは通常使わないので、漏れは docstring で案内する。

**``from comken import config`` かどうかは確認しない。** ``config.X.Y`` の形で
書かれていれば拾う。``other.FILES.KEY`` のような別名経由は名前 ``config`` で
ない限り拾えないので、誤検出しても「config.ini に無い」と表示されるだけで
実害が小さい（**値そのものは絶対に出さない**ので情報漏洩にもならない）。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# 走査対象のルートとスキップするディレクトリの名前。
# 雛形プロジェクトのレイアウトを前提にする:
# ``main.py`` がプロジェクトのルートに置かれ、``src/`` 配下に本体が来る。
# ``.venv`` / ``__pycache__`` / ``typings`` は実行環境・生成物なので走査しない。
# ``tests`` はテストプロジェクト側のコードで、本体プロジェクトの ``config.ini``
# とは独立しているため走査しない。
_TARGET_FILES_AT_ROOT: tuple[str, ...] = ("main.py",)
_TARGET_GLOB = "src/**/*.py"
_SKIP_DIR_NAMES: frozenset[str] = frozenset(
    {".venv", "__pycache__", "typings", "tests", ".git", ".ruff_cache", ".pytest_cache"}
)


@dataclass(frozen=True)
class UsageHit:
    """コード中で見つかった ``config.SECTION.KEY`` の 1 件。

    Attributes:
        path: 見つかったファイル（プロジェクトルートからの相対パス）。
        line: 1 始まりの行番号。
        section: ``SECTION`` 部分（**キーまで指定していない** ``config.SECTION`` は含めない）。
        key: ``KEY`` 部分。
    """

    path: Path
    line: int
    section: str
    key: str


@dataclass(frozen=True)
class RequireHit:
    """コード中で見つかった ``config.require(...)`` の 1 件。

    Attributes:
        path: 見つかったファイル（プロジェクトルートからの相対パス）。
        line: 1 始まりの行番号。
        name: ``require()`` に渡された ``"SECTION.KEY"`` 文字列。
            **AST の引数がリテラルでない場合はこのオブジェクトが作られない**
            （動的な ``require(key)`` は拾えない）。
            1 つの ``require(...)`` 呼び出しで複数の文字列リテラルが
            渡された場合はリテラルごとに 1 件ずつ作る。
    """

    path: Path
    line: int
    name: str


@dataclass(frozen=True)
class ProjectScan:
    """プロジェクト側のソースから集めた結果。

    Attributes:
        root: 走査したプロジェクトのルート（= ``config.ini`` のあるフォルダ）。
        usages: ``config.SECTION.KEY`` の使用箇所（**値そのものは載せない**）。
        requires: ``config.require("SECTION.KEY")`` に書かれている項目。
    """

    root: Path
    usages: tuple[UsageHit, ...]
    requires: tuple[RequireHit, ...]

    @property
    def used_names(self) -> set[str]:
        """使われている ``SECTION.KEY`` 集合（大文字に揃えたもの）。"""
        return {f"{u.section.upper()}.{u.key.upper()}" for u in self.usages}

    @property
    def required_names(self) -> set[str]:
        """``require()`` に書かれている ``SECTION.KEY`` 集合（大文字に揃えたもの）。"""
        return {r.name.upper() for r in self.requires}


def collect_scan_targets(root: Path) -> list[Path]:
    """走査対象の Python ファイルを並べる。

    ルート直下の ``main.py`` と ``src/**/*.py`` を集める。``.venv`` や
    ``__pycache__`` などは除外する。**該当が無ければ空リストを返す**
    （config.ini 単独で使うプロジェクトでも ``--check`` が動くように）。

    Args:
        root: プロジェクトのルート。

    Returns:
        ルートからの相対パスで整列した Python ファイルのリスト。
    """
    root = root.resolve()
    found: list[Path] = []
    for name in _TARGET_FILES_AT_ROOT:
        candidate = root / name
        if candidate.is_file():
            found.append(candidate)
    src_dir = root / "src"
    if src_dir.is_dir():
        for path in sorted(src_dir.rglob("*.py")):
            if not _is_inside_skipped(path, src_dir):
                found.append(path)
    # 表示と安定ソートのため相対パスで整列
    return sorted(set(found), key=lambda p: str(p.relative_to(root)).replace("\\", "/"))


def _is_inside_skipped(path: Path, root: Path) -> bool:
    """``path`` がスキップ対象ディレクトリ配下にあるか。

    Args:
        path: 判定対象のファイル。
        root: 走査の起点（``src/`` など）。

    Returns:
        スキップすべきなら True。
    """
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return any(part in _SKIP_DIR_NAMES for part in relative.parts)


def scan_project(root: Path) -> ProjectScan:
    """プロジェクト全体を走査し、``config`` への参照を集める。

    Args:
        root: プロジェクトのルート（``config.ini`` のあるフォルダ）。

    Returns:
        走査結果。**該当するファイルが無ければ ``usages`` / ``requires``
        が空のまま返る**（呼び出し側で「節を出さない」処理に使う）。
    """
    root = root.resolve()
    usages: list[UsageHit] = []
    requires: list[RequireHit] = []
    for file_path in collect_scan_targets(root):
        _scan_one(file_path, root, usages, requires)
    return ProjectScan(
        root=root,
        usages=tuple(usages),
        requires=tuple(requires),
    )


def _scan_one(
    file_path: Path,
    root: Path,
    usages: list[UsageHit],
    requires: list[RequireHit],
) -> None:
    """1 ファイル分の AST 解析。検出結果は ``usages`` / ``requires`` に追加する。

    構文エラー（中途半端な Python ファイル）は **走査全体では無視** する。
    そのファイルの結果は落ちるが、``--check`` の目的は config.ini の診断なので、
    1 ファイルの構文エラーで全体が止まると別の事故を見落とす。
    """
    try:
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # バイナリ読み取り不能・非 UTF-8 は走査側からはスキップ（実行時の import が止める）
        return
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return
    relative = file_path.relative_to(root)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            section, key = _as_config_section_key(node)
            if section and key:
                usages.append(UsageHit(relative, node.lineno, section, key))
        elif isinstance(node, ast.Call):
            names = _as_config_require_call(node)
            for name in names:
                requires.append(RequireHit(relative, node.lineno, name))


def _as_config_section_key(node: ast.Attribute) -> tuple[str | None, str | None]:
    """``config.SECTION.KEY`` の AST ノードなら ``(SECTION, KEY)`` を返す。

    判定基準: ``node`` が ``Attribute`` で ``node.value`` も ``Attribute``、
    さらにその ``value`` が ``Name(id="config")``。それ以外は ``(None, None)``。
    ``config.SECTION``（キーまで無い）や ``other.FILES.KEY`` は拾わない。

    Args:
        node: AST の ``Attribute`` ノード。

    Returns:
        ``(SECTION, KEY)``。該当しなければ ``(None, None)``。
    """
    value = node.value
    if not isinstance(value, ast.Attribute):
        return (None, None)
    base = value.value
    if not isinstance(base, ast.Name) or base.id != "config":
        return (None, None)
    # SECTION は大文字強制（ConfigLowerCaseNameError で実行時に止まる）だが、
    # AST 側は表記そのままを拾う。大文字小文字の差は呼び出し側で揃える。
    return (value.attr, node.attr)


def _as_config_require_call(node: ast.Call) -> list[str]:
    """``config.require("A.B", "C.D")`` の各文字列引数を返す。

    判定基準: ``node.func`` が ``Attribute`` で ``node.func.value`` が
    ``Name(id="config")``、``node.func.attr == "require"``。**引数が
    文字列リテラルでないものはスキップ**（変数を組み立てる動的 ``require``
    は追えない）。空リストなら「``config.require(...)`` ではない、または
    文字列引数がない」。

    Args:
        node: AST の ``Call`` ノード。

    Returns:
        拾った ``SECTION.KEY`` 文字列のリスト。
    """
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "require":
        return []
    base = func.value
    if not isinstance(base, ast.Name) or base.id != "config":
        return []
    return [
        arg.value
        for arg in node.args
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
    ]
