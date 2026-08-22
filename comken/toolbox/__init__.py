"""comken/toolbox/__init__.py — 何かを操作する・通信するための部品。

Excel・CSV・Access・Outlook・Windows・ブラウザ・Salesforce・社内 RPA 基盤など、
**外にあるものを触る道具**をここに置く。相手が社内のものかどうかは問わない
（社内 RPA 基盤も「呼び出すための部品」なのでここに入る）。

    from comken.toolbox.excel import Excel
    from comken.toolbox.csv import CSV

ここに置かないもの:

- **設定・実行モード・ログ・状態・例外・定数** は comken 直下に置く。
  何を操作するかに関係なく使うため（`from comken.exceptions import ComkenError`）。
- **外を触らない汎用部品**（ファイル操作・文字列操作・日時・待機など）は
  comken/core/ に置く（利用者は ``from comken import ...`` の facade 経由で取る）。
- **社内の決まりに沿って部品を組み合わせた仕組み** は comken/services/ に置く。
"""

from comken.core.table.model import Table
from comken.core.table.transfer import Transfer

__all__ = ["Table", "Transfer"]
