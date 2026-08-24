# comken.toolbox.holidays — 祝日判定ライブラリ

RPA 置き換えプロジェクトで「いま取るべきレポートか」を判定するために使う、
内閣府の祝日 CSV を基にした祝日判定ライブラリ。

`HolidayCalendar` 1 個に「内閣府の祝日」と「社内管理表の会社休日」をマージして
持ち、`is_business_day()` でその日が営業日かを判定する。

## 最短の使い方

```python
from datetime import date
from pathlib import Path

from comken.toolbox.holidays import (
    CabinetOfficeCSVSource,
    ComkenMasterTableSource,
    HolidayCalendar,
    is_business_day,
)

calendar = HolidayCalendar.from_sources(
    [
        CabinetOfficeCSVSource(),  # 既定: ~/.comken/holidays/syukujitsu.csv にキャッシュ
        ComkenMasterTableSource(Path(r"\\server\share\管理表.xlsx")),
    ]
)

if is_business_day(date.today(), calendar=calendar):
    ...  # レポートを取りに行く
```

## 取得元

| ソース               | 概要                                                       | 必要なもの                |
| -------------------- | ---------------------------------------------------------- | ------------------------- |
| `CabinetOfficeCSVSource`   | 内閣府の `syukujitsu.csv` を URL から取得                  | `requests` （取得時のみ） |
| `ComkenMasterTableSource`  | 社内管理表（Excel）の「会社休日」シート                     | `openpyxl` （既に依存）   |

内閣府 CSV は **CP932（Shift_JIS）** で配布され、列は
「国民の祝日・休日月日」「国民の祝日・休日名称」。1 行目はヘッダーなので
読み込み時にスキップする。

## キャッシュ

`CabinetOfficeCSVSource` は `~/.comken/holidays/syukujitsu.csv` を既定の
キャッシュ先とする（`cache_path` 引数で変更可）。TTL（既定 24 時間）内は
キャッシュをそのまま使い、TTL 経過時のみダウンロードを試みる。
**ダウンロードに失敗してもキャッシュが残っていれば警告ログのみで動く**。

```python
from comken.toolbox.holidays import CabinetOfficeCSVSource

source = CabinetOfficeCSVSource(
    cache_path=Path("D:/work/cache/syukujitsu.csv"),
    ttl_seconds=12 * 60 * 60,  # 半日に1回取り直す
)
```

`HolidayCalendar.is_business_day` などはネットに繋がらずに動くので、
オフライン PC で requests が無いときも import は成功する。

## 期限切れの警告

収録済み祝日のうち最も新しい日付を「収録最終日」とし、
「今日」が収録最終日に近づいたら WARNING ログを出す。

| 状況                                | 挙動                                                                  |
| ----------------------------------- | --------------------------------------------------------------------- |
| 今日 < 収録最終日 − 30 日           | 警告なし                                                              |
| 収録最終日 − 30 日 <= 今日 <= 収録最終日 | WARNING ログを **同じ日に 1 度だけ** 出す                            |
| 今日 > 収録最終日                   | 警告なしで動くが、`is_holiday()` は常に `False`（「祝日ではない」側） |

期限切れ後はあえて「祝日ではない」側に倒す——誤って「祝日扱い」にしてレポートを
取り逃すより、誤って「平日扱い」して RPA を走らせ、次回ログから気付く方が
被害が少ないため。

## 公開 API

| 名前                              | 役割                                                       |
| --------------------------------- | ---------------------------------------------------------- |
| `Holiday`                         | 1 件の祝日（日付 + 名称）。`@dataclass(frozen=True)`        |
| `HolidaySource`                   | `load() -> Iterable[Holiday]` の Protocol                   |
| `HolidayCalendar`                 | 祝日を保持し、営業日判定を行う本体                          |
| `HolidayCalendar.from_csv(path)`  | 内閣府 CSV を直接読む最短ルート                             |
| `HolidayCalendar.from_sources(...)` | 複数の `HolidaySource` をマージするルート                  |
| `is_business_day(d, *, calendar)` | カレンダー指定で営業日かを返すモジュールレベル関数        |
| `CabinetOfficeCSVSource`          | 内閣府 CSV を URL + キャッシュで取得する `HolidaySource`   |
| `ComkenMasterTableSource`         | 社内管理表の「会社休日」シートを読む `HolidaySource`        |
| `ComputedHolidaySource`           | 計算で祝日の和集合を返す `HolidaySource`（mokejp/holidays_jp MIT 由来） |
| `HolidayCalendarError` 系         | 例外（`HolidayCalendarFetchError` / `HolidayCalendarSourceError` / `HolidayCalendarFormatError` / `HolidayCalendarExpiredError`） |

`HolidayCalendar.is_business_day` はキーワード専用 `skip_weekends=True` を持ち、
`False` にすると土曜・日曜でも祝日でなければ「営業日」と判定する
（振替休日を平日扱いしたいシナリオ用）。

## 注意事項

- **祝日名は業務情報ではない**ため、ドキュメント・ログに出してよい
  （`docs/csv.md` の「値そのもの」の禁止とは別）。
- 同じ日付に複数の祝日が登録されたときは**先勝ち + WARNING ログ**
  （内閣府と管理表で重なったときに、後から来た方を黙って捨てない）。
- 内閣府 CSV 以外のファイル（シフト JIS でない・日付列が無いなど）を
  内閣府 CSV として読み込もうとすると `HolidayCalendarFormatError` で止める。

## 関連

- 内閣府: <https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv>
- comken 仕様書 §4.35: `docs/開発/仕様書.md`
- comken 例外階層: `comken/exceptions/__init__.py`