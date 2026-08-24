"""comken/toolbox/holidays/sources/cabinet_office.py — 内閣府 CSV ソース。

内閣府の ``syukujitsu.csv`` を URL から取得し、``cache_path`` に保存する。
キャッシュ済みのファイルがあれば毎回ダウンロードせず、``refresh()`` を
呼んだときだけ強制再取得する。

取得に失敗した場合、キャッシュが残っていれば**警告ログのみでキャッシュを返す**
（オフライン運用の PC でも、1度落としてあれば動き続ける）。
キャッシュも無い場合は ``HolidayCalendarFetchError`` を上げる。

TTL は設けていない（内閣府の祝日データは年に 1 回しか変わらないため、
24h ごとに再取得する設定は無駄だった）。「明示的に最新を取りに行きたいとき」
は ``refresh()`` を使うか、キャッシュファイルを消す。

requests は import 時ではなく ``load()`` 内で遅延 import する。
これにより ``comken.toolbox.holidays`` を import するだけのコードは
requests の存在に影響を受けない（社内 BO 環境で pip 制限がある場面向け）。
"""

import datetime as _dt
import logging
from pathlib import Path

from comken.core.holidays.calendar import Holiday, HolidaySource, RefreshableHolidaySource
from comken.core.timer import measure
from comken.exceptions import HolidayCalendarFetchError, HolidayCalendarFormatError

logger = logging.getLogger(__name__)

# 内閣府の祝日 CSV。CP932（Shift_JIS）で配布されている
DEFAULT_URL = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"

# 既定のキャッシュ先（呼び出し側で明示されたらそちらを優先）
DEFAULT_CACHE_PATH = Path.home() / ".comken" / "holidays" / "syukujitsu.csv"


