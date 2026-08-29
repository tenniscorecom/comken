"""comken/core/config/stubs.py — config.ini からエディタ補完用スタブ（.pyi）を生成する

Config の属性（config.SECTION.KEY）は config.ini から実行時に動的に作られるため、
そのままではエディタが補完できない。ここで config.ini の内容を型付きの .pyi に書き出し、
補完を効かせる。設定値の読み込みとはモジュール内で責務を分けている。

- ``Config(path)`` を呼ぶと**同じパスにつきプロセス内で 1 回**だけ ``update_stub()``
  が自動で走る。 ``Config`` は ``Path.resolve()`` 後の絶対パスをキーに
  ``functools.lru_cache`` で構築結果を共有するので、 ``Config(path)`` /
  ``from comken import config`` どちらの経路でも、 同じパスは 1 度しか
  スタブ更新が走らない（ループ内で ``config.SECTION.KEY`` を呼ぶたびに
  スタブ書き込みが走る問題を避ける）。
- ``_write_stub_atomic`` は内容が既存ファイルと同じならディスクに触らないため、
  連続呼び出しの disk I/O は発生しない
- コードを書く前に手動で作りたい場合は generate_stub() を直接呼ぶ
  （CLI 入口 `python -m comken config` は v1.0.0 で削除済み）
"""

import configparser
from pathlib import Path

from comken.core.config import _is_mapping_section, _parse_value
from comken.core.files.atomic import atomic_write
from comken.core.files.ops import cleanup_stale_tmp
from comken.exceptions import ConfigFileNotFoundError

_STUB_HEADER = '''"""config.ini から自動生成されたエディタ補完用スタブ。手で編集しない。

Config() を呼ぶたびに同じパスならプロセス内で 1 回だけ自動更新される
（手動生成 CLI `python -m comken config` は v1.0.0 で削除済み）。
"""
'''


def generate_stub(
    ini_path: str | Path = "config.ini", output_path: str | Path | None = None
) -> Path:
    """config.ini からエディタ補完用の型スタブ（.pyi）を手動生成する。

    通常は Config(path) を呼ぶと同じパスにつきプロセス内で 1 回だけ自動更新されるため、
    手動で実行する必要はない。 「コードをまだ書いていないが先にスタブだけ作りたい」
    場合に generate_stub() を直接呼び出す（CLI 入口 `python -m comken config` は
    v1.0.0 で削除済み）。

    Args:
        ini_path: 読み込む config.ini のパス。
        output_path: スタブの出力先。省略時は config.ini と同じ場所を基準に決める
                     （src/config.py があれば src/config.pyi、無ければ
                     typings/comken/core/ に from comken.core.config 用 / from comken
                     用 のスタブ）。

    Returns:
        生成したスタブファイルのパス（typings 方式では config.pyi のパス）。

    Raises:
        ConfigError: config.ini が見つからない場合。
    """
    cfg = configparser.ConfigParser(interpolation=None)
    loaded = cfg.read(ini_path, encoding="utf-8-sig")
    if not loaded:
        raise ConfigFileNotFoundError(Path(ini_path).resolve())

    # 実行時の Config と同じセクション名（前後空白落とし済み）で補完スタブを出す。
    from comken.core.config import _build_section_map

    section_map = _build_section_map(cfg)

    if output_path is not None:
        # 出力先を明示した場合は class スタブ（src/config.pyi 形式）を書く
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            _build_stub_content(cfg, section_map, Path(ini_path).resolve().parent),
            encoding="utf-8",
        )
        return output_path

    stub_path = _resolve_stub_path(ini_path)
    if stub_path is not None:
        # src/config.py（または config.py）がある → その隣に class スタブ
        stub_path.parent.mkdir(parents=True, exist_ok=True)
        stub_path.write_text(
            _build_stub_content(cfg, section_map, Path(ini_path).resolve().parent),
            encoding="utf-8",
        )
        return stub_path

    # src/config.py が無い → typings スタブ一式
    project_dir = Path(ini_path).resolve().parent
    _write_typings_stubs(project_dir, cfg, section_map)
    return project_dir / "typings" / "comken" / "core" / "config.pyi"


