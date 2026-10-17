"""comken/core/__init__.py — 直下にだけ依存する部品を置く場所。

`comken.core` には、外側（ファイル・Excel・ブラウザ・Salesforce 等）を触らない
純粋な部品だけを置く。logger / state / config / dates / text / diff / columns /
files などがここに入る。外に触る道具は toolbox に置く。

利用者は、その名前を ``__all__`` で公開している **いちばん浅い**
パッケージ・モジュールから取る。

- ``comken`` 直下にあるものは ``from comken import X``（今までどおり）
- それ以外は **その名前を ``__all__`` で公開している、いちばん浅いパッケージか
  モジュールから取る**。例::

      from comken.core.dates import today
      from comken.core.files import project_dir
      from comken.core.table import Table, DiffResult
      from comken.core.text import normalize
      from comken.core.timer import Timer
      from comken.core.wait import wait_until

ライブラリの中（``comken/`` 配下）は定義しているモジュールまで書く
（``from comken.core.text import normalize`` のように）。サブパッケージの
``__init__.py`` 経由で読むと循環 import になりやすい。
"""
