"""comken/__init__.py — comken 全体の基盤 API を公開するパッケージ。

「comken 直下」は、どんなプロジェクトからでも使える土台だけを置く場所。
利用者は ``from comken import ...`` だけで必要なものに届く形にする。
部品は ``comken.core`` から集め、ここから facade として再輸出する。

toolbox / services は facade には上げない。``from comken.toolbox.excel import ExcelWriter``
のように深いパスのままで十分で、そこには「どの機能群に依存しているか」が読める意味があるため。
"""

# バージョンの定義はここ1箇所だけ（pyproject.toml は dynamic version でここを参照する）
__version__ = "0.8.0"

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

from .core import config as config
from .core.config import Config as Config
from .core.logger import setup_logging as setup_logging
from .runtime import debug, dry_run, is_debug, is_dry_run

__all__ = [
    "Config",
    "config",
    "debug",
    "dry_run",
    "is_debug",
    "is_dry_run",
    "setup_logging",
]
