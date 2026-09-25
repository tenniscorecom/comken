# comken.core.calendar — カレンダー判定ライブラリ

RPA 置き換えプロジェクトで「いま取るべきレポートか」を判定するために使う、
**会社用カレンダー CSV** ベースの営業日判定ライブラリ。

実装本体は `comken/core/calendar/` 配下にある（外部ライブラリに依存しない）。
内閣府の祝日 CSV と会社休日ルールを合成した「会社用カレンダー CSV」を
`comken/core/calendar/data/company_calendar.csv` に **git 管理下で同梱** しており、
**Python 実行時と VBA 側の両方が同じ 1 ファイルを読む**。自動ダウンロード機能は
廃止した（YAGNI）。

ライブラリは **既定カレンダー 1 本だけ** を公開する。利用者が独自のカレンダーを
組み立てる API は公開していない（差し替え口はテスト用の **非公開** 関数のみ）。
会社独自の休業日は `comken/core/calendar/build.py` の冒頭で **コード直書き**
で表現する（`COMPANY_HOLIDAYS` / `COMPANY_HOLIDAYS_EXTRA`）。

国民の祝日と会社休日をマージして、`is_business_day()` で「今日が営業日か」を
判定する。国民の祝日と会社休日が同じ日に重なった場合は **国民の祝日が先勝ち**
（生成ツールが 1 行に焼き込んでいる）。

## 全体像

```mermaid
graph LR
    A[内閣府 syukujitsu.csv<br/>comken/core/calendar/data/] --> B[comken.core.calendar.build<br/>合成ツール]
    C[build.py 冒頭の定数<br/>会社休日ルール] --> B
    B --> D[company_calendar.csv<br/>comken/core/calendar/data/]
    D --> E[Python: comken.core.calendar<br/>読むだけ]
    D --> F[VBA: Excel / Access から参照<br/>読むだけ]
```

| 段階 | 知っていること | 知らないこと |
|---|---|---|
| 内閣府 CSV（`comken/core/calendar/data/syukujitsu.csv`） | 国民の祝日の「公表値」 | 会社休日・最終的な生成物 |
| 生成ツール（`comken.core.calendar.build`） | 内閣府 CSV の形式・会社休日ルール | 実行時の利用方法 |
| **生成物**（`comken/core/calendar/data/company_calendar.csv`） | （国民の祝日＋会社休日を焼いただけ） | ー |
| 実行時（Python） | （生成物を読むだけ） | 内閣府 CSV・会社休日ルール |
| VBA | （生成物を読むだけ） | 内閣府 CSV・会社休日ルール |

内閣府 CSV の解析は **生成ツールだけ** が持つ（形式が変わって困るのは
生成ツールだけ）。実行時（Python・VBA 双方）は内閣府 CSV を知らずに
CSV を読むだけ。

## 最短の使い方

```python
from datetime import date

from comken.core.calendar import is_business_day

if is_business_day(date.today()):     # 既定カレンダーで判定
    ...  # レポートを取りに行く
```

`is_business_day` / `business_day_after` / `last_business_day_of_month` /
`is_holiday` / `holiday_name` などは **既定カレンダー** をそのまま使う。
カレンダーを組み立てる API は公開していない。

## 会社休日の定義

会社の休業日は `comken/core/calendar/build.py` の冒頭でコードで書く。

```python
# comken/core/calendar/build.py
COMPANY_HOLIDAYS = {
    "年末年始休暇": ((12, 29), (12, 30), (12, 31), (1, 1), (1, 2), (1, 3)),
}
COMPANY_HOLIDAYS_EXTRA = ()  # その年だけの臨時休業。date(2026, 12, 28) のように足す
```

`COMPANY_HOLIDAYS` は **毎年繰り返す** 休み（年は書かない）。内閣府 CSV の
収録範囲（最初の年〜最後の年）に合わせて展開される。国民の祝日と重なった日は
**国民の祝日が先勝ち** で 1 行に焼き込まれる。`COMPANY_HOLIDAYS_EXTRA` は
その年だけの臨時休業で、名称は `会社休業日` になる。

休業日を追加するときは `build.py` 冒頭の定数を編集する。

