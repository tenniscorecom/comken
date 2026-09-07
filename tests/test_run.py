"""comken.run の動作を確認する。

`comken.run.backoffice` / `comken.run.intranet` は、社内 RPA 基盤の最小実装。
`main()` を呼んでその戻り値をそのまま返すだけ。``project_name`` は
呼び出し規約（シグネチャ）を保つために受け取るが、現状では未使用。
"""

from __future__ import annotations

from unittest import mock

import pytest

from comken.run import backoffice, intranet


class TestBackoffice:
    """`backoffice` のテスト。"""

    def test_calls_main_and_returns_its_result(self) -> None:
        """`main()` を呼んで、その戻り値をそのまま返す。"""
        sentinel_main = mock.Mock(return_value="ok")
        result = backoffice(sentinel_main, "project")
        sentinel_main.assert_called_once_with()
        assert result == "ok"

    def test_main_is_actually_invoked(self) -> None:
        """`main` が呼ばれないと結果が決まらない（Mock の呼び出し回数で担保）。"""
        not_called_main = mock.Mock()
        backoffice(not_called_main, "project")
        assert not_called_main.call_count == 1

    def test_exception_in_main_propagates_unchanged(self) -> None:
        """`main` 内で出た例外は変換されず、そのまま呼び出し側へ伝わる。"""
        boom_main = mock.Mock(side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            backoffice(boom_main, "project")


class TestIntranet:
    """`intranet` のテスト。"""

    def test_calls_main_and_returns_its_result(self) -> None:
        """`main()` を呼んで、その戻り値をそのまま返す。"""
        sentinel_main = mock.Mock(return_value="ok")
        result = intranet(sentinel_main, "project")
        sentinel_main.assert_called_once_with()
        assert result == "ok"

    def test_main_is_actually_invoked(self) -> None:
        """`main` が呼ばれないと結果が決まらない（Mock の呼び出し回数で担保）。"""
        not_called_main = mock.Mock()
        intranet(not_called_main, "project")
        assert not_called_main.call_count == 1

    def test_exception_in_main_propagates_unchanged(self) -> None:
        """`main` 内で出た例外は変換されず、そのまま呼び出し側へ伝わる。"""
        boom_main = mock.Mock(side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            intranet(boom_main, "project")


@pytest.mark.parametrize(
    "project_name",
    ["", "ascii-name", "日本語のプロジェクト名"],
)
def test_project_name_is_accepted_for_backoffice(project_name: str) -> None:
    """`project_name` が何の値でもエラーにならない（型を問わない）。"""
    sentinel_main = mock.Mock(return_value=None)
    assert backoffice(sentinel_main, project_name) is None


@pytest.mark.parametrize(
    "project_name",
    ["", "ascii-name", "日本語のプロジェクト名"],
)
def test_project_name_is_accepted_for_intranet(project_name: str) -> None:
    """`intranet` も `project_name` が何の値でもエラーにならない。"""
    sentinel_main = mock.Mock(return_value=None)
    assert intranet(sentinel_main, project_name) is None
