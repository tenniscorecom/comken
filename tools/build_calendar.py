"""tools/build_calendar.py — 「会社用カレンダー CSV 1ファイル」を生成するツール。

内閣府の祝日 CSV（``tools/calendar_data/syukujitsu.csv``）と、
ファイル先頭で定義している **会社休日ルール** を合成し、
``comken/core/calendar/data/company_calendar.csv`` を生成する。

生成されたファイルは git 管理下に置かれ、Python 側（``comken.core.calendar``）
と VBA 側の両方が同じファイルを読み取って営業日判定に使う。生成ツールだけが
内閣府 CSV の形式を知っていればよく、実行時は内閣府 CSV も会社休日のルールも
知らずに CSV を判定するだけになる（内閣府 CSV の形式変更は生成ツールだけが
対応すればよい）。

## 使い方

**年 1 回の内閣府 CSV 更新**（毎年 2 月頃、内閣府が翌年分を公表）:

1. 開発機で内閣府から ``syukujitsu.csv`` を取得する
2. ``tools/calendar_data/syukujitsu.csv`` をダウンロードしたファイルで上書きする
3. ``python tools\\build_calendar.py`` を実行して
   ``comken/core/calendar/data/company_calendar.csv`` を再生成する
4. ``syukujitsu.csv`` と ``company_calendar.csv`` の更新をまとめてコミットする

**会社休日を変えるとき**（年末年始休暇の日付を変える等）:

1. このファイル先頭の ``COMPANY_HOLIDAYS`` / ``COMPANY_HOLIDAYS_EXTRA`` を直す
2. ``python tools\\build_calendar.py`` を実行する
3. ``company_calendar.csv`` の更新をコミットする

``--path`` で任意の書き出し先を指定できる（既定は
``comken/core/calendar/data/company_calendar.csv``）。

::

    python tools\\build_calendar.py
    python tools\\build_calendar.py --path tmp/company_calendar.csv
"""

from __future__ import annotations

import argparse
import datetime as _dt
import logging
import sys
from pathlib import Path

# スクリプト実行時に tools/ が sys.path 先頭に入るため、リポジトリルートを
# 明示的に追加して comken を import する
ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comken.core.table.model import Table  # noqa: E402
from comken.toolbox.csv import CSV  # noqa: E402

logger = logging.getLogger(__name__)

# ── 会社休日の定義 ────────────────────────────────────────────────────────
# 毎年繰り返す会社の休業日。**年は書かない**（毎年その月日が休みになる）。
# 休みを増やすときは (月, 日) を書き足すだけでよい。年またぎの年末年始も
# 月日で書けばそのまま毎年適用される。
# ここを変えたら ``python tools\\build_calendar.py`` を実行して
# ``comken/core/calendar/data/company_calendar.csv`` を更新する。
COMPANY_HOLIDAYS: dict[str, tuple[tuple[int, int], ...]] = {
    "年末年始休暇": ((12, 29), (12, 30), (12, 31), (1, 1), (1, 2), (1, 3)),
}

# その年だけの臨時の休み。年月日で書く。
# 例: 2026 年だけ 12/28 も休みにする → date(2026, 12, 28) を足す。
# 古くなった年の行は消してよい（消しても過去の判定が変わるだけで、運用に影響しない）。
COMPANY_HOLIDAYS_EXTRA: tuple[_dt.date, ...] = ()

# ``COMPANY_HOLIDAYS_EXTRA`` に登録された年月日（=年単位の月日ルールに
# 当てはまらない臨時休業日）の名称。
EXTRA_HOLIDAY_NAME: str = "会社休業日"

# ── ファイルパス ────────────────────────────────────────────────────────
# 内閣府 CSV のパス（生成ツールだけの入力）。
SYUKUJITSU_CSV_PATH: Path = Path(__file__).parent / "calendar_data" / "syukujitsu.csv"

# 生成物のパス。comken/core/calendar/data/company_calendar.csv は git 管理下の正本で、
# Python 実行時と VBA 側の両方がここを読む（共有サーバー上の同じファイル）。
COMPANY_CALENDAR_CSV_PATH: Path = (
    ROOT / "comken" / "core" / "calendar" / "data" / "company_calendar.csv"
)

# company_calendar.csv の列名（Python 実行時と VBA の両方が同じ前提で見る）。
CSV_HEADER_DATE = "date"
CSV_HEADER_NAME = "name"


