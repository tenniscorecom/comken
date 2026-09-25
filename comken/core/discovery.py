"""comken/core/discovery.py — パッケージ内のサブクラスを自動収集する。

``comken.toolbox.salesforce.sites``・``comken.toolbox.browser.sites`` など、
「新しいクラスを 1 つ足したら自動で ``SITES`` に加わる」形にしたいパッケージで
使う共通関数。同じ処理（``pkgutil.walk_packages`` + ``importlib.import_module``
+ ``cls.__module__ == module.__name__`` 判定）を 3 箇所以上で書き散らさないため、
ここに置く。

``include`` 引数で「土台の基底クラス（``NAME`` や ``DOMAIN_URL`` が空のもの）を
除外する」などのフィルタを呼出側が書ける。**重複検査はこの関数には入れない** —
``KEY`` 重複など、用途別の検査は呼び出し側に残す。

``__init__.py`` の中で ``find_subclasses(...)`` を呼んで ``SITES`` を作ると、
配下のモジュールが ``__init__`` の実行中に import される。配下のモジュールから
その ``__init__`` の名前を import すると循環するので、しないこと。
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from types import ModuleType


def find_subclasses[T](
    package: ModuleType,
    base: type[T],
    *,
    include: Callable[[type[T]], bool] | None = None,
) -> tuple[type[T], ...]:
    """``package`` 配下のモジュールを再帰的に走査し、
    ``base`` のサブクラスのうち「そのモジュール自身で定義された」ものを集めて返す。

    Args:
        package: 走査対象の import 済みパッケージ（モジュールオブジェクト）。
            ``pkgutil.walk_packages(package.__path__, prefix=package.__name__ + ".")``
            で**サブパッケージも再帰的に**たどる。
        base: 集める対象の基底クラス。``base`` 自身と、
            ``cls.__module__ != module.__name__`` のクラス（他モジュールから
            ``from ... import`` しただけのクラス）は含まない。
        include: 真偽を返す任意のフィルタ。``False`` を返したクラスは結果から
            除外される。土台の基底クラス（``NAME`` / ``DOMAIN_URL`` が空のもの）
            を除外するのに使う。省略時は常に ``True``。

    Returns:
        見つかったクラスのタプル。並びは**モジュールの完全名の昇順**、
        同一モジュール内は ``vars(module)`` の順（Python 3.7+ の定義順を保持）。
        同じ入力に対して常に同じ順序になる（決定的）。

    Notes:
        - 名前の**どこかの階層**が ``_`` で始まるモジュール・パッケージは除外
          （``_template.py`` / ``_sample/`` など。``__init__`` 自体は対象外＝
          走査しない）
        - 重複検査はこの関数には入れない
        - キャッシュはしない（``importlib.import_module`` は import 済みなら
          ほぼノーコストで返るので、毎回走査し直しても無視できる）
    """
    found: list[type[T]] = []
    for module_info in pkgutil.walk_packages(package.__path__, prefix=package.__name__ + "."):
        module_name = module_info.name
        if any(segment.startswith("_") for segment in module_name.split(".")):
            # ``_template.py`` / ``_sample/`` のような雛形は登録しない
            continue
        module = importlib.import_module(module_name)
        for cls in vars(module).values():
            if not isinstance(cls, type) or not issubclass(cls, base) or cls is base:
                continue
            # 他モジュールから ``from ... import`` しただけのクラスは拾わない
            if cls.__module__ != module.__name__:
                continue
            if include is not None and not include(cls):
                continue
            found.append(cls)
    return tuple(found)
