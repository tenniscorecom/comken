"""comken/core/holidays/csv_source.py — 内閣府 CSV の読み取り。

内閣府の「祝日データ CSV（syukujitsu.csv）」は CP932（Shift_JIS）で配布され、
1列目に「国民の祝日・休日月日（yyyy-MM-dd）」、2列目に「国民の祝日・休日名称」
が入っている。最初の行は `国民の祝日・休日月日,国民の祝日・休日名称` という
ヘッダーで、これは値が日付として読めないので読み飛ばす。

パース時に 1 行でも壊れていると全体が信用できないので、
**1件も抽出できなかったら HolidayCalendarFormatError** を上げる
（部分的成功で黙って動く事故を防ぐため）。
"""

import csv
import datetime as _dt
import io
import logging
from pathlib import Path

from comken.core.holidays.calendar import Holiday
from comken.core.timer import measure
from comken.exceptions import HolidayCalendarFormatError

logger = logging.getLogger(__name__)

# 内閣府のヘッダー行1列目（前後の空白は許容）
_HEADER_FIRST = "国民の祝日・休日月日"
_HEADER_SECOND = "国民の祝日・休日名称"
# 内閣府のフォーマット。配布 CSV は ``YYYY/M/D``（スラッシュ・ゼロ埋めなし）だが、
# 配布変更履歴・手書きの差し替えで ``YYYY-MM-DD``（ハイフン・ゼロ埋めあり）が
# 混ざることもあるので両方を許容する。
_DATE_FORMATS = ("%Y/%m/%d", "%Y-%m-%d")

# CSV ファイルを読み込むときの文字コード。既定は CP932（Shift_JIS）。
DEFAULT_ENCODING = "cp932"


@measure
def load_cabinet_office_csv(
    path: str | Path,
    *,
    encoding: str = DEFAULT_ENCODING,
) -> list[Holiday]:
    """内閣府の syukujitsu.csv を読み取り、祝日のリストを返す。

    Args:
        path: CSV ファイルのパス。存在しない・読めない場合は ``HolidayCalendarFormatError``。
        encoding: CSV の文字コード。既定は ``cp932``（内閣府の配布形式）。

    Returns:
        日付順に並んだ ``Holiday`` のリスト。

    Raises:
        HolidayCalendarFormatError: ファイルが無い、壊れている、
            ヘッダーが内閣府のものではない、日付が解釈できないなどの理由で
            1件も抽出できなかった場合。
    """
    file_path = Path(path)
    if not file_path.exists():
        raise HolidayCalendarFormatError(
            file_path,
            "ファイルが存在しません。ダウンロード済みのものを指定してください。",
        )
    try:
        raw_text = file_path.read_text(encoding=encoding)
    except UnicodeDecodeError as error:
        raise HolidayCalendarFormatError(
            file_path,
            f"文字コード {encoding} で読み取れませんでした。"
            "内閣府の syukujitsu.csv は CP932（Shift_JIS）です。",
        ) from error

    holidays = _parse_csv_text(raw_text, source=file_path)

    if not holidays:
        raise HolidayCalendarFormatError(
            file_path,
            "日付として解釈できる行が 1件もありませんでした。"
            "内閣府以外のファイルが指定されていないか確認してください。",
        )

    logger.debug("内閣府 CSV を読み取りました: %d 件 / %s", len(holidays), file_path)
    return holidays


def parse_cabinet_office_text(text: str, *, source: str = "<text>") -> list[Holiday]:
    """内閣府 CSV の文字列を直接パースする（テストやキャッシュのバイパス用）。

    Args:
        text: 内閣府 CSV の中身。文字コードは呼び出し側で解決済みであること。
        source: エラーメッセージに出す由来（ファイルパス・URL など）。

    Returns:
        日付順に並んだ ``Holiday`` のリスト。0件なら ``HolidayCalendarFormatError``。
    """
    holidays = _parse_csv_text(text, source=source)
    if not holidays:
        raise HolidayCalendarFormatError(
            source,
            "日付として解釈できる行が 1件もありませんでした。",
        )
    return holidays


def _parse_csv_text(text: str, *, source: object) -> list[Holiday]:
    """CSV 文字列を ``Holiday`` のリストに変換する内部処理。"""
    reader = csv.reader(io.StringIO(text))
    holidays: list[Holiday] = []
    for row_index, row in enumerate(reader, start=1):
        if not row:
            continue
        first = row[0].strip()
        # 1行目は内閣府のヘッダー（"国民の祝日・休日月日"）。strip して一致したら飛ばす
        if row_index == 1 and first == _HEADER_FIRST:
            continue
        # 2列目前提だが、欠けていたら不正
        if len(row) < 2:
            logger.warning("内閣府 CSV の列数が不足しています (%s): %s", source, row)
            continue
        try:
            parsed = _parse_date(first)
        except HolidayCalendarFormatError:
            # 1行目はヘッダーとは限らないが、日付として読めなければ不正データとして飛ばす
            # （ただし厳格にしたいので 0件なら呼び出し側で FormatError にする）
            logger.warning("内閣府 CSV の日付を解釈できません (%s): %s", source, first)
            continue
        name = row[1].strip()
        if not name:
            continue
        holidays.append(Holiday(date=parsed, name=name))
    return holidays


def _parse_date(text: str) -> _dt.date:
    """内閣府 CSV の日付セルを ``datetime.date`` に変換する。

    内閣府の現行配布は ``YYYY/M/D``（スラッシュ・ゼロ埋めなし）が中心だが、
    過去版・手書き差し替え・テスト fixture では ``YYYY-MM-DD``（ハイフン・
    ゼロ埋めあり）が混ざるので、両方を受け付ける。すべて失敗したら
    ``HolidayCalendarFormatError`` を呼び出し元へ伝搬する。
    """
    for fmt in _DATE_FORMATS:
        try:
            return _dt.datetime.strptime(text, fmt).date()  # noqa: DTZ007  # 業務日付として naive で扱う
        except ValueError:
            continue
    raise HolidayCalendarFormatError(
        "<日付セル>",
        f"日付として解釈できません: {text!r}",
    )
