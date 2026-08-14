"""社内 RPA 基盤ラッパーのテスト。

社内ライブラリは自宅・CI には存在しないため、偽のモジュールを
sys.modules に差し込んで配線だけを検証する。
"""

from __future__ import annotations

import sys
import types

import pytest

from comken import run
from comken.exceptions import RpaError, RpaLibraryNotFoundError

# comken/run.py が読む社内ライブラリのパス。実装の import 行と揃える。
LIB_PACKAGE = "example_libs.v0000.rpa"


@pytest.fixture
def fake_library(monkeypatch):
    """社内ライブラリの形だけを真似たモジュールを差し込む。"""
    calls = []

    def rpta(main, project_name):
        calls.append((main, project_name))
        return main()

    package = types.ModuleType(LIB_PACKAGE)
    for name in ("backoffice", "intranet"):
        setattr(package, name, types.SimpleNamespace(rpta=rpta))

    # `from a.b.c import d` は途中のパッケージも解決するため、親も差し込む。
    parts = LIB_PACKAGE.split(".")
    for depth in range(1, len(parts)):
        path = ".".join(parts[:depth])
        monkeypatch.setitem(sys.modules, path, types.ModuleType(path))
    monkeypatch.setitem(sys.modules, LIB_PACKAGE, package)
    return calls


class TestRunners:
    """backoffice / intranet のテスト。"""

    def test_backoffice_passes_main_and_project_name(self, fake_library):
        """main とプロジェクト名がそのまま社内ライブラリへ渡ることを確認する。"""

        def main():
            return "完了"

        assert run.backoffice(main, "受注取込") == "完了"
        assert fake_library == [(main, "受注取込")]

    def test_intranet_uses_its_own_entry(self, fake_library):
        """イントラネット側も同じ形で呼べることを確認する。"""
        assert run.intranet(lambda: 1, "社内照会") == 1
        assert fake_library[0][1] == "社内照会"

    def test_project_code_does_not_name_the_library(self):
        """呼び出し側が社内ライブラリ名とバージョンを書かずに済むことを確認する。"""
        assert hasattr(run, "backoffice")
        assert hasattr(run, "intranet")


class TestMissingLibrary:
    """社内ライブラリが無い環境のテスト。"""

    def test_raises_readable_error(self, monkeypatch):
        """社内ライブラリが無いときは対処法を含む例外になることを確認する。"""
        monkeypatch.delitem(sys.modules, LIB_PACKAGE, raising=False)
        with pytest.raises(RpaLibraryNotFoundError) as exc:
            run.backoffice(lambda: None, "受注取込")
        assert "PYTHONPATH" in str(exc.value)

    def test_is_catchable_as_rpa_error(self, monkeypatch):
        """カテゴリ基底クラスでまとめて捕捉できることを確認する。"""
        monkeypatch.delitem(sys.modules, LIB_PACKAGE, raising=False)
        with pytest.raises(RpaError):
            run.intranet(lambda: None, "社内照会")

    def test_comken_run_is_importable_without_the_library(self):
        """社内ライブラリが無くても comken.run 自体は読み込めることを確認する。"""
        # import を関数の外に出すと、社内ライブラリの無い PC で comken.run が壊れる。
        assert run.__name__ == "comken.run"
