"""comken/core/calendar/_calendar.py — カレンダー本体（実装詳細）。

モジュール名は ``_calendar.py`` にしておき、``comken.core.calendar``
（パッケージ本体）と ``calendar`` （クラス名）が被らないようにしている。

``Holiday`` 1 個に国民の祝日を統一し、内閣府 CSV・管理表・テスト用 iterable など
入手経路（``_Source``）を差し替え可能にする。国民の祝日と会社休日
（``comken.core.calendar.company`` で実行時判定）をマージして
``is_bholiday`` / ``is_business_day`` / ``business_day_after`` などの判定関数が
直接呼べる形に組み立てる。

ネット系依存（requests）はこのモジュールには入らない。
"""

import datetime as _dt
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, Self, runtime_checkable

from comken.core.calendar.company import company_holiday_name
from comken.core.clock import month_end, month_start, today
from comken.exceptions import BusinessDayNotFoundError

logger = logging.getLogger(__name__)

# 1ヶ月未満で切れる場合に警告する日数。30 日 ≒ 「切れた瞬間まで気付かない」を避ける閾値
EXPIRING_WARNING_DAYS = 30

# 「次の営業日」を探すときの日数上限。祝日データが壊れていたり、社内管理表に
# 会社休日が広範囲に登録されていたりすると無限ループになるため、必ず上限を切る。
BUSINESS_DAY_SEARCH_LIMIT = 30


@dataclass(frozen=True)
class Holiday:
    """祝日の1件。日付と名称だけを運ぶシンプルな箱。

    Attributes:
        date: 祝日の日付（時刻・タイムゾーンは持たない業務日付）。
        name: 祝日の日本語名称（例: "建国記念の日"）。
        approximate: ``True`` なら、計算式など内閣府発表と ±1 日前後する
            可能性がある値。``is_holiday`` などで該当 Holiday を返したときに
            WARNING ログを出して、業務フローを止めずに気づけるようにする。
            デフォルトは ``False``（内閣府 CSV 由来または確実な計算結果）。
    """

    date: _dt.date
    name: str
    approximate: bool = False


@runtime_checkable
class _Source(Protocol):
    """祝日を 1セット取り出せる仕組みの共通インタフェース（**非公開**）。

    ``_ComputedSource`` などがこれを実装するため、利用側は入手経路を
    意識せずに ``_Calendar`` へ渡せる。

    この Protocol はメソッドの型を ``Iterable[Holiday]`` に固定する。
    ``load()`` を呼んだその瞬間に取得が走る（キャッシュは実装側で持つ）のが
    一貫していて読みやすい。実装が iterable を返したい場合は
    中で ``list()`` してから返してもよい。
    """

    def load(self) -> Iterable[Holiday]:
        """祝日セットを取り出して ``Iterable[Holiday]`` で返す。"""
        ...


