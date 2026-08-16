"""comken/__init__.py — comken の基本入口。

「comken 直下」には、**何をするプロジェクトかに関係なく使う**土台だけを置く。
設定・ログ・実行モードの7個で、それ以外の部品は ``comken.core`` から取る
（``from comken.core import FileFinder``）。

書くときは ``from comken import X`` が第一選択。そこに無いものだけ
``from comken.core import Y`` で取る（仕様書 4.32）。

toolbox / services はこの2階層に上げない。``from comken.toolbox.excel import ExcelWriter``
のように深いパスのままで十分で、そこには「どの機能群に依存しているか」が読める意味があるため。
"""

# バージョンの定義はここ1箇所だけ（pyproject.toml は dynamic version でここを参照する）
# リリースタグ（v0.10.0 等）と必ず一致させる。config が起動時にこの値をログへ出すので、
# ズレると「どのタグが動いているか」がログから追えなくなる。
__version__ = "0.10.0"

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
