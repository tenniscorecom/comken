"""comken/services/__init__.py — 複数の業務領域を組み合わせた業務ワークフローを置く場所。

`toolbox/` は Salesforce API クライアントのような単一領域の薄い部品を置く。
`services/` は Excel 入力・スケジュール判定・通知・ファイル配置など **複数領域を
組み合わせた業務ワークフローの置き場所** として棲み分けている。

    services/salesforce_downloader/   Salesforce レポートの集約取得と履歴管理

判別の基準:

- toolbox の1クライアント・1ライブラリだけで完結するなら toolbox に置く
- 複数の業務領域（外部 API + Excel + CSV など）を組み合わせて1つの業務フロー
  になるなら services に置く
"""
