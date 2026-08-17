"""comken/core/config/__init__.py — INI ファイル読み込みユーティリティ

config.ini を読み込み、config.SECTION.KEY の形式でアクセスできる Config クラスを提供する。

いちばん簡単な使い方（プロジェクトに src/config.py を作らなくてよい）:

    from comken import config
    path = config.FILES.INPUT_FOLDER / config.FILES.CSV_EAST

    → 初回アクセス時にカレントディレクトリの config.ini を1度だけ読む（遅延読み込み）。
      config.ini が別の場所にある場合は、最初に使う前に config.read("パス") を呼ぶ。

明示的にインスタンスを持ちたい場合（従来どおり）:

    from comken.core.config import Config
    config = Config()                 # または Config("path/to/config.ini")

エディタの補完候補:
    属性は実行時に動的に作られるため、そのままではエディタが補完できないが、
    Config() を呼ぶたびに補完用のスタブ（src/config.pyi）が自動更新されるため、
    一度スクリプトを実行すれば config.SECTION.KEY が型付きで補完されるようになる。

    まだ一度も実行していない状態で先にスタブだけ作りたい場合は手動で生成する:

        python -m comken.core.config

※ ブラウザの設定は config.ini ではなく BrowserOptions のインスタンス
   （src/browser_options.py）で行う。config はブラウザ設定を持たない。
"""

import configparser
import logging
import math
import shutil
import types
from pathlib import Path
from typing import NoReturn

from comken.exceptions import (
    ConfigCreatedFromExampleError,
    ConfigFileNotFoundError,
    ConfigLowerCaseNameError,
    ConfigRequiredKeysMissingError,
    ConfigSectionNotFoundError,
)

logger = logging.getLogger(__name__)

_is_version_logged = False
MAPPING_SECTION_SUFFIX = "MAPPING"


def _is_mapping_section(section: str) -> bool:
    """列名の対応表として扱うセクションかを返す。"""
    return section.endswith(MAPPING_SECTION_SUFFIX)


def _create_from_example(path: Path) -> Path | None:
    """config.ini が無いとき、隣の config.ini.example からコピーして作る。

    作らずにエラーだけ出すと、毎回「example をコピーする」手作業が要る。
    ただし作ってそのまま動かすと、ダミーの値のまま別のフォルダを読み書きしうるため、
    作るところまでで止めて確認を促す（呼び出し元で例外にする）。
    """
    example = path.with_name(f"{path.name}.example")
    if not example.is_file():
        return None
    shutil.copy2(example, path)
    return path.resolve()


def _validate_upper_case(cfg: configparser.ConfigParser, path: Path) -> None:
    """セクション名・キー名が大文字で書かれているか確かめる。

    小文字で書かれていても読み込み自体は成功し、大文字に直して保持されるため、
    小文字のままアクセスしたときに初めて「そんなセクションはない」と言われる。
    書いた場所から遠いエラーになるので、読み込んだ時点で止める。
    """
    wrong = [f"[{s}] → [{s.upper()}]" for s in cfg.sections() if s != s.upper()]
    wrong += [
        f"[{s}] の {k} → {k.upper()}"
        for s in cfg.sections()
        if not _is_mapping_section(s)
        for k in cfg.options(s)
        if k != k.upper()
    ]
    if wrong:
        raise ConfigLowerCaseNameError(path.resolve(), wrong)


