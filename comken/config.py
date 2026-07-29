"""
config.py — INI ファイル読み込みユーティリティ

config.ini を読み込み、config.SECTION.KEY の形式でアクセスできる Config クラスを提供する。

いちばん簡単な使い方（プロジェクトに src/config.py を作らなくてよい）:

    from comken import config
    path = config.FILES.INPUT_FOLDER / config.FILES.CSV_EAST

    → 初回アクセス時にカレントディレクトリの config.ini を1度だけ読む（遅延読み込み）。
      config.ini が別の場所にある場合は、最初に使う前に config.read("パス") を呼ぶ。

明示的にインスタンスを持ちたい場合（従来どおり）:

    from comken.config import Config
    config = Config()                 # または Config("path/to/config.ini")

エディタの補完候補:
    属性は実行時に動的に作られるため、そのままではエディタが補完できないが、
    Config() を呼ぶたびに補完用のスタブ（src/config.pyi）が自動更新されるため、
    一度スクリプトを実行すれば config.SECTION.KEY が型付きで補完されるようになる。

    まだ一度も実行していない状態で先にスタブだけ作りたい場合は手動で生成する:

        python -m comken.config

※ ブラウザの設定は config.ini ではなく BrowserOptions のインスタンス
   （src/browser_options.py）で行う。config はブラウザ設定を持たない。
"""

import configparser
import logging
import math
import types
from pathlib import Path
from typing import NoReturn

from . import __version__
from .exceptions import ConfigFileNotFoundError, ConfigSectionNotFoundError

logger = logging.getLogger(__name__)

_is_version_logged = False


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

    使い方:
        config = Config() # カレントディレクトリの config.ini を読む
        config = Config("path/to/config.ini") # パスを指定する場合

        config.BROWSER.HEADLESS        # → False（bool）
        config.BROWSER.WAIT_SECONDS    # → 10（int）
        config.FILES.INPUT_FOLDER      # → Path("C:\\作業\\input")
        config.FILES.INPUT_FOLDER / "支店A.csv"  # → Path("C:\\作業\\input\\支店A.csv")
        config.REPORT.TARGET_SHEETS    # → ["支店A", "支店B", "集計"]
    """

    def __init__(self, path: str | Path = "config.ini") -> None:
        """
        Args:
            path: config.ini のパス。省略するとカレントディレクトリの config.ini を読む。
        """
        cfg = configparser.ConfigParser(interpolation=None)
        # utf-8-sig: メモ帳等で保存すると BOM 付き UTF-8 になるため（BOM なしも読める）
        loaded = cfg.read(path, encoding="utf-8-sig")
        if not loaded:
            # configparser はファイルがなくても黙って空になるため、明示的にエラーにする
            # （後で config.FILES 等が分かりにくい AttributeError になるのを防ぐ）
            raise ConfigFileNotFoundError(Path(path).resolve())

        for section in cfg.sections():
            ns = types.SimpleNamespace(
                **{k.upper(): _parse_value(cfg, section, k) for k in cfg.options(section)}
            )
            setattr(self, section.upper(), ns)

        # エディタ補完用スタブ（src/config.pyi）を自動更新する。
        # config.ini を変更してもスタブが古くならない（失敗しても本処理は止めない）。
        # スタブ生成は別モジュール（config_stub）に分離しており、遅延 import で循環を避ける
        from .config_stub import update_stub

        update_stub(cfg, path)
        _log_version_once()

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
        読み込んだ Config インスタンス（以後 comken.config が返すもの）。
    """
    global _singleton
    _singleton = Config(path)
    return _singleton


def __getattr__(name: str) -> types.SimpleNamespace:
    # PEP 562: `comken.config.FILES` のようにモジュール属性として見つからない名前で呼ばれる。
    # セクションは大文字なので、大文字名のときだけ遅延シングルトンへ委譲する
    # （Config / read などの実体は通常の属性解決で見つかるためここには来ない）。
    if name.isupper():
        global _singleton
        if _singleton is None:
            _singleton = Config()  # 初回アクセス時にカレントの config.ini を読む
        return getattr(_singleton, name)
    raise AttributeError(f"module 'comken.config' has no attribute {name!r}")


# ── 内部ヘルパー：ini 値の型変換 ───────────────────────────────────────────────


def _split_list_items(text: str) -> list[str]:
    """カンマまたは改行区切りの文字列をリストに変換する。空文字は除外する。"""
    items = text.replace("\n", ",").split(",")
    return [s.strip() for s in items if s.strip()]


def _log_version_once() -> None:
    """設定の初回読み込み後に障害調査用のバージョンを1回だけ記録する。"""
    global _is_version_logged
    if not _is_version_logged:
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


if __name__ == "__main__":
    # スタブの手動生成（python -m comken.config）。生成本体は config_stub にある
    from .config_stub import generate_stub

    stub_path = generate_stub()
    print(f"補完用スタブを生成しました: {stub_path.resolve()}")
    print("以後は Config() を呼ぶたびに自動更新されます。")
