"""comken/core/result.py — 検査 1 項目の結果を表す共通の型

``python -m comken doctor``（環境の切り分け診断）と ``python -m comken check``
（comken 更新後の破損検査）は、目的は違うが**結果の形はまったく同じ**
（検査名・ok/ng/skip・1行メッセージ・細目）。同じ dataclass を 2 つ書くと、
片方にフィールドを足したときにもう片方が置いていかれるので、ここに 1 つ置く。

    from comken.core.result import CheckResult, summarize

    results = [CheckResult(name="version", status="ok", message="v0.12.0")]
    ok, ng, skip = summarize(results)

``DoctorResult`` は ``CheckResult`` の別名。``from comken import DoctorResult``
が公開 API として先にあったので、名前をそのまま残している。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "CheckResult",
    "CheckStatus",
    "DoctorResult",
    "summarize",
]

# 検査結果の状態。``str`` にすると "OK" や "NG" の打ち間違いが型で止まらないため、
# py.typed を出している以上ここは Literal で固定する
CheckStatus = Literal["ok", "ng", "skip"]


@dataclass(frozen=True)
class CheckResult:
    """検査 1 項目の結果。

    Attributes:
        name: 検査名（例: "version" / "deps.openpyxl" / "share.master_path"）。
        status: 結果（"ok" / "ng" / "skip" のいずれか）。
        message: 人が読むための1行メッセージ。**秘密の値は載せない**。
        details: 検査の細目。1 行に収まらないとき ``message`` の下に並べて出す。
            デフォルトは空タプル（大半の検査は ``message`` 1 行で完結する）。
    """

    name: str
    status: CheckStatus
    message: str
    details: tuple[str, ...] = ()


# ``from comken import DoctorResult`` が先にあったので、公開名はそのまま残す。
# 中身は CheckResult と同一（doctor も「検査」なので、型を分ける理由がない）
DoctorResult = CheckResult


def summarize(results: list[CheckResult]) -> tuple[int, int, int]:
    """``(ok, ng, skip)`` の件数を返す。"""
    ok = sum(1 for r in results if r.status == "ok")
    ng = sum(1 for r in results if r.status == "ng")
    skip = sum(1 for r in results if r.status == "skip")
    return ok, ng, skip
