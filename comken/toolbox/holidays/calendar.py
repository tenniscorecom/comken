"""comken/toolbox/holidays/calendar.py — 祝日カレンダー本体（facade から呼ばれる）。

データ形式は ``Holiday`` 1個に統一し、内閣府 CSV・管理表・テスト用 iterable など
入手経路（``HolidaySource``）を差し替え可能にする。判定ロジックはここに集約され、
``is_holiday`` / ``is_business_day`` / ``next_business_day`` / ``expires_after`` を提供する。

ネット系依存（requests）はこのモジュールには入らない。
内閣府からの取得は ``sources/cabinet_office.py`` 側に閉じ込めている。
"""

import datetime as _dt
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from comken.exceptions import HolidayCalendarFetchError

logger = logging.getLogger(__name__)

# 1ヶ月未満で切れる場合に警告する日数。30 日 ≒ 「切れた瞬間まで気付かない」を避ける閾値
EXPIRING_WARNING_DAYS = 30


@dataclass(frozen=True)
class Holiday:
    """祝日の1件。日付と名称だけを運ぶシンプルな箱。

    Attributes:
        date: 祝日の日付（時刻・タイムゾーンは持たない業務日付）。
        name: 祝日の日本語名称（例: "建国記念の日"）。
        approximate: ``True`` なら、計算式など内閣府発表と ±1 日前後する
            可能性がある値。``HolidayCalendar.is_holiday`` などで該当 Holiday
            を返したときに WARNING ログを出して、業務フローを止めずに気づける
            ようにする。デフォルトは ``False``（内閣府 CSV 由来または確実な
            計算結果）。
    """

    date: _dt.date
    name: str
    approximate: bool = False


@runtime_checkable
class HolidaySource(Protocol):
    """祝日を 1セット取り出せる仕組みの共通インタフェース。

    内閣府の ``CabinetOfficeCsvSource`` と、社内の ``ComkenMasterTableSource`` の両方が
    これを実装するため、利用側は入手経路を意識せずに ``from_sources`` に渡せる。

    この Protocol はメソッドの型を ``Iterable[Holiday]`` に固定する。
    ``load()`` を呼んだその瞬間に取得が走る（キャッシュは実装側で持つ）のが
    一貫していて読みやすい。実装が iterable を返したい場合は
    中で ``list()`` してから返してもよい。
    """

    def load(self) -> Iterable[Holiday]:
        """祝日セットを取り出して ``Iterable[Holiday]`` で返す。"""
        ...


@runtime_checkable
class RefreshableHolidaySource(Protocol):
    """TTL を無視して強制再取得できる祝日 source（例: 内閣府の ``CabinetOfficeCsvSource``）。

    ``HolidayCalendar`` がターゲットが今年/来年のときに内閣府への
    再取得を試みるためのフック。短いタイムアウト（既定 0.5 秒）で実装する。
    必須ではなく、管理表など再取得が要らない source は実装しなくてよい。
    """

    def refresh(self) -> Iterable[Holiday]:
        """TTL を無視して強制再取得する。"""
        ...