class Config:
    """config.ini を読み込み、config.SECTION.KEY の形式でアクセスできるクラス。

    値の型変換（_parse_value の変換順と同じ）:
        - true / false → bool
        - [a, b, c] → list[str]
        - 絶対パス（C:\\ / \\\\ / /）→ Path
        - 整数 → int
        - 小数 → float
        - それ以外 → str

    数値を文字列として使いたい場合はコード側で str() に変換する。

    config.ini の例（セクション名・キー名は大文字で書く）:
        [BROWSER]
        WAIT_SECONDS = 10
        HEADLESS = false

        [FILES]
        INPUT_FOLDER = C:\\作業\\input

        [REPORT]
        TARGET_SHEETS = [支店A, 支店B, 集計]

    """

    def __init__(self, path: str | Path = "config.ini") -> None:
        """
        Args:
            path: config.ini のパス。省略するとカレントディレクトリの config.ini を読む。
        """
        cfg = configparser.ConfigParser(interpolation=None)
        # configparser は既定でキー名を小文字に潰すため、書かれたとおりの綴りを保つ。
        # これがないと「大文字で書かれていたか」を判定できない（_validate_upper_case）。
        cfg.optionxform = str  # type: ignore[method-assign]
        # utf-8-sig: メモ帳等で保存すると BOM 付き UTF-8 になるため（BOM なしも読める）
        loaded = cfg.read(path, encoding="utf-8-sig")
        if not loaded:
            # configparser はファイルがなくても黙って空になるため、明示的にエラーにする
            # （後で config.FILES 等が分かりにくい AttributeError になるのを防ぐ）
            created = _create_from_example(Path(path))
            if created is not None:
                raise ConfigCreatedFromExampleError(created)
            raise ConfigFileNotFoundError(Path(path).resolve())

        _validate_upper_case(cfg, Path(path))

        self._path = Path(path).resolve()
        self._mappings: dict[str, dict[str, str]] = {}
        for section in cfg.sections():
            if _is_mapping_section(section):
                self._mappings[section] = {
                    key: cfg.get(section, key).strip() for key in cfg.options(section)
                }
                continue
            ns = types.SimpleNamespace(
                **{k.upper(): _parse_value(cfg, section, k) for k in cfg.options(section)}
            )
            setattr(self, section.upper(), ns)

        # エディタ補完用スタブ（src/config.pyi）を自動更新する。
        # config.ini を変更してもスタブが古くならない（失敗しても本処理は止めない）。
        # スタブ生成は別モジュールへ分離しており、遅延 import で循環を避ける
        from comken.core.config.stubs import update_stub

        update_stub(cfg, path)
        _log_version_once()

    def mapping(self, section: str) -> dict[str, str]:
        """マッピングセクションを列名が書かれたままの辞書で返す。

        Args:
            section: `MAPPING` で終わるセクション名。

        Returns:
            転記元の列名をキー、転記先の列名を値とする辞書。

        Raises:
            ConfigSectionNotFoundError: 指定したマッピングセクションがない場合。
        """
        try:
            return self._mappings[section]
        except KeyError:
            raise ConfigSectionNotFoundError(section, list(self._mappings)) from None

    def __getattr__(self, name: str) -> NoReturn:
        # 通常の属性（設定済みセクション）は __dict__ にあり、ここには来ない。
        # 未定義セクションのアクセスだけがここに来るので、分かりやすいエラーにする。
        if name.startswith("_"):  # copy/pickle 等の内部属性探索は通常の AttributeError に
            raise AttributeError(name)
        sections = [k for k in vars(self) if k.isupper()]
        raise ConfigSectionNotFoundError(name, sections)


# ── `from comken import config` 用の遅延シングルトン ──────────────────────────
# プロジェクトごとに src/config.py（config = Config()）を書く手間を省く。
# config.SECTION.KEY への初回アクセス時にカレントディレクトリの config.ini を
# 1度だけ読む（import 時ではないので、config.ini を持たないプロジェクトやテストで
# comken を import しても失敗しない）。

_singleton: Config | None = None


def read(path: str | Path = "config.ini") -> Config:
    """`from comken import config` が読む config.ini の場所を指定する（省略時は config.ini）。

    config.ini がカレントディレクトリ以外にある場合に、config を使う前に呼ぶ:

        from comken import config
        config.read(r"C:\\作業\\config.ini")   # 場所を指定（省略すればカレントの config.ini）
        path = config.FILES.INPUT_FOLDER

    Returns:
        読み込んだ Config インスタンス（以後 comken.core.config が返すもの）。
    """
    global _singleton
    _singleton = Config(path)
    return _singleton


def mapping(section: str) -> dict[str, str]:
    """遅延シングルトンからマッピングセクションを辞書で返す。"""
    global _singleton
    if _singleton is None:
        _singleton = Config()
    return _singleton.mapping(section)