- **複数日まとめて 1 つの名称** が要るときは、`COMPANY_HOLIDAYS` の 1 キーに
  `(月, 日)` を並べる（上の「年末年始休暇」のように）
- 年またぎ（12 月 → 1 月）も `(月, 日)` で書けばそのまま毎年適用される
- **その年だけ臨時の休み** を足したいときは `COMPANY_HOLIDAYS_EXTRA` に足す。
  古くなった年の行は消してよい（消しても過去の判定が変わるだけで、運用に
  影響しない）
- 編集したら `python -m comken.core.calendar.build` を実行して
  `company_calendar.csv` を更新しコミットする

## 生成物（`company_calendar.csv`）

国民の祝日と会社休日を 1 ファイルに合成した「会社用カレンダー CSV」。
`comken/core/calendar/data/company_calendar.csv` に **git 管理下** で置かれる。

| 列 | 形式 | 内容 |
|---|---|---|
| `date` | `YYYY-MM-DD` | 日付 |
| `name` | 文字列 | 国民の祝日名または会社休日名 |

- **文字コード**: UTF-8 BOM 付き。Excel で開いても文字化けしない。VBA の `Open` 文は ANSI（CP932）前提で読むため、**祝日名が化け、1行目に BOM が混ざる**。VBA からは下の `ADODB.Stream` の例のように UTF-8 を指定して読むこと（日付の列だけなら `Open` 文でも読めるが、1行目の BOM に注意）
- **並び順**: 日付昇順
- **国民の祝日と会社休日の重複**: 国民の祝日が先勝ちで 1 行だけ
- **土日との重複**: 振替は行わない（土日がそのまま休業）
- **生成物の中身は内閣府 CSV と会社休日ルールだけで決まり、呼ぶ日に依存しない**

### VBA から読むときの例

`comken/core/calendar/data/company_calendar.csv` は UTF-8 BOM 付きなので、VBA では
`ADODB.Stream` で文字コードに UTF-8 を指定して読む（`Open` 文だと祝日名が化ける）。

```vba
' 祝日かどうかを返す例（Dictionary に読み込んで判定する）
Function LoadCalendar(ByVal csvPath As String) As Object
    Dim dict As Object, stm As Object, lines() As String, i As Long, parts() As String
    Set dict = CreateObject("Scripting.Dictionary")
    Set stm = CreateObject("ADODB.Stream")
    stm.Type = 2                 ' adTypeText
    stm.Charset = "UTF-8"        ' BOM 付きでも UTF-8 として読める
    stm.Open
    stm.LoadFromFile csvPath
    lines = Split(stm.ReadText, vbCrLf)
    stm.Close
    For i = 1 To UBound(lines)   ' 0 行目は見出し（date,name）
        If Len(lines(i)) > 0 Then
            parts = Split(lines(i), ",")
            dict(parts(0)) = parts(1)   ' キーは "2026-01-01" 形式の文字列
        End If
    Next i
    Set LoadCalendar = dict
End Function

' 使い方: If cal.Exists(Format(d, "yyyy-mm-dd")) Then ... （祝日・会社休日）
```

ファイルは git 管理下の正本で、共有サーバーのチェックアウト（リリースタグ）にある `company_calendar.csv` を、Python と同じパスのまま参照する。タグを切り替えるまで内容は変わらないので、Python と VBA は常に同じカレンダーを読む。
**収録範囲外の日付は「祝日ではない」扱いになる**（下の「範囲外の扱い」を参照）。

## 年 1 回の更新手順

内閣府は **毎年 2 月頃** に翌年分の祝日を公表する。更新は以下の流れで行う:

1. 開発機で内閣府の `syukujitsu.csv` をダウンロードする
   （URL: <https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv>）
2. `comken/core/calendar/data/syukujitsu.csv` をダウンロードしたファイルで
   上書きする（文字コード CP932 のまま。中身を変換しない）
3. `python -m comken.core.calendar.build` を実行して
   `comken/core/calendar/data/company_calendar.csv` を再生成する