class _Calendar:
    """国民の祝日を保持し、**会社休日を毎回判定**して返すカレンダー本体。

    国民の祝日データは ``__init__`` で受け取って索引化する。
    会社休日は ``_Source`` を持たず、呼び出しのたびに
    ``comken.core.calendar.company.company_holiday_name`` で判定する（年範囲
    を固定しないルールのため）。

    同じ日付に複数の祝日が登録された場合は**先勝ち**で採用する
    （内閣府 CSV の複数回登録など）。国民の祝日と会社休日が同じ日に重なった
    ときは **国民の祝日が先勝ち**（会社休日は国民の祝日を上書きしない）。
    """

    def __init__(self, holidays: Iterable[Holiday]) -> None:
        """``Holiday`` の iterable から ``{日付: Holiday}`` の索引を作る。

        Args:
            holidays: 国民の祝日の iterable。同じ日付が複数含まれていたら
                先勝ちで採用。
        """
        self._holidays: dict[_dt.date, Holiday] = {}
        for holiday in holidays:
            existing = self._holidays.get(holiday.date)
            if existing is None:
                self._holidays[holiday.date] = holiday
        # 期限切れ警告を「同じ日に 1度だけ」出すためのキャッシュキー
        self._expiry_warned_on: _dt.date | None = None

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        *,
        encoding: str = "cp932",
    ) -> Self:
        """内閣府の ``syukujitsu.csv`` を直接読む最短ルート。"""
        from comken.core.calendar.csv_source import load_cabinet_office_csv

        return cls(load_cabinet_office_csv(path, encoding=encoding))

    @classmethod
    def from_sources(cls, sources: Iterable[_Source]) -> Self:
        """複数の ``_Source`` を合体させる。"""
        merged: list[Holiday] = []
        for source in sources:
            merged.extend(source.load())
        return cls(merged)

    def is_holiday(self, target: _dt.date) -> bool:
        """``target`` が国民の祝日または会社休日に当たれば ``True``。

        国民の祝日を優先し、重複時は国民の祝日側の名前を返す。会社休日は
        国民の祝日に重なっても黙って上書きしない。
        """
        if target in self._holidays:
            return True
        return company_holiday_name(target) is not None

    def holiday_name(self, target: _dt.date) -> str | None:
        """``target`` の祝日・会社休日名称を返す。祝日でも会社休日でも
        なければ ``None``。

        国民の祝日が先勝ち（会社休日と同日でも国民の祝日を採用）。
        """
        holiday = self._holidays.get(target)
        if holiday is not None:
            if holiday.approximate:
                logger.warning(
                    "祝日 %s 「%s」 は計算式による暫定値。"
                    "実際とは ±1 日前後する可能性があります。",
                    target.isoformat(),
                    holiday.name,
                )
            return holiday.name
        return company_holiday_name(target)

    def expires_after(self, target: _dt.date) -> bool:
        """``target`` が収録済み最終日以降（＝「収録期限を過ぎた」）なら ``True``。

        会社休日はルール判定のため期限を持たないので、ここでは国民の祝日の
        収録最終日だけを見る。
        """
        last = self.last_known_date()
        if last is None:
            return True
        return target >= last

    def days_until_expiry(self, today: _dt.date) -> int:
        """``today`` から収録最終日までの日数。最終日を過ぎていれば負の値。

        Args:
            today: 「今日」とみなす日付。

        Returns:
            ``last_known - today`` の日数差。収録済み祝日が無いと ``-1``。
        """
        last = self.last_known_date()
        if last is None:
            return -1
        return (last - today).days

    def last_known_date(self) -> _dt.date | None:
        """収録済み祝日のうち最も新しい日付。無ければ ``None``。"""
        if not self._holidays:
            return None
        return max(self._holidays.keys())

    def all_holidays(self) -> list[Holiday]:
        """国民の祝日を日付順に並べたリストを返す（会社休日は含まない）。"""
        return sorted(self._holidays.values(), key=lambda h: h.date)

    def all_entries(self, year_range: tuple[int, int]) -> list[Holiday]:
        """国民の祝日と会社休日を ``year_range`` で指定した範囲について結合し、
        日付順に並べたリストを返す。

        ``export_csv`` が国民の祝日＋公司休日を 1 つの CSV にまとめて書き出す
        ために使う。国民の祝日が会社休日に重なった場合は国民の祝日を先勝ちで
        採用する（``is_holiday`` と同じ優先順位）。会社休日は ``approximate=False``
        で出力する。

        Args:
            year_range: ``(開始年, 終了年)``。両端を含む。
        """
        result: list[Holiday] = list(self._holidays.values())
        from_year, to_year = year_range
        for year in range(from_year, to_year + 1):
            for month in range(1, 13):
                for day in range(1, _days_in_month(year, month) + 1):
                    target = _dt.date(year, month, day)
                    if target in self._holidays:
                        continue  # 国民の祝日が先勝ち
                    name = company_holiday_name(target)
                    if name is not None:
                        result.append(Holiday(date=target, name=name))
        return sorted(result, key=lambda h: h.date)

    def export_csv(self, path: str | Path | None = None, *, encoding: str = "utf-8-sig") -> Path:
        """保持している国民の祝日＋会社休日を CSV へ書き出す。

        Python を使わない Excel・VBA からも同じ祝日データを参照したいときに使う。
        列は ``date``（``YYYY-MM-DD``）・``name``・``approximate``（``True``/``False``）
        の3列。``comken.toolbox.csv`` は使わず標準ライブラリの ``csv`` だけで書く
        （``comken.core`` は外を触らない部品の置き場で、``toolbox`` を import しない
        という層のルールに従うため）。

        Args:
            path: 書き出す CSV のパス。省略時は内閣府 CSV と同じ ``data/`` フォルダの
                ``holidays.csv``（``EXPORTED_CSV_PATH``）に書き出す。Excel・VBA 側から
                見に行く場所を固定できる。
            encoding: 既定は ``utf-8-sig``（BOM付き）。Excel は BOM 無しの UTF-8 だと
                文字化けするため。

        Returns:
            書き出した CSV のパス。
        """
        import csv as _csv

        file_path = Path(path) if path is not None else EXPORTED_CSV_PATH
        file_path.parent.mkdir(parents=True, exist_ok=True)
        entries = self.all_entries((EXPORTED_FROM_YEAR, EXPORTED_TO_YEAR))
        with file_path.open("w", encoding=encoding, newline="") as file:
            writer = _csv.writer(file)
            writer.writerow(["date", "name", "approximate"])
            for holiday in entries:
                writer.writerow([holiday.date.isoformat(), holiday.name, holiday.approximate])
        logger.debug(
            "祝日カレンダーをCSVへ書き出しました: %s (%d件)", file_path, len(entries)
        )
        return file_path

    def _maybe_warn_expiring(self, today: _dt.date) -> None:
        """期限切れが近いとき、**同じ日付で 1度だけ** WARNING ログを出す。"""
        if self._expiry_warned_on == today:
            return
        remaining = self.days_until_expiry(today)
        if 0 <= remaining < EXPIRING_WARNING_DAYS:
            last = self.last_known_date()
            logger.warning(
                "祝日カレンダーの収録期限が近づいています: 残り %d 日（最終収録日: %s）。"
                "内閣府の syukujitsu.csv をダウンロードして"
                "comken/core/calendar/data/syukujitsu.csv を上書きし、コミット・タグ打ちして"
                "配布してください（docs/calendar.md の「年1回の手動更新手順」参照）。"
                "なお会社休日（年末年始休暇など）はコードで判定しているため期限はありません。",
                remaining,
                last,
            )
            self._expiry_warned_on = today