class HolidayCalendar:
    """祝日を保持し、営業日判定を行うカレンダー本体。

    同じ日付に複数の祝日が登録された場合は**先勝ち**で WARNING ログを出す
    （内閣府と管理表の重複は珍しくないが、黙って採用するとどちらが正かを
    後から追えなくなる）。

    期限切れの警告（``EXPIRING_WARNING_DAYS`` を切った日）は **同じ日に
    1回だけ**出す。同じ日に ``is_business_day`` が何回呼ばれても
    ログが埋もれないため。
    """

    def __init__(self, holidays: Iterable[Holiday]) -> None:
        """``Holiday`` の iterable から ``{日付: Holiday}`` の索引を作る。

        Args:
            holidays: 祝日の iterable。同じ日付が複数含まれていたら先勝ちで WARNING。
        """
        self._holidays: dict[_dt.date, Holiday] = {}
        for holiday in holidays:
            existing = self._holidays.get(holiday.date)
            if existing is None:
                self._holidays[holiday.date] = holiday
                continue
            if existing.name != holiday.name:
                logger.warning(
                    "祝日が重複しています: %s 「%s」と「%s」の両方があるため、先勝ちを使います",
                    holiday.date,
                    existing.name,
                    holiday.name,
                )
        # 同日重複は黙って 1件にするので list 化はそのままキーで参照
        self._expiry_warned_on: _dt.date | None = None
        # 同じ年には 1 回だけ内閣府 refresh を試みるためのキャッシュキー
        self._refreshed_keys: set[int] = set()
        # ``refresh()`` メソッドを持つ source のリスト（``from_sources`` で設定）。
        # 単発利用（``HolidayCalendar([holidays])``）では空のまま。
        self._refreshable_sources: list[RefreshableHolidaySource] = []

    # ── ファクトリ ───────────────────────────────────────────────────────────

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        *,
        encoding: str = "cp932",
    ) -> "HolidayCalendar":
        """内閣府の ``syukujitsu.csv`` を直接読む最短ルート。

        Args:
            path: CSV のパス。CP932（Shift_JIS）固定。
            encoding: 文字コード。通常は ``cp932`` のままで良い。

        Returns:
            読み込み結果から作った ``HolidayCalendar``。
        """
        # 遅延 import を避けるため、ここで csv_source を import する。
        # csv_source は標準ライブラリのみで動く（requests 不要）
        from comken.toolbox.holidays.csv_source import load_cabinet_office_csv

        return cls(load_cabinet_office_csv(path, encoding=encoding))

    @classmethod
    def from_sources(cls, sources: Iterable[HolidaySource]) -> "HolidayCalendar":
        """複数の ``HolidaySource`` を合体させる（内閣府 + 管理表など）。

        **カスケード動作**: 前の source が ``HolidayCalendarFetchError``
        （内閣府の取得失敗・``requests`` 不在など）を投げたら次の source へ
        フォールバックする。**内閣府が取れない環境で Computed に切り替えたい**
        ケース（オフライン BO 環境・期限切れ）を想定。
        全部失敗したら最後の ``HolidayCalendarFetchError`` をそのまま送出。

        Args:
            sources: ``load()`` を持つ ``HolidaySource`` の iterable。
                同じ日付が複数ソースにあれば **最初のソースの Holiday** が優先される。

        Returns:
            全ソースを結合した ``HolidayCalendar``。

        Raises:
            HolidayCalendarFetchError: 全 source が ``HolidayCalendarFetchError``
                を投げた場合、最後のエラーをそのまま送出する。
        """
        merged: list[Holiday] = []
        last_error: HolidayCalendarFetchError | None = None
        sources_list = list(sources)
        for source in sources_list:
            try:
                merged.extend(source.load())
            except HolidayCalendarFetchError as error:
                logger.warning(
                    "HolidaySource %s の取得に失敗しました。次のソースへフォールバックします: %s",
                    type(source).__name__,
                    error,
                )
                last_error = error
                continue
        if not merged and last_error is not None:
            raise last_error
        # ``refresh()`` メソッドを持つ source を保持。``is_business_day`` が
        # 呼ばれたときに内閣府への強制再取得を指示するため。
        instance = cls(merged)
        instance._refreshable_sources = [
            s for s in sources_list if isinstance(s, RefreshableHolidaySource)
        ]
        return instance

    # ── 判定 ─────────────────────────────────────────────────────────────────

    def is_holiday(self, target: _dt.date) -> bool:
        """``target`` が祝日（または休日）なら ``True``。

        ターゲットが今年/来年なら、内閣府 source への強制再取得を試みる
        （今年中に 1 回だけ。失敗時はサイレント）。
        計算式由来の暫定値（``approximate=True``）を返すときは WARNING ログ。
        """
        self._maybe_refresh_for(target)
        holiday = self._holidays.get(target)
        if holiday is None:
            return False
        if holiday.approximate:
            logger.warning(
                "祝日 %s 「%s」 は計算式による暫定値です。実際とは ±1 日前後する可能性があります。",
                target.isoformat(),
                holiday.name,
            )
        return True

    def holidays_in(self, start: _dt.date, end: _dt.date) -> list[Holiday]:
        """``start <= 日付 <= end`` の範囲に入る祝日を、日付順に返す。

        Args:
            start: 範囲開始（含む）。
            end: 範囲終了（含む）。

        Returns:
            範囲内の ``Holiday`` を日付昇順で並べたリスト。
            該当が無ければ空リスト。
        """
        if start > end:
            return []
        return sorted(
            (holiday for date, holiday in self._holidays.items() if start <= date <= end),
            key=lambda h: h.date,
        )

    def is_business_day(
        self,
        target: _dt.date,
        *,
        skip_weekends: bool = True,
    ) -> bool:
        """``target`` が営業日なら ``True``。

        ``skip_weekends=True``（既定）なら土曜・日曜も休業扱いにする。
        ``False`` を渡すと、土曜・日曜であっても祝日でなければ「営業日」と
        判定される（振替休日を平日扱いするシナリオ向け）。

        「収録済み最終日 <= target」のときは期限切れを WARNING ログで 1度だけ
        通知する。判定自体は通常どおり行う（誤って平日扱いにならないよう、
        **収録範囲外は祝日ではない側に倒す**）。
        """
        self._maybe_warn_expiring(target)
        if skip_weekends and target.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            return False
        return not self.is_holiday(target)

    def next_business_day(
        self,
        target: _dt.date,
        *,
        skip_weekends: bool = True,
    ) -> _dt.date:
        """``target`` より後で最初の営業日（``is_business_day`` が True になる日）を返す。

        収録範囲外でも日付は進むが、祝日判定は「祝日ではない」と扱う。
        期限切れの警告は ``next_business_day`` の入口で 1度だけ出す。
        """
        self._maybe_warn_expiring(target)
        cursor = target + _dt.timedelta(days=1)
        while not self.is_business_day(cursor, skip_weekends=skip_weekends):
            cursor += _dt.timedelta(days=1)
        return cursor

    def expires_after(self, target: _dt.date) -> bool:
        """``target`` が収録済み最終日以降（＝「収録期限を過ぎた」）なら ``True``。

        「収録済み最終日 <= target」を期限切れとみなす。等号を含めるのは、
        「収録最終日ぴったり」を「期限の境目」として扱うため（最終日当日は
        収録済みの祝日として判定できるが、それ以降は収録外）。
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

    def holiday_names(self, target: _dt.date) -> Sequence[str]:
        """``target`` に登録された祝日名称のタプル（同日が複数あれば複数要素）。"""
        holiday = self._holidays.get(target)
        if holiday is None:
            return ()
        return (holiday.name,)

    def all_holidays(self) -> list[Holiday]:
        """保持している祝日を日付順に並べたリストを返す。"""
        return sorted(self._holidays.values(), key=lambda h: h.date)

    def _maybe_warn_expiring(self, today: _dt.date) -> None:
        """期限切れが近いとき、**同じ日付で 1度だけ** WARNING ログを出す。"""
        if self._expiry_warned_on == today:
            return
        remaining = self.days_until_expiry(today)
        if 0 <= remaining < EXPIRING_WARNING_DAYS:
            last = self.last_known_date()
            logger.warning(
                "祝日カレンダーの収録期限が近づいています: 残り %d 日（最終収録日: %s）。"
                "内閣府の祝日 CSV を更新するか、管理表に直近の祝日を追加してください。",
                remaining,
                last,
            )
            self._expiry_warned_on = today

    def _maybe_refresh_for(self, target: _dt.date) -> None:
        """ターゲットが今年/来年なら、今年中に 1 回だけ内閣府に refresh を試みる。

        キャッシュに ``target`` が無い or ``approximate=True`` (Computed の
        近似式由来) のときに、内閣府に強制再取得を試みる。**今年中に 1 回だけ**
        試す（複数回呼ばれるのを防ぐ）。失敗時はサイレント（既存のキャッシュ
        または Computed の近似式で判定する）。
        """
        if not self._refreshable_sources:
            return
        today_year = _dt.date.today().year  # noqa: DTZ011
        if target.year not in (today_year, today_year + 1):
            return
        if today_year in self._refreshed_keys:
            return  # 同じ年には 1 回だけ
        self._refreshed_keys.add(today_year)
        for source in self._refreshable_sources:
            try:
                fresh = source.refresh()
            except HolidayCalendarFetchError as error:
                logger.warning(
                    "HolidaySource %s への強制再取得に失敗しました: %s",
                    type(source).__name__,
                    error,
                )
                continue
            # 内閣府由来の値（``approximate=False``）は Computed の近似式を
            # 上書きする。逆は上書きしない（内閣府が取れない以上、Computed
            # の近似式しかなく、ユーザーに誤情報を与えないため）。
            for holiday in fresh:
                existing = self._holidays.get(holiday.date)
                if existing is not None and not existing.approximate:
                    continue  # 既に内閣府由来 → 上書きしない
                self._holidays[holiday.date] = holiday
            return  # 1 個目の source が成功したら終了


def is_business_day(
    target: _dt.date,
    *,
    calendar: HolidayCalendar,
    skip_weekends: bool = True,
) -> bool:
    """``calendar`` を介さずに使える簡易判定。

    ``calendar`` をキーワード専用にして、呼び出し側がうっかり位置引数で
    日付とカレンダーを取り違える事故を防ぐ。
    """
    return calendar.is_business_day(target, skip_weekends=skip_weekends)
