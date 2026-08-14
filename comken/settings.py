r"""comken/settings.py — comken 自身の設定（社内固有の値）。

**共有サーバーの comken は git チェックアウトなので、コード内の定数を書き換えると
`git pull` のたびに衝突する。** 社内の共有フォルダのパスのように、公開リポジトリへ
書けない値は git 管理外の `settings.ini` に置く。

    共有サーバー \\server\share\tools\comken\
        comken/                ← git 管理（pull で更新される）
        settings.ini           ← git 管理外（社内固有の値。pull で消えない）
        settings.ini.example   ← git 管理（雛形）

プロジェクトの `config.ini`（`comken.config`）とは別物。

| | 誰の設定か | 誰が書くか |
|---|---|---|
| `config.ini` | **そのプロジェクト**（入力フォルダ・出力先など） | プロジェクトの利用者 |
| `settings.ini` | **comken 自身**（共有フォルダの場所など） | comken を配置する人（1回だけ） |

**無ければ example から作って、そこで止める**（config.ini と同じ）。作り忘れも、
仮の値のまま動かすことも防ぐ。

読み込みは**初回アクセス時**に行う。import しただけでは読まないので、settings.ini を
用意していない開発環境でも comken を import できる。
"""

import configparser
import shutil
from pathlib import Path

from .exceptions import (
    SettingsCreatedFromExampleError,
    SettingsKeyNotFoundError,
    SettingsSectionNotFoundError,
)

# settings.ini はリポジトリのルート（comken パッケージの親）に置く
_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = _ROOT / "settings.ini"
EXAMPLE_PATH = _ROOT / "settings.ini.example"

_parser: configparser.ConfigParser | None = None


def get(section: str, key: str) -> str:
    """設定を1つ読む。

    Args:
        section: セクション名（例: "SALESFORCE_DOWNLOADER"）。
        key: キー名（例: "MASTER_PATH"）。

    Raises:
        SettingsCreatedFromExampleError: settings.ini が無く、example から作った場合。
        SettingsSectionNotFoundError: セクションが無い場合。
        SettingsKeyNotFoundError: キーが無い場合。
    """
    parser = _load()
    if not parser.has_section(section):
        raise SettingsSectionNotFoundError(section, parser.sections(), SETTINGS_PATH)
    if not parser.has_option(section, key):
        raise SettingsKeyNotFoundError(section, key, parser.options(section), SETTINGS_PATH)
    return parser.get(section, key).strip()


def get_path(section: str, key: str) -> Path:
    """設定をパスとして読む。"""
    return Path(get(section, key))


def reload() -> None:
    """次のアクセスで settings.ini を読み直す（テストと、設定を書き換えた直後に使う）。"""
    global _parser
    _parser = None


def _load() -> configparser.ConfigParser:
    """settings.ini を読む（初回だけ）。無ければ example から作って止める。"""
    global _parser
    if _parser is not None:
        return _parser

    if not SETTINGS_PATH.exists():
        created = _create_from_example()
        raise SettingsCreatedFromExampleError(SETTINGS_PATH, created)

    parser = configparser.ConfigParser()
    # キー名を小文字にしない（config.ini と同じく、書いたとおりの大文字で引く）
    parser.optionxform = str
    parser.read(SETTINGS_PATH, encoding="utf-8")
    _parser = parser
    return parser


def _create_from_example() -> bool:
    """example から settings.ini を作る。example も無ければ False を返す。"""
    if not EXAMPLE_PATH.exists():
        return False
    shutil.copyfile(EXAMPLE_PATH, SETTINGS_PATH)
    return True