def require(*names: str) -> None:
    """config.ini に必要な項目がそろっているかを、起動時にまとめて確かめる。

    足りないものを1つずつ見つけるのではなく、**全部集めて一度に報告する**。
    1つ直して実行、また別の項目で止まる、を繰り返すと、config.ini を書く人が
    何回も往復することになるため。

    使い方（main.py の最初で呼ぶ）:

        from comken import config

        config.require("FILES.INPUT_CSV", "REPORT.OUTPUT_FOLDER")

    Args:
        *names: ``"SECTION.KEY"`` の形で書いた項目名。大文字小文字は問わない。

    Raises:
        ConfigRequiredKeysMissingError: 1つでも足りない場合。
            足りない項目を全部並べて報告する。
        ConfigFileNotFoundError: config.ini が無い場合。
        ConfigCreatedFromExampleError: example から作成した場合。
    """
    global _singleton
    if _singleton is None:
        _singleton = Config()
    missing = []
    for name in names:
        section, _, key = name.partition(".")
        try:
            # 無いセクションは ConfigSectionNotFoundError になる（既定値を返さない）ので、
            # ここで受けて「足りないもの」へ積む。1件目で止めずに最後まで数える。
            namespace = getattr(_singleton, section.strip().upper())
        except ConfigSectionNotFoundError:
            missing.append(name.strip().upper())
            continue
        if not hasattr(namespace, key.strip().upper()):
            missing.append(name.strip().upper())
    if missing:
        raise ConfigRequiredKeysMissingError(missing, _singleton._path)


def __getattr__(name: str) -> types.SimpleNamespace:
    # PEP 562: `comken.core.config.FILES` のようにモジュール属性として見つからない名前で呼ばれる。
    # セクションは大文字なので、大文字名のときだけ遅延シングルトンへ委譲する
    # （Config / read などの実体は通常の属性解決で見つかるためここには来ない）。
    if name.isupper():
        global _singleton
        if _singleton is None:
            _singleton = Config()  # 初回アクセス時にカレントの config.ini を読む
        return getattr(_singleton, name)
    raise AttributeError(f"module 'comken.core.config' has no attribute {name!r}")


# ── 内部ヘルパー：ini 値の型変換 ───────────────────────────────────────────────


def _split_list_items(text: str) -> list[str]:
    """カンマまたは改行区切りの文字列をリストに変換する。空文字は除外する。"""
    items = text.replace("\n", ",").split(",")
    return [s.strip() for s in items if s.strip()]


def _log_version_once() -> None:
    """設定の初回読み込み後に障害調査用のバージョンを1回だけ記録する。"""
    global _is_version_logged
    if not _is_version_logged:
        # 親パッケージ側の __version__ は comken/__init__.py で定義されるため、
        # モジュール先頭で `from ... import __version__` すると import 順序に
        # 依存した循環が起きる。関数の内側で取る形にすることで循環を断つ。
        from comken import __version__

        logger.info("comken v%s", __version__)
        _is_version_logged = True


def _parse_value(
    cfg: configparser.ConfigParser, section: str, key: str
) -> bool | int | float | Path | list[str] | str:
    """ini の値を適切な Python 型に変換して返す。

    変換の優先順位:
        1. true / false（大文字小文字問わず）→ bool
        2. [a, b, c] → list[str]（改行区切りも可）
        3. 絶対パス（C:\\ / \\\\ / / で始まる）→ Path
        4. 整数に変換できる → int（ただし先頭ゼロの数字は文字列のまま）
        5. 小数に変換できる → float（ただし nan / inf は文字列のまま）
        6. それ以外 → str

    文字列として使いたい数値（例: シート名 "2024"）はコード側で str() に変換する。
    先頭ゼロ（電話番号 "0521234567"・社員番号 "007" 等）は int にすると桁落ちするため
    文字列で返す。nan / inf は float() が受理してしまうので数値化しない。
    """
    value = cfg.get(section, key).strip()
    lower = value.lower()

    if lower == "true":
        return True
    if lower == "false":
        return False

    if value.startswith("[") and value.endswith("]"):
        return _split_list_items(value[1:-1])

    if len(value) >= 2 and (value[1:3] == ":\\" or value[:2] == "\\\\" or value[0] == "/"):
        return Path(value)

    # 先頭ゼロの数字は電話番号・社員番号等とみなし、桁落ちを避けて文字列のまま返す
    unsigned = value[1:] if value[:1] in ("+", "-") else value
    if len(unsigned) > 1 and unsigned[0] == "0" and unsigned.isdigit():
        return value

    try:
        return int(value)
    except ValueError:
        pass
    try:
        parsed = float(value)
        if math.isfinite(parsed):  # nan / inf は設定値として無効なので文字列扱い
            return parsed
    except ValueError:
        pass

    return value
