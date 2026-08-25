"""comken/core/clock.py — 日付・時刻まわりのユーティリティ。

タイムゾーンが必要なのは「今の時刻を取るとき」だけ。
業務で扱う日付（CSV に書かれた日付、ファイル名に入っている日付、帳票の日付）は
「その日」を表すただの日付であり、時刻もタイムゾーンも持たない。
これらは datetime.date のまま扱い、タイムゾーンを付けようとしないこと。
"""

import calendar as _calendar
import datetime


def now() -> datetime.datetime:
    """タイムゾーン付きの現在時刻（この PC のローカル時刻）を返す。"""
    # NOTE: Windows のオフライン環境で追加の tzdata を要求しないよう ZoneInfo は使わない。
    return datetime.datetime.now(datetime.UTC).astimezone()


def today() -> datetime.date:
    """この PC のローカルの今日の日付を返す。"""
    return now().date()


def month_start(target: datetime.date) -> datetime.date:
    """``target`` が属する月の 1日を返す。

    祝日に依存しない純粋な暦計算。営業日計算の前段として
    「その月の最初の営業日を探す」ために使う。
    """
    return target.replace(day=1)


def month_end(target: datetime.date) -> datetime.date:
    """``target`` が属する月の最終日を返す。

    月ごとの日数・閏年を ``calendar.monthrange`` で正しく扱う。
    """
    last_day = _calendar.monthrange(target.year, target.month)[1]
    return target.replace(day=last_day)


# 「日」列が文字列で入っていた場合に受け付ける書き方。
# Excel / CSV から読む業務シートでよくある表記をカバーする。
# 新しい書式を増やすときは**ここを変えても CSV 内閣府の祝日パーサ
# （``comken.core.holidays.csv_source`` の ``_parse_date``）には影響しない**。
# 祝日 CSV は配布フォーマットの制約で 2 形式に固定しており、 緩めた
# 場合に「内閣府以外のファイルを取り違えても気付かない」リスクがあるため
# 別口のままで揃えていない（``_parse_date`` の docstring 参照）。
_DATE_TEXT_FORMATS: tuple[str, ...] = (
    "%Y/%m/%d",
    "%Y-%m-%d",
    "%Y年%m月%d日",
    "%Y/%m/%d %H:%M:%S",
)


def parse_cell_date(value: object) -> datetime.date | None:
    """セルの値を ``datetime.date`` に変換する。読めなければ `` ``None`` 。

    Excel から ``Table`` 行を読むとき、 日付列は

    - ``datetime.datetime`` オブジェクト（Excel の日付型セル）
    - ``datetime.date`` オブジェクト
    - 文字列（手入力・他システムからのエクスポート）

    のどれでも来うる。 それぞれを ``date`` に揃え、 **読めなかった値は
    ``None`` を返す**（例外にはしない）。 利用側は ``None`` を「対象外の行」
    として数えて ``WARNING`` に出す形に向いている（読み込みは止めずに、
    何件スキップしたかだけ報告する業務運用）。

    受け付ける書式は ``_DATE_TEXT_FORMATS`` に固定。 新しい書式を足すときは
    ここにタプル要素として追加する（内閣府 CSV の ``_parse_date`` とは別口
    なので、 祝日 CSV の安全弁を緩めない）。
    """
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for date_format in _DATE_TEXT_FORMATS:
        try:
            return datetime.datetime.strptime(text, date_format).date()  # noqa: DTZ007  # 業務日付として naive で扱う
        except ValueError:
            continue
    return None
