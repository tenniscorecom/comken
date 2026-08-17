"""comken/core/config/cli.py — ``python -m comken config`` から呼ばれる本体。

旧 ``python -m comken.core.config`` は廃止。入口は ``python -m comken`` に
集約したので、このファイルは直接実行されない（``__main__.py`` ではないため）。

このファイルが持つもの:
- `main()` — 補完用スタブを生成して終了コードを返す（``comken/__main__.py`` から呼ばれる）
"""

from comken.core.config.stubs import generate_stub


def main(_argv: list[str] | None = None) -> int:
    """補完用スタブを生成する。

    Args:
        _argv: 受け取っておくが中身は使わない（``comken/__main__.py`` との
            インタフェースを揃えるため）。

    Returns:
        常に 0。
    """
    stub_path = generate_stub()
    print(f"補完用スタブを生成しました: {stub_path.resolve()}")
    print("以後は Config() を呼ぶたびに自動更新されます。")
    return 0
