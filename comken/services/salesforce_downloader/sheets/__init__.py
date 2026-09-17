"""comken/services/salesforce_downloader/sheets/__init__.py — シート単位のモジュール置き場。

ワークブック・CSVの「1枚（1ファイル）」ごとに、そこにある列と意味を宣言する
モジュールを集めている:

    master.py           レポート管理表シート（``ReportEntry``）
    schedule.py         スケジュールシート（``ScheduleRule``）
    group_settings.py   設定シート（``GroupSetting``、出力先のベースパスを管理）
    history.py           履歴CSV（``HistoryRow`` / ``COLUMNS``、読み取り関数）

Excel を読む・雛形を作る共通の仕組み（``MasterRow`` / ``column()``）は
`sheets/` の外、`report_master.py` にある。
"""
