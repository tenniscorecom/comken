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

列名の対応表セクション（``[*_MAPPING]``）は ``config.SECTION_MAPPING`` で dict 互換
オブジェクトとして読める。型は ``dict[str, str]`` で、中の値は必ず ``str``。
**列があるかないかを判別したいときは ``in`` を使う**（
``"列名" in config.SECTION_MAPPING``）。
``.get("未知の列")`` は ``str | None`` を返すので ``is None`` で判定できる。
未知のキーを ``["未知の列"]`` で読むと素の ``dict`` と同じく ``KeyError`` になる。
公開型は ``MappingDict``（``from comken.core.config import MappingDict``）で、
``_LenientDict`` は内部実装（``comken.core.config.base`` 内）。

``*_MAPPING`` セクションの **値（対応先）が空欄のときは読み込みエラー**にする
（``ConfigError``）。空欄のまま進めると「対応列の最初の値が
空文字列」と解釈されて、業務データが空欄で書き戻される事故になるため、
書いた人と実行の挙動が乖離しないよう読み込み時点で止める。 ``=`` を
付け忘れた行（``cfg.get()`` が ``None`` を返す行）もまとめて空欄扱いにする。
検知は ``*_MAPPING`` に限るため、通常セクションの ``READ_PASSWORD =`` のように
「設定しない」を示す空欄はそのまま読める。

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
``Config`` / ``MappingDict`` は通常の属性なので ``__getattr__`` に来ない
（=import だけで config.ini を読まない）。

# `_` プレフィックス付き名を再エクスポートしない理由
実装本体（``comken.core.config.base``）には ``_`` プレフィックス付きの
ヘルパーが多数あるが、 ここでは ``Config`` / ``MappingDict`` だけを公開し、
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
    MappingDict,
    _default_config_path,
    _get_or_build_config,
)

# ── 公開 API ────────────────────────────────────────────────────────────────
# 利用者が ``from comken.core.config import ...`` で直接取りに来る名前だけを
# 載せる。 ``Config`` が本体、 ``MappingDict`` は ``[*_MAPPING]`` セクションの
# dict 互換オブジェクトの公開型。 ``_LenientDict`` は ``_`` プレフィックスで
# 内部実装なので載せない（``MappingDict = _LenientDict`` で公開型に昇格済み）。
__all__ = ["Config", "MappingDict"]


def __getattr__(name: str) -> Any:
    # PEP 562: `comken.core.config.FILES` のようにモジュール属性として見つからない名前で呼ばれる。
    # セクションは大文字なので、大文字名のときだけ Config() を生成して委譲する
    # （Config / MappingDict などの実体は通常の属性解決で見つかるためここには来ない）。
    # 戻り値は ``Config.__getattr__`` と同じ理由で ``Any``
    # （セクションは config.ini から実行時に作るため）。
    if name.isupper():
        return getattr(_get_or_build_config(_default_config_path()), name)
    raise AttributeError(f"module 'comken.core.config' has no attribute {name!r}")
