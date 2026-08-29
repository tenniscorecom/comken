# comken.core.holidays — 祝日判定ライブラリ

RPA 置き換えプロジェクトで「いま取るべきレポートか」を判定するために使う、
内閣府の祝日 CSV を基にした祝日判定ライブラリ。

実装本体は `comken.core.holidays/` 配下にある（外部ライブラリに依存しないため
`core` 層へ移設済み）。`comken.toolbox.holidays` は旧パスからの
後方互換 re-export のみで、**新規コードでは `comken.core.holidays` を使うこと**。

`HolidayCalendar` 1 個に「内閣府の祝日」と「会社の休業日」をマージして
持ち、`is_business_day()` でその日が営業日かを判定する。

## 最短の使い方

ネットワークから内閣府の `syukujitsu.csv` を取ってきたいとき（業務 PC で `requests` が
使える環境）は次の通り。`CabinetOfficeCSVSource` だけ toolbox 側にある
（`comken.core` は `requests` を import しないため）。

```python
from datetime import date

from comken.core.holidays import (
    CompanyHolidaySource,
    HolidayCalendar,
    is_business_day,
)
from comken.toolbox.holidays.sources.cabinet_office import CabinetOfficeCSVSource

calendar = HolidayCalendar.from_sources(
    [
        CabinetOfficeCSVSource(),  # 既定: 同梱 CSV をそのまま使う
        CompanyHolidaySource(),    # コード直書きの会社休日
    ]
)

if is_business_day(date.today(), calendar=calendar):
    ...  # レポートを取りに行く
```

## 取得元

| ソース               | 概要                                                       | 必要なもの                |
| -------------------- | ---------------------------------------------------------- | ------------------------- |
| `CabinetOfficeCSVSource`   | 内閣府の `syukujitsu.csv` を URL から取得                  | `requests` （取得時のみ） |
| `ComputedHolidaySource`    | 純粋計算で祝日を組み立てる（mokejp/holidays_jp MIT 由来）  | 標準ライブラリのみ        |
| `CompanyHolidaySource`     | 会社の休業日をコードに直書きして返す                       | 標準ライブラリのみ        |

内閣府 CSV は **CP932（Shift_JIS）** で配布され、列は
「国民の祝日・休日月日」「国民の祝日・休日名称」。1 行目はヘッダーなので
読み込み時にスキップする。

## 保存先（キャッシュ）

**内閣府 CSV は `comken/core/holidays/data/syukujitsu.csv` に同梱** している。
`CabinetOfficeCSVSource` は **この同梱 CSV を保存先としても使う**（git 管理下の
1ファイルが正本）。`default_calendar()` も同じファイルを指す。**PC ごとの
キャッシュは廃止** した（「どの PC のキャッシュがいつのものか」を追えなくなる
問題を防ぐため）。

`cache_path` 引数を渡せば **別の場所を指定できる**（既定以外を使うケース）。
ただし通常は変更しない。

```python
from comken.toolbox.holidays.sources.cabinet_office import CabinetOfficeCSVSource

source = CabinetOfficeCSVSource(
    cache_path=Path("D:/work/cache/syukujitsu.csv"),  # 既定以外を使うときだけ
)
```

`source.refresh()` を呼ぶと **同梱 CSV を上書き** する。共有サーバーの
**読み取り専用チェックアウト** で動かすとここで `PermissionError` で失敗する
（エラーメッセージに「どこに書こうとしたか」と「年1回の手動更新手順」が
出る）。通常は次の **年1回の手動更新** に乗せて配布する。

```text
1. 開発機で内閣府から取得（CabinetOfficeCSVSource().refresh() でも可）
2. git に差分が出るのでコミット → タグを打つ
3. 共有サーバー側で checkout
```

内閣府のデータは年に数回しか変わらないので、TTL は設けていない。

`HolidayCalendar.is_business_day` などはネットに繋がらずに動くので、
オフライン PC で requests が無いときも import は成功する。

## 内閣府 CSV の同梱（既定カレンダー）

