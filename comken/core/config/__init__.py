"""comken/core/config/__init__.py — INI ファイル読み込みユーティリティ（公開 API 入口）

config.ini を読み込み、config.SECTION.KEY の形式でアクセスできる Config クラスを提供する。

いちばん簡単な使い方（プロジェクトに src/config.py を作らなくてよい）:

    from comken import config
    path = config.FILES.INPUT_FOLDER / config.FILES.CSV_EAST

    → 初回アクセス時にプロジェクトディレクトリの config.ini を1度だけ読む（遅延読み込み）。
      別の場所にある config.ini を読むときも ``Config(path)`` でよく、
      同じパスなら **同じインスタンスが返る**（プロセス内で1度だけ読む。
      同じパスのファイルを書き換えても自動では反映されない。反映するには
      新しいプロセスを起動する）。

明示的にインスタンスを持ちたい場合:

    from comken.core.config import Config
    config = Config()                 # または Config("path/to/config.ini")

エディタの補完候補:
    属性は実行時に動的に作られるため、そのままではエディタが補完できないが、
    ``Config()`` を呼ぶと**同じパスにつきプロセス内で 1 回**だけ補完用の
    スタブ（src/config.pyi）が自動更新される。 1度スクリプトを実行すれば
    ``config.SECTION.KEY`` が型付きで補完されるようになる。 config.ini を
    書き換えたら次の実行で追随する（実行中のプロセスはキャッシュ済みなので
    自動では反映されない。 反映したいときは新しいプロセスを起動する）。

※ ブラウザの設定は config.ini ではなく BrowserOptions のインスタンス
   （src/browser_options.py）で行う。config はブラウザ設定を持たない。

# `__getattr__` による遅延読み込みがなぜこの形か
``from comken import config`` だけで ``Config()`` が走ると config.ini 読み込みと
補完スタブ書き込みが必ず発生する。 ``__init__.py`` の ``__getattr__`` は
``config.SECTION`` を初めて読んだ瞬間にだけ ``Config()`` を構築する。
``Config`` は通常の属性なので ``__getattr__`` に来ない
（=import だけで config.ini を読まない）。

# `_` プレフィックス付き名を再エクスポートしない理由
実装本体（``comken.core.config.base``）には ``_`` プレフィックス付きの
ヘルパーが多数あるが、 ここでは ``Config`` だけを公開し、
``_`` 付きの内部名は再エクスポートしない。
comken 内部の ``stubs.py`` は ``from comken.core.config.base import _X``
で直接 ``base`` モジュールから取る。 利用者が ``_`` 付き名にアクセスする
経路を残すと「公開 API なのか内部実装なのか」の境界が曖昧になるため、
``__all__`` には載せない方針で揃える。
"""

from __future__ import annotations

from typing import Any

from comken.core.config.base import (
    Config,
    default_config_path,
    get_or_build_config,
)

# ── 公開 API ────────────────────────────────────────────────────────────────
# 利用者が ``from comken.core.config import ...`` で直接取りに来る名前だけを
# 載せる。 ``Config`` が本体。 ``_`` 付きの内部名は載せない。
__all__ = ["Config"]


def __getattr__(name: str) -> Any:
    # PEP 562: `comken.core.config.FILES` のようにモジュール属性として見つからない名前で呼ばれる。
    # セクションは大文字なので、大文字名のときだけ Config() を生成して委譲する
    # （Config のような実体は通常の属性解決で見つかるためここには来ない）。
    # 戻り値は ``Config.__getattr__`` と同じ理由で ``Any``
    # （セクションは config.ini から実行時に作るため）。
    if name.isupper():
        return getattr(get_or_build_config(default_config_path()), name)
    raise AttributeError(f"module 'comken.core.config' has no attribute {name!r}")
