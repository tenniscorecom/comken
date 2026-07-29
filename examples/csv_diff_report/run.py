"""
サンプル: 昨日と今日の CSV を比較して差分レポート（Excel）を作る

「毎日更新されるデータの変更点だけ知りたい」という定番処理を動かす。
diff_rows で追加・削除・変更を検出し、区分ごとに色分けした Excel レポートにまとめる。

実行方法:
    リポジトリのルートで python -m examples.csv_diff_report.run

実行の流れ（外部システム・ネット接続は不要）:
    1. サンプルデータを output/ に生成する（名簿_昨日.csv と 名簿_今日.csv）
    2. diff_rows で社員番号をキーに突合し、追加・削除・変更を検出する
    3. 区分（追加=緑 / 削除=赤 / 変更=黄）で色分けした Excel レポートを出力する
"""

import logging
from pathlib import Path

from comken.constants import Color
from comken.csv import CsvReader, CsvWriter
from comken.excel import ExcelWriter
from comken.utils import diff_rows
from comken.utils.files import DateNameBuilder

HERE = Path(__file__).parent
OUTPUT_FOLDER = HERE / "output"
YESTERDAY_CSV = OUTPUT_FOLDER / "名簿_昨日.csv"
TODAY_CSV = OUTPUT_FOLDER / "名簿_今日.csv"

SHEET = "Sheet1"
HEADER_ROW = 1
KEY = "社員番号"

STATUS_COL = "区分"
DETAIL_COL = "変更内容"
STATUS_ADDED = "追加"
STATUS_REMOVED = "削除"
STATUS_CHANGED = "変更"
REPORT_HEADERS = [STATUS_COL, KEY, "氏名", "部署", DETAIL_COL]
FILL_COLORS = {
    STATUS_ADDED: Color.LIGHT_GREEN,
    STATUS_REMOVED: Color.RED,
    STATUS_CHANGED: Color.YELLOW,
}

# サンプル用のデータ（今日は 002 の部署が変わり、003 が消え、004 が増えている）
YESTERDAY_ROWS = [
    {"社員番号": "001", "氏名": "山田 太郎", "部署": "営業部"},
    {"社員番号": "002", "氏名": "佐藤 花子", "部署": "総務部"},
    {"社員番号": "003", "氏名": "田中 一郎", "部署": "開発部"},
]
TODAY_ROWS = [
    {"社員番号": "001", "氏名": "山田 太郎", "部署": "営業部"},
    {"社員番号": "002", "氏名": "佐藤 花子", "部署": "経理部"},
    {"社員番号": "004", "氏名": "鈴木 次郎", "部署": "営業部"},
]

logger = logging.getLogger(__name__)


def create_sample_files() -> None:
    """入力になる CSV を生成する（サンプルを自己完結させるための準備処理）。"""
    fieldnames = list(YESTERDAY_ROWS[0].keys())
    CsvWriter(YESTERDAY_CSV, fieldnames=fieldnames).write_rows(YESTERDAY_ROWS)
    CsvWriter(TODAY_CSV, fieldnames=fieldnames).write_rows(TODAY_ROWS)


def main() -> None:
    create_sample_files()

    before = CsvReader(YESTERDAY_CSV).rows()
    after = CsvReader(TODAY_CSV).rows()

    # キー列で突合して差分を取る（added / removed / changed に分かれて返る）
    result = diff_rows(before, after, key=KEY)
    logger.info(
        "追加 %d 件 / 削除 %d 件 / 変更 %d 件",
        len(result.added),
        len(result.removed),
        len(result.changed),
    )
    if not (result.added or result.removed or result.changed):
        logger.info("差分がないためレポートは作りません")
        return

    # 差分を「区分 + 行データ + 変更内容」の形のレポート行に組み立てる
    report_rows = []
    for row in result.added:
        report_rows.append({STATUS_COL: STATUS_ADDED, DETAIL_COL: "", **row})
    for row in result.removed:
        report_rows.append({STATUS_COL: STATUS_REMOVED, DETAIL_COL: "", **row})
    for change in result.changed:
        # 変わった列だけ「部署: 総務部 → 経理部」の形で並べる
        detail = " / ".join(f"{col}: {old} → {new}" for col, (old, new) in change.columns.items())
        report_rows.append({STATUS_COL: STATUS_CHANGED, DETAIL_COL: detail, **change.after})

    output_path = OUTPUT_FOLDER / DateNameBuilder("差分レポート").suffix()
    with ExcelWriter.create(output_path) as f:
        s = f.sheet(SHEET)
        s.write_table(report_rows, headers=REPORT_HEADERS)
        # 区分セルを色分けする（データはヘッダーの次の行から始まる）
        for i, row in enumerate(report_rows, start=HEADER_ROW + 1):
            s.set_fill(row=i, col=1, color=FILL_COLORS[row[STATUS_COL]])
        s.auto_width()
        s.freeze_header()
        f.save()

    logger.info("差分レポート出力: %s", output_path)


if __name__ == "__main__":
    # ログの設定は社内の共通ライブラリ側で行う。ここでは logging をそのまま使う
    main()