既定カレンダー（→ [既定カレンダー](#既定カレンダーcalendar-を省略する書き方)）は、
内閣府の `syukujitsu.csv` を `comken/core/holidays/data/` に**同梱**している。
業務 PC がオフラインでも `default_calendar()` はそのまま動く。

- **年 1 回手動で更新する**（リポジトリを更新してタグを打つ流れに乗る）
- TTL による自動再取得はしない（年に数回の更新を毎日取りに行く設定は無駄だった）
- 収録期限（= 同梱 CSV に書かれた最新日付）が近づくと `EXPIRING_WARNING_DAYS`（既定 30 日）
  未満で **WARNING ログが 1 度だけ**出る（更新タイミングの検知）
- 期限を過ぎても止まらず `ComputedHolidaySource`（計算式）でカバーする。
  春分・秋分のみ内閣府発表日との ±1 日のずれが起きうる

## 会社休日

会社の休業日は `CompanyHolidaySource` で表す。**コードに直書きする**ため、
設定ファイルや管理表を編集する運用負荷が要らない。
**年が書いてない月日のリスト**で表現するので、**毎年のメンテナンスが要らない**
のが要点。

```python
from comken.core.holidays import CompanyHolidaySource

# 既定で 12/29-1/3 を「年末年始休暇」として休業扱い
source = CompanyHolidaySource()
```

休業日を追加するときは `CompanyHolidaySource` と同じディレクトリの
`company.py` 冒頭の定数を編集する:

```python
COMPANY_HOLIDAYS: Final[dict[str, tuple[tuple[int, int], ...]]] = {
    "年末年始休暇": ((12, 29), (12, 30), (12, 31), (1, 1), (1, 2), (1, 3)),
}

# その年だけの臨時の休み。年月日で書く
COMPANY_HOLIDAYS_EXTRA: Final[tuple[_dt.date, ...]] = ()
```

「年末年始休暇」のような**複数日まとめて 1 つ**の名称が要るときは
`COMPANY_HOLIDAYS` のキーに `((月, 日), (月, 日), …)` のタプルを書く。
1 日だけの休業は `((月, 日),)` のように 1 要素のタプルにする。
年またぎ（12 月 → 1 月）も月日の連なりで書けばそのまま毎年適用される。
**その年だけ臨時の休み**を足したいときは `COMPANY_HOLIDAYS_EXTRA` に
`date(2026, 12, 28)` のように年月日で 1 行足す。古くなった行は消してよい
（消しても過去の判定が変わるだけで、運用に影響しない）。

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
| `business_day_after(d, *, calendar)` | `d` より後で最初の営業日（`d` 自身を含まない）            |
| `business_day_before(d, *, calendar)` | `d` より前で最初の営業日（`d` 自身を含まない）           |
| `business_day_on_or_after(d, *, calendar)` | `d` 以降で最初の営業日（`d` を含む）           |
| `business_day_on_or_before(d, *, calendar)` | `d` 以前で最初の営業日（`d` を含む）           |
| `first_business_day_of_month(d, *, calendar)` | `d` の月の最初の営業日                      |
| `last_business_day_of_month(d, *, calendar)`  | `d` の月の最後の営業日                      |
| `nth_business_day_of_month(d, n, *, calendar)` | `d` の月の第 `n` 営業日（`n` は 1 始まり） |
| `add_business_days(d, n, *, calendar)` | `d` から `n` 営業日後の日付（`n` が負なら前）           |
| `BUSINESS_DAY_SEARCH_LIMIT`       | 「次の営業日」探索の上限日数（既定 30）                     |
| `BUNDLED_CSV_PATH`                | 内閣府 CSV を同梱しているパス（git 管理下の正本）           |
| `CabinetOfficeCSVSource`          | 内閣府 CSV を URL から取得して `BUNDLED_CSV_PATH` へ書く `HolidaySource` |
| `ComputedHolidaySource`           | 計算で祝日の和集合を返す `HolidaySource`（mokejp/holidays_jp MIT 由来） |
| `CompanyHolidaySource`            | 会社独自の休業日（コード直書き）の `HolidaySource`         |
| `HolidayCalendarError` 系         | 例外（`HolidayCalendarFetchError` / `HolidayCalendarSourceError` / `HolidayCalendarFormatError` / `BusinessDayNotFoundError`） |

`HolidayCalendar.is_business_day` はキーワード専用 `skip_weekends=True` を持ち、
`False` にすると土曜・日曜でも祝日でなければ「営業日」と判定する
（振替休日を平日扱いしたいシナリオ用）。
このフラグは `business_day_after` / `first_business_day_of_month` など、
他の営業日オフセット計算にも同じキーワード専用で渡せる。

### 営業日オフセットの選び方

`after` / `before` は「その日を含まない」、`on_or_after` / `on_or_before` は
「その日を含む」。営業日かどうかにかかわらず、必ずしも「その日が答え」に
なるわけではないので、要件に合わせて選ぶ。

```python
from datetime import date
from comken.core.holidays import (
    HolidayCalendar,
    business_day_after,
    business_day_on_or_before,
    last_business_day_of_month,
    nth_business_day_of_month,
)

cal = HolidayCalendar(...)  # 構築は省略

# 月末の最終営業日（例: 月末が土日祝なら直前の営業日）
last_business_day_of_month(date(2026, 8, 20), calendar=cal)

# 月初の営業日（例: 1日が土日祝なら翌営業日）
first_business_day_of_month(date(2026, 8, 20), calendar=cal)

# 第 3 営業日
nth_business_day_of_month(date(2026, 8, 20), 3, calendar=cal)

# 15 日、休みならその前の営業日
business_day_on_or_before(date(2026, 8, 15), calendar=cal)

# 8/20 の「翌営業日」。8/20 が営業日でも翌営業日が返る
business_day_after(date(2026, 8, 20), calendar=cal)
```

`business_day_after(d)` は `d` 自身が営業日でも翌日以降を返す点に注意。
「今日から 1 営業日後」を `add_business_days(d, 1)` で書いた場合は、
`d` が営業日でも翌営業日（n 営業日分進む）が返る。
「翌営業日」と「1 営業日後」は別物なので、目的に合わせて使い分ける。

| 関数                    | `d` が営業日のとき | `d` が非営業日のとき         |
| ----------------------- | ------------------ | ---------------------------- |
| `business_day_after`    | `d` の次の営業日   | `d` より後で最初の営業日     |
| `business_day_before`   | `d` の前の営業日   | `d` より前で最初の営業日     |
| `business_day_on_or_after`  | `d` 自身       | `d` 以降で最初の営業日       |
| `business_day_on_or_before` | `d` 自身       | `d` 以前で最初の営業日       |

「`d` を含むかどうか」だけが違うので、「`d` が営業日のときにスキップして
ほしくない」ケースは `on_or_*` を選ぶ。

`nth_business_day_of_month` は月の初日から数えて `n` 番目の営業日。
その月の営業日数を超える `n` を渡すと `BusinessDayNotFoundError`。
その月に営業日が 1 日も無い月でも `BusinessDayNotFoundError`。

`business_day_after` 系の探索は最大 `BUSINESS_DAY_SEARCH_LIMIT` 日
（既定 30 日）で打ち切り、見つからなければ `BusinessDayNotFoundError` を送る。
祝日データが壊れていたり、`CompanyHolidaySource` に休日を広範囲に登録してしまった
ときの無限ループを防ぐため。

## 既定カレンダー（`calendar` を省略する書き方）

`is_business_day` / `business_day_after` / `last_business_day_of_month` などの
**モジュール関数版**は `calendar=` を省略できる。省略時は「既定カレンダー」
が使われ、利用者は `HolidayCalendar` を組み立てずに済む。

```python
from datetime import date
from comken.core.holidays import (
    is_business_day,
    business_day_after,
    nth_business_day_of_month,
)

if is_business_day(date.today()):           # 既定カレンダーで判定
    ...

nth_business_day_of_month(date.today(), 3)  # 今月の第 3 営業日
```

既定カレンダーは次の 3 つから組み立てる。**ネットワークには一切出ない。**

1. `ComputedHolidaySource`（純粋計算。土台）
2. 同梱の `comken/core/holidays/data/syukujitsu.csv`（内閣府の実値。計算式の上書き用）
3. `CompanyHolidaySource`（会社の休業日。コード直書き）

`CabinetOfficeCSVSource` は `requests` 依存・業務 PC の通信制限に阻まれる
ため既定には含めない。**`comken.core` は `requests` を import しないので、
オフライン環境・社内 BO 端末でも `from comken.core import is_business_day`
がそのまま動く。**

会社独自の年末年始などを追加したいプロジェクトは、起動時に
`set_default_calendar()` を一度呼んで差し替える。

```python
from comken.core.holidays import (
    HolidayCalendar,
    ComputedHolidaySource,
    CompanyHolidaySource,
    set_default_calendar,
)

# 起動時に 1 回だけ呼ぶ
my_calendar = HolidayCalendar.from_sources([
    ComputedHolidaySource(),
    CompanyHolidaySource(),
])
set_default_calendar(my_calendar)

# 以降は calendar= なしで使える
```

`set_default_calendar(None)` でリセットすると、次回の呼び出しで
既定の遅延生成に戻る。

## 注意事項

- **祝日名は業務情報ではない**ため、ドキュメント・ログに出してよい
  （`docs/csv.md` の「値そのもの」の禁止とは別）。
- 同じ日付に複数の祝日が登録されたときは**先勝ち**で採用される
  （内閣府 CSV と会社の年末年始休暇など、複数 source が同じ日を
  返すのは正常な状態）。
- 内閣府 CSV 以外のファイル（シフト JIS でない・日付列が無いなど）を
  内閣府 CSV として読み込もうとすると `HolidayCalendarFormatError` で止める。

## 関連

- 内閣府: <https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv>
- comken 仕様書 §4.35: `docs/開発/仕様書.md`
- comken 例外階層: `comken/exceptions/__init__.py`
