"""comken/core/file/__init__.py — ファイル操作の公開窓口

``comken/core/files/``（plural、フォルダ・コピー等の汎用 I/O）とは別に、
``file/``（singular、業務自動化の頻出パターンのみの薄い窓口）を置く。

    from comken.core.file import wait_for_file

ここには「``comken.core`` の facade に上げるほどではないが、業務スクリプトが
毎回書くのはしんどい」ものを集約する。``wait_for_file`` が第一号。
"""

from comken.core.file.wait import wait_for_file

__all__ = ["wait_for_file"]
