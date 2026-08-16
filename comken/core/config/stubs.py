"""comken/core/config/stubs.py — config.ini からエディタ補完用スタブ（.pyi）を生成する

Config の属性（config.SECTION.KEY）は config.ini から実行時に動的に作られるため、
そのままではエディタが補完できない。ここで config.ini の内容を型付きの .pyi に書き出し、
補完を効かせる。設定値の読み込みとはモジュール内で責務を分けている。

- Config() を呼ぶたびに update_stub() が自動で走る（config パッケージから呼ばれる）
- コードを書く前に手動で作りたい場合は generate_stub()（`python -m comken.core.config`）
"""

import configparser
import os
from pathlib import Path

from ...exceptions import ConfigFileNotFoundError
from ..utils.files.ops import cleanup_stale_tmp
from . import _is_mapping_section, _parse_value

_STUB_HEADER = '''"""config.ini から自動生成されたエディタ補完用スタブ。手で編集しない。

Config() を呼ぶたびに自動更新される（手動生成: python -m comken.core.config）。
"""
'''


def generate_stub(
    ini_path: str | Path = "config.ini", output_path: str | Path | None = None
) -> Path:
    """config.ini からエディタ補完用の型スタブ（.pyi）を手動生成する。

    通常は Config() を呼ぶたびに自動更新されるため、手動で実行する必要はない。
    「コードをまだ書いていないが先にスタブだけ作りたい」場合に使う:

        python -m comken.core.config

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

    if output_path is not None:
        # 出力先を明示した場合は class スタブ（src/config.pyi 形式）を書く
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(_build_stub_content(cfg), encoding="utf-8")
        return output_path

    stub_path = _resolve_stub_path(ini_path)
    if stub_path is not None:
        # src/config.py（または config.py）がある → その隣に class スタブ
        stub_path.parent.mkdir(parents=True, exist_ok=True)
        stub_path.write_text(_build_stub_content(cfg), encoding="utf-8")
        return stub_path

    # src/config.py が無い → typings スタブ一式
    project_dir = Path(ini_path).resolve().parent
    _write_typings_stubs(project_dir, cfg)
    return project_dir / "typings" / "comken" / "core" / "config.pyi"


def update_stub(cfg: configparser.ConfigParser, ini_path: str | Path) -> None:
    """スタブを自動更新する（Config() から呼ばれる。失敗しても本処理は止めない）。

    - src/config.py（または config.py）がある → その隣に config.pyi（class スタブ）。
      `from src.config import config` / `from .config import config` の補完に効く
    - どちらもない → typings/comken/core/config.pyi（module スタブ）。
      `from comken.core.config import ...` の補完に効く（Pylance の typings 上書き機能を利用）
    - 内容が変わっていなければ書き込まない（無駄なファイル更新をしない）
    """
    stub_path = _resolve_stub_path(ini_path)
    if stub_path is not None:
        _write_stub_atomic(stub_path, _build_stub_content(cfg))
        return
    _write_typings_stubs(Path(ini_path).resolve().parent, cfg)


def _write_typings_stubs(project_dir: Path, cfg: configparser.ConfigParser) -> None:
    """`from comken.core.config` 方式向けの補完スタブ一式を書く。

    Pylance の typings 上書きを使う。config.pyi だけだと comken の他の公開シンボル
    （実行モード関数等）が解決できなくなるため、__init__.pyi で本物の comken を
    再エクスポートして両立させる。
    """
    comken_core_typings = project_dir / "typings" / "comken" / "core"
    comken_typings = project_dir / "typings" / "comken"
    _write_stub_atomic(comken_core_typings / "config.pyi", _build_module_stub_content(cfg))
    _write_stub_atomic(comken_typings / "__init__.pyi", _build_package_init_stub(cfg))


def _write_stub_atomic(stub_path: Path, content: str) -> None:
    """スタブを一時ファイル経由でアトミックに書き込む（内容が同じなら何もしない）。"""
    try:
        if stub_path.exists() and stub_path.read_text(encoding="utf-8") == content:
            return
        stub_path.parent.mkdir(parents=True, exist_ok=True)
        cleanup_stale_tmp(stub_path)  # 前回クラッシュ時の .tmp 残骸を掃除
        # 一時ファイル経由で置き換える（複数プロセス同時起動時の書き込み競合対策）
        tmp_path = stub_path.with_suffix(f"{stub_path.suffix}.{os.getpid()}.tmp")
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(stub_path)
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


def _build_stub_content(cfg: configparser.ConfigParser) -> str:
    """読み込み済みの ConfigParser からスタブファイルの中身を組み立てる。"""
    section_lines: list[str] = []
    config_attrs: list[str] = []
    for section in cfg.sections():
        # マッピングのキーは列名という動的データなので、属性としてスタブに列挙しない。
        if _is_mapping_section(section):
            continue
        class_name = f"_{section.upper()}"
        config_attrs.append(f"    {section.upper()}: {class_name}")
        section_lines.append(f"class {class_name}:")
        options = cfg.options(section)
        if not options:
            section_lines.append("    pass")
        for key in options:
            value = _parse_value(cfg, section, key)
            section_lines.append(f"    {key.upper()}: {_stub_type_name(value)}")
        section_lines.append("")

    # Path は Config.__init__ のシグネチャでも使うため常に import する
    lines = [_STUB_HEADER, "from pathlib import Path\n", "from typing import NoReturn\n", ""]
    lines.extend(section_lines)
    lines.append("class Config:")
    lines.extend(config_attrs or ["    pass"])
    lines.append("    def __init__(self, path: str | Path = ...) -> None: ...")
    lines.append("    def mapping(self, section: str) -> dict[str, str]: ...")
    lines.append("")
    lines.append("config: Config")
    return "\n".join(lines) + "\n"


def _build_module_stub_content(cfg: configparser.ConfigParser) -> str:
    """typings/comken/core/config.pyi 用の module スタブを組み立てる。

    `from comken.core.config import ...` の型をプロジェクトの config.ini に
    合わせて上書きし、config.SECTION.KEY を補完させる。公開シンボル
    （Config / read）も宣言して他の import を壊さない。
    """
    section_lines: list[str] = []
    module_attrs: list[str] = []
    for section in cfg.sections():
        # マッピングは mapping() で辞書として読むため、動的な列名を補完候補にしない。
        if _is_mapping_section(section):
            continue
        class_name = f"_{section.upper()}"
        module_attrs.append(f"{section.upper()}: {class_name}")
        section_lines.append(f"class {class_name}:")
        options = cfg.options(section)
        if not options:
            section_lines.append("    pass")
        for key in options:
            value = _parse_value(cfg, section, key)
            section_lines.append(f"    {key.upper()}: {_stub_type_name(value)}")
        section_lines.append("")

    lines = [_STUB_HEADER, "from pathlib import Path\n", "from typing import NoReturn\n", ""]
    lines.extend(section_lines)
    lines.append("class Config:")
    lines.append("    def __init__(self, path: str | Path = ...) -> None: ...")
    lines.append("    def mapping(self, section: str) -> dict[str, str]: ...")
    lines.append("    def __getattr__(self, name: str) -> NoReturn: ...")
    lines.append("")
    lines.append("def read(path: str | Path = ...) -> Config: ...")
    lines.append("def mapping(section: str) -> dict[str, str]: ...")
    lines.append("")
    lines.extend(module_attrs)
    return "\n".join(lines) + "\n"


def _build_package_init_stub(cfg: configparser.ConfigParser) -> str:
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

    lines = [_STUB_HEADER]
    for module in sorted(by_module):
        names = sorted(by_module[module])
        inner = "".join(f"    {name} as {name},\n" for name in names)
        lines.append(f"from {module} import (\n{inner})")
    config_attrs: list[str] = []
    for section in cfg.sections():
        if _is_mapping_section(section):
            continue
        class_name = f"_{section.upper()}"
        config_attrs.append(f"    {section.upper()}: {class_name}")
        lines.append(f"class {class_name}:")
        options = cfg.options(section)
        if not options:
            lines.append("    pass")
        for key in options:
            value = _parse_value(cfg, section, key)
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
