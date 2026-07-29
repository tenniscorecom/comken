# バージョンの定義はここ1箇所だけ（pyproject.toml は dynamic version でここを参照する）
__version__ = "0.2.0"

# ── バイトコードキャッシュをローカルに逃がす ─────────────────────────────────
# comken は共有サーバー上の1か所を直接参照する運用（PYTHONPATH で参照）。
# 共有サーバーが読み取り専用だと各サブモジュールの __pycache__ を書けず、
# 毎回コンパイルが走って遅くなる。そこで .pyc の出力先をローカルに向ける。
# ここより下の comken サブモジュールの import から有効になる。
# 既にユーザーが設定している場合（環境変数 or sys.pycache_prefix）は尊重して触らない。
import os as _os
import sys as _sys
from pathlib import Path as _Path

if _sys.pycache_prefix is None and not _os.environ.get("PYTHONPYCACHEPREFIX"):
    _base = _os.environ.get("LOCALAPPDATA") or str(_Path.home() / ".cache")
    _sys.pycache_prefix = str(_Path(_base) / "comken-pycache")
# ────────────────────────────────────────────────────────────────────────────

from .config import Config
from .exceptions import (
    ColumnNotFoundError,
    ConfigError,
    CsvError,
    ExcelError,
    MacroError,
    OriginalLibsError,
    SheetNotFoundError,
)
from .logger import setup_logger
from .runtime import is_debug, is_dry_run, set_debug, set_dry_run

__all__ = [
    "Config",
    "setup_logger",
    "set_debug",
    "is_debug",
    "set_dry_run",
    "is_dry_run",
    "OriginalLibsError",
    "ExcelError",
    "SheetNotFoundError",
    "MacroError",
    "ColumnNotFoundError",
    "CsvError",
    "ConfigError",
]