4. `syukujitsu.csv` と `company_calendar.csv` をまとめてコミットし、push する
5. リリースタグを打つ（共有サーバーのチェックアウトは**リリース済みのタグだけ**に保つ運用のため。`docs/ARCHITECTURE.md` の「パッケージ構成と配置・運用」を参照）
6. 共有サーバー側で、そのタグをチェックアウトして配布する（**ブランチをチェックアウトしない**）

## 会社休日変更手順

年末年始休暇の日付を変える等、会社休日ルールを変えるとき:

1. `comken/core/calendar/build.py` 冒頭の `COMPANY_HOLIDAYS` /
   `COMPANY_HOLIDAYS_EXTRA` を直す
2. `python -m comken.core.calendar.build` を実行する
3. `company_calendar.csv` の更新をコミットする

## 範囲外の扱い

`company_calendar.csv` の収録範囲（内閣府 CSV の最初の年〜最後の年）の
**外の日付** には、国民の祝日も会社休日も付かない（土日だけで営業日判定される）。
範囲を延ばすには内閣府 CSV を入れ替えて再生成する。

例:

| 日付 | 収録範囲内か | `is_holiday()` |
|---|---|---|
| 2026-05-04（みどりの日） | 内 | `True` |
| 2027-12-31（年末年始休暇） | 内 | `True` |
| 2028-05-03（憲法記念日相当） | **外** | `False` |
| 2028-12-31 | **外** | `False` |

期限切れ警告（後述）は「収録最終日」が今日に近づいたときに出るため、
2027 年分の内閣府 CSV を公表されたらすぐ取り込み直す運用が望ましい。

## 期限切れの警告

収録済み祝日のうち最も新しい日付（`company_calendar.csv` の最後の行）を
「収録最終日」とし、「今日」が収録最終日に近づいたら WARNING ログを出す。

| 状況 | 挙動 |
|---|---|
| 今日 < 収録最終日 − 30 日 | 警告なし |
| 収録最終日 − 30 日 <= 今日 <= 収録最終日 | WARNING ログを **同じ日に 1 度だけ** 出す |
| 今日 > 収録最終日 | 警告なしで動くが、`is_holiday()` は常に `False`（「祝日ではない」側） |

期限切れ後はあえて「祝日ではない」側に倒す——誤って「祝日扱い」にしてレポートを
取り逃すより、誤って「平日扱い」して RPA を走らせ、次回ログから気付く方が
被害が少ないため。

## 公開 API

| 名前 | 役割 |
|---|---|
| `is_holiday(d)` | 国民の祝日または会社休日に当たれば `True` |
| `holiday_name(d)` | 国民の祝日または会社休日の名称を返す（無ければ `None`） |
| `is_business_day(d, *, skip_weekends=True)` | 国民の祝日＋会社休日＋土日を判定して `True`/`False` |
| `business_day_after(d, *, skip_weekends=True)` | `d` より後で最初の営業日（`d` 自身を含まない） |
| `business_day_before(d, *, skip_weekends=True)` | `d` より前で最初の営業日（`d` 自身を含まない） |
| `non_business_days_after(d, *, skip_weekends=True)` | `d` の翌日から、次の営業日の前日までの休みの日（連休）を日付順に返す。翌日が営業日なら空 |
| `non_business_days_before(d, *, skip_weekends=True)` | `d` の前日から、前の営業日の翌日までの休みの日を、`d` に近い順に返す |
| `business_day_on_or_after(d, *, skip_weekends=True)` | `d` 以降で最初の営業日（`d` を含む） |
| `business_day_on_or_before(d, *, skip_weekends=True)` | `d` 以前で最初の営業日（`d` を含む） |
| `first_business_day_of_month(d, *, skip_weekends=True)` | `d` の月の最初の営業日 |
| `last_business_day_of_month(d, *, skip_weekends=True)` | `d` の月の最後の営業日 |
| `nth_business_day_of_month(d, n, *, skip_weekends=True)` | `d` の月の第 `n` 営業日（`n` は 1 始まり） |
| `add_business_days(d, n, *, skip_weekends=True)` | `d` から `n` 営業日後の日付（`n` が負なら前） |
| `warn_if_calendar_expiring_soon()` | 既定カレンダーの収録期限が近ければ起動時に WARNING を出す |
| `BUSINESS_DAY_SEARCH_LIMIT` | 「次の営業日」探索の上限日数（既定 30） |
| `EXPIRING_WARNING_DAYS` | 期限切れ警告を出すまでの日数（既定 30） |
| `CALENDAR_CSV_PATH` | 会社用カレンダーCSV のパス（git 管理下の正本） |
| `CalendarError` 系 | 例外（`CalendarFormatError` / `BusinessDayNotFoundError`） |

