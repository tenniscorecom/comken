"""README・ドキュメント内の python コードブロックが構文として壊れていないか検証する。

サンプルコードは環境（Excel・ブラウザ）がないと実行まではできないため、
ここでは compile() による構文チェックを行う（タイプミス・インデント崩れ・未閉じ括弧を検出）。
実際に動くことの担保は test_examples.py（オフライン例の実行）が担う。
"""

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_DOCS = [_ROOT / "README.md", _ROOT / "examples" / "README.md", *(_ROOT / "docs").glob("*.md")]

_CODE_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _python_blocks() -> list:
    blocks = []
    for doc in _DOCS:
        if not doc.exists():
            continue
        for i, match in enumerate(_CODE_BLOCK.finditer(doc.read_text(encoding="utf-8"))):
            blocks.append(pytest.param(match.group(1), id=f"{doc.name}#{i + 1}"))
    return blocks


@pytest.mark.parametrize("code", _python_blocks())
def test_python_code_block_compiles(code):
    """ドキュメントの ```python ブロックが構文エラーなくコンパイルできる。"""
    # 抜粋（... で省略した）説明用スニペットは構文が通らないので対象外にする
    if "..." in code:
        pytest.skip("説明用の抜粋スニペット")
    compile(code, "<doc>", "exec")
