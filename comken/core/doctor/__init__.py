"""comken/core/doctor/__init__.py — 環境の切り分け診断

``python -m comken doctor`` の本体と、ライブラリ関数 ``doctor()`` を提供する。

    from comken import doctor, DoctorResult

    results = doctor()         # 環境・依存・設定・接続を一括検査
    for r in results:
        print(r.name, r.status, r.message)

「動かない」の切り分けを 1 コマンドに集約するのが目的で、非エンジニアに
「これを打って結果を送って」と言える形にする。

**``doctor()`` は cli.py に置く。** toolbox / services への依存が要るため、
runner.py（純粋検査）に置くと core → toolbox / services の層違反になる。
cli は CLI 入口なので依存してもよい。
"""

from comken.core.doctor.runner import DoctorResult, summarize

__all__ = ["DoctorResult", "summarize"]
