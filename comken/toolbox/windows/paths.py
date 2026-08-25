"""comken/toolbox/windows/paths.py — よく使う標準フォルダのパス取得。

レジストリを触る（``winreg``）ため、外側にあるものを触らない ``comken.core`` ではなく
``comken.toolbox.windows`` に置いている。

    from comken.toolbox.windows import Paths
    Paths.downloads()
"""

import os
import tempfile
from pathlib import Path

# レジストリ「User Shell Folders」の Downloads の値名（固定 GUID）
_DOWNLOADS_GUID = "{374DE290-123F-4565-9164-39C4925E467B}"


class Paths:
    """よく使うフォルダのパスを返すユーティリティ。インスタンス化せず静的メソッドで使う。

    Desktop / Downloads は OneDrive の「既知のフォルダーの移動」で
    C:\\Users\\xxx 直下にないことがあるため、レジストリから実際の場所を取得する。

    **結果のキャッシュ**: ``downloads()`` / ``desktop()`` は **モジュールレベル**
    で1度だけレジストリを引き、 以降は同じ ``Path`` を返す。 フォルダの場所は
    プロセスが生きている間に変わらないので、 ループ内で ``Paths.downloads()``
    が N 回呼ばれてもレジストリ I/O は最初の一度だけ。 テストで挙動を
    入れ替えるときは内部関数 ``_reset_cached_shell_folders()`` を呼ぶ。

    """

    @staticmethod
    def downloads() -> Path:
        """ダウンロードフォルダのパスを返す（レジストリ解決、結果はキャッシュ）。"""
        return _get_shell_folder(_DOWNLOADS_GUID, Path.home() / "Downloads")

    @staticmethod
    def desktop() -> Path:
        """デスクトップのパスを返す（OneDrive リダイレクトにも追従する、結果はキャッシュ）。"""
        return _get_shell_folder("Desktop", Path.home() / "Desktop")

    @staticmethod
    def temp_dir() -> Path:
        """システムの一時フォルダのパスを返す。

        ``tempfile.gettempdir()`` 自体が **プロセス内で1度だけ解決して
        キャッシュ** しているので、ここではそれをそのまま ``Path`` に包むだけ。
        標準ライブラリ側のキャッシュに乗せてもらっているので、 ラッパ側で
        さらにキャッシュする必要は無い。
        """
        return Path(tempfile.gettempdir())


# ── レジストリ結果のモジュールレベル遅延キャッシュ ────────────────────────────
# ``Paths.downloads()`` が呼ばれるたびに ``winreg.OpenKey`` + ``QueryValueEx`` を
# 実行すると、 例えば ``for report in reports: p = Paths.downloads() / report``
# のような業務フローで N 件のレポートごとにレジストリ I/O が走る。 フォルダの
# 場所はプロセスが生きている間に変わらないので、 **モジュールレベル**で
# ``value_name → Path`` の 1 度だけのキャッシュにする。 ``Config`` や
# ``load_master`` で使ったのと同じ「呼び出しごとに外部リソースへ触らない」
# 方針の延長。
#
# ``temp_dir()`` は ``tempfile.gettempdir()`` が標準ライブラリ側で
# キャッシュしているので、 ラッパ側でさらにキャッシュする必要は無い。
_shell_folder_cache: dict[str, Path] = {}


def _get_shell_folder(value_name: str, default: Path) -> Path:
    """レジストリから特殊フォルダの実際のパスを取得する（結果はキャッシュ）。

    キャッシュの無効化条件:
    - **プロセスが生きている間は値を返し続ける**。 「ログオン中のセッションで
      場所が変わる」という業務シナリオは想定しない。 変わったら
      ``_reset_cached_shell_folders()`` を呼んでからアクセスする。
    - 取得できなかったときは ``default`` を返し、 その結果もキャッシュする
      （OSError が出続ける環境で毎回走らせない）。
    - ``stat()`` による更新確認はしない（業務ツールは実行中のフォルダ移動を
      想定しない。 ``Config`` と同じ理由:  1 回 25 マイクロ秒、共有サーバー
      ではネットワーク往復）。
    - キャッシュが増え続けないことの担保:  ``downloads()`` と ``desktop()``
      からしか呼ばれず、 値も固定 GUID / "Desktop" の 2 種類しか入らないので
      上限を気にする必要は無い。
    """
    if value_name in _shell_folder_cache:
        return _shell_folder_cache[value_name]
    path = _read_shell_folder(value_name, default)
    _shell_folder_cache[value_name] = path
    return path


def _read_shell_folder(value_name: str, default: Path) -> Path:
    """Windows の特殊フォルダの実際の場所をレジストリから取得する（キャッシュ無し）。

    OneDrive の「既知のフォルダーの移動」やユーザーによる場所変更で
    Desktop / Downloads が C:\\Users\\xxx 直下にないことがあるため、
    Path.home() 決め打ちではなくレジストリを見る。取得できなければ default を返す。
    """
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            raw, _ = winreg.QueryValueEx(key, value_name)
        return Path(os.path.expandvars(raw))
    except (OSError, ImportError):
        return default


def _reset_cached_shell_folders() -> None:
    """**レジストリ解決のキャッシュを破棄する**（テスト用）。

    テストで別のレジストリ値を偽装したいケースに備えて用意している。 普通の
    利用では呼ぶ必要は無い（フォルダの場所は実行中に変わらない）。
    """
    _shell_folder_cache.clear()
