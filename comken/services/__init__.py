"""comken/services/__init__.py — core / toolbox の機能を組み合わせて、
まとまった業務処理を実現する場所。

`toolbox/` は Salesforce API クライアントのような単一領域の薄い部品を置く。
`services/` は Excel 入力・スケジュール判定・通知・ファイル配置など **複数領域を
組み合わせた業務処理**、または **会社・組織で決まる業務固有のデータ**
（列名・IDのリスト等）を持つ処理の置き場所として棲み分けている。
使う人が1人か複数かは問わない（利用者の数は services に置く条件ではない）。

    services/salesforce_downloader/   Salesforce レポートの集約取得と履歴管理
    services/csv_column_reducer.py    応需CSVの新ロール→旧ロール列削減（業務固有の列リストを持つ）

判別の基準:

- toolbox の1クライアント・1ライブラリだけで完結するなら toolbox に置く
- 複数の業務領域（外部 API + Excel + CSV など）を組み合わせて1つの業務フロー
  になる、または業務固有のデータ（会社・組織で決まる列名・IDなど）を
  持つなら services に置く
"""
