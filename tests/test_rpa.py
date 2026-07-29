"""社内 RPA 基盤ラッパーのテスト。

社内ライブラリは自宅・CI には存在しないため、偽のモジュールを
sys.modules に差し込んで配線だけを検証する。
"""

import sys
import types

import pytest

from comken import rpa
from comken.exceptions import RpaError, RpaLibraryNotFoundError


@pytest.fixture
def fake_library(monkeypatch):
    """社内ライブラリの形だけを真似たモジュールを差し込む。"""
    calls = []

    def rpta(main, project_name):
        calls.append((main, project_name))
        return main()

    root = types.ModuleType(rpa.LIB_ROOT)
    version = types.ModuleType(f"{rpa.LIB_ROOT}.{rpa.LIB_VERSION}")
    package = types.ModuleType(f"{rpa.LIB_ROOT}.{rpa.LIB_VERSION}.rpa")
    for name in ("backoffice", "intranet"):
        entry = types.SimpleNamespace(rpta=rpta)
        setattr(package, name, entry)

    monkeypatch.setitem(sys.modules, rpa.LIB_ROOT, root)
    monkeypatch.setitem(sys.modules, f"{rpa.LIB_ROOT}.{rpa.LIB_VERSION}", version)
    monkeypatch.setitem(sys.modules, f"{rpa.LIB_ROOT}.{rpa.LIB_VERSION}.rpa", package)
    return calls


class TestRunners:
    """run_backoffice / run_intranet のテスト。"""

    def test_backoffice_passes_main_and_project_name(self, fake_library):
        """main とプロジェクト名がそのまま社内ライブラリへ渡ることを確認する。"""

        def main():
            return "完了"

        assert rpa.run_backoffice(main, "受注取込") == "完了"
        assert fake_library == [(main, "受注取込")]

    def test_intranet_uses_its_own_entry(self, fake_library):
        """イントラネット側も同じ形で呼べることを確認する。"""
        assert rpa.run_intranet(lambda: 1, "社内照会") == 1
        assert fake_library[0][1] == "社内照会"

    def test_project_code_does_not_name_the_library(self):
        """呼び出し側が社内ライブラリ名とバージョンを書かずに済むことを確認する。"""
        # このテスト自体が from comken.rpa import ... だけで完結していることが要件。
        assert hasattr(rpa, "run_backoffice")
        assert hasattr(rpa, "run_intranet")


class TestMissingLibrary:
    """社内ライブラリが無い環境のテスト。"""

    def test_raises_readable_error(self, monkeypatch):
        """社内ライブラリが無いときは対処法を含む例外になることを確認する。"""
        monkeypatch.delitem(sys.modules, rpa.LIB_ROOT, raising=False)
        with pytest.raises(RpaLibraryNotFoundError) as exc:
            rpa.run_backoffice(lambda: None, "受注取込")
        message = str(exc.value)
        assert "PYTHONPATH" in message
        assert "LIB_VERSION" in message

    def test_is_catchable_as_rpa_error(self, monkeypatch):
        """カテゴリ基底クラスでまとめて捕捉できることを確認する。"""
        monkeypatch.delitem(sys.modules, rpa.LIB_ROOT, raising=False)
        with pytest.raises(RpaError):
            rpa.run_intranet(lambda: None, "社内照会")