def build_rows() -> list[tuple[_dt.date, str]]:
    """内閣府 CSV と会社休日ルールを合成して、``(date, name)`` のリストを返す。

    国民の祝日（内閣府 CSV 全行）と会社休日（内閣府 CSV の最初の年〜最後の年
    の各年に ``COMPANY_HOLIDAYS`` の月日と ``COMPANY_HOLIDAYS_EXTRA`` を展開）
    をマージし、日付順に並べる。同じ日に国民の祝日と会社休日の両方が当たる
    場合は **国民の祝日が先勝ち**（国民の祝日の名称が採用され、会社休日は
    黙って上書きされない）。土日と重なっても振替は行わない（国民の祝日側で
    処理されないものはそのまま）。

    会社休日の名称は ``COMPANY_HOLIDAYS`` のキー（例: ``"年末年始休暇"``）。
    ``COMPANY_HOLIDAYS_EXTRA`` に登録された年月日は ``EXTRA_HOLIDAY_NAME``
    （既定 ``"会社休業日"``）。

    Returns:
        日付順に並んだ ``(date, name)`` のタプルのリスト。
    """
    national_holidays = _load_national_holidays()
    if not national_holidays:
        raise ValueError(
            f"内閣府 CSV から国民の祝日を 1 件も読み取れませんでした: {SYUKUJITSU_CSV_PATH}"
            "形式が変わっていないか確認してください。"
        )
    first_year, last_year = _year_range(national_holidays)

    merged: dict[_dt.date, str] = dict(national_holidays)
    for year in range(first_year, last_year + 1):
        for name, month_days in COMPANY_HOLIDAYS.items():
            for month, day in month_days:
                target = _dt.date(year, month, day)
                if target not in merged:
                    merged[target] = name
    for target in COMPANY_HOLIDAYS_EXTRA:
        if target not in merged:
            merged[target] = EXTRA_HOLIDAY_NAME

    return sorted(merged.items(), key=lambda item: item[0])


def _load_national_holidays() -> list[tuple[_dt.date, str]]:
    """内閣府の ``syukujitsu.csv`` を読み、国民の祝日を ``(date, name)`` で返す。

    CSV クラス（``comken.toolbox.csv.CSV``）の ``read()`` で読み取り、
    1列目を ``YYYY/M/D`` または ``YYYY-MM-DD`` の ``datetime.date`` へ変換する。
    内閣府以外を読み込もうとして日付が 1 件も取れないケースは呼び出し元
    （``build_rows()``）が検知して止める。
    """
    with CSV(
        SYUKUJITSU_CSV_PATH,
        read_only=True,
        columns=[CSV_HEADER_DATE, CSV_HEADER_NAME],
    ) as csv_file:
        table = csv_file.read()
    rows = table.to_rows()
    holidays: list[tuple[_dt.date, str]] = []
    for row in rows:
        date_text = row[CSV_HEADER_DATE]
        name = row[CSV_HEADER_NAME].strip()
        # 内閣府 CSV の1行目ヘッダー（"国民の祝日・休日月日"）が混入した場合は
        # 日付パースで失敗するのでスキップする。
        try:
            parsed = _parse_date(str(date_text).strip())
        except ValueError:
            continue
        if not name:
            continue
        holidays.append((parsed, name))
    return holidays


def _parse_date(text: str) -> _dt.date:
    """内閣府 CSV の日付セルを ``datetime.date`` に変換する。

    内閣府の現行配布は ``YYYY/M/D``（スラッシュ・ゼロ埋めなし）が中心だが、
    手書き差し替え・テスト fixture では ``YYYY-MM-DD``（ハイフン・ゼロ埋めあり）
    が混ざるので、両方を受け付ける。すべて失敗したら ``ValueError`` を上げる
    （``build_rows()`` 側で「内閣府 CSV として読めない」と検知される）。
    """
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(text, fmt).date()  # noqa: DTZ007  # 業務日付として naive で扱う
        except ValueError:
            continue
    raise ValueError(f"内閣府 CSV の日付を解釈できません: {text!r}")


def _year_range(holidays: list[tuple[_dt.date, str]]) -> tuple[int, int]:
    """国民の祝日のうち最も古い年・最も新しい年を返す。"""
    first = holidays[0][0]
    last = holidays[0][0]
    for date_, _ in holidays[1:]:
        if date_ < first:
            first = date_
        if date_ > last:
            last = date_
    return first.year, last.year


def write_company_calendar_csv(
    rows: list[tuple[_dt.date, str]],
    path: Path = COMPANY_CALENDAR_CSV_PATH,
) -> Path:
    """``(date, name)`` のリストを ``company_calendar.csv`` へ書き出す。

    列は ``date`` / ``name`` の 2 列のみ。``date`` は ``YYYY-MM-DD`` 形式、
    文字コードは **UTF-8 BOM 付き**（Excel・VBA 双方で文字化けしない）。
    日付順に並べて出力する。
    """
    table_rows = [
        {CSV_HEADER_DATE: date_.isoformat(), CSV_HEADER_NAME: name} for date_, name in rows
    ]
    with CSV(
        path,
        columns=[CSV_HEADER_DATE, CSV_HEADER_NAME],
        encoding="utf-8-sig",
    ) as csv_file:
        csv_file.replace(Table([CSV_HEADER_DATE, CSV_HEADER_NAME], table_rows))
    return path


def main() -> None:
    """内閣府 CSV + 会社休日ルール → ``company_calendar.csv`` を生成する。"""
    parser = argparse.ArgumentParser(
        description="内閣府CSVと会社休日ルールを合成して company_calendar.csv を生成する",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=COMPANY_CALENDAR_CSV_PATH,
        help="書き出し先（省略時は comken/core/calendar/data/company_calendar.csv）",
    )
    args = parser.parse_args()

    rows = build_rows()
    written = write_company_calendar_csv(rows, path=args.path)
    logger.info("書き出し完了: %s (%d 件)", written, len(rows))


if __name__ == "__main__":
    main()