`skip_weekends=False` にすると土曜・日曜でも祝日でなければ「営業日」と
判定する（振替休日を平日扱いしたいシナリオ用）。
このフラグは `business_day_after` / `first_business_day_of_month` など、
他の営業日オフセット計算にも同じキーワード専用で渡せる。

### 営業日オフセットの選び方

`after` / `before` は「その日を含まない」、`on_or_after` / `on_or_before` は
「その日を含む」。営業日かどうかにかかわらず、必ずしも「その日が答え」に
なるわけではないので、要件に合わせて選ぶ。

```python
from datetime import date
from comken.core.calendar import (
    business_day_after,
    business_day_on_or_before,
    last_business_day_of_month,
    nth_business_day_of_month,
)

# 月末の最終営業日（例: 月末が土日祝なら直前の営業日）
last_business_day_of_month(date(2026, 8, 20))

# 月初の営業日（例: 1日が土日祝なら翌営業日）
first_business_day_of_month(date(2026, 8, 20))

# 第 3 営業日
nth_business_day_of_month(date(2026, 8, 20), 3)

# 15 日、休みならその前の営業日
business_day_on_or_before(date(2026, 8, 15))

# 8/20 の「翌営業日」。8/20 が営業日でも翌営業日が返る
business_day_after(date(2026, 8, 20))
```

`business_day_after(d)` は `d` 自身が営業日でも翌日以降を返す点に注意。
「今日から 1 営業日後」を `add_business_days(d, 1)` で書いた場合は、
`d` が営業日でも翌営業日（n 営業日分進む）が返る。
「翌営業日」と「1 営業日後」は別物なので、目的に合わせて使い分ける。

| 関数 | `d` が営業日のとき | `d` が非営業日のとき |
| --- | --- | --- |
| `business_day_after` | `d` の次の営業日 | `d` より後で最初の営業日 |
| `business_day_before` | `d` の前の営業日 | `d` より前で最初の営業日 |
| `business_day_on_or_after` | `d` 自身 | `d` 以降で最初の営業日 |
| `business_day_on_or_before` | `d` 自身 | `d` 以前で最初の営業日 |

「`d` を含むかどうか」だけが違うので、「`d` が営業日のときにスキップして
ほしくない」ケースは `on_or_*` を選ぶ。

`nth_business_day_of_month` は、`n` が月の営業日数を超える場合と、その月に
営業日が 1 日も無い場合のどちらも `BusinessDayNotFoundError`。

## 注意事項

- **国民の祝日名・会社休日名は業務情報ではない**ため、ドキュメント・ログに
  出してよい（`docs/機能/csv.md` の「値そのもの」の禁止とは別）。
- 国民の祝日と会社休日が同じ日に重なった場合は**国民の祝日が先勝ち**
  （生成ツールが 1 行に焼き込んでいるため）。
- 収録範囲外の日付は国民の祝日も会社休日も付かない（`is_holiday()` が
  `False`）。範囲を延ばすには内閣府 CSV を入れ替えて再生成する。
- 会社用カレンダーCSV が壊れている・ヘッダーが違う・日付が解釈できない場合は
  `CalendarFormatError` で止める（業務運用の場面）。
- **ネットワークには一切出ない。** `comken.core` は `requests` を import
  しないので、オフライン環境・社内 BO 端末でもそのまま動く。

## 関連

- 内閣府: <https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv>
- comken 設計書: `docs/ARCHITECTURE.md`
- comken 例外階層: `comken/exceptions/__init__.py`
- 生成ツール: `comken/core/calendar/build.py`（`python -m comken.core.calendar.build`）
- 会社休日ルール: `comken/core/calendar/build.py` 冒頭の `COMPANY_HOLIDAYS`
