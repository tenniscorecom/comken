"""テスト間で comken の内部状態を初期化する関数。

ライブラリ本体にはテスト用の入口を置かない方針なので、モジュールの内部状態
（キャッシュ・フラグ・シングルトン）はテスト側で直接初期化する。
"""

from __future__ import annotations

from comken.core.config import base as config_base
from comken.core.dates import holidays
from comken.core.logger import environment


def reset_cached_config() -> None:
    """``Config(path)`` のキャッシュとパス解決のキャッシュを破棄する。"""
    config_base._get_or_build_config.cache_clear()
    config_base._default_config_path.cache_clear()
    config_base._path_resolution_cache.clear()


def set_holiday_calendar(calendar: holidays._Holidays | None) -> None:
    """既定の祝日カレンダーを差し替える。``None`` で次回アクセス時に CSV から作り直す。"""
    holidays._singleton = calendar


def reset_version_log() -> None:
    """「comken のバージョンを記録済み」のフラグを下ろす。"""
    environment._version_logged = False
