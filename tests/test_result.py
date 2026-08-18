"""``comken.core.result`` のテスト。

Result 型は「想定内の業務結果」を統一的に返すための箱。
ok / warn / empty / skip の各コンストラクタと、Result 自身の
frozen 性と ``to_dict`` の挙動を確かめる。
"""

from __future__ import annotations

import dataclasses

import pytest

from comken.core import empty, ok, skip, warn
from comken.core.result import Result as DirectResult


class TestOk:
    def test_success_true(self) -> None:
        """ok() は success=True で作る。"""
        result = ok()
        assert result.success is True

    def test_default_message_is_empty(self) -> None:
        """ok() はメッセージ省略可。"""
        result = ok()
        assert result.message == ""

    def test_count_can_be_set(self) -> None:
        """count を指定できる。"""
        result = ok("3件処理しました", count=3)
        assert result.count == 3
        assert result.message == "3件処理しました"

    def test_data_can_be_carried(self) -> None:
        """data に任意の値を載せられる。"""
        result = ok("done", data={"rows": [1, 2, 3]})
        assert result.data == {"rows": [1, 2, 3]}

    def test_no_warning(self) -> None:
        """ok() は警告を持たない。"""
        result = ok("完了")
        assert result.has_warning is False
        assert result.warnings == ()


class TestWarn:
    def test_success_is_true(self) -> None:
        """warn() は success=True (警告は成功の中の細分類)。"""
        result = warn("一部スキップしました")
        assert result.success is True

    def test_has_warning_true(self) -> None:
        """warnings を渡すと has_warning が True になる。"""
        result = warn("一部スキップ", warnings=("3行目: 値がありません",))
        assert result.has_warning is True
        assert result.warnings == ("3行目: 値がありません",)

    def test_empty_warnings_list(self) -> None:
        """warnings を渡さなければ has_warning は False。"""
        result = warn("警告なし")
        assert result.has_warning is False

    def test_multiple_warnings(self) -> None:
        """複数の警告を持てる。"""
        result = warn("警告複数", warnings=("w1", "w2", "w3"))
        assert len(result.warnings) == 3

    def test_warnings_stored_as_tuple(self) -> None:
        """warnings は tuple で保持される（frozen な Result に合う形で）。"""
        result = warn("warning", warnings=["a", "b"])
        assert isinstance(result.warnings, tuple)


class TestEmpty:
    def test_success_true(self) -> None:
        """empty() は success=True。"""
        result = empty()
        assert result.success is True

    def test_count_is_zero(self) -> None:
        """empty() は count=0 が既定。"""
        result = empty()
        assert result.count == 0

    def test_default_message(self) -> None:
        """empty() の既定メッセージは「対象データなし」。"""
        result = empty()
        assert result.message == "対象データなし"

    def test_message_override(self) -> None:
        """メッセージは上書きできる。"""
        result = empty("今月の対象データはありません")
        assert result.message == "今月の対象データはありません"


class TestSkip:
    def test_success_true(self) -> None:
        """skip() は success=True (スキップは正常終了)。"""
        result = skip("今日は処理しません")
        assert result.success is True

    def test_message_required(self) -> None:
        """skip() の message は必須。"""
        result = skip("skip理由")
        assert result.message == "skip理由"


class TestResultImmutable:
    def test_frozen_instance_attribute(self) -> None:
        """frozen=True なのでフィールドを書き換えられない。"""
        result = ok("msg")
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.success = False  # type: ignore[misc]

    def test_frozen_dataclass_class_flag(self) -> None:
        """dataclass(frozen=True) で生成されている。"""
        assert dataclasses.is_dataclass(DirectResult)
        # frozen=True かどうかはフィールドが frozen slots を持つかでも分かる
        # ここでは書き換えエラーで確認している（前テスト）

    def test_equal(self) -> None:
        """同じ値を持つ Result は等価。"""
        a = ok("msg", count=2)
        b = ok("msg", count=2)
        assert a == b


class TestToDict:
    def test_returns_json_friendly_dict(self) -> None:
        """to_dict は JSON シリアライズ可能な dict を返す。"""
        result = warn("warn", warnings=("w1", "w2"), count=2)
        d = result.to_dict()
        assert d == {
            "success": True,
            "message": "warn",
            "count": 2,
            "warnings": ["w1", "w2"],
        }

    def test_warnings_become_list(self) -> None:
        """warnings (tuple) は list へ変換される。"""
        result = warn("m", warnings=("a", "b"))
        d = result.to_dict()
        assert isinstance(d["warnings"], list)

    def test_does_not_include_data(self) -> None:
        """to_dict には data を含めない（JSON 化できない型を運べるように）。"""
        # 仮に data に独自クラスを載せても to_dict は落ちない
        result = ok("ok", data=object())
        d = result.to_dict()
        assert "data" not in d


class TestFacadeExports:
    def test_from_comken_core(self) -> None:
        """``comken.core`` から取得できる。"""
        import comken.core

        assert hasattr(comken.core, "Result")
        assert hasattr(comken.core, "ok")
        assert hasattr(comken.core, "warn")
        assert hasattr(comken.core, "empty")
        assert hasattr(comken.core, "skip")
        for name in ("Result", "ok", "warn", "empty", "skip"):
            assert name in comken.core.__all__

    def test_does_not_leak_to_comken_top(self) -> None:
        """comken 直下には漏らさない（facade 拡張方針に従う）。"""
        import comken

        for name in ("Result", "ok", "warn", "empty", "skip"):
            assert name not in comken.__all__
            assert not hasattr(comken, name), f"{name} が comken 直下から取れる"