# ── 既定カレンダー ──────────────────────────────────────────────────────
# 「アプリ起動時に 1度だけ遅延生成」されるシングルトン。ネットワークには出ない
# （``_ComputedSource`` + 同梱 CSV だけ。会社休日は ``company.py`` の
# ルールで毎回判定するため保持しない）。

# 内閣府の祝日 CSV を git 管理下に同梱したパス。``_resolve_singleton()`` が
# 読む正本はここ。PC ごとのキャッシュは持たない。
# 更新は年 1 回の手動作業（開発機で内閣府から取得 → コミット → 共有サーバーへ配置）。
BUNDLED_CSV_PATH: Final[Path] = Path(__file__).parent / "data" / "syukujitsu.csv"

# ``export_csv()`` の既定の書き出し先。内閣府 CSV と同じ data/ フォルダに
# 置くことで、Excel・VBA 側は常にこのパスを見に行けばよい（git 管理下）。
EXPORTED_CSV_PATH: Final[Path] = BUNDLED_CSV_PATH.parent / "holidays.csv"

# CSV 書き出しの対象期間。固定（内閣府 CSV の収録範囲と同じ 1948-2099）。
# ``export_csv()`` の結果が呼ぶ日に依存しないよう、ここで固定する。
EXPORTED_FROM_YEAR: Final = 1948
EXPORTED_TO_YEAR: Final = 2099

_singleton: _Calendar | None = None


