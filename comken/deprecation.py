"""comken/deprecation.py — 名前変更時の後方互換ヘルパー

comken の公開 API の名前を変更する場合、旧名は削除せずこのヘルパーで警告を出し続ける。
警告は「1バージョンだけ」ではなく、旧名を使うコードが残っている限りずっと出す
（共有サーバーの comken を全プロジェクトが参照するため、静かに壊すことはしない）。

FutureWarning を使う理由:
    DeprecationWarning は Python のデフォルト設定では表示されない。
    FutureWarning はエンドユーザーにも常に表示されるため、
    非エンジニアが実行しても「名前が変わった」ことに気づける。

使い方（関数・クラスの改名時、モジュールの末尾に書く）:
    from comken.deprecation import warn_renamed

    def old_function(*args, **kwargs):
        warn_renamed("old_function", "new_function")
        return new_function(*args, **kwargs)

使い方（モジュール属性の改名時、__getattr__ で残す）:
    def __getattr__(name):
        if name == "OldClass":
            warn_renamed("OldClass", "NewClass")
            return NewClass
        raise AttributeError(name)
"""

from __future__ import annotations

import warnings


def warn_renamed(old_name: str, new_name: str) -> None:
    """旧名が使われたときに、新しい名前への書き換えを促す警告を出す。

    Args:
        old_name: 変更前の名前（関数名・クラス名・引数名など）。
        new_name: 変更後の名前。
    """
    warnings.warn(
        f"{old_name} は {new_name} に名前が変わりました。"
        f"動作しますが、コードを {new_name} に書き換えてください。",
        FutureWarning,
        stacklevel=3,
    )
