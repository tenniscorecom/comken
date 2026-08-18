"""comken/core/result.py — 業務結果を統一的に返す型

業務自動化では、正常終了の中にも「成功 / 警告付き成功 / 対象なし / スキップ」
といった状態が発生する。これらを ``Result`` で揃えて返すことで、呼び出し側が
「成功か失敗か」だけでなく「成功の中での中身」も扱えるようにする。

    from comken.core.result import Result, ok, warn, empty, skip

    def process() -> Result:
        rows = read_rows()
        if not rows:
            return empty("対象データなし")
        return ok("3件処理しました", count=3)

**想定外のエラーは Exception のまま流す。** Result は「想定内の業務結果」
だけを受け持ち、ライブラリ利用者が投げる例外は握りつぶさない。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")

__all__ = [
    "Result",
    "empty",
    "ok",
    "skip",
    "warn",
]


@dataclass(frozen=True)
class Result(Generic[T]):
    """業務結果を統一的に返す型。

    想定内の業務結果（成功・警告・空・スキップ）を Result で返す。
    想定外のエラーは Exception のまま流す (握りつぶさない)。

    Attributes:
        success: 想定内かどうかの成否。警告付き成功も含む正常終了なら True。
        message: 人が読むための1行メッセージ。
        count: 処理件数などの数値情報。省略時 0。
        warnings: 警告メッセージのタプル。1個でもあれば ``has_warning`` が True。
        data: 呼び出し側が結果を運ぶための任意の値（任意型）。
    """

    success: bool
    message: str = ""
    count: int = 0
    warnings: tuple[str, ...] = ()
    data: T | None = None

    @property
    def has_warning(self) -> bool:
        """警告があるかどうか。"""
        return len(self.warnings) > 0

    def to_dict(self) -> dict[str, Any]:
        """JSON シリアライズ用の dict。

        ``data`` は JSON 化できない型が渡される可能性があるので、ここでは
        含めない。``warnings`` は list へ変換する (tuple のままだと
        json.dumps が内部で list へ変換するため、形式を合わせておく)。
        """
        return {
            "success": self.success,
            "message": self.message,
            "count": self.count,
            "warnings": list(self.warnings),
        }


def ok(message: str = "", *, count: int = 0, data: Any = None) -> Result:
    """成功 Result を作る。

    Args:
        message: 人が読むための1行メッセージ（省略可）。
        count: 処理件数などの数値情報（省略時 0）。
        data: 呼び出し側が結果を運ぶための任意の値（省略可）。
    """
    return Result(success=True, message=message, count=count, warnings=(), data=data)


def warn(
    message: str,
    *,
    warnings: Sequence[str] = (),
    count: int = 0,
    data: Any = None,
) -> Result:
    """警告付き成功 Result を作る。success=True だが warnings が付く。

    Args:
        message: 人が読むための1行メッセージ。
        warnings: 警告メッセージの列。空でも Result は生成できる。
        count: 処理件数などの数値情報（省略時 0）。
        data: 呼び出し側が結果を運ぶための任意の値（省略可）。
    """
    return Result(
        success=True,
        message=message,
        count=count,
        warnings=tuple(warnings),
        data=data,
    )


def empty(message: str = "対象データなし", *, count: int = 0) -> Result:
    """空の Result (正常終了・データ無し)。

    Args:
        message: 人が読むための1行メッセージ。省略時は ``"対象データなし"``。
        count: 処理件数（省略時 0）。
    """
    return Result(success=True, message=message, count=count, warnings=(), data=None)


def skip(message: str) -> Result:
    """スキップ Result (今回は処理しなかった)。success=True (スキップは正常)。

    Args:
        message: 人が読むための1行メッセージ。省略不可。
    """
    return Result(success=True, message=message, count=0, warnings=(), data=None)