def _resolve_singleton() -> _Calendar:
    """プロセスの遅延生成シングルトンとして保持している ``_Calendar`` を返す。

    **1回だけ**組み立てて以降は同じインスタンスを返す。

    構成は 2 つだけ:

    1. ``_ComputedSource``（純粋計算。土台）
    2. 同梱の ``syukujitsu.csv`` を ``load_cabinet_office_csv`` で読む
       （内閣府の実値。計算式の上書き用）

    **ネットワークには一切出ない。** 会社休日は ``company.py`` のルールで
    毎回判定するため、ここでは保持しない。
    """
    global _singleton
    if _singleton is None:
        from comken.core.calendar.computed import _ComputedSource

        _singleton = _Calendar.from_sources(
            [
                _ComputedSource(),
                _BundledCabinetCSVSource(BUNDLED_CSV_PATH),
            ]
        )
    return _singleton


def _set_calendar_for_test(calendar: _Calendar | None) -> None:
    """テストで既定カレンダーを差し替えるための **非公開** 入口。

    通常は使わない。テストが個別の ``_Calendar`` を組み立てて
    ``is_business_day`` などの公開関数の挙動を確かめたいときに使う。
    ``None`` を渡すと遅延生成に戻る。
    """
    global _singleton
    _singleton = calendar


class _BundledCabinetCSVSource:
    """同梱の ``syukujitsu.csv`` を読むための最小実装。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[Holiday]:
        """同梱の ``syukujitsu.csv`` を読み ``Holiday`` のリストを返す。"""
        from comken.core.calendar.csv_source import load_cabinet_office_csv

        return load_cabinet_office_csv(self._path)


# ── 公開関数 ────────────────────────────────────────────────────────────


def warn_if_calendar_expiring_soon() -> None:
    """既定の祝日カレンダーの収録期限が近ければ、起動時に警告する。

    祝日判定 (``is_business_day`` 等) を実際に使うかどうかに関わらず、
    RPA スクリプトの起動直後に呼ぶことを想定している
    (``comken.run.backoffice`` / ``intranet`` から呼ばれる)。
    同じ日に複数回呼んでも警告は 1日 1回だけ (``_maybe_warn_expiring``
    の既存の重複防止をそのまま使う)。
    """
    cal = _resolve_singleton()
    cal._maybe_warn_expiring(today())


def is_holiday(target: _dt.date) -> bool:
    """``target`` が国民の祝日または会社休日に当たれば ``True``。"""
    return _resolve_singleton().is_holiday(target)


def holiday_name(target: _dt.date) -> str | None:
    """``target`` の祝日・会社休日名称を返す。祝日でも会社休日でも
    なければ ``None``。

    国民の祝日が先勝ち（会社休日に重なっても国民の祝日を採用）。
    """
    return _resolve_singleton().holiday_name(target)


def is_business_day(
    target: _dt.date,
    *,
    skip_weekends: bool = True,
) -> bool:
    """``target`` が営業日なら ``True``。

    国民の祝日（内閣府 CSV + 計算値）と会社休日ルールで判定する。
    ``skip_weekends=True``（既定）なら土曜・日曜も休業扱いにする。
    ``False`` を渡すと、土曜・日曜であっても祝日でなければ「営業日」と
    判定される（振替休日を平日扱いするシナリオ向け）。

    「収録済み最終日 <= target」のときは期限切れを WARNING ログで 1度だけ
    通知する。判定自体は通常どおり行う（誤って平日扱いにならないよう、
    **収録範囲外は祝日ではない側に倒す**）。
    """
    cal = _resolve_singleton()
    cal._maybe_warn_expiring(target)
    if skip_weekends and target.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        return False
    return not cal.is_holiday(target)


def business_day_after(
    target: _dt.date,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` より後で最初の営業日（``target`` 自身を含まない）。

    ``target`` が営業日でも翌営業日を返す。収録範囲外でも日付は進むが、
    祝日判定は「祝日ではない」と扱う。期限切れの警告は入口で 1度だけ出す。

    Raises:
        BusinessDayNotFoundError: ``BUSINESS_DAY_SEARCH_LIMIT`` 日探索しても
            営業日が見つからなかった（祝日データ欠落・社内休日広範囲など）。
    """
    cal = _resolve_singleton()
    cal._maybe_warn_expiring(target)
    return _search_business_day(
        start=target + _dt.timedelta(days=1),
        step_days=1,
        skip_weekends=skip_weekends,
    )


