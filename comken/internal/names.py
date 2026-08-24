"""comken/internal/names.py — 社内ライブラリ群のルートパッケージ名。

``INTERNAL_LIBRARY_ROOT`` を 1 か所で書き換えれば、 ``RPA_LIBRARY_NAME`` と
``SALESFORCE_LIBRARY_NAME`` の両方が追随する。 配置（共有サーバーへの設置）の
際は [docs/運用/配置.md](../運用/配置.md) の手順に従い、 **この値だけ** を
実名へ差し替える。
"""

from __future__ import annotations

# 社内 LAN 環境にだけ存在する社内ライブラリ群のルートパッケージ名（バージョンを含む）。
# 上がるたびにこの 1 行だけを直せば、 ``RPA_LIBRARY_NAME`` /
# ``SALESFORCE_LIBRARY_NAME`` を通じて全プロジェクトが追随する。
INTERNAL_LIBRARY_ROOT = "example_libs.v0000"

__all__ = ["INTERNAL_LIBRARY_ROOT"]
