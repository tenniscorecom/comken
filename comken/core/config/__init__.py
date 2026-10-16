"""comken/core/config/__init__.py — INI ファイル読み込みユーティリティ（公開 API 入口）

config.ini を読み込み、config.SECTION.KEY の形式でアクセスできる Config クラスを提供する。

いちばん簡単な使い方（プロジェクトに src/config.py を作らなくてよい）:

    from comken import config
    path = config.FILES.INPUT_FOLDER / config.FILES.CSV_EAST

    → 初回アクセス時にプロジェクトディレクトリの config.ini を1度だけ読む（遅延読み込み）。
      別の場所にある config.ini を読むときも ``Config(path)`` でよく、
      同じパスなら **同じインスタンスが返る**（プロセス内で1度だけ読む。
      同じパスのファイルを書き換えても自動では反映されない。反映するには
      ``_reset_cached_config()`` を呼ぶ）。

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
``_LenientDict`` は内部実装。

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
    自動では反映されない。 反映したいときは ``_reset_cached_config()`` を
    呼ぶか、新しいプロセスを起動する）。

※ ブラウザの設定は config.ini ではなく BrowserOptions のインスタンス
   （src/browser_options.py）で行う。config はブラウザ設定を持たない。

# `__getattr__` による遅延読み込みがなぜこの形か
``from comken import config`` だけで ``Config()`` が走ると config.ini 読み込みと
補完スタブ書き込みが必ず発生する。 ``__init__.py`` の ``__getattr__`` は
``config.SECTION`` を初めて読んだ瞬間にだけ ``Config()`` を構築する。
``Config`` / ``MappingDict`` / ``_reset_cached_config`` は通常の属性なので
``__getattr__`` に来ない（=import だけで config.ini を読まない）。
"""

from __future__ import annotations

# ── 実装本体は _impl.py ──
# Config クラス・エラーヘルパー・キャッシュ層（_get_or_build_config / _default_config_path）
# は _impl.py に置く。 ここでは名前を再エクスポートする（comken 内部の
# stubs.py と、外部リポジトリの tests/ が ``from comken.core.config import _X``
# の形で取りに来るための互換性を維持する）。
# ruff が「未使用の import」を出さないよう、 各再エクスポートに ``# noqa: F401`` を付ける。
from comken.core.config._impl import (  # noqa: F401
    _PATH_RESOLUTION_CACHE_MAXSIZE,
    MAPPING_SECTION_SUFFIX,
    Config,
    MappingDict,
    _build_section_map,
    _CaseSensitiveConfigParser,
    _create_from_example,
    _created_from_example_error,
    _default_config_path,
    _get_or_build_config,
    _is_mapping_section,
    _LenientDict,
    _looks_like_path,
    _lower_case_name_error,
    _mapping_empty_value_error,
    _parse_value,
    _path_resolution_cache,
    _path_resolution_cache_get,
    _path_resolution_cache_put,
    _reset_cached_config,
    _section_not_found_error,
    _SectionNamespace,
    _split_list_items,
    _subclassing_not_supported_error,
    _validate_upper_case,
)

# ── 公開 API ────────────────────────────────────────────────────────────────
# 利用者が ``from comken.core.config import ...`` で直接取りに来る名前だけを
# 載せる。 ``Config`` が本体、 ``MappingDict`` は ``[*_MAPPING]`` セクションの
# dict 互換オブジェクトの公開型。 ``_LenientDict`` は ``_`` プレフィックスで
# 内部実装なので載せない（``MappingDict = _LenientDict`` で公開型に昇格済み）。
__all__ = ["Config", "MappingDict"]


def __getattr__(name: str) -> object:
    # PEP 562: `comken.core.config.FILES` のようにモジュール属性として見つからない名前で呼ばれる。
    # セクションは大文字なので、大文字名のときだけ Config() を生成して委譲する
    # （Config / MappingDict などの実体は通常の属性解決で見つかるためここには来ない）。
    if name.isupper():
        return getattr(_get_or_build_config(_default_config_path()), name)
    raise AttributeError(f"module 'comken.core.config' has no attribute {name!r}")