def business_day_before(
    target: _dt.date,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` より前で最初の営業日（``target`` 自身を含まない）。

    ``target`` が営業日でも前営業日を返す。

    Raises:
        BusinessDayNotFoundError: ``BUSINESS_DAY_SEARCH_LIMIT`` 日探索しても
            営業日が見つからなかった。
    """
    return _search_business_day(
        start=target - _dt.timedelta(days=1),
        step_days=-1,
        skip_weekends=skip_weekends,
    )


def business_day_on_or_after(
    target: _dt.date,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` 以降で最初の営業日（``target`` を含む）。

    ``target`` が営業日なら ``target`` をそのまま返す。
    営業日でなければ、``business_day_after`` と同じ動きで翌日以降を探す。

    Raises:
        BusinessDayNotFoundError: ``BUSINESS_DAY_SEARCH_LIMIT`` 日探索しても
            営業日が見つからなかった。
    """
    if is_business_day(target, skip_weekends=skip_weekends):
        return target
    return business_day_after(target, skip_weekends=skip_weekends)


def business_day_on_or_before(
    target: _dt.date,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` 以前で最初の営業日（``target`` を含む）。

    ``target`` が営業日なら ``target`` をそのまま返す。
    営業日でなければ、``business_day_before`` と同じ動きで前日以前を探す。

    Raises:
        BusinessDayNotFoundError: ``BUSINESS_DAY_SEARCH_LIMIT`` 日探索しても
            営業日が見つからなかった。
    """
    if is_business_day(target, skip_weekends=skip_weekends):
        return target
    return business_day_before(target, skip_weekends=skip_weekends)


def first_business_day_of_month(
    target: _dt.date,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` が属する月の最初の営業日。

    Raises:
        BusinessDayNotFoundError: その月に営業日が 1日も無いとき。
    """
    start = month_start(target)
    try:
        return business_day_on_or_after(start, skip_weekends=skip_weekends)
    except BusinessDayNotFoundError as error:
        raise BusinessDayNotFoundError(
            f"{target.year} 年 {target.month} 月に営業日が見つかりません: {error}"
        ) from error


def last_business_day_of_month(
    target: _dt.date,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` が属する月の最後の営業日。

    月末が土日・祝日のときは直前の営業日に遡る（例: 8/31 が日曜なら 8/29 金）。

    Raises:
        BusinessDayNotFoundError: その月に営業日が 1日も無いとき。
    """
    end = month_end(target)
    try:
        return business_day_on_or_before(end, skip_weekends=skip_weekends)
    except BusinessDayNotFoundError as error:
        raise BusinessDayNotFoundError(
            f"{target.year} 年 {target.month} 月に営業日が見つかりません: {error}"
        ) from error


def nth_business_day_of_month(
    target: _dt.date,
    n: int,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` が属する月の第 ``n`` 営業日を返す（``n`` は 1 始まり）。

    月の初日から数えて ``n`` 番目の営業日。
    その月の営業日数を超える ``n`` を渡すと ``BusinessDayNotFoundError``。

    Raises:
        BusinessDayNotFoundError: ``n`` が 1 未満、またはその月の営業日数を超える。
    """
    if n < 1:
        raise BusinessDayNotFoundError(
            f"第 n 営業日の n は 1 以上で指定してください（指定値: {n}）"
        )
    start = month_start(target)
    end = month_end(target)
    cursor = start
    for _ in range(n):
        try:
            cursor = business_day_on_or_after(cursor, skip_weekends=skip_weekends)
        except BusinessDayNotFoundError as error:
            raise BusinessDayNotFoundError(
                f"{target.year} 年 {target.month} 月に {n} 営業日は存在しません: {error}"
            ) from error
        if cursor > end:
            raise BusinessDayNotFoundError(
                f"{target.year} 年 {target.month} 月に {n} 営業日は存在しません"
                f"（最終営業日: {end}）"
            )
        cursor = cursor + _dt.timedelta(days=1)
    # ループを抜けた時点で ``cursor`` は「n 番目の翌営業日」を指している。
    # ひとつ戻して返す。
    return cursor - _dt.timedelta(days=1)


def add_business_days(
    target: _dt.date,
    n: int,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` から ``n`` 営業日後の日付（``n`` が負なら前）。

    ``n == 0`` のときは ``target`` を**そのまま**返す（``target`` が営業日か
    どうかを問わない）。これは Excel の ``WORKDAY`` と同じ挙動で、
    「今日から N 営業日後」を組み立てるときに条件分岐を書かなくて済む。

    例: 2024/5/2（木、祝日前日）に ``add_business_days(d, 1)`` を呼ぶと
    2024/5/7（火、5/3〜5/6 が祝日＋土日）を返す。

    Raises:
        BusinessDayNotFoundError: 探索が ``BUSINESS_DAY_SEARCH_LIMIT`` に達した。
    """
    if n == 0:
        return target
    # ``target`` を 0 営業日目と数え、``n`` 回「次の（前の）営業日」へ進める。
    # ``target`` が営業日のとき n=1 で翌日営業日、非営業日のときでも
    # ``business_day_after`` が翌営業日にスナップするので結果は同じになる。
    cursor = target
    steps = n if n > 0 else -n
    for _ in range(steps):
        if n > 0:
            cursor = business_day_after(cursor, skip_weekends=skip_weekends)
        else:
            cursor = business_day_before(cursor, skip_weekends=skip_weekends)
    return cursor


def export_csv(path: str | Path | None = None, *, encoding: str = "utf-8-sig") -> Path:
    """国民の祝日と会社休日を 1948-2099 年ぶんの CSV へ書き出す。

    国民の祝日（内閣府 CSV + 計算値）と会社休日をまとめて 1 ファイルに書き出す。
    列は ``date`` / ``name`` / ``approximate`` の3列。呼び出した日（実行時の
    今日）に依存せず、結果は固定（国民の祝日は内閣府 CSV が定める範囲、
    会社休日は ``COMPANY_HOLIDAYS`` の ``(月, 日)`` ルールで毎回判定）。

    Args:
        path: 書き出し先。省略時は ``EXPORTED_CSV_PATH``
            （= ``comken/core/calendar/data/holidays.csv``）に書き出す。
        encoding: 既定は ``utf-8-sig``（BOM付き）。

    Returns:
        書き出した CSV のパス。
    """
    return _resolve_singleton().export_csv(path, encoding=encoding)


# ── 内部ヘルパー ────────────────────────────────────────────────────────


def _search_business_day(
    *,
    start: _dt.date,
    step_days: int,
    skip_weekends: bool,
) -> _dt.date:
    """``start`` から ``step_days`` 日ずつ進め（または戻し）て最初の営業日を探す。

    ``BUSINESS_DAY_SEARCH_LIMIT`` を超えると ``BusinessDayNotFoundError``
    を上げる（祝日データが壊れている／社内休日が広範囲なときの無限ループ防止）。
    """
    if step_days == 0:
        raise ValueError("step_days には 0 以外の値を渡してください")
    cursor = start
    for _ in range(BUSINESS_DAY_SEARCH_LIMIT):
        if is_business_day(cursor, skip_weekends=skip_weekends):
            return cursor
        cursor += _dt.timedelta(days=step_days)
    raise BusinessDayNotFoundError(
        f"{BUSINESS_DAY_SEARCH_LIMIT} 日探索しても営業日が見つかりません。"
        "祝日データに過不足がないか、社内休日が広範囲に登録されていないか確認してください。"
    )


def _days_in_month(year: int, month: int) -> int:
    """``(year, month)`` の月の日数（28/29/30/31）を返す。"""
    import calendar as _cal

    return _cal.monthrange(year, month)[1]
