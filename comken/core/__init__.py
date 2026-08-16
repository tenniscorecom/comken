"""comken/core/__init__.py — 直下にだけ依存する部品を置く場所。

`comken.core` には、外側（ファイル・Excel・ブラウザ・Salesforce 等）を触らない
純粋な部品だけを置く。logger / state / config / utils（clock / files など）が
ここに入る。外に触る道具は toolbox に置く。

入口を増やさないため、再エクスポートは行わない。
利用側は ``from comken.core.utils.files import ...`` のように深いパスで読む。
"""