def update_stub(
    cfg: configparser.ConfigParser,
    ini_path: str | Path,
    section_map: dict[str, str] | None = None,
) -> None:
    """スタブを自動更新する（Config() から呼ばれる。失敗しても本処理は止めない）。

    - src/config.py（または config.py）がある → その隣に config.pyi（class スタブ）。
      `from src.config import config` / `from .config import config` の補完に効く
    - どちらもない → typings/comken/core/config.pyi（module スタブ）。
      `from comken.core.config import ...` の補完に効く（Pylance の typings 上書き機能を利用）
    - 内容が変わっていなければ書き込まない（無駄なファイル更新をしない）

    section_map に空白を落とした対応表を渡すと、実行時と同じセクション名で
    補完スタブを出せる。省略時は Config と整合させるため内部で再計算する。
    """
    if section_map is None:
        from comken.core.config import _build_section_map

        section_map = _build_section_map(cfg)
    stub_path = _resolve_stub_path(ini_path)
    if stub_path is not None:
        _write_stub_atomic(
            stub_path,
            _build_stub_content(cfg, section_map, Path(ini_path).resolve().parent),
        )
        return
    _write_typings_stubs(Path(ini_path).resolve().parent, cfg, section_map)


def _write_typings_stubs(
    project_dir: Path,
    cfg: configparser.ConfigParser,
    section_map: dict[str, str] | None = None,
) -> None:
    """`from comken.core.config` 方式向けの補完スタブ一式を書く。

    Pylance の typings 上書きを使う。config.pyi だけだと comken の他の公開シンボル
    （実行モード関数等）が解決できなくなるため、__init__.pyi で本物の comken を
    再エクスポートして両立させる。

    ``project_dir`` を ``_build_module_stub_content`` / ``_build_package_init_stub``
    に ``base_dir`` として渡し、相対パスを ``Path`` 型ヒントで出す。
    """
    if section_map is None:
        from comken.core.config import _build_section_map

        section_map = _build_section_map(cfg)
    comken_core_typings = project_dir / "typings" / "comken" / "core"
    comken_typings = project_dir / "typings" / "comken"
    _write_stub_atomic(
        comken_core_typings / "config.pyi",
        _build_module_stub_content(cfg, section_map, project_dir),
    )
    _write_stub_atomic(
        comken_typings / "__init__.pyi",
        _build_package_init_stub(cfg, section_map, project_dir),
    )


def _write_stub_atomic(stub_path: Path, content: str) -> None:
    """スタブを一時ファイル経由でアトミックに書き込む（内容が同じなら何もしない）。

    書き込み本体は ``atomic_write`` に統一し、``cleanup_stale_tmp`` で前回クラッシュ
    時の残骸を片付ける。**内容が既存ファイルと同じなら何もしない**（連続呼び出し
    で毎回ファイル更新しないため）。**読み取り専用フォルダなど ``OSError`` が
    出ても黙って返す**（補完が更新されないだけで実行に影響させないため）。
    """
    try:
        if stub_path.exists() and stub_path.read_text(encoding="utf-8") == content:
            return
        stub_path.parent.mkdir(parents=True, exist_ok=True)
        cleanup_stale_tmp(stub_path)  # 前回クラッシュ時の残骸を掃除
        # ``atomic_write`` は親フォルダを作らないので、上の mkdir で存在を保証する
        with atomic_write(stub_path) as tmp:
            tmp.write_text(content, encoding="utf-8")
    except OSError:
        pass  # 読み取り専用フォルダ等。補完が更新されないだけで実行には影響しない


# ── 内部ヘルパー ──────────────────────────────────────────────────────────────


def _stub_type_name(value: bool | int | float | Path | list | str) -> str:
    """スタブに書く型名を返す。"""
    if isinstance(value, bool):  # bool は int のサブクラスなので先に判定する
        return "bool"
    if isinstance(value, Path):
        return "Path"
    if isinstance(value, list):
        return "list[str]"
    return type(value).__name__


