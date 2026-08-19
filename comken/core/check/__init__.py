"""comken/core/check/__init__.py — comken 更新後の破損検査

``python -m comken check`` の検査項目。**純粋ロジックは runner.py**、
CLI の組み立てと表示は cli.py にある（doctor と同じ形）。

    from comken.core.check import check_version, run_all

comken を新しいバージョンへ差し替えたあと、利用プロジェクトが壊れていないかを
確かめるのが目的。環境そのものの切り分けは ``python -m comken doctor`` が担当で、
こちらは「comken を更新したせいで動かなくなっていないか」を見る。
"""

from comken.core.check.runner import (
    CheckResult,
    check_deprecations,
    check_facade,
    check_imports,
    check_pyright,
    check_version,
    summarize,
)

__all__ = [
    "CheckResult",
    "check_deprecations",
    "check_facade",
    "check_imports",
    "check_pyright",
    "check_version",
    "summarize",
]
