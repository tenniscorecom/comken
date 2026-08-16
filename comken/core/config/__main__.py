"""comken/core/config/__main__.py — ``python -m comken.core.config`` で補完用スタブを生成する。"""

from .stubs import generate_stub

stub_path = generate_stub()
print(f"補完用スタブを生成しました: {stub_path.resolve()}")
print("以後は Config() を呼ぶたびに自動更新されます。")