def _build_stub_content(
    cfg: configparser.ConfigParser,
    section_map: dict[str, str],
    base_dir: Path | None = None,
) -> str:
    """読み込み済みの ConfigParser からスタブファイルの中身を組み立てる。

    ``base_dir`` は相対パスを ``Path`` 化するときの基準（config.ini の親）。
    ``update_stub`` / ``generate_stub`` から呼ばれるので ``ini_path`` 経由で
    解決済みの親を渡す。実行時の ``Config._initialize`` と同じ判定結果を
    返すことで、スタブの型ヒントと実行時の型が一致する。
    """
    section_lines: list[str] = []
    config_attrs: list[str] = []
    for stripped_section, original_section in section_map.items():
        class_name = f"_{stripped_section.upper()}"
        if _is_mapping_section(stripped_section):
            # ``*_MAPPING`` セクションはキーが動的な列名なので個別クラスを作らず、
            # ``MappingDict[str, str]`` として属性に並べる。``MappingDict`` は ``dict``
            # のサブクラスで ``__missing__`` が ``None`` を返す（型と実行時の齟齬の
            # 詳細は ``_LenientDict`` の docstring を参照）。
            config_attrs.append(f"    {stripped_section.upper()}: MappingDict[str, str]")
            continue
        config_attrs.append(f"    {stripped_section.upper()}: {class_name}")
        section_lines.append(f"class {class_name}:")
        options = cfg.options(original_section)
        if not options:
            section_lines.append("    pass")
        for key in options:
            value = _parse_value(cfg, original_section, key, base_dir=base_dir)
            section_lines.append(f"    {key.upper()}: {_stub_type_name(value)}")
        section_lines.append("")

    # Path は Config.__init__ のシグネチャでも使うため常に import する
    lines = [
        _STUB_HEADER,
        "from pathlib import Path\n",
        "from typing import NoReturn\n",
        "",
        # ``MappingDict`` は実行時の ``_LenientDict`` を ``.pyi`` 側で表現する型。
        # ``dict[str, str]`` の ``__missing__`` が ``str | None`` を返すので、
        # ``config.SECTION_MAPPING["未知の列"] is None`` は型エラーになる（``in`` か
        # ``.get()`` を使う。詳細は ``_LenientDict`` の docstring）。
        "class MappingDict(dict[str, str]):\n"
        "    def __missing__(self, key: str) -> str | None: ...\n",
        "",
    ]
    lines.extend(section_lines)
    lines.append("class Config:")
    lines.extend(config_attrs or ["    pass"])
    lines.append("    def __init__(self, path: str | Path = ...) -> None: ...")
    lines.append("")
    lines.append("config: Config")
    return "\n".join(lines) + "\n"


def _build_module_stub_content(
    cfg: configparser.ConfigParser,
    section_map: dict[str, str],
    base_dir: Path | None = None,
) -> str:
    """typings/comken/core/config.pyi 用の module スタブを組み立てる。

    `from comken.core.config import ...` の型をプロジェクトの config.ini に
    合わせて上書きし、config.SECTION.KEY を補完させる。公開シンボル
    （Config / read）も宣言して他の import を壊さない。
    """
    section_lines: list[str] = []
    module_attrs: list[str] = []
    for stripped_section, original_section in section_map.items():
        class_name = f"_{stripped_section.upper()}"
        if _is_mapping_section(stripped_section):
            # ``*_MAPPING`` は ``MappingDict[str, str]`` で宣言する（実行時は
            # ``_LenientDict`` = dict のサブクラス）。型と実行時の齟齬の詳細は
            # ``_LenientDict`` の docstring を参照。
            module_attrs.append(f"{stripped_section.upper()}: MappingDict[str, str]")
            continue
        module_attrs.append(f"{stripped_section.upper()}: {class_name}")
        section_lines.append(f"class {class_name}:")
        options = cfg.options(original_section)
        if not options:
            section_lines.append("    pass")
        for key in options:
            value = _parse_value(cfg, original_section, key, base_dir=base_dir)
            section_lines.append(f"    {key.upper()}: {_stub_type_name(value)}")
        section_lines.append("")

    lines = [
        _STUB_HEADER,
        "from pathlib import Path\n",
        "from typing import NoReturn\n",
        "",
        # ``MappingDict`` は実行時の ``_LenientDict`` を ``.pyi`` 側で表現する型。
        # ``dict[str, str]`` の ``__missing__`` が ``str | None`` を返す。
        "class MappingDict(dict[str, str]):\n"
        "    def __missing__(self, key: str) -> str | None: ...\n",
        "",
    ]
    lines.extend(section_lines)
    lines.append("class Config:")
    lines.append("    def __init__(self, path: str | Path = ...) -> None: ...")
    lines.append("    def __getattr__(self, name: str) -> NoReturn: ...")
    lines.append("")
    lines.extend(module_attrs)
    return "\n".join(lines) + "\n"