class CabinetOfficeCSVSource(HolidaySource, RefreshableHolidaySource):
    """内閣府の ``syukujitsu.csv`` をダウンロードして ``Holiday`` の iterable を返す。

    初回 ``load()`` 時にキャッシュが無ければダウンロードし、あればキャッシュを返す。
    ``refresh()`` を呼ぶと TTL に関係なく強制再取得する。

    Args:
        url: 内閣府の CSV の URL。既定は ``syukujitsu.csv`` の配布 URL。
        cache_path: ダウンロードした CSV の保存先。既定は ``~/.comken/holidays/syukujitsu.csv``。
        encoding: CSV の文字コード。CP932（Shift_JIS）のままで良い。
        fetch_timeout_seconds: requests.get() のタイムアウト秒数。
        refresh_timeout_seconds: refresh() で使う短いタイムアウト秒数（業務フロー停止を防ぐ）。
    """

    def __init__(
        self,
        url: str = DEFAULT_URL,
        cache_path: Path | str | None = None,
        *,
        encoding: str = "cp932",
        fetch_timeout_seconds: float = 30.0,
        refresh_timeout_seconds: float = 0.5,
    ) -> None:
        self._url = url
        self._cache_path = Path(cache_path) if cache_path is not None else DEFAULT_CACHE_PATH
        self._encoding = encoding
        self._fetch_timeout = fetch_timeout_seconds
        self._refresh_timeout = refresh_timeout_seconds

    @measure
    def load(self) -> list[Holiday]:
        """キャッシュがあればそれを、無ければダウンロードして ``Holiday`` を返す。

        Returns:
            内閣府の祝日を日付順に並べた ``Holiday`` のリスト。

        Raises:
            HolidayCalendarFetchError: ダウンロードもキャッシュも読めない場合。
        """
        cached_bytes = self._read_cache_bytes()
        if cached_bytes is not None:
            return self._decode(cached_bytes)

        try:
            fresh_bytes = self._download()
        except HolidayCalendarFetchError as error:
            raise HolidayCalendarFetchError(
                self._url,
                f"{error}\nキャッシュも無いので起動できません。",
            ) from error

        self._write_cache(fresh_bytes)
        return self._decode(fresh_bytes)

    @measure
    def refresh(self) -> list[Holiday]:
        """TTL を無視して内閣府から強制再取得する（業務フローを止めない短時間タイムアウト）。

        ``HolidayCalendar.is_business_day(target)`` などでターゲットが
        今年/来年で内閣府 CSV に該当データが無い場合に呼ばれる。
        **タイムアウトは ``refresh_timeout_seconds``（既定 0.5 秒）** にして、
        ネットワークが遅い環境でも業務を止めない。

        取得できなくても例外は投げず、**キャッシュがあれば警告ログを出して
        キャッシュで代用**する（``load()`` と同じ挙動）。キャッシュも無い
        ときだけ ``HolidayCalendarFetchError`` を送出する。

        Returns:
            内閣府の祝日を日付順に並べた ``Holiday`` のリスト。

        Raises:
            HolidayCalendarFetchError: ダウンロードに失敗し、キャッシュも無い場合。
        """
        try:
            fresh_bytes = self._download(self._refresh_timeout)
        except HolidayCalendarFetchError as error:
            stale_bytes = self._read_cache_bytes()
            if stale_bytes is not None:
                logger.warning(
                    "内閣府 CSV の取得に失敗したためキャッシュで代用します: %s",
                    error,
                )
                return self._decode(stale_bytes)
            raise

        self._write_cache(fresh_bytes)
        return self._decode(fresh_bytes)

    # ── キャッシュ I/O ───────────────────────────────────────────────────────

    def _read_cache_bytes(self) -> bytes | None:
        """キャッシュがあればバイト列を返す。取得失敗時のフォールバック専用。"""
        if not self._cache_path.exists():
            return None
        return self._cache_path.read_bytes()

    def _write_cache(self, raw_bytes: bytes) -> None:
        """取得したバイト列をキャッシュに書き込む（ディレクトリが無ければ作る）。"""
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        # 既存ファイルを上書き（同名・同内容のとき mtime だけ更新するのを避けるため、
        # 一度消してから書く）
        if self._cache_path.exists():
            self._cache_path.unlink()
        self._cache_path.write_bytes(raw_bytes)

    # ── ダウンロード ─────────────────────────────────────────────────────────

    def _download(self, timeout: float | None = None) -> bytes:
        """requests で内閣府の CSV を取得する。失敗時は HolidayCalendarFetchError。

        ``timeout`` を省略すると ``fetch_timeout_seconds`` を使う。``refresh()``
        側からは短い ``refresh_timeout_seconds`` を渡せる。
        """
        if timeout is None:
            timeout = self._fetch_timeout
        # 遅延 import: requests はオフライン環境で入っていないことがあるため、
        # 使うときだけ import し、無い環境では HolidayCalendarFetchError に変える。
        # 社内 BO 環境はオフラインで pip が使えないため requests の型スタブを
        # 取得できず、pyright が ``import-not-found`` / ``attr-defined`` を
        # 誤検知する。実行時は `requests.get(...)` / `RequestException` が動く。
        try:
            import requests  # type: ignore[import-not-found]
        except ImportError as error:
            raise HolidayCalendarFetchError(
                self._url,
                "requests ライブラリがインストールされていません。",
            ) from error

        try:
            response = requests.get(self._url, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as error:  # type: ignore[attr-defined]
            raise HolidayCalendarFetchError(self._url, str(error)) from error

        return response.content

    # ── デコード ─────────────────────────────────────────────────────────────

    def _decode(self, raw_bytes: bytes) -> list[Holiday]:
        """ダウンロードしたバイト列を ``Holiday`` のリストに変換する。"""
        # CP932 で復号する。失敗時は文字コード違いとして FormatError にする
        try:
            text = raw_bytes.decode(self._encoding)
        except UnicodeDecodeError as error:
            raise HolidayCalendarFetchError(
                self._url,
                f"文字コード {self._encoding} で復号できませんでした: {error}",
            ) from error

        # csv_source は標準ライブラリだけで動くのでここで直接 import
        from comken.core.holidays.csv_source import parse_cabinet_office_text

        try:
            return parse_cabinet_office_text(text, source=self._url)
        except HolidayCalendarFormatError as error:
            raise HolidayCalendarFetchError(
                self._url,
                f"ダウンロードした内容を内閣府 CSV として解釈できません: {error}",
            ) from error


__all__ = ["CabinetOfficeCSVSource", "DEFAULT_URL", "DEFAULT_CACHE_PATH"]


def _build_default_cache_path() -> Path:
    """既定のキャッシュパスを組み立てる（テストで monkeypatch しやすいように分離）。"""
    return DEFAULT_CACHE_PATH


def _today() -> _dt.date:
    """テストの差し替え用に ``datetime.date`` の生成を 1か所に集める。"""
    return _dt.date.today()  # noqa: DTZ011  # ローカルタイムの日付を意図的に取得
