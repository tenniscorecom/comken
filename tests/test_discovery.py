"""comken.core.discovery のテスト。

``find_subclasses`` は ``pkgutil.walk_packages`` で走査する関係上、テスト用に
一時パッケージを**実ファイル**で作り、``sys.path`` へ追加して ``importlib.invalidate_caches()``
で再走査させる。``_Base`` 相当の基底クラスは一時パッケージ側に置いて、
そのパッケージ内のサブクラス定義と ``find_subclasses`` の出力を比較する。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from comken.core import discovery


def _write(path: Path, source: str) -> None:
    """``path`` を UTF-8 で書き、``importlib.invalidate_caches()`` を呼ぶ。"""
    path.write_text(source, encoding="utf-8")
    importlib.invalidate_caches()


@pytest.fixture
def tmp_pkg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """``sys.path`` に ``tmp_path`` を足し、その直下に ``testpkg/``（空の ``__init__.py``）
    と ``testpkg/base.py``（``class Base``）を置く。``testpkg.Base`` を ``Base``
    として ``yield`` する。サブクラスはこの ``Base`` を継承して書く。

    **重要**: 各テストで ``tmp_path`` が新しくなる。前のテストで ``testpkg`` が
    ``sys.modules`` に残っていると、別の ``tmp_path`` の同名パッケージへ到達
    できなくなるため、フィクスチャの先頭／末尾で必ず削除する。
    """
    # 前のテストの残骸を取り除く（同名パッケージ・別 tmp_path の衝突を防ぐ）
    _purge_testpkg_from_sys_modules()
    importlib.invalidate_caches()

    pkg_dir = tmp_path / "testpkg"
    pkg_dir.mkdir()
    _write(pkg_dir / "__init__.py", "")
    _write(pkg_dir / "base.py", "class Base:\n    pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    pkg = importlib.import_module("testpkg")
    base_module = importlib.import_module("testpkg.base")
    yield pkg_dir, pkg, base_module.Base
    # このテストで読み込んだ testpkg.* を片付ける
    _purge_testpkg_from_sys_modules()
    importlib.invalidate_caches()


def _purge_testpkg_from_sys_modules() -> None:
    """``testpkg`` と ``testpkg.*`` を ``sys.modules`` から除く。"""
    for mod_name in [
        name for name in sys.modules if name == "testpkg" or name.startswith("testpkg.")
    ]:
        del sys.modules[mod_name]


class TestHappyPath:
    """基本動作（置いたクラスの拾い上げ）。"""

    def test_picks_up_class_in_top_level_module(self, tmp_pkg):
        """トップレベルに置いた ``.py`` のクラスが拾われる。"""
        pkg_dir, pkg, base_cls = tmp_pkg
        _write(
            pkg_dir / "alpha.py",
            "from testpkg.base import Base\nclass Alpha(Base):\n    pass\n",
        )
        classes = discovery.find_subclasses(pkg, base_cls)
        assert classes == (importlib.import_module("testpkg.alpha").Alpha,)

    def test_picks_up_class_in_subpackage(self, tmp_pkg):
        """サブパッケージ内の ``.py`` のクラスも拾われる（再帰）。"""
        pkg_dir, pkg, base_cls = tmp_pkg
        sub = pkg_dir / "sub"
        sub.mkdir()
        _write(sub / "__init__.py", "")
        _write(
            sub / "beta.py",
            "from testpkg.base import Base\nclass Beta(Base):\n    pass\n",
        )
        classes = discovery.find_subclasses(pkg, base_cls)
        assert classes == (importlib.import_module("testpkg.sub.beta").Beta,)

    def test_does_not_pick_up_unrelated_class(self, tmp_pkg):
        """``base`` ではない継承元（``object`` だけのクラス）は拾われない。"""
        pkg_dir, pkg, base_cls = tmp_pkg
        _write(
            pkg_dir / "plain.py",
            "class Plain:\n    pass\n",
        )
        assert discovery.find_subclasses(pkg, base_cls) == ()

    def test_does_not_pick_up_base_itself(self, tmp_pkg):
        """``base`` 自身は結果に含めない。"""
        _, pkg, base_cls = tmp_pkg
        classes = discovery.find_subclasses(pkg, base_cls)
        assert base_cls not in classes
        assert classes == ()


class TestUnderscoreExclusion:
    """名前のどこかの階層が ``_`` で始まるモジュール／パッケージは対象外。"""

    def test_skips_module_starting_with_underscore(self, tmp_pkg):
        """``_skipped.py`` は走査対象外（import すらされない）。"""
        pkg_dir, pkg, base_cls = tmp_pkg
        _write(
            pkg_dir / "_skipped.py",
            "from testpkg.base import Base\nclass Skipped(Base):\n    pass\n",
        )
        assert "_skipped" not in sys.modules
        assert discovery.find_subclasses(pkg, base_cls) == ()
        assert "testpkg._skipped" not in sys.modules

    def test_skips_subpackage_starting_with_underscore(self, tmp_pkg):
        """``_internal/`` のようなサブパッケージも対象外。"""
        pkg_dir, pkg, base_cls = tmp_pkg
        sub = pkg_dir / "_internal"
        sub.mkdir()
        _write(sub / "__init__.py", "")
        _write(
            sub / "thing.py",
            "from testpkg.base import Base\nclass Thing(Base):\n    pass\n",
        )
        assert discovery.find_subclasses(pkg, base_cls) == ()

    def test_picks_up_nested_underscore_segment(self, tmp_pkg):
        """途中の階層（サブパッケージ名）が ``_`` 始まりなら、その中は対象外。"""
        pkg_dir, pkg, base_cls = tmp_pkg
        sub = pkg_dir / "sub"
        sub.mkdir()
        _write(sub / "__init__.py", "")
        _write(
            sub / "_nested.py",
            "from testpkg.base import Base\nclass Nested(Base):\n    pass\n",
        )
        # ``sub/__init__.py`` には何も書かない → 何も拾われない
        assert discovery.find_subclasses(pkg, base_cls) == ()


class TestImportedOnlyClass:
    """他モジュールから ``from ... import`` しただけのクラスは拾わない。"""

    def test_imported_only_class_is_excluded(self, tmp_pkg):
        """``definitions.py`` で定義された ``Real`` は拾われるが、
        ``importer.py`` から ``from definitions import Real`` しただけでは拾わない。
        """
        pkg_dir, pkg, base_cls = tmp_pkg
        _write(
            pkg_dir / "definitions.py",
            "from testpkg.base import Base\nclass Real(Base):\n    pass\n",
        )
        _write(
            pkg_dir / "importer.py",
            "from testpkg.definitions import Real\n",
        )
        classes = discovery.find_subclasses(pkg, base_cls)
        # ``Real`` は ``definitions`` にだけ登録され、件数は 1
        assert len(classes) == 1
        assert classes[0].__name__ == "Real"
        assert classes[0].__module__ == "testpkg.definitions"


class TestIncludeFilter:
    """``include`` コールバックでフィルタする。"""

    def test_include_excludes_classes_by_predicate(self, tmp_pkg):
        """``include`` が False を返したクラスは結果から除かれる。"""
        pkg_dir, pkg, base_cls = tmp_pkg
        _write(
            pkg_dir / "named.py",
            "from testpkg.base import Base\nclass Named(Base):\n    NAME = 'named'\n    pass\n",
        )
        _write(
            pkg_dir / "unnamed.py",
            "from testpkg.base import Base\nclass Unnamed(Base):\n    NAME = ''\n    pass\n",
        )
        classes = discovery.find_subclasses(
            pkg, base_cls, include=lambda cls: bool(getattr(cls, "NAME", ""))
        )
        names = [cls.__name__ for cls in classes]
        assert names == ["Named"]

    def test_include_none_keeps_all(self, tmp_pkg):
        """``include=None``（既定）はフィルタなしで全件返す。"""
        pkg_dir, pkg, base_cls = tmp_pkg
        _write(
            pkg_dir / "a.py",
            "from testpkg.base import Base\nclass A(Base):\n    pass\n",
        )
        _write(
            pkg_dir / "b.py",
            "from testpkg.base import Base\nclass B(Base):\n    pass\n",
        )
        classes = discovery.find_subclasses(pkg, base_cls)
        assert {cls.__name__ for cls in classes} == {"A", "B"}


class TestOrder:
    """並び順の決定性（モジュール完全名の昇順・同一モジュール内は定義順）。"""

    def test_module_order_is_alphabetical(self, tmp_pkg):
        """複数ファイルのクラスはモジュール完全名の昇順で返る。"""
        pkg_dir, pkg, base_cls = tmp_pkg
        for stem in ("zebra", "apple", "mango"):
            _write(
                pkg_dir / f"{stem}.py",
                f"from testpkg.base import Base\nclass {stem.capitalize()}(Base):\n    pass\n",
            )
        classes = discovery.find_subclasses(pkg, base_cls)
        assert [cls.__module__ for cls in classes] == [
            "testpkg.apple",
            "testpkg.mango",
            "testpkg.zebra",
        ]

    def test_definition_order_within_module(self, tmp_pkg):
        """同一モジュール内で複数定義したときの定義順（``vars(module)`` 順）。"""
        pkg_dir, pkg, base_cls = tmp_pkg
        _write(
            pkg_dir / "many.py",
            (
                "from testpkg.base import Base\n"
                "class First(Base):\n    pass\n"
                "class Second(Base):\n    pass\n"
                "class Third(Base):\n    pass\n"
            ),
        )
        classes = discovery.find_subclasses(pkg, base_cls)
        assert [cls.__name__ for cls in classes] == ["First", "Second", "Third"]

    def test_order_is_stable_across_calls(self, tmp_pkg):
        """入力が同じなら、毎回まったく同じ順序で返る（決定的）。"""
        pkg_dir, pkg, base_cls = tmp_pkg
        for stem in ("a", "b", "c"):
            _write(
                pkg_dir / f"{stem}.py",
                f"from testpkg.base import Base\nclass {stem.upper()}(Base):\n    pass\n",
            )
        first = discovery.find_subclasses(pkg, base_cls)
        second = discovery.find_subclasses(pkg, base_cls)
        assert first == second


class TestImplementationBreaks:
    """実装の特定チェックを「壊した」バージョンを作って、既存テストが落ちることを確かめる。"""

    def test_underscore_check_matters(self, tmp_pkg):
        """``_`` 始まりの除外を外すと、``TestUnderscoreExclusion`` が落ちる。"""

        def broken_find_subclasses(package, base, *, include=None):
            # ``_`` 始まりの除外を意図的に外した壊れた版
            import importlib
            import pkgutil

            found: list[type] = []
            for module_info in pkgutil.walk_packages(
                package.__path__, prefix=package.__name__ + "."
            ):
                module = importlib.import_module(module_info.name)
                for cls in vars(module).values():
                    if not isinstance(cls, type) or not issubclass(cls, base) or cls is base:
                        continue
                    if cls.__module__ != module.__name__:
                        continue
                    if include is not None and not include(cls):
                        continue
                    found.append(cls)
            return tuple(found)

        pkg_dir, pkg, base_cls = tmp_pkg
        _write(
            pkg_dir / "_skipped.py",
            "from testpkg.base import Base\nclass Skipped(Base):\n    pass\n",
        )
        # 壊れた版は ``_skipped.py`` まで拾ってしまう
        broken_result = broken_find_subclasses(pkg, base_cls)
        real_result = discovery.find_subclasses(pkg, base_cls)
        assert len(broken_result) > len(real_result)
        # 本物は除外できている
        assert real_result == ()

    def test_module_check_matters(self, tmp_pkg):
        """``cls.__module__ == module.__name__`` を外すと、imported-only が拾われる。"""
        pkg_dir, pkg, base_cls = tmp_pkg
        _write(
            pkg_dir / "definitions.py",
            "from testpkg.base import Base\nclass Real(Base):\n    pass\n",
        )
        _write(
            pkg_dir / "importer.py",
            "from testpkg.definitions import Real\n",
        )

        def broken_find_subclasses(package, base, *, include=None):
            # ``__module__`` 判定を意図的に外した壊れた版
            import importlib
            import pkgutil

            found: list[type] = []
            for module_info in pkgutil.walk_packages(
                package.__path__, prefix=package.__name__ + "."
            ):
                module_name = module_info.name
                if any(seg.startswith("_") for seg in module_name.split(".")):
                    continue
                module = importlib.import_module(module_name)
                for cls in vars(module).values():
                    if not isinstance(cls, type) or not issubclass(cls, base) or cls is base:
                        continue
                    if include is not None and not include(cls):
                        continue
                    found.append(cls)
            return tuple(found)

        broken_result = broken_find_subclasses(pkg, base_cls)
        # 壊れた版は ``Real`` を2回拾う（definitions で1回・importer で再 import した1回）
        assert len(broken_result) == 2
        # 本物は definitions からの1件だけ（``__module__`` 判定で importer 側を除外）
        real_result = discovery.find_subclasses(pkg, base_cls)
        assert len(real_result) == 1
        assert real_result[0].__module__ == "testpkg.definitions"