def _build_package_init_stub(
    cfg: configparser.ConfigParser,
    section_map: dict[str, str],
    base_dir: Path | None = None,
) -> str:
    """typings/comken/__init__.pyi を組み立てる。

    core/config.pyi で comken.core.config を上書きすると、そのままでは comken 直下の
    公開シンボル（実行モード関数等）が解決できなくなる。ここで本物の comken の
    __all__ を、定義元サブモジュールから再エクスポートして両立させる。
    comken の公開 API を内省して作るので、comken 側が増えても追従する。
    """
    import comken

    by_module: dict[str, list[str]] = {}
    for name in comken.__all__:
        module = getattr(getattr(comken, name), "__module__", "")
        if module.startswith("comken."):
            by_module.setdefault(module, []).append(name)

    # Path はセクション属性の型注釈に出るため常に import する。
    # 入れないと Path 型のキーが `Unknown` として解決され、補完が静かに落ちる
    # （bool や str は組み込みなので解決してしまい、Path だけ抜けが出る）。
    lines = [_STUB_HEADER, "from pathlib import Path\n", ""]
    for module in sorted(by_module):
        names = sorted(by_module[module])
        inner = "".join(f"    {name} as {name},\n" for name in names)
        lines.append(f"from {module} import (\n{inner})")
    # ``MappingDict`` は実行時の ``_LenientDict`` を ``.pyi`` 側で表現する型。
    # ここで宣言しないと ``config.SECTION_MAPPING`` が ``Unknown`` として解決され、
    # Pylance 補完が静かに落ちる。
    lines.append(
        "class MappingDict(dict[str, str]):\n"
        "    def __missing__(self, key: str) -> str | None: ...\n"
    )
    lines.append("")
    config_attrs: list[str] = []
    for stripped_section, original_section in section_map.items():
        class_name = f"_{stripped_section.upper()}"
        if _is_mapping_section(stripped_section):
            # ``*_MAPPING`` は ``MappingDict[str, str]`` として facade に並べる。
            config_attrs.append(f"    {stripped_section.upper()}: MappingDict[str, str]")
            continue
        config_attrs.append(f"    {stripped_section.upper()}: {class_name}")
        lines.append(f"class {class_name}:")
        options = cfg.options(original_section)
        if not options:
            lines.append("    pass")
        for key in options:
            value = _parse_value(cfg, original_section, key, base_dir=base_dir)
            lines.append(f"    {key.upper()}: {_stub_type_name(value)}")
        lines.append("")
    lines.append("class _ConfigFacade:")
    lines.extend(config_attrs or ["    pass"])
    lines.append("")
    lines.append("config: _ConfigFacade")
    lines.append("")
    lines.append("__version__: str")
    return "\n".join(lines) + "\n"


def _resolve_stub_path(ini_path: str | Path) -> Path | None:
    """スタブの出力先を config.ini の場所を基準に決める。

    .pyi は同名の .py の隣に置かないとエディタに認識されないため、
    src/config.py（推奨構成）→ config.py の順に探し、どちらもなければ None。
    """
    base = Path(ini_path).resolve().parent
    if (base / "src" / "config.py").exists():
        return base / "src" / "config.pyi"
    if (base / "config.py").exists():
        return base / "config.pyi"
    return None
