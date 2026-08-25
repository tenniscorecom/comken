# comken 公開 API

> [!IMPORTANT]
> このファイルは自動生成物です。手で編集しないでください。
> 再生成: `python export_for_chat.py`

[README（ドキュメントの入口）へ戻る](../../README.md)

各パッケージの `__all__` にある公開名だけを掲載しています。

## `from comken import ...`

### `Config`

```text
class Config:
```

#### 説明

config.ini を読み込み、config.SECTION.KEY の形式でアクセスできるクラス。

値の型変換（_parse_value の変換順と同じ）:
    - true / false → bool
    - [a, b, c] → list[str]
    - 絶対パス（C:\ / \\ / /）→ Path
    - 整数 → int
    - 小数 → float
    - それ以外 → str

数値を文字列として使いたい場合はコード側で str() に変換する。

config.ini の例（セクション名・キー名は大文字で書く）:
    [BROWSER]
    WAIT_SECONDS = 10
    HEADLESS = false

    [FILES]
    INPUT_FOLDER = C:\作業\input

    [REPORT]
    TARGET_SHEETS = [支店A, 支店B, 集計]

``Config(path)`` は ``Path.resolve()`` 後の絶対パスをキーに **プロセス内で
1 度だけ** Config を構築してキャッシュする。 同じパスで 2 回目を呼ぶと
同じインスタンスが返る。 **同じパスのファイルを書き換えても反映されない**
（反映には ``_reset_cached_config()`` を呼ぶ）。 ``stat()`` による更新確認は
しない（業務ツールは実行中の設定変更を想定しない。詳細は
``_get_or_build_config`` の docstring）。

#### `__init__`

```text
def __init__(self, path: str | Path | None=None) -> None:
```

### `config`

定義を解決できませんでした。

### `debug`

```text
@contextmanager
def debug(enabled: bool=True) -> Iterator[None]:
```

#### 説明

ブロック内だけデバッグモードにする。

Args:
    enabled: True で有効（デフォルト）。False ならブロック内だけ無効。

### `dry_run`

```text
@contextmanager
def dry_run(enabled: bool=True) -> Iterator[None]:
```

#### 説明

ブロック内だけ dry-run モードにする。

Args:
    enabled: True で有効（デフォルト）。False ならブロック内だけ無効。

### `Backoffice`

```text
class Backoffice(LoggerSite):
```

#### 説明

バックオフィス環境のログ設定。

comken 共通のクラス。OWNER は ``"comken"``。

### `Intranet`

```text
class Intranet(LoggerSite):
```

#### 説明

イントラネット環境のログ設定。

comken 共通のクラス。OWNER は ``"comken"``。

### `comken_logger`

定義を解決できませんでした。


## `from comken.core import ...`

### `BUSINESS_DAY_SEARCH_LIMIT`

公開定数。

### `ComputedHolidaySource`

```text
class ComputedHolidaySource(HolidaySource):
```

#### 説明

計算で祝日の和集合を返すソース。

``HolidaySource`` Protocol を実装する。``load()`` で ``Iterable[Holiday]`` を返す。
``CabinetOfficeCSVSource`` と並列に置いて、
``from_sources([Cabinet, Computed])`` のように和集合で運用する
（``HolidayCalendar`` 側の先勝ち WARNING ログが衝突をハンドリングする）。

このソースは **純粋計算のみ** — 外部通信・ファイル読み込みは一切しない。
社内 BO 環境（オフライン・pip 制限）でもそのまま動く。

Args:
    from_year: 対象範囲の開始年。省略時は ``DEFAULT_FROM_YEAR`` (1948)。
    to_year: 対象範囲の終了年。省略時は ``DEFAULT_TO_YEAR`` (2099)。
        範囲外でも祝日計算は走るが、春分／秋分の近似精度が下がる旨を
        WARNING ログで知らせる。

#### `__init__`

```text
def __init__(self, *, from_year: int | None=None, to_year: int | None=None) -> None:
```

#### `load`

```text
def load(self) -> list[Holiday]:
```

##### 説明

対象年の範囲について計算した祝日をまとめて返す。

Returns:
    日付順に並んだ ``Holiday`` のリスト。

### `DateNameBuilder`

```text
class DateNameBuilder:
```

#### 説明

今日の日付を付けたファイル名を組み立てる。

日付は ``__init__`` 時点で確定する。``for_date=None`` のときだけ
``__init__`` 呼び出し時点の日付を使い、``prefix()`` / ``suffix()`` を
呼ぶたびに日付を取り直すことはない。

日付はコンストラクタで固定できる。テストや過去日付のファイル名を組み立てる
ときは ``date(2026, 8, 20)`` 等を渡す。省略時は呼び出し時点の日付。

拡張子は **名前の文字列に含めて** 渡す（例: ``DateNameBuilder("ログ.csv")``）。
拡張子なしの名前は ``FileSuffixMissingError`` を送出して止める。

#### `__init__`

```text
def __init__(self, name: str, for_date: date | datetime | None=None) -> None:
```

##### 説明

Args:
    name: ファイル名（**拡張子を含む**）。例: ``"売上.xlsx"`` / ``"ログ.csv"``。
        拡張子が無いと ``FileSuffixMissingError``。
    for_date: ファイル名に付ける日付。``None``（既定）なら ``__init__``
        呼び出し時点の日付。``prefix()`` / ``suffix()`` を呼ぶたびに
        日付を取り直すことはない。``date`` / ``datetime`` どちらも
        受け付ける（``datetime`` は内部で ``.date()`` に変換）。

Raises:
    FileSuffixMissingError: ``name`` に拡張子が含まれていないとき。

#### `prefix`

```text
def prefix(self, prefix: str='{:%Y%m%d}_') -> str:
```

##### 説明

``prefix + 日付 + ベース名 + 拡張子`` を返す（例: ``"20260825_売上.xlsx"``）。

``prefix("DIY_{:%Y%m%d}_")`` のように日付の位置と書式を指定する。
日付書式を含まない prefix には ``YYYYMMDD`` を末尾へ補う。
日付は **拡張子の手前** に入る。

#### `suffix`

```text
def suffix(self, date_format: str='%Y%m%d') -> str:
```

##### 説明

今日の日付を後ろに付けたファイル名を返す（例: ``"売上_20260825.xlsx"``）。

日付は **拡張子の手前** に入る。メソッド名 ``suffix()`` と「拡張子（suffix）」が
紛らわしいため、内部状態は ``_extension``（= 拡張子）と ``_stem``（= 拡張子を除いた
ベース名）で持つ。``self._extension`` は常にドット付きで ``".xlsx"`` / ``".csv"`` 等。

### `DateFileFinder`

```text
class DateFileFinder:
```

#### 説明

指定した名前と日付を持つファイルを探す。

探す名前に **拡張子を含める**（例: ``"売上レポート.csv"``）。拡張子無しの名前を
渡すと ``FileSuffixMissingError`` で止める。

**注意: ``prefix()`` / ``dated()`` は呼ぶたびにフォルダを走査する**。 同じ結果を
何度も使うなら変数に受けること（業務時間中に新しいファイルが降ってくる前提の
道具なので、 敢えてキャッシュしていない）。

#### `__init__`

```text
def __init__(self, folder: str | Path, for_date: datetime.date | None=None) -> None:
```

#### `prefix`

```text
@measure
def prefix(self, name: str, required: bool=True) -> Path | None:
```

##### 説明

``prefix + 日付 + 拡張子`` に一致するファイルを返す。

``name`` に ``{:%Y-%m-%d}`` のような日付書式があれば、その位置へ日付を
入れる。書式がなければ末尾へ ``YYYYMMDD`` を付ける。日付は **拡張子の手前** に入る。

#### `dated`

```text
@measure
def dated(self, prefix: str) -> list[Path]:
```

##### 説明

``prefix`` で始まり日付を含むファイルを全件、日付の新しい順で返す。

``prefix`` には **拡張子を含む完全なファイル名の一部** を渡す（例:
``"売上レポート.csv"`` — 拡張子は必須）。フォルダ内のファイル名から
``date_in_name`` で日付を取り出し、**日付の新しい順** に並べる。同じ日付の
ときは更新日時が新しい方を先にする。該当するファイルが無ければ空リストを
返す（例外は出さない）。

``prefix()`` との違い:

- ``prefix`` 内の日付書式（``{:%Y-%m-%d}`` 等）は解釈せず、文字どおりの前方一致だけを行う。
- コンストラクタの ``for_date`` は使わない。フォルダ内の全件が対象になる。
- 見つからないときに例外を上げず、空リストを返す（``required`` 相当の引数も無い）。

Args:
    prefix: ファイル名の先頭（この通りの前方一致。日付書式は解釈しない）。
        拡張子は必須。

Returns:
    日付の新しい順に並んだ ``Path`` のリスト。同じ日付のときは更新日時が新しい順。
    該当するファイルが無ければ空リスト。

Raises:
    FileSuffixMissingError: ``prefix`` に拡張子が含まれていないとき。

### `DiffResult`

```text
class DiffResult:
```

#### 説明

diff_rows の結果。

なぜ added / removed が ``Table`` で changed が ``list[RowChange]`` なのか —
``changed`` の1件は「変更前・変更後・差分列」の3つを抱えており、表の1行に収まらない
（同じ列名で2つの値を並べると区別できない）ため ``RowChange`` のリストのままで持つ。
一方 ``added`` / ``removed`` は表の行と同じ形なので ``Table`` へ揃え、
``filter`` / ``select`` / ``count`` などの Table 標準の操作が直接使えるようにしてある。

この ``added`` / ``removed`` と ``TableComparison.only_in_read`` / ``only_in_write``
は名前こそ近いが別の系統で、前者は時系列の差分（昨日のデータ → 今日のデータ）、
後者は2つの表の突合（read 側と write 側）であり、方向の意味が違う。
1つに統一せず、用途が違うものは別の名前で持つのが正しい。``diff_rows`` は
時系列の差分なので ``added`` / ``removed`` の語彙を維持する。

### `EXPIRING_WARNING_DAYS`

公開定数。

### `Holiday`

```text
class Holiday:
```

#### 説明

祝日の1件。日付と名称だけを運ぶシンプルな箱。

Attributes:
    date: 祝日の日付（時刻・タイムゾーンは持たない業務日付）。
    name: 祝日の日本語名称（例: "建国記念の日"）。
    approximate: ``True`` なら、計算式など内閣府発表と ±1 日前後する
        可能性がある値。``HolidayCalendar.is_holiday`` などで該当 Holiday
        を返したときに WARNING ログを出して、業務フローを止めずに気づける
        ようにする。デフォルトは ``False``（内閣府 CSV 由来または確実な
        計算結果）。

### `HolidayCalendar`

```text
class HolidayCalendar:
```

#### 説明

祝日を保持し、営業日判定を行うカレンダー本体。

同じ日付に複数の祝日が登録された場合は**先勝ち**で採用する
（内閣府 CSV と会社の年末年始休暇など、複数 source の重複は珍しくない）。
名称が違う祝日が同じ日に重なっても黙って先を採用する。

期限切れの警告（``EXPIRING_WARNING_DAYS`` を切った日）は **同じ日に
1回だけ**出す。同じ日に ``is_business_day`` が何回呼ばれても
ログが埋もれないため。

#### `__init__`

```text
def __init__(self, holidays: Iterable[Holiday]) -> None:
```

##### 説明

``Holiday`` の iterable から ``{日付: Holiday}`` の索引を作る。

Args:
    holidays: 祝日の iterable。同じ日付が複数含まれていたら先勝ちで採用。

#### `from_csv`

```text
@classmethod
def from_csv(cls, path: str | Path, *, encoding: str='cp932') -> 'HolidayCalendar':
```

##### 説明

内閣府の ``syukujitsu.csv`` を直接読む最短ルート。

Args:
    path: CSV のパス。CP932（Shift_JIS）固定。
    encoding: 文字コード。通常は ``cp932`` のままで良い。

Returns:
    読み込み結果から作った ``HolidayCalendar``。

#### `from_sources`

```text
@classmethod
def from_sources(cls, sources: Iterable[HolidaySource]) -> 'HolidayCalendar':
```

##### 説明

複数の ``HolidaySource`` を合体させる（内閣府 + Computed + 会社休日 など）。

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

#### `is_holiday`

```text
def is_holiday(self, target: _dt.date) -> bool:
```

##### 説明

``target`` が祝日（または休日）なら ``True``。

ターゲットが今年/来年なら、内閣府 source への強制再取得を試みる
（今年中に 1 回だけ。失敗時はサイレント）。
計算式由来の暫定値（``approximate=True``）を返すときは WARNING ログ。

#### `holidays_in`

```text
def holidays_in(self, start: _dt.date, end: _dt.date) -> list[Holiday]:
```

##### 説明

``start <= 日付 <= end`` の範囲に入る祝日を、日付順に返す。

Args:
    start: 範囲開始（含む）。
    end: 範囲終了（含む）。

Returns:
    範囲内の ``Holiday`` を日付昇順で並べたリスト。
    該当が無ければ空リスト。

#### `expires_after`

```text
def expires_after(self, target: _dt.date) -> bool:
```

##### 説明

``target`` が収録済み最終日以降（＝「収録期限を過ぎた」）なら ``True``。

「収録済み最終日 <= target」を期限切れとみなす。等号を含めるのは、
「収録最終日ぴったり」を「期限の境目」として扱うため（最終日当日は
収録済みの祝日として判定できるが、それ以降は収録外）。

#### `days_until_expiry`

```text
def days_until_expiry(self, today: _dt.date) -> int:
```

##### 説明

``today`` から収録最終日までの日数。最終日を過ぎていれば負の値。

Args:
    today: 「今日」とみなす日付。

Returns:
    ``last_known - today`` の日数差。収録済み祝日が無いと ``-1``。

#### `last_known_date`

```text
def last_known_date(self) -> _dt.date | None:
```

##### 説明

収録済み祝日のうち最も新しい日付。無ければ ``None``。

#### `holiday_names`

```text
def holiday_names(self, target: _dt.date) -> Sequence[str]:
```

##### 説明

``target`` に登録された祝日名称のタプル（同日が複数あれば複数要素）。

#### `all_holidays`

```text
def all_holidays(self) -> list[Holiday]:
```

##### 説明

保持している祝日を日付順に並べたリストを返す。

### `HolidaySource`

```text
class HolidaySource(Protocol):
```

#### 説明

祝日を 1セット取り出せる仕組みの共通インタフェース。

内閣府の ``CabinetOfficeCSVSource`` や ``ComputedHolidaySource`` / 会社の
``CompanyHolidaySource`` の両方がこれを実装するため、利用側は入手経路を
意識せずに ``from_sources`` に渡せる。

この Protocol はメソッドの型を ``Iterable[Holiday]`` に固定する。
``load()`` を呼んだその瞬間に取得が走る（キャッシュは実装側で持つ）のが
一貫していて読みやすい。実装が iterable を返したい場合は
中で ``list()`` してから返してもよい。

#### `load`

```text
def load(self) -> Iterable[Holiday]:
```

##### 説明

祝日セットを取り出して ``Iterable[Holiday]`` で返す。

### `RefreshableHolidaySource`

```text
class RefreshableHolidaySource(Protocol):
```

#### 説明

TTL を無視して強制再取得できる祝日 source（例: 内閣府の ``CabinetOfficeCSVSource``）。

``HolidayCalendar`` がターゲットが今年/来年のときに内閣府への
再取得を試みるためのフック。短いタイムアウト（既定 0.5 秒）で実装する。
必須ではなく、管理表など再取得が要らない source は実装しなくてよい。

#### `refresh`

```text
def refresh(self) -> Iterable[Holiday]:
```

##### 説明

TTL を無視して強制再取得する。

### `RowChange`

```text
class RowChange:
```

#### 説明

diff_rows が返す「変更のあった行」の情報。

### `State`

```text
class State:
```

#### 説明

プログラムが次回実行へ持ち越す値を state.ini に保存する。

``set()`` は呼び出すたびに UTF-8 で原子的に保存する。dry-run 中に状態を
書くと、試運転したファイルが本番で処理済みと判断されうるため、ファイルは
変更せず、書く予定だった内容だけをログへ出す。

保存できる値は、真偽値・整数・小数・文字列・文字列のリスト。

Args:
    path: state.ini のパス。省略するとプロジェクトのフォルダ（main.py の場所）の
          state.ini。

#### `__init__`

```text
def __init__(self, path: str | Path | None=None) -> None:
```

#### `get`

```text
def get(self, key: str, default: StateValue | None=None) -> StateValue | None:
```

##### 説明

保存済みの値を返す。無い場合は default を返す。

#### `set`

```text
@measure
def set(self, key: str, value: StateValue) -> None:
```

##### 説明

値を保存する。dry-run 中はファイルもメモリ上の状態も変更しない。

### `Timer`

```text
class Timer:
```

#### 説明

処理時間を計測して INFO ログに出す。with・デコレータ両対応。

Attributes:
    elapsed: 経過秒数（float）。with を抜けた後に参照できる。

#### `__init__`

```text
def __init__(self, name: str='処理') -> None:
```

##### 説明

Args:
    name: ログに出す処理名（例: "CSV読み込み"）。

### `Table`

```text
class Table:
```

#### 説明

列と辞書行をメモリで扱う表。

CSVやExcelに直接依存しないため、加工処理をファイルI/Oから分離できます。
``types`` は入力時に明示された列だけを変換し、暗黙の型推測は行いません。

#### `__init__`

```text
def __init__(self, columns: list[str] | tuple[str, ...], rows: list[dict[str, Any]], *, types: Mapping[str, Callable[[Any], Any]] | None=None) -> None:
```

#### `read`

```text
def read(self) -> list[dict[str, Any]]:
```

##### 説明

現在の行をコピーして返す。元のTableは変更しない。

#### `replace`

```text
def replace(self, rows: list[dict]) -> 'Table':
```

##### 説明

表の全行を置き換え、同じTableを返す。

#### `append`

```text
def append(self, rows: list[dict] | dict) -> 'Table':
```

##### 説明

1行または複数行を末尾へ追加する。

#### `count`

```text
def count(self) -> int:
```

##### 説明

行数を返す。

#### `select`

```text
def select(self, *columns: str) -> 'Table':
```

##### 説明

指定した列だけを持つ新しいTableを返す。

#### `filter`

```text
def filter(self, predicate: Callable[[dict], bool]) -> 'Table':
```

##### 説明

条件に一致する行だけを持つ新しいTableを返す。

#### `column`

```text
def column(self, name: str) -> list[Any]:
```

##### 説明

指定列の値を順番どおりに返す。

#### `index`

```text
def index(self, key: str) -> dict[Any, dict]:
```

##### 説明

指定列をキーにした辞書を返す。

#### `group_by`

```text
def group_by(self, key: str) -> dict[Any, 'Table']:
```

##### 説明

指定列の値ごとにTableを分けて返す。

#### `concat`

```text
def concat(self, other: 'Table') -> 'Table':
```

##### 説明

同じ列定義の表を縦に連結する。

列の順番は異なっていても構わないが、列名の集合が異なる表は
別のデータとして扱う。列不足を空欄で補うと、入力ミスに気づけず
データ欠落につながるため、ここでは明示的にエラーにする。

### `TableComparison`

```text
class TableComparison:
```

#### 説明

readとwriteの比較結果を、方向が分かる名前で保持する。

### `Transfer`

```text
class Transfer:
```

#### 説明

Table 間のキー突合と転記を行う。

基本的な用法は次のとおり。 ``mapping`` は「転記元の列名 → 転記先の列名」。
3つの取り出し口を使い分けて、read / write を行単位で加工する:

- ``matched_rows()``: 両方にキーが揃う行を ``(read_row, write_row)`` で返す
  （**両方とも作業 Table の実体行**）
- ``transfer_rows()``: read 全行を ``(read_row, write_row | None)`` で返す
  （write に無い行は ``None``、``read_row`` は **コピー**）
- ``unmatched()``: 突合しなかった行を ``UnmatchedRows`` で返す
  - ``only_in_read`` は **コピー**（``Table``）。書き換えても ``read`` にも
    ``result()`` にも影響しない
  - ``only_in_write`` は **作業 Table の実体行**（``list[Row]``）。書き換えると
    ``result()`` に反映される

Example:
    transfer = Transfer(read_table, write_table, mapping,
                        read_key="顧客ID", write_key="顧客ID")
    for read_row, write_row in transfer.matched_rows():
        if 条件:
            continue                       # この行は破棄
        transfer.apply_mapping(read_row, write_row)   # mapping の値をコピー
        # 必要なら write_row["備考"] = "..." のように追加加工
    # write に無い read 行は result() に追加していく（新規行の追加）
    for read_row in transfer.unmatched().only_in_read:
        transfer.result().append({
            "顧客ID": read_row["顧客ID"],
            "顧客名": read_row["取引先"],
            "請求額": read_row["金額"],
            "備考": "新規追加",
        })
    # read に無い write 行は「転記元に無し」と書き換える（result() に出るので別途 filter する）
    for write_row in transfer.unmatched().only_in_write:
        write_row["備考"] = "転記元に無し"

**条件は ``apply_mapping()`` より前に書くこと。** Python の ``for`` ループは
``continue`` したかどうかを呼び出し側に伝えないため、ループ内で
``apply_mapping()`` を呼ばずに ``continue`` した行は、作業 Table へ反映されない。
条件判定を ``apply_mapping()`` の後ろに書くと、``continue`` しても mapping が
適用済みとなり破棄できないので、判定は必ず ``apply_mapping()`` の前に置く。

**空キー (``None`` / ``""``) は突合対象外**。 値が無いキーは read 側・write 側の
どちらでも照合に使わず、``unmatched()`` 側へ流れる。 ``0`` や ``False`` は
空ではない（数値・bool の 0 落ち判定を避けるため）。 複合キーは **1要素でも空**
なら空とみなす。

#### `__init__`

```text
def __init__(self, read: Table, write: Table, mapping: Mapping[str, str], *, read_key: str | Sequence[str] | None=None, write_key: str | Sequence[str] | None=None) -> None:
```

#### `transfer_rows`

```text
def transfer_rows(self) -> Iterator[tuple[Row, Row | None]]:
```

##### 説明

転記元の全行を ``(read_row, write_row)`` で返す。

転記先に存在しない行は ``(read_row, None)`` として返す。新規行の追加が
必要かどうかは利用者が ``if write_row is None: ...`` で判定する。
書き込みは ``apply_mapping(read_row, write_row)`` を中心に行い、
必要な列だけを ``write_row[write_col] = read_row[read_col]`` の形で
個別に上書きする。 結果は ``result()`` で取り出す。

#### `matched_rows`

```text
def matched_rows(self) -> Iterator[tuple[Row, Row]]:
```

##### 説明

両方に存在する行だけを ``(read_row, write_row)`` で返す。

転記先に存在しない行（``destination`` が ``None``）は含まない。

#### `unmatched`

```text
def unmatched(self) -> UnmatchedRows:
```

##### 説明

突合しなかった行を ``UnmatchedRows`` で返す。

``only_in_read`` は write に対応が無い read 行（追加候補）。
``Table`` として返すので ``.read()`` / ``.filter()`` などの Table 標準の
インターフェースが使える。 戻り値は ``Table.read()`` と同じく **read 行の
コピー** で、書き換えても ``read`` にも ``result()`` にも影響しない。

``only_in_write`` は read に対応が無い write 行（破棄候補）。
戻り値は ``matched_rows()`` が返す ``write_row`` と同じく **作業 Table の
実体行**。 ``write_row["備考"] = "破棄予定"`` のように書き換えると
``result()`` の戻り値へ反映される。

空キー (``None`` / ``""``) の行も両側に含む。 キーが空なので照合に使えず、
必ず対応が無いため。

``transfer_rows()`` / ``matched_rows()`` を呼ばずに呼んでも動く。

#### `apply_mapping`

```text
def apply_mapping(self, read_row: Row, write_row: Row | None) -> None:
```

##### 説明

コンストラクタで渡された ``mapping`` どおりに値を ``write_row`` へコピーする。

mapping の read 列 / write 列は ``__init__`` で存在を検証済みなので、
ここで再びキー存在を確かめない。 ``write_row`` が ``None`` の場合
（``transfer_rows()`` の ``(read_row, None)`` をそのまま渡した場合など）は
転記先の行が無いので ``TransferDestinationMissingError`` で停止する。

入力 ``read`` / ``write`` には触れない。書き込みは Transfer 内部の
作業 Table に紐づいた ``write_row`` に対して行う。

Args:
    read_row: 転記元の行。
    write_row: 転記先の行。 ``matched_rows()`` の戻り値か、
        ``transfer_rows()`` の戻り値で ``None`` でないもの。

Raises:
    TransferDestinationMissingError: ``write_row`` が ``None`` のとき。

#### `result`

```text
def result(self) -> Table:
```

##### 説明

変更後の Table を返す。

``transfer_rows()`` / ``matched_rows()`` のイテレーション中に ``write_row``
に対して行った変更が反映された作業用 Table を返す。 イテレータを 1 度も
進めないうちに ``result()`` を呼ぶと ``write`` のコピー（変更なし）が返る。

``result()`` は同じ作業 Table インスタンスを返し続けるので、
``result().append(...)`` のように破壊的に加工した場合や、 ``result()`` を
呼んだ後に ``unmatched().only_in_write`` の ``write_row`` を書き換えた場合も、
後続の ``result().read()`` 呼び出しに反映される（``Table._iter_rows_for_update``
経由で実体 dict を共有しているため）。

Example:
    transfer = Transfer(source, destination, mapping,
                        read_key="顧客ID", write_key="顧客ID")
    for source_row, destination_row in transfer.matched_rows():
        transfer.apply_mapping(source_row, destination_row)
    final_table = transfer.result()  # 変更後の Table

### `add_business_days`

```text
def add_business_days(target: _dt.date, n: int, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` から ``n`` 営業日後の日付（``n`` が負なら前）。``calendar`` 省略可。

### `business_day_after`

```text
def business_day_after(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` より後で最初の営業日（``target`` 自身を含まない）。

``calendar=None`` のときは**既定カレンダー**を使う。

### `business_day_before`

```text
def business_day_before(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` より前で最初の営業日（``target`` 自身を含まない）。

``calendar=None`` のときは**既定カレンダー**を使う。

### `business_day_on_or_after`

```text
def business_day_on_or_after(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` 以降で最初の営業日（``target`` を含む）。``calendar`` 省略可。

### `business_day_on_or_before`

```text
def business_day_on_or_before(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` 以前で最初の営業日（``target`` を含む）。``calendar`` 省略可。

### `compare_tables`

```text
def compare_tables(read: Table, write: Table, *, read_key: str | Sequence[str], write_key: str | Sequence[str]) -> TableComparison:
```

#### 説明

2つのTableをキーで比較し、4種類のTableに分けて返す。

### `copy_file`

```text
@measure
def copy_file(src: str | Path, dst: str | Path) -> Path:
```

#### 説明

ファイルをコピーする（更新日時などの属性も保持する）。

ルールは move_file と同じ:
    - dst が既存フォルダなら、その中に同名でコピーする
    - それ以外はファイルパスとして扱う（親フォルダがなければ自動作成する）
    - コピー先に同名ファイルがあれば上書きする

Args:
    src: コピーするファイルのパス。
    dst: コピー先（フォルダ、またはファイルパス）。

Returns:
    コピー後のファイルパス。

### `date_in_name`

```text
def date_in_name(name: str) -> datetime.date | None:
```

#### 説明

ファイル名に含まれる **最初の日付** を返す。日付が無ければ None。

1つのファイル名に日付が複数あるときは、先に出てくる方を使う。
ファイル名の日付とファイル内容の日付を突き合わせる業務で使うため公開している。
すべての日付が要るときは ``dates_in_name`` を使う。

### `dates_in_name`

```text
def dates_in_name(name: str) -> list[datetime.date]:
```

#### 説明

ファイル名に含まれる日付を **すべて** 出現順で返す。無ければ空リスト。

``_DATE_IN_NAME`` 正規表現で日付らしい数字（``20260729`` / ``2026-07-29`` /
``2026_07_29`` / ``2026.07.29``）を抜き出し、``date`` に変換できたものだけを
順番に並べる。``20261345`` のように数字は揃っていても日付として成立しないものは
結果に含まない。

### `default_calendar`

```text
def default_calendar() -> HolidayCalendar:
```

#### 説明

既定カレンダーを取得する（**プロセス内で 1回だけ**遅延生成）。

構成は 3 つだけ:
    1. ``ComputedHolidaySource``（純粋計算。土台）
    2. 同梱の ``syukujitsu.csv`` を ``load_cabinet_office_csv`` で読む
       （内閣府の実値。計算式の上書き用）
    3. ``CompanyHolidaySource``（会社独自の休業日。コード直書き）

**ネットワークには一切出ない。** ``CabinetOfficeCSVSource`` は
含めない（``comken.core`` は ``requests`` に依存できないし、業務 PC の
通信制限下でも動く必要があるため）。

### `delete_file`

```text
@measure
def delete_file(path: str | Path, missing_ok: bool=False) -> None:
```

#### 説明

ファイルを削除する。dry-run ではログを出してスキップする。

削除は不可逆なので、削除したファイルのパスを INFO ログに残す。
dry-run のときもログだけ出して、実際には消さない。

Args:
    path: 削除するファイルのパス。
    missing_ok: True なら対象ファイルが存在しなくても例外を送出しない。

Raises:
    FileNotFoundError: ファイルが存在せず missing_ok が False の場合。

### `delete_files`

```text
def delete_files(paths: Iterable[str | Path], missing_ok: bool=True) -> None:
```

#### 説明

複数のファイルをまとめて削除する。1件目で失敗しても残りは削除する。

各ファイルは ``delete_file()`` に委譲するため、dry-run 対応（ログを出して
スキップ・dry-run 外で実際に削除）と、「何を消したか」の INFO ログがそのまま効く。

削除できなかったファイルはあきらめずに全部試したうえで、``FileDeletionError`` に
まとめて乗せて返す。呼び出し側が「消せたものは消したい」場面で使われる想定。
1件目で例外を投げて止まると、消せたはずの別ファイルまで消さずに終わってしまう。

Args:
    paths: 削除対象ファイルのパス（Iterable。str / Path 混在可）。
    missing_ok: True（既定）なら対象が存在しない場合は失敗扱いにしない。

Raises:
    FileDeletionError: 1件以上のファイルを削除できなかった場合。
        残ったパスは ``.remaining`` で読める。

### `diff_row`

```text
def diff_row(before: dict, after: dict) -> dict[str, tuple]:
```

#### 説明

1行同士を比較し、値が異なる列だけを {列名: (変更前, 変更後)} で返す。

CSV の str と Excel の数値は同一視する（"1000" と 1000 は差分にならない）。
片方にしか存在しない列は、もう片方を空文字（``""``）に揃えて比較する。

先頭ゼロ付きの文字列（社員番号 "0001" 等）は数値化しない。
"0001" と 1 は別の値として差分になる（先頭ゼロの消失を検出できる）。
Args:
    before: 変更前の行（辞書）。
    after: 変更後の行（辞書）。

Returns:
    {列名: (変更前の値, 変更後の値)} の辞書。値は元の型のまま返す。

### `diff_rows`

```text
def diff_rows(before: Table | list[dict], after: Table | list[dict], key: str) -> DiffResult:
```

#### 説明

2つのデータセットをキー列で突合し、差分を返す。

CSV と Excel をまたいだ比較にも使える（"1000" と 1000 は同一視される）。
キーが重複する場合は後の行が優先される。

``before`` / ``after`` には ``Table`` または辞書のリストを渡せる。
``CSV.read()`` のように ``Table`` を返す API と組み合わせるときは ``Table`` を、
既存の ``list[dict]`` をそのまま渡すときはリストを指定する。戻り値の
``added`` / ``removed`` は ``Table`` になり、``filter`` / ``select`` /
``count`` などの Table 標準の操作が直接使える。
Args:
    before: 変更前のデータ（``Table`` または辞書のリスト）。
    after: 変更後のデータ（``Table`` または辞書のリスト）。
    key: 行を一意に識別するキー列名。

Returns:
    DiffResult（``added`` / ``removed`` は ``Table``、``changed`` は ``list[RowChange]``）。

Raises:
    KeyColumnNotFoundError: key で指定した列が存在しない場合。

### `first_business_day_of_month`

```text
def first_business_day_of_month(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` が属する月の最初の営業日。``calendar`` 省略可。

### `is_business_day`

```text
def is_business_day(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> bool:
```

#### 説明

``target`` が営業日なら ``True``。``calendar`` を省略できる簡易判定。

``calendar=None`` のときは**既定カレンダー**（``default_calendar()``）を使う。
アプリ側で ``set_default_calendar()`` を呼んでおけば、利用者は
``HolidayCalendar`` を組み立てなくても「今日が営業日か」を判定できる。

``calendar`` をキーワード専用にして、呼び出し側がうっかり位置引数で
日付とカレンダーを取り違える事故を防ぐ。

### `last_business_day_of_month`

```text
def last_business_day_of_month(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` が属する月の最後の営業日。``calendar`` 省略可。

### `load_cabinet_office_csv`

```text
@measure
def load_cabinet_office_csv(path: str | Path, *, encoding: str=DEFAULT_ENCODING) -> list[Holiday]:
```

#### 説明

内閣府の syukujitsu.csv を読み取り、祝日のリストを返す。

Args:
    path: CSV ファイルのパス。存在しない・読めない場合は ``HolidayCalendarFormatError``。
    encoding: CSV の文字コード。既定は ``cp932``（内閣府の配布形式）。

Returns:
    日付順に並んだ ``Holiday`` のリスト。

Raises:
    HolidayCalendarFormatError: ファイルが無い、壊れている、
        ヘッダーが内閣府のものではない、日付が解釈できないなどの理由で
        1件も抽出できなかった場合。

### `local_copy`

```text
@contextmanager
def local_copy(path: str | Path) -> Iterator[Path]:
```

#### 説明

ネットワーク上のファイルをローカルにコピーし、処理後に自動削除する。

NAS やネットワークドライブ上の大きなファイルを直接開くと遅い場合や、
win32com（Excel COM）でネットワークファイルが不安定な場合に使う。

テンポラリファイルの保存先: C:\Users\<ユーザー名>\AppData\Local\Temp\
with ブロックを抜けると自動削除される（例外が発生した場合も削除される）。
Args:
    path: コピー元のファイルパス（ネットワークパス・UNCパス・マップドドライブ）。

Yields:
    ローカルのテンポラリファイルパス（Path）。

### `measure`

```text
def measure(func: Callable[_P, _R]) -> Callable[_P, _R]:
```

#### 説明

デバッグモード時だけ対象関数の出入りを DEBUG ログに出すデコレータ。

呼び出しごとに次の3種のうち、いずれか1組を出す:

- 開始
- 完了 ○.○○○秒        （正常終了）
- 中断 ○.○○○秒        （例外で抜けた場合。BaseException も拾う）

**「開始」を必ず出してから本体を呼ぶ。** 処理が外部待ちで止まったとき、
ログの末尾が「開始」で終わっていれば、そこが停止位置だと分かる。
終了時にしかログを出さないと、止まった処理の記録は永久に残らない。

**引数・戻り値はログに出さない。** comken は DPAPI のトークン・client_secret・
パスワードを扱うため、汎用デコレータが自動で引数を出せる形になっていると、
いつか秘密の値がログへ載る危険がある。「どのメソッドで止まったか」までは
ライブラリが受け持ち、「どのファイル・どの行で止まったか」は呼び出し側が
処理対象を DEBUG ログへ出す形にする。

例外は `BaseException` で捕捉し、`raise` で必ず再送出する
（`KeyboardInterrupt` も拾う。ハングして Ctrl+C で止めたときに
「どこで待っていたか」が分かるのが狙い）。

Timer との使い分け:
    - Timer: 常にログに出したい・経過秒数を値として使いたい場合
    - measure: 普段は出さず、調査のときだけ with debug(): で出したい場合

### `month_end`

```text
def month_end(target: datetime.date) -> datetime.date:
```

#### 説明

``target`` が属する月の最終日を返す。

月ごとの日数・閏年を ``calendar.monthrange`` で正しく扱う。

### `month_start`

```text
def month_start(target: datetime.date) -> datetime.date:
```

#### 説明

``target`` が属する月の 1日を返す。

祝日に依存しない純粋な暦計算。営業日計算の前段として
「その月の最初の営業日を探す」ために使う。

### `move_file`

```text
@measure
def move_file(src: str | Path, dst: str | Path) -> Path:
```

#### 説明

ファイルを移動する。

shutil.move の分かりにくい点をなくしたラッパー:
    - dst が既存フォルダなら、その中に同名で移動する
    - それ以外はファイルパスとして扱う（親フォルダがなければ自動作成する）
    - 移動先に同名ファイルがあれば上書きする
Args:
    src: 移動するファイルのパス。
    dst: 移動先（フォルダ、またはファイルパス）。

Returns:
    移動後のファイルパス。

### `nth_business_day_of_month`

```text
def nth_business_day_of_month(target: _dt.date, n: int, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` が属する月の第 ``n`` 営業日（``n`` は 1 始まり）。``calendar`` 省略可。

### `now`

```text
def now() -> datetime.datetime:
```

#### 説明

タイムゾーン付きの現在時刻（この PC のローカル時刻）を返す。

### `project_dir`

```text
def project_dir() -> Path:
```

#### 説明

実行したスクリプトが置かれているフォルダを返す。

`python main.py` で動かしたときの `main.py` の場所、つまりプロジェクトの
ルートを指す。`src/run.py` のような下の階層から呼んでも同じ場所を返す。

利用側で `Path(__file__).parent` と書かなくて済むようにするためのもの。
あの書き方はファイルを別の階層へ移した瞬間に指す先が変わるが、
こちらは呼ぶ場所を選ばない。

入力元・出力先は config.ini に書くのが基本なので、これが要るのは
**プロジェクトに同梱したファイルを読む**ような場面に限られる。

社内 RPA 基盤は `C:\` など別の場所をカレントにして
`python <絶対パス>\main.py` と呼ぶ。**カレントではなくスクリプトの場所**を
返すのはそのためで、config.ini・state.ini・logs/ もこれを基準にしている。

``sys.argv[0]`` が想定外の値になるケースのフォールバック:
- ``sys.argv[0] == ""`` : 対話実行（REPL）。``Path.cwd()`` を返す
- ``sys.argv[0]`` が ``-m`` で起動されたパッケージ名を含む形
  （例: ``.../python -m comken`` など）: ``Path.cwd()`` を返す
- ``sys.argv[0]`` が解決できない: ``Path.cwd()`` を返す

Returns:
    実行スクリプトのあるフォルダ。**想定外のときは ``Path.cwd()`` に
    フォールバック**して例外で止まらないようにする（state.ini / logs/
    の置き場所が「現在の作業フォルダ」になる）。

### `normalize`

```text
def normalize(value: object) -> str:
```

#### 説明

表データの値を比較しやすい文字列へ正規化する。

主な変換:
    - 全角英数字・記号 → 半角（ａ→a, １→1, （→(, ．→.）
    - 半角カタカナ     → 全角カタカナ（ｱ→ア, ｶﾞ→ガ）
    - 合字             → 展開（㌔→km, ㍉→mm）

Args:
    value: Excel / CSV から得た値。``None`` は空文字として扱う。

Returns:
    正規化後の文字列。

### `parse_cell_date`

```text
def parse_cell_date(value: object) -> datetime.date | None:
```

#### 説明

セルの値を ``datetime.date`` に変換する。読めなければ `` ``None`` 。

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

### `remove_spaces`

```text
def remove_spaces(text: str) -> str:
```

#### 説明

文字列中の半角・全角スペースをすべて除去する。

電話番号・郵便番号など、スペースを含んではいけない値の正規化に使う。

Args:
    text: 処理する文字列。

Returns:
    スペースを除去した文字列。

### `retry`

```text
def retry(times: int=3, wait: float=1.0, on: tuple=(Exception,)) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
```

#### 説明

失敗したら wait 秒空けて実行し直すデコレータ。

Args:
    times: 合計の実行回数（デフォルト: 3。「3回試して全部失敗ならエラー」）。
    wait: 失敗から次の実行までの待機秒数（デフォルト: 1秒）。
    on: リトライ対象の例外のタプル（デフォルト: すべての Exception 系）。
        ``Exception`` のサブクラスを指定する。**``BaseException`` 系
        （``KeyboardInterrupt`` / ``SystemExit``）は ``on`` に含まれていても
        リトライしない**（Ctrl+C で止められることを保証するため）。
        ``on`` に含まれない例外は即座にそのまま出る。

Raises:
    ValueError: times が正の整数でない、または wait が負の値。
    最後の実行で出た例外（times 回すべて失敗した場合）。

Note:
    入力値検証で ``ValueError`` を投げる。``times`` を 0 以下にしたいケースは
    ループ自体を不要としているので、黙って 1 にするのではなく例外で知らせる
    （誤って ``times=None`` を渡して 1 回しか実行されない事故を防ぐ）。

### `set_default_calendar`

```text
def set_default_calendar(calendar: HolidayCalendar | None) -> None:
```

#### 説明

既定カレンダーを差し替える（``None`` を渡すと既定の遅延生成に戻る）。

会社独自の年末年始などを追加したいプロジェクトは、起動時に
``set_default_calendar(HolidayCalendar.from_sources([...]))`` を一度
呼んでおけば、利用者は ``is_business_day(target)`` のような
モジュール関数を直接呼べる。

### `strip_spaces`

```text
def strip_spaces(text: str) -> str:
```

#### 説明

前後の半角・全角スペースを除去する。

str.strip() は全角スペース（U+3000）を除去しないため、
業務データの氏名・住所フィールドで使うのに向いている。

Args:
    text: 処理する文字列。

Returns:
    前後のスペースを除去した文字列。

### `today`

```text
def today() -> datetime.date:
```

#### 説明

この PC のローカルの今日の日付を返す。

### `unzip`

```text
@measure
def unzip(src: str | Path, dst: str | Path | None=None) -> Path:
```

#### 説明

zip を展開する。

Windows のエクスプローラーで作られた zip（ファイル名が cp932）も
文字化けせずに展開できる（UTF-8 の zip はそのまま正しく読まれる）。

Args:
    src: 展開する zip のパス。
    dst: 展開先フォルダ。省略すると zip の隣に同名フォルダ（data.zip → data\）。
         同名ファイルがあれば上書きされる。

Returns:
    展開先フォルダのパス。

### `wait_for_file`

```text
@measure
def wait_for_file(folder: str | Path, name_pattern: str, timeout: float=DEFAULT_TIMEOUT_SECONDS, poll_interval: float=DEFAULT_POLL_INTERVAL_SECONDS) -> Path:
```

#### 説明

``folder`` 内で ``name_pattern`` にマッチするファイルが出現するまで待つ。

1度でも見つかれば、その時点で mtime が最新のファイルを返して終了する。
``poll_interval`` 秒ごとに再検索し、``timeout`` 秒経っても見つからなければ
``FileNotFoundError`` を送出する。

**「ファイルが存在するまで」しか待たない。** 作成直後のファイルは
書き込み途中でも ``is_file()`` が True になるので、書き込み完了まで
待ってから読みたいときは ``wait_until_stable()`` を続けて呼ぶ::

    path = wait_for_file(folder, "data_*.csv")
    path = wait_until_stable(path)   # サイズが落ち着くまで待つ

**フォルダが無い場合は待たずに即座に失敗する。** ``Path.glob()`` は
存在しないフォルダでも例外を出さず空を返すので、そのまま回すと
「共有サーバーが切れている」「パスを打ち間違えた」も
「ファイルがまだ来ていない」と同じ形で ``timeout`` 秒後に失敗し、
原因が分からなくなる。フォルダの不在は待っても直らないので、
ここで区別して即座に知らせる。

Args:
    folder: 監視するフォルダ。
    name_pattern: ファイル名の glob パターン（例: ``"data_*.csv"``）。
    timeout: 最大待機秒数。デフォルトは 60 秒。
    poll_interval: 再検索の間隔秒数。デフォルトは 1 秒。

Returns:
    見つかったファイルのうち mtime が最新のもの。

Raises:
    FileNotFoundError: 監視するフォルダが存在しない場合（待たずに即座）。
        待っている間にフォルダが消えた場合も同じ（``timeout`` 到達時）。
    NotADirectoryError: ``folder`` にフォルダではなくファイルを渡した場合。
    FileNotFoundError: ``timeout`` 秒経っても該当ファイルが見つからなかった場合。

### `wait_seconds`

```text
def wait_seconds(n: float) -> None:
```

#### 説明

``n`` 秒待機する。

Args:
    n: 待機秒数。小数も指定できる（例: 0.5）。

### `wait_until`

```text
def wait_until(condition: Callable[[], bool], timeout: float=60, interval: float=1.0) -> bool:
```

#### 説明

``condition`` が True になるまで待つ。

Args:
    condition: 引数なしで呼び出せる callable。True を返したら待機終了。
    timeout: 最大待機秒数（デフォルト: 60秒）。
    interval: 確認間隔（秒）（デフォルト: 1秒）。

Returns:
    True: 条件が満たされた。
    False: タイムアウトした（条件は満たされなかった）。

### `wait_until_stable`

```text
@measure
def wait_until_stable(path: str | Path, stable_for: float=DEFAULT_STABLE_FOR_SECONDS, timeout: float=DEFAULT_TIMEOUT_SECONDS, poll_interval: float=DEFAULT_POLL_INTERVAL_SECONDS) -> Path:
```

#### 説明

ファイルへの書き込みが終わるまで待つ。

サイズと更新時刻を ``poll_interval`` 秒ごとに見て、``stable_for`` 秒のあいだ
どちらも変わらなければ「書き終わった」とみなして返す。共有サーバーへ
他のシステムが置きにくるファイルを、途中まで読んでしまうのを防ぐ。

    path = wait_until_stable(r"\\server\share\in\data.csv", stable_for=2.0)
    rows = read_csv(path)      # 全部書き終わってから読む

**サイズと更新時刻でしか判断できないので、確実ではない。** 書き込み側が
``stable_for`` より長く止まると、途中でも「書き終わった」と判定する。
ネットワークが不安定な共有フォルダでは ``stable_for`` を長めに取る。

**書き込み側を自分で書けるなら、この関数より
「別名で書いてから rename する」ほうが確実**（``comken.core.files`` の
atomic 系がその形）。rename は一瞬で終わるので、読む側が途中の状態を
見ることがない。この関数は**書き込み側に手を出せないとき**の手段。

Args:
    path: 監視するファイル。
    stable_for: サイズと更新時刻が変わらないでいてほしい秒数。デフォルトは 2 秒。
        ``0`` 以下を渡すと待たずにそのまま返す。
    timeout: 最大待機秒数。デフォルトは 60 秒。
    poll_interval: 確認の間隔秒数。デフォルトは 1 秒。

Returns:
    書き込みが終わったとみなせるファイルの ``Path``。

Raises:
    FileNotFoundError: ファイルが無い場合。待っている間に消えた場合も同じ。
    TimeoutError: ``timeout`` までに書き込みが終わらなかった場合。

### `zip_files`

```text
def zip_files(files: Sequence[str | Path], dst: str | Path) -> Path:
```

#### 説明

ファイルを選んで zip に圧縮する（zip 内はフラットに並ぶ）。

Args:
    files: 圧縮するファイルパスのリスト。
    dst: 出力する zip のパス。親フォルダがなければ自動作成される。

Returns:
    作成した zip のパス。

Raises:
    FileNotFoundError: files の中に存在しないファイルがある場合。
    ValueError: zip 内で同じ名前になるファイルが複数ある場合。

### `zip_folder`

```text
@measure
def zip_folder(folder: str | Path, dst: str | Path | None=None) -> Path:
```

#### 説明

フォルダの中身をまるごと zip に圧縮する（サブフォルダも含む）。

Args:
    folder: 圧縮するフォルダ。
    dst: 出力する zip のパス。省略するとフォルダの隣に「フォルダ名.zip」。
         親フォルダがなければ自動作成される。既存の zip は上書きされる。

Returns:
    作成した zip のパス。

Raises:
    FileNotFoundError: folder が存在しない場合。


## `from comken.core.files import ...`

### `DateNameBuilder`

```text
class DateNameBuilder:
```

#### 説明

今日の日付を付けたファイル名を組み立てる。

日付は ``__init__`` 時点で確定する。``for_date=None`` のときだけ
``__init__`` 呼び出し時点の日付を使い、``prefix()`` / ``suffix()`` を
呼ぶたびに日付を取り直すことはない。

日付はコンストラクタで固定できる。テストや過去日付のファイル名を組み立てる
ときは ``date(2026, 8, 20)`` 等を渡す。省略時は呼び出し時点の日付。

拡張子は **名前の文字列に含めて** 渡す（例: ``DateNameBuilder("ログ.csv")``）。
拡張子なしの名前は ``FileSuffixMissingError`` を送出して止める。

#### `__init__`

```text
def __init__(self, name: str, for_date: date | datetime | None=None) -> None:
```

##### 説明

Args:
    name: ファイル名（**拡張子を含む**）。例: ``"売上.xlsx"`` / ``"ログ.csv"``。
        拡張子が無いと ``FileSuffixMissingError``。
    for_date: ファイル名に付ける日付。``None``（既定）なら ``__init__``
        呼び出し時点の日付。``prefix()`` / ``suffix()`` を呼ぶたびに
        日付を取り直すことはない。``date`` / ``datetime`` どちらも
        受け付ける（``datetime`` は内部で ``.date()`` に変換）。

Raises:
    FileSuffixMissingError: ``name`` に拡張子が含まれていないとき。

#### `prefix`

```text
def prefix(self, prefix: str='{:%Y%m%d}_') -> str:
```

##### 説明

``prefix + 日付 + ベース名 + 拡張子`` を返す（例: ``"20260825_売上.xlsx"``）。

``prefix("DIY_{:%Y%m%d}_")`` のように日付の位置と書式を指定する。
日付書式を含まない prefix には ``YYYYMMDD`` を末尾へ補う。
日付は **拡張子の手前** に入る。

#### `suffix`

```text
def suffix(self, date_format: str='%Y%m%d') -> str:
```

##### 説明

今日の日付を後ろに付けたファイル名を返す（例: ``"売上_20260825.xlsx"``）。

日付は **拡張子の手前** に入る。メソッド名 ``suffix()`` と「拡張子（suffix）」が
紛らわしいため、内部状態は ``_extension``（= 拡張子）と ``_stem``（= 拡張子を除いた
ベース名）で持つ。``self._extension`` は常にドット付きで ``".xlsx"`` / ``".csv"`` 等。

### `DateFileFinder`

```text
class DateFileFinder:
```

#### 説明

指定した名前と日付を持つファイルを探す。

探す名前に **拡張子を含める**（例: ``"売上レポート.csv"``）。拡張子無しの名前を
渡すと ``FileSuffixMissingError`` で止める。

**注意: ``prefix()`` / ``dated()`` は呼ぶたびにフォルダを走査する**。 同じ結果を
何度も使うなら変数に受けること（業務時間中に新しいファイルが降ってくる前提の
道具なので、 敢えてキャッシュしていない）。

#### `__init__`

```text
def __init__(self, folder: str | Path, for_date: datetime.date | None=None) -> None:
```

#### `prefix`

```text
@measure
def prefix(self, name: str, required: bool=True) -> Path | None:
```

##### 説明

``prefix + 日付 + 拡張子`` に一致するファイルを返す。

``name`` に ``{:%Y-%m-%d}`` のような日付書式があれば、その位置へ日付を
入れる。書式がなければ末尾へ ``YYYYMMDD`` を付ける。日付は **拡張子の手前** に入る。

#### `dated`

```text
@measure
def dated(self, prefix: str) -> list[Path]:
```

##### 説明

``prefix`` で始まり日付を含むファイルを全件、日付の新しい順で返す。

``prefix`` には **拡張子を含む完全なファイル名の一部** を渡す（例:
``"売上レポート.csv"`` — 拡張子は必須）。フォルダ内のファイル名から
``date_in_name`` で日付を取り出し、**日付の新しい順** に並べる。同じ日付の
ときは更新日時が新しい方を先にする。該当するファイルが無ければ空リストを
返す（例外は出さない）。

``prefix()`` との違い:

- ``prefix`` 内の日付書式（``{:%Y-%m-%d}`` 等）は解釈せず、文字どおりの前方一致だけを行う。
- コンストラクタの ``for_date`` は使わない。フォルダ内の全件が対象になる。
- 見つからないときに例外を上げず、空リストを返す（``required`` 相当の引数も無い）。

Args:
    prefix: ファイル名の先頭（この通りの前方一致。日付書式は解釈しない）。
        拡張子は必須。

Returns:
    日付の新しい順に並んだ ``Path`` のリスト。同じ日付のときは更新日時が新しい順。
    該当するファイルが無ければ空リスト。

Raises:
    FileSuffixMissingError: ``prefix`` に拡張子が含まれていないとき。

### `atomic_write`

```text
@contextmanager
def atomic_write(path: str | Path) -> Iterator[Path]:
```

#### 説明

出力先と同じフォルダに一時ファイルを作り、ブロック終了時に置き換える。

ブロック内で起きた例外や、置き換える前の中断（プロセス停止など）に対しては、
**一時ファイルを片付けてから** 例外をそのまま上位へ返す。置き換え先が
既に存在する場合は ``os.replace`` で上書きされる。

ブロック内では **出力先ファイル（``path``）に触らない** こと。同じプロセスが
読んでいる最中に置換が走ると、読んでいる側が半端な状態を見る可能性がある。

**親フォルダは作らない。** 無ければそのまま失敗する。書き間違えたパスへ
勝手にフォルダを作ると、**誰も見ない場所へ出力し続けても気づけない**
（保存先を勝手に作らない、という Downloader の判断と同じ理由）。
作る必要があるなら、**呼ぶ側が明示的に** `path.parent.mkdir(...)` する。

Args:
    path: 最終的に置きたいファイルのパス。**親フォルダは存在している前提**。

Yields:
    一時ファイルのパス。

Raises:
    FileNotFoundError: 親フォルダが無い場合。

### `copy_file`

```text
@measure
def copy_file(src: str | Path, dst: str | Path) -> Path:
```

#### 説明

ファイルをコピーする（更新日時などの属性も保持する）。

ルールは move_file と同じ:
    - dst が既存フォルダなら、その中に同名でコピーする
    - それ以外はファイルパスとして扱う（親フォルダがなければ自動作成する）
    - コピー先に同名ファイルがあれば上書きする

Args:
    src: コピーするファイルのパス。
    dst: コピー先（フォルダ、またはファイルパス）。

Returns:
    コピー後のファイルパス。

### `copy_to_local_if_large`

```text
@measure
def copy_to_local_if_large(path: str | Path, threshold_mb: float) -> tuple[Path, Path | None]:
```

#### 説明

ファイルサイズが閾値を超えていればローカルへコピーして、そのパスを返す。

NAS・ネットワークドライブ上のファイルを openpyxl や win32com が開くときに
遅い・不安定になる事があり、社内ルールで許可されていればローカルへコピーして
安定化させる。``threshold_mb=0`` を指定すればコピーせず元のまま返す
（社内ルールでローカルコピーが禁止されている場合のオプトアウト）。

返り値は ``(working_path, tmp_path_or_None)``。第2要素が ``None`` 以外の
ときは呼び出し側がローカルコピーの所有者となり、不要になったら
``tmp_path.unlink(missing_ok=True)`` で削除する。
``local_copy`` のような ``with`` ブロックでの自動削除はしない
（openpyxl / win32com は ``close()`` までパスを保持する必要があるため、
スコープがクラス側に寄る）。

この関数は ``comken.core.files`` の ``__all__`` にのみ入れる
（``comken.core`` からは再エクスポートしない）。利用者が直接呼ぶことは
想定せず、Excel / ExcelCOMHandler などクラス側の自動コピールーチンが使う。

Args:
    path: 元のファイルパス。
    threshold_mb: この値（MB）を**超える**ファイルはコピーする。
                  0 を指定するとコピーしない。

Returns:
    (working_path, tmp_path_or_None) のタプル。
    コピーしたときは ``(ローカルコピーへのPath, そのPath)``、
    コピーしなかったときは ``(元のパス, None)``。

### `date_in_name`

```text
def date_in_name(name: str) -> datetime.date | None:
```

#### 説明

ファイル名に含まれる **最初の日付** を返す。日付が無ければ None。

1つのファイル名に日付が複数あるときは、先に出てくる方を使う。
ファイル名の日付とファイル内容の日付を突き合わせる業務で使うため公開している。
すべての日付が要るときは ``dates_in_name`` を使う。

### `dates_in_name`

```text
def dates_in_name(name: str) -> list[datetime.date]:
```

#### 説明

ファイル名に含まれる日付を **すべて** 出現順で返す。無ければ空リスト。

``_DATE_IN_NAME`` 正規表現で日付らしい数字（``20260729`` / ``2026-07-29`` /
``2026_07_29`` / ``2026.07.29``）を抜き出し、``date`` に変換できたものだけを
順番に並べる。``20261345`` のように数字は揃っていても日付として成立しないものは
結果に含まない。

### `delete_file`

```text
@measure
def delete_file(path: str | Path, missing_ok: bool=False) -> None:
```

#### 説明

ファイルを削除する。dry-run ではログを出してスキップする。

削除は不可逆なので、削除したファイルのパスを INFO ログに残す。
dry-run のときもログだけ出して、実際には消さない。

Args:
    path: 削除するファイルのパス。
    missing_ok: True なら対象ファイルが存在しなくても例外を送出しない。

Raises:
    FileNotFoundError: ファイルが存在せず missing_ok が False の場合。

### `delete_files`

```text
def delete_files(paths: Iterable[str | Path], missing_ok: bool=True) -> None:
```

#### 説明

複数のファイルをまとめて削除する。1件目で失敗しても残りは削除する。

各ファイルは ``delete_file()`` に委譲するため、dry-run 対応（ログを出して
スキップ・dry-run 外で実際に削除）と、「何を消したか」の INFO ログがそのまま効く。

削除できなかったファイルはあきらめずに全部試したうえで、``FileDeletionError`` に
まとめて乗せて返す。呼び出し側が「消せたものは消したい」場面で使われる想定。
1件目で例外を投げて止まると、消せたはずの別ファイルまで消さずに終わってしまう。

Args:
    paths: 削除対象ファイルのパス（Iterable。str / Path 混在可）。
    missing_ok: True（既定）なら対象が存在しない場合は失敗扱いにしない。

Raises:
    FileDeletionError: 1件以上のファイルを削除できなかった場合。
        残ったパスは ``.remaining`` で読める。

### `local_copy`

```text
@contextmanager
def local_copy(path: str | Path) -> Iterator[Path]:
```

#### 説明

ネットワーク上のファイルをローカルにコピーし、処理後に自動削除する。

NAS やネットワークドライブ上の大きなファイルを直接開くと遅い場合や、
win32com（Excel COM）でネットワークファイルが不安定な場合に使う。

テンポラリファイルの保存先: C:\Users\<ユーザー名>\AppData\Local\Temp\
with ブロックを抜けると自動削除される（例外が発生した場合も削除される）。
Args:
    path: コピー元のファイルパス（ネットワークパス・UNCパス・マップドドライブ）。

Yields:
    ローカルのテンポラリファイルパス（Path）。

### `move_file`

```text
@measure
def move_file(src: str | Path, dst: str | Path) -> Path:
```

#### 説明

ファイルを移動する。

shutil.move の分かりにくい点をなくしたラッパー:
    - dst が既存フォルダなら、その中に同名で移動する
    - それ以外はファイルパスとして扱う（親フォルダがなければ自動作成する）
    - 移動先に同名ファイルがあれば上書きする
Args:
    src: 移動するファイルのパス。
    dst: 移動先（フォルダ、またはファイルパス）。

Returns:
    移動後のファイルパス。

### `project_dir`

```text
def project_dir() -> Path:
```

#### 説明

実行したスクリプトが置かれているフォルダを返す。

`python main.py` で動かしたときの `main.py` の場所、つまりプロジェクトの
ルートを指す。`src/run.py` のような下の階層から呼んでも同じ場所を返す。

利用側で `Path(__file__).parent` と書かなくて済むようにするためのもの。
あの書き方はファイルを別の階層へ移した瞬間に指す先が変わるが、
こちらは呼ぶ場所を選ばない。

入力元・出力先は config.ini に書くのが基本なので、これが要るのは
**プロジェクトに同梱したファイルを読む**ような場面に限られる。

社内 RPA 基盤は `C:\` など別の場所をカレントにして
`python <絶対パス>\main.py` と呼ぶ。**カレントではなくスクリプトの場所**を
返すのはそのためで、config.ini・state.ini・logs/ もこれを基準にしている。

``sys.argv[0]`` が想定外の値になるケースのフォールバック:
- ``sys.argv[0] == ""`` : 対話実行（REPL）。``Path.cwd()`` を返す
- ``sys.argv[0]`` が ``-m`` で起動されたパッケージ名を含む形
  （例: ``.../python -m comken`` など）: ``Path.cwd()`` を返す
- ``sys.argv[0]`` が解決できない: ``Path.cwd()`` を返す

Returns:
    実行スクリプトのあるフォルダ。**想定外のときは ``Path.cwd()`` に
    フォールバック**して例外で止まらないようにする（state.ini / logs/
    の置き場所が「現在の作業フォルダ」になる）。

### `unzip`

```text
@measure
def unzip(src: str | Path, dst: str | Path | None=None) -> Path:
```

#### 説明

zip を展開する。

Windows のエクスプローラーで作られた zip（ファイル名が cp932）も
文字化けせずに展開できる（UTF-8 の zip はそのまま正しく読まれる）。

Args:
    src: 展開する zip のパス。
    dst: 展開先フォルダ。省略すると zip の隣に同名フォルダ（data.zip → data\）。
         同名ファイルがあれば上書きされる。

Returns:
    展開先フォルダのパス。

### `zip_files`

```text
def zip_files(files: Sequence[str | Path], dst: str | Path) -> Path:
```

#### 説明

ファイルを選んで zip に圧縮する（zip 内はフラットに並ぶ）。

Args:
    files: 圧縮するファイルパスのリスト。
    dst: 出力する zip のパス。親フォルダがなければ自動作成される。

Returns:
    作成した zip のパス。

Raises:
    FileNotFoundError: files の中に存在しないファイルがある場合。
    ValueError: zip 内で同じ名前になるファイルが複数ある場合。

### `zip_folder`

```text
@measure
def zip_folder(folder: str | Path, dst: str | Path | None=None) -> Path:
```

#### 説明

フォルダの中身をまるごと zip に圧縮する（サブフォルダも含む）。

Args:
    folder: 圧縮するフォルダ。
    dst: 出力する zip のパス。省略するとフォルダの隣に「フォルダ名.zip」。
         親フォルダがなければ自動作成される。既存の zip は上書きされる。

Returns:
    作成した zip のパス。

Raises:
    FileNotFoundError: folder が存在しない場合。


## `from comken.core.holidays import ...`

### `BUNDLED_CSV_PATH`

公開定数。

### `BUSINESS_DAY_SEARCH_LIMIT`

公開定数。

### `BusinessDayNotFoundError`

```text
class BusinessDayNotFoundError(HolidayCalendarError):
```

#### 説明

営業日が見つからなかった

月の途中で「指定した月の営業日数を超える n 番目」を求めたとき、
その月に営業日が 1 日も無いとき、祝日データ欠落などで 400 日探索しても
次の営業日にたどり着けなかったときに送る。
いずれも「カレンダー側がおかしい」または「指定値が暦と合わない」場合に
起き、業務ロジック側のミスではないので、呼び出し側で握り潰さずユーザーに
顕在化させる必要がある。

発生箇所: comken.core.holidays.calendar の HolidayCalendar
    - nth_business_day_of_month（n が月の営業日数超え、または n < 1）
    - first_business_day_of_month / last_business_day_of_month
      （その月に営業日が 1 日も無い）
    - business_day_after / business_day_before /
      business_day_on_or_after / business_day_on_or_before
      （400 日の探索上限に達した）

対処:
    n をその月の営業日数以下に直す、対象月の祝日に過不足がないか
    確認する、社内管理表（会社休日）が広範囲に登録されていないか確認する

#### `__init__`

```text
def __init__(self, detail: str) -> None:
```

### `CompanyHolidaySource`

```text
class CompanyHolidaySource(HolidaySource):
```

#### 説明

コードに直書きした会社休日を ``Holiday`` の iterable で返すソース。

``HolidaySource`` Protocol を実装する。既定カレンダーは
``default_calendar()`` が組み立てるので、利用者が自分で
``HolidayCalendar.from_sources(...)`` を書く必要はない
（使うだけなら ``is_business_day(today())`` と書く）。

国民の祝日（内閣府 CSV / Computed）と重なったときは**先勝ち**で
採用される（``HolidayCalendar`` 側の挙動）。警告は出さない。

このソースは **外部 I/O を一切しない** 純粋な Python 計算。
社内 BO 環境（オフライン・pip 制限）でもそのまま動く。

Args:
    from_year: 対象範囲の開始年。省略時は ``DEFAULT_FROM_YEAR`` (1900)。
    to_year: 対象範囲の終了年。省略時は ``DEFAULT_TO_YEAR`` (2200)。

#### `__init__`

```text
def __init__(self, *, from_year: int | None=None, to_year: int | None=None) -> None:
```

#### `load`

```text
def load(self) -> list[Holiday]:
```

##### 説明

会社休日を ``Holiday`` のリストで返す。

日付順に並べた状態で返す。国民の祝日と重なっても気にせずそのまま出す
（``HolidayCalendar`` 側で先勝ち採用される）。

### `ComputedHolidaySource`

```text
class ComputedHolidaySource(HolidaySource):
```

#### 説明

計算で祝日の和集合を返すソース。

``HolidaySource`` Protocol を実装する。``load()`` で ``Iterable[Holiday]`` を返す。
``CabinetOfficeCSVSource`` と並列に置いて、
``from_sources([Cabinet, Computed])`` のように和集合で運用する
（``HolidayCalendar`` 側の先勝ち WARNING ログが衝突をハンドリングする）。

このソースは **純粋計算のみ** — 外部通信・ファイル読み込みは一切しない。
社内 BO 環境（オフライン・pip 制限）でもそのまま動く。

Args:
    from_year: 対象範囲の開始年。省略時は ``DEFAULT_FROM_YEAR`` (1948)。
    to_year: 対象範囲の終了年。省略時は ``DEFAULT_TO_YEAR`` (2099)。
        範囲外でも祝日計算は走るが、春分／秋分の近似精度が下がる旨を
        WARNING ログで知らせる。

#### `__init__`

```text
def __init__(self, *, from_year: int | None=None, to_year: int | None=None) -> None:
```

#### `load`

```text
def load(self) -> list[Holiday]:
```

##### 説明

対象年の範囲について計算した祝日をまとめて返す。

Returns:
    日付順に並んだ ``Holiday`` のリスト。

### `EXPIRING_WARNING_DAYS`

公開定数。

### `Holiday`

```text
class Holiday:
```

#### 説明

祝日の1件。日付と名称だけを運ぶシンプルな箱。

Attributes:
    date: 祝日の日付（時刻・タイムゾーンは持たない業務日付）。
    name: 祝日の日本語名称（例: "建国記念の日"）。
    approximate: ``True`` なら、計算式など内閣府発表と ±1 日前後する
        可能性がある値。``HolidayCalendar.is_holiday`` などで該当 Holiday
        を返したときに WARNING ログを出して、業務フローを止めずに気づける
        ようにする。デフォルトは ``False``（内閣府 CSV 由来または確実な
        計算結果）。

### `HolidayCalendar`

```text
class HolidayCalendar:
```

#### 説明

祝日を保持し、営業日判定を行うカレンダー本体。

同じ日付に複数の祝日が登録された場合は**先勝ち**で採用する
（内閣府 CSV と会社の年末年始休暇など、複数 source の重複は珍しくない）。
名称が違う祝日が同じ日に重なっても黙って先を採用する。

期限切れの警告（``EXPIRING_WARNING_DAYS`` を切った日）は **同じ日に
1回だけ**出す。同じ日に ``is_business_day`` が何回呼ばれても
ログが埋もれないため。

#### `__init__`

```text
def __init__(self, holidays: Iterable[Holiday]) -> None:
```

##### 説明

``Holiday`` の iterable から ``{日付: Holiday}`` の索引を作る。

Args:
    holidays: 祝日の iterable。同じ日付が複数含まれていたら先勝ちで採用。

#### `from_csv`

```text
@classmethod
def from_csv(cls, path: str | Path, *, encoding: str='cp932') -> 'HolidayCalendar':
```

##### 説明

内閣府の ``syukujitsu.csv`` を直接読む最短ルート。

Args:
    path: CSV のパス。CP932（Shift_JIS）固定。
    encoding: 文字コード。通常は ``cp932`` のままで良い。

Returns:
    読み込み結果から作った ``HolidayCalendar``。

#### `from_sources`

```text
@classmethod
def from_sources(cls, sources: Iterable[HolidaySource]) -> 'HolidayCalendar':
```

##### 説明

複数の ``HolidaySource`` を合体させる（内閣府 + Computed + 会社休日 など）。

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

#### `is_holiday`

```text
def is_holiday(self, target: _dt.date) -> bool:
```

##### 説明

``target`` が祝日（または休日）なら ``True``。

ターゲットが今年/来年なら、内閣府 source への強制再取得を試みる
（今年中に 1 回だけ。失敗時はサイレント）。
計算式由来の暫定値（``approximate=True``）を返すときは WARNING ログ。

#### `holidays_in`

```text
def holidays_in(self, start: _dt.date, end: _dt.date) -> list[Holiday]:
```

##### 説明

``start <= 日付 <= end`` の範囲に入る祝日を、日付順に返す。

Args:
    start: 範囲開始（含む）。
    end: 範囲終了（含む）。

Returns:
    範囲内の ``Holiday`` を日付昇順で並べたリスト。
    該当が無ければ空リスト。

#### `expires_after`

```text
def expires_after(self, target: _dt.date) -> bool:
```

##### 説明

``target`` が収録済み最終日以降（＝「収録期限を過ぎた」）なら ``True``。

「収録済み最終日 <= target」を期限切れとみなす。等号を含めるのは、
「収録最終日ぴったり」を「期限の境目」として扱うため（最終日当日は
収録済みの祝日として判定できるが、それ以降は収録外）。

#### `days_until_expiry`

```text
def days_until_expiry(self, today: _dt.date) -> int:
```

##### 説明

``today`` から収録最終日までの日数。最終日を過ぎていれば負の値。

Args:
    today: 「今日」とみなす日付。

Returns:
    ``last_known - today`` の日数差。収録済み祝日が無いと ``-1``。

#### `last_known_date`

```text
def last_known_date(self) -> _dt.date | None:
```

##### 説明

収録済み祝日のうち最も新しい日付。無ければ ``None``。

#### `holiday_names`

```text
def holiday_names(self, target: _dt.date) -> Sequence[str]:
```

##### 説明

``target`` に登録された祝日名称のタプル（同日が複数あれば複数要素）。

#### `all_holidays`

```text
def all_holidays(self) -> list[Holiday]:
```

##### 説明

保持している祝日を日付順に並べたリストを返す。

### `HolidayCalendarError`

```text
class HolidayCalendarError(ComkenError):
```

#### 説明

祝日カレンダーに関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `HolidayCalendarFetchError`

```text
class HolidayCalendarFetchError(HolidayCalendarError):
```

#### 説明

内閣府の祝日 CSV を取得できない

オフライン環境・社内ネットワークの制約・内閣府サイトの保守などの理由で
ダウンロードが失敗する。**ただしキャッシュが残っている場合は警告ログのみで動く**
（cached フラグで運用側が検知できる）。

発生箇所: comken.toolbox.holidays.sources.cabinet_office の CabinetOfficeCSVSource

対処:
    ネットワーク接続と社内プロキシの設定を確認する。
    それでも直らない場合は、保存済みのキャッシュで当面動かすか、
    管理表（Excel）に会社休日を登録して代用する

#### `__init__`

```text
def __init__(self, url: str, reason: str) -> None:
```

### `HolidayCalendarFormatError`

```text
class HolidayCalendarFormatError(HolidayCalendarSourceError):
```

#### 説明

内閣府 CSV 以外のファイルや壊れたファイルを内閣府 CSV として読み込もうとした

発生箇所: comken.core.holidays.csv_source の load_cabinet_office_csv

対処:
    内閣府の syukujitsu.csv を直接取得し直す。文字コードは CP932 (Shift_JIS)

#### `__init__`

```text
def __init__(self, path: Path | str, detail: str) -> None:
```

### `HolidayCalendarSourceError`

```text
class HolidayCalendarSourceError(HolidayCalendarError):
```

#### 説明

祝日データの読み取りに失敗した

内閣府の CSV 形式が変わった・社内管理表のシート名が違う・列が無い・
文字化けしたなどの理由で、祝日を 1件も抽出できない場合に上げる。

発生箇所: comken.core.holidays の csv_source

対処:
    内閣府の CSV の場合: 内閣府の仕様変更。管理者へ連絡する

#### `__init__`

```text
def __init__(self, source: str, reason: str) -> None:
```

### `HolidaySource`

```text
class HolidaySource(Protocol):
```

#### 説明

祝日を 1セット取り出せる仕組みの共通インタフェース。

内閣府の ``CabinetOfficeCSVSource`` や ``ComputedHolidaySource`` / 会社の
``CompanyHolidaySource`` の両方がこれを実装するため、利用側は入手経路を
意識せずに ``from_sources`` に渡せる。

この Protocol はメソッドの型を ``Iterable[Holiday]`` に固定する。
``load()`` を呼んだその瞬間に取得が走る（キャッシュは実装側で持つ）のが
一貫していて読みやすい。実装が iterable を返したい場合は
中で ``list()`` してから返してもよい。

#### `load`

```text
def load(self) -> Iterable[Holiday]:
```

##### 説明

祝日セットを取り出して ``Iterable[Holiday]`` で返す。

### `RefreshableHolidaySource`

```text
class RefreshableHolidaySource(Protocol):
```

#### 説明

TTL を無視して強制再取得できる祝日 source（例: 内閣府の ``CabinetOfficeCSVSource``）。

``HolidayCalendar`` がターゲットが今年/来年のときに内閣府への
再取得を試みるためのフック。短いタイムアウト（既定 0.5 秒）で実装する。
必須ではなく、管理表など再取得が要らない source は実装しなくてよい。

#### `refresh`

```text
def refresh(self) -> Iterable[Holiday]:
```

##### 説明

TTL を無視して強制再取得する。

### `add_business_days`

```text
def add_business_days(target: _dt.date, n: int, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` から ``n`` 営業日後の日付（``n`` が負なら前）。``calendar`` 省略可。

### `business_day_after`

```text
def business_day_after(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` より後で最初の営業日（``target`` 自身を含まない）。

``calendar=None`` のときは**既定カレンダー**を使う。

### `business_day_before`

```text
def business_day_before(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` より前で最初の営業日（``target`` 自身を含まない）。

``calendar=None`` のときは**既定カレンダー**を使う。

### `business_day_on_or_after`

```text
def business_day_on_or_after(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` 以降で最初の営業日（``target`` を含む）。``calendar`` 省略可。

### `business_day_on_or_before`

```text
def business_day_on_or_before(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` 以前で最初の営業日（``target`` を含む）。``calendar`` 省略可。

### `default_calendar`

```text
def default_calendar() -> HolidayCalendar:
```

#### 説明

既定カレンダーを取得する（**プロセス内で 1回だけ**遅延生成）。

構成は 3 つだけ:
    1. ``ComputedHolidaySource``（純粋計算。土台）
    2. 同梱の ``syukujitsu.csv`` を ``load_cabinet_office_csv`` で読む
       （内閣府の実値。計算式の上書き用）
    3. ``CompanyHolidaySource``（会社独自の休業日。コード直書き）

**ネットワークには一切出ない。** ``CabinetOfficeCSVSource`` は
含めない（``comken.core`` は ``requests`` に依存できないし、業務 PC の
通信制限下でも動く必要があるため）。

### `first_business_day_of_month`

```text
def first_business_day_of_month(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` が属する月の最初の営業日。``calendar`` 省略可。

### `is_business_day`

```text
def is_business_day(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> bool:
```

#### 説明

``target`` が営業日なら ``True``。``calendar`` を省略できる簡易判定。

``calendar=None`` のときは**既定カレンダー**（``default_calendar()``）を使う。
アプリ側で ``set_default_calendar()`` を呼んでおけば、利用者は
``HolidayCalendar`` を組み立てなくても「今日が営業日か」を判定できる。

``calendar`` をキーワード専用にして、呼び出し側がうっかり位置引数で
日付とカレンダーを取り違える事故を防ぐ。

### `last_business_day_of_month`

```text
def last_business_day_of_month(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` が属する月の最後の営業日。``calendar`` 省略可。

### `load_cabinet_office_csv`

```text
@measure
def load_cabinet_office_csv(path: str | Path, *, encoding: str=DEFAULT_ENCODING) -> list[Holiday]:
```

#### 説明

内閣府の syukujitsu.csv を読み取り、祝日のリストを返す。

Args:
    path: CSV ファイルのパス。存在しない・読めない場合は ``HolidayCalendarFormatError``。
    encoding: CSV の文字コード。既定は ``cp932``（内閣府の配布形式）。

Returns:
    日付順に並んだ ``Holiday`` のリスト。

Raises:
    HolidayCalendarFormatError: ファイルが無い、壊れている、
        ヘッダーが内閣府のものではない、日付が解釈できないなどの理由で
        1件も抽出できなかった場合。

### `nth_business_day_of_month`

```text
def nth_business_day_of_month(target: _dt.date, n: int, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` が属する月の第 ``n`` 営業日（``n`` は 1 始まり）。``calendar`` 省略可。

### `set_default_calendar`

```text
def set_default_calendar(calendar: HolidayCalendar | None) -> None:
```

#### 説明

既定カレンダーを差し替える（``None`` を渡すと既定の遅延生成に戻る）。

会社独自の年末年始などを追加したいプロジェクトは、起動時に
``set_default_calendar(HolidayCalendar.from_sources([...]))`` を一度
呼んでおけば、利用者は ``is_business_day(target)`` のような
モジュール関数を直接呼べる。


## `from comken.core.logger import ...`

### `Backoffice`

```text
class Backoffice(LoggerSite):
```

#### 説明

バックオフィス環境のログ設定。

comken 共通のクラス。OWNER は ``"comken"``。

### `Intranet`

```text
class Intranet(LoggerSite):
```

#### 説明

イントラネット環境のログ設定。

comken 共通のクラス。OWNER は ``"comken"``。

### `setup_logging`

```text
def setup_logging(site: type[LoggerSite], *, allow_existing: bool=False) -> None:
```

#### 説明

site の指定に従い root logger を設定する。

PID は同じ端末で同時に動くプロセスを見分ける値であり、保存先を選ぶ端末名とは
用途が異なる。Formatter の固定値として渡し、ログ呼び出し側へ負担を増やさない。

``setup_local_logging()`` が先に走っている場合（root に console と local
ファイルだけがある場合）は console を再利用し、environment ファイルだけを
追加する。逆順（``setup_logging()`` が先）では通常どおり console と
environment ファイルを追加する。両方がすでに走っている場合は
``LoggingAlreadyConfiguredError`` を送出して、二重出力を防ぐ。

comken 以外の handler が root に混ざっている場合は ``LoggingConflictError``
を送出する。既存 handler の出力先やレベルを勝手に変えてしまうため。
``allow_existing=True`` を指定すると、その判定を**警告ログだけ**に留めて処理を
続行する（comken の handler が両方走っているケースは許可しない — 何が3つ目に
なるか曖昧になり、誤って出力に気付くのが遅れるため）。

### `setup_local_logging`

```text
def setup_local_logging(*, console_level: int=logging.INFO, file_level: int=logging.INFO, path: str | Path | None=None, allow_existing: bool=False) -> None:
```

#### 説明

ローカル実行用に root logger を設定する。

``path`` はファイル名ではなく保存先フォルダ。省略時は ``project_dir()`` で
起動スクリプトのプロジェクトを求め、その ``logs`` を使う。``setup_logging()`` の
直後（root に console と environment ファイルだけがある状態）でも、
``setup_logging()`` と組み合わせず単独でも呼べる。``setup_logging()`` 直後なら
console を使い回して local ファイルだけを追加し、単独なら console と local
ファイルの 2 種を追加する。

``setup_logging()`` と ``setup_local_logging()`` が両方走った状態や、関係のない
handler が混ざっている場合は ``LoggingAlreadyConfiguredError`` を送出して
二重出力を防ぐ。comken 以外（他ライブラリ由来）の handler が混ざっている場合は
``LoggingConflictError`` を送出し、既存 handler の出力先やレベルを勝手に
変えてしまうことを防ぐ。``allow_existing=True`` を指定すると、その判定を
**警告ログだけ**に留めて処理を続行する。


## `from comken.core.table import ...`

### `Table`

```text
class Table:
```

#### 説明

列と辞書行をメモリで扱う表。

CSVやExcelに直接依存しないため、加工処理をファイルI/Oから分離できます。
``types`` は入力時に明示された列だけを変換し、暗黙の型推測は行いません。

#### `__init__`

```text
def __init__(self, columns: list[str] | tuple[str, ...], rows: list[dict[str, Any]], *, types: Mapping[str, Callable[[Any], Any]] | None=None) -> None:
```

#### `read`

```text
def read(self) -> list[dict[str, Any]]:
```

##### 説明

現在の行をコピーして返す。元のTableは変更しない。

#### `replace`

```text
def replace(self, rows: list[dict]) -> 'Table':
```

##### 説明

表の全行を置き換え、同じTableを返す。

#### `append`

```text
def append(self, rows: list[dict] | dict) -> 'Table':
```

##### 説明

1行または複数行を末尾へ追加する。

#### `count`

```text
def count(self) -> int:
```

##### 説明

行数を返す。

#### `select`

```text
def select(self, *columns: str) -> 'Table':
```

##### 説明

指定した列だけを持つ新しいTableを返す。

#### `filter`

```text
def filter(self, predicate: Callable[[dict], bool]) -> 'Table':
```

##### 説明

条件に一致する行だけを持つ新しいTableを返す。

#### `column`

```text
def column(self, name: str) -> list[Any]:
```

##### 説明

指定列の値を順番どおりに返す。

#### `index`

```text
def index(self, key: str) -> dict[Any, dict]:
```

##### 説明

指定列をキーにした辞書を返す。

#### `group_by`

```text
def group_by(self, key: str) -> dict[Any, 'Table']:
```

##### 説明

指定列の値ごとにTableを分けて返す。

#### `concat`

```text
def concat(self, other: 'Table') -> 'Table':
```

##### 説明

同じ列定義の表を縦に連結する。

列の順番は異なっていても構わないが、列名の集合が異なる表は
別のデータとして扱う。列不足を空欄で補うと、入力ミスに気づけず
データ欠落につながるため、ここでは明示的にエラーにする。

### `TableComparison`

```text
class TableComparison:
```

#### 説明

readとwriteの比較結果を、方向が分かる名前で保持する。

### `Transfer`

```text
class Transfer:
```

#### 説明

Table 間のキー突合と転記を行う。

基本的な用法は次のとおり。 ``mapping`` は「転記元の列名 → 転記先の列名」。
3つの取り出し口を使い分けて、read / write を行単位で加工する:

- ``matched_rows()``: 両方にキーが揃う行を ``(read_row, write_row)`` で返す
  （**両方とも作業 Table の実体行**）
- ``transfer_rows()``: read 全行を ``(read_row, write_row | None)`` で返す
  （write に無い行は ``None``、``read_row`` は **コピー**）
- ``unmatched()``: 突合しなかった行を ``UnmatchedRows`` で返す
  - ``only_in_read`` は **コピー**（``Table``）。書き換えても ``read`` にも
    ``result()`` にも影響しない
  - ``only_in_write`` は **作業 Table の実体行**（``list[Row]``）。書き換えると
    ``result()`` に反映される

Example:
    transfer = Transfer(read_table, write_table, mapping,
                        read_key="顧客ID", write_key="顧客ID")
    for read_row, write_row in transfer.matched_rows():
        if 条件:
            continue                       # この行は破棄
        transfer.apply_mapping(read_row, write_row)   # mapping の値をコピー
        # 必要なら write_row["備考"] = "..." のように追加加工
    # write に無い read 行は result() に追加していく（新規行の追加）
    for read_row in transfer.unmatched().only_in_read:
        transfer.result().append({
            "顧客ID": read_row["顧客ID"],
            "顧客名": read_row["取引先"],
            "請求額": read_row["金額"],
            "備考": "新規追加",
        })
    # read に無い write 行は「転記元に無し」と書き換える（result() に出るので別途 filter する）
    for write_row in transfer.unmatched().only_in_write:
        write_row["備考"] = "転記元に無し"

**条件は ``apply_mapping()`` より前に書くこと。** Python の ``for`` ループは
``continue`` したかどうかを呼び出し側に伝えないため、ループ内で
``apply_mapping()`` を呼ばずに ``continue`` した行は、作業 Table へ反映されない。
条件判定を ``apply_mapping()`` の後ろに書くと、``continue`` しても mapping が
適用済みとなり破棄できないので、判定は必ず ``apply_mapping()`` の前に置く。

**空キー (``None`` / ``""``) は突合対象外**。 値が無いキーは read 側・write 側の
どちらでも照合に使わず、``unmatched()`` 側へ流れる。 ``0`` や ``False`` は
空ではない（数値・bool の 0 落ち判定を避けるため）。 複合キーは **1要素でも空**
なら空とみなす。

#### `__init__`

```text
def __init__(self, read: Table, write: Table, mapping: Mapping[str, str], *, read_key: str | Sequence[str] | None=None, write_key: str | Sequence[str] | None=None) -> None:
```

#### `transfer_rows`

```text
def transfer_rows(self) -> Iterator[tuple[Row, Row | None]]:
```

##### 説明

転記元の全行を ``(read_row, write_row)`` で返す。

転記先に存在しない行は ``(read_row, None)`` として返す。新規行の追加が
必要かどうかは利用者が ``if write_row is None: ...`` で判定する。
書き込みは ``apply_mapping(read_row, write_row)`` を中心に行い、
必要な列だけを ``write_row[write_col] = read_row[read_col]`` の形で
個別に上書きする。 結果は ``result()`` で取り出す。

#### `matched_rows`

```text
def matched_rows(self) -> Iterator[tuple[Row, Row]]:
```

##### 説明

両方に存在する行だけを ``(read_row, write_row)`` で返す。

転記先に存在しない行（``destination`` が ``None``）は含まない。

#### `unmatched`

```text
def unmatched(self) -> UnmatchedRows:
```

##### 説明

突合しなかった行を ``UnmatchedRows`` で返す。

``only_in_read`` は write に対応が無い read 行（追加候補）。
``Table`` として返すので ``.read()`` / ``.filter()`` などの Table 標準の
インターフェースが使える。 戻り値は ``Table.read()`` と同じく **read 行の
コピー** で、書き換えても ``read`` にも ``result()`` にも影響しない。

``only_in_write`` は read に対応が無い write 行（破棄候補）。
戻り値は ``matched_rows()`` が返す ``write_row`` と同じく **作業 Table の
実体行**。 ``write_row["備考"] = "破棄予定"`` のように書き換えると
``result()`` の戻り値へ反映される。

空キー (``None`` / ``""``) の行も両側に含む。 キーが空なので照合に使えず、
必ず対応が無いため。

``transfer_rows()`` / ``matched_rows()`` を呼ばずに呼んでも動く。

#### `apply_mapping`

```text
def apply_mapping(self, read_row: Row, write_row: Row | None) -> None:
```

##### 説明

コンストラクタで渡された ``mapping`` どおりに値を ``write_row`` へコピーする。

mapping の read 列 / write 列は ``__init__`` で存在を検証済みなので、
ここで再びキー存在を確かめない。 ``write_row`` が ``None`` の場合
（``transfer_rows()`` の ``(read_row, None)`` をそのまま渡した場合など）は
転記先の行が無いので ``TransferDestinationMissingError`` で停止する。

入力 ``read`` / ``write`` には触れない。書き込みは Transfer 内部の
作業 Table に紐づいた ``write_row`` に対して行う。

Args:
    read_row: 転記元の行。
    write_row: 転記先の行。 ``matched_rows()`` の戻り値か、
        ``transfer_rows()`` の戻り値で ``None`` でないもの。

Raises:
    TransferDestinationMissingError: ``write_row`` が ``None`` のとき。

#### `result`

```text
def result(self) -> Table:
```

##### 説明

変更後の Table を返す。

``transfer_rows()`` / ``matched_rows()`` のイテレーション中に ``write_row``
に対して行った変更が反映された作業用 Table を返す。 イテレータを 1 度も
進めないうちに ``result()`` を呼ぶと ``write`` のコピー（変更なし）が返る。

``result()`` は同じ作業 Table インスタンスを返し続けるので、
``result().append(...)`` のように破壊的に加工した場合や、 ``result()`` を
呼んだ後に ``unmatched().only_in_write`` の ``write_row`` を書き換えた場合も、
後続の ``result().read()`` 呼び出しに反映される（``Table._iter_rows_for_update``
経由で実体 dict を共有しているため）。

Example:
    transfer = Transfer(source, destination, mapping,
                        read_key="顧客ID", write_key="顧客ID")
    for source_row, destination_row in transfer.matched_rows():
        transfer.apply_mapping(source_row, destination_row)
    final_table = transfer.result()  # 変更後の Table

### `UnmatchedRows`

```text
class UnmatchedRows:
```

#### 説明

突合しなかった行。

``only_in_read`` は **コピー**（``Table``）。書き換えても ``read`` にも
``result()`` にも影響しない。
``only_in_write`` は **作業 Table の実体行**（``list[Row]``）。書き換えると
``result()`` に反映される。型が違うのはこの違いを表すため。

### `compare_tables`

```text
def compare_tables(read: Table, write: Table, *, read_key: str | Sequence[str], write_key: str | Sequence[str]) -> TableComparison:
```

#### 説明

2つのTableをキーで比較し、4種類のTableに分けて返す。


## `from comken.exceptions import ...`

### `ComkenError`

```text
class ComkenError(Exception):
```

#### 説明

comken が出す固有エラー全体

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `SiteOwnerRequiredError`

```text
class SiteOwnerRequiredError(ComkenError):
```

#### 説明

`SiteBase` / `SalesforceBase` のサブクラスに `OWNER` が設定されていない

継承してサイト／組織クラスを作った事実がライブラリ管理者に届かないと、
同じ社内システムのクラスが複数プロジェクトで重複しても気づけない。
ドキュメントの努力目標では守れないので、起動時に OWNER の設定を強制する。

発生箇所: SiteBase.__enter__() / Browsers.launch(SiteBase) /
         SalesforceBase.__init__()

対処:
    サブクラスに `OWNER = "プロジェクト名 / 担当者"` を1行追加する。
    ライブラリ（`comken.toolbox.browser.sites/` または
    `comken.toolbox.salesforce.sites/`）に入れるべきサイトかは
    `docs/開発/ライブラリ開発規約.md` の「サイト／組織クラスを昇格させる基準」を
    参照して判断する。ライブラリに昇格したい場合はライブラリ管理者へ連絡する。

#### `__init__`

```text
def __init__(self, site_cls: type, base_cls_name: str) -> None:
```

### `InternalLibraryError`

```text
class InternalLibraryError(ComkenError):
```

#### 説明

社内ライブラリの呼び出しに失敗したときの基底例外

対処:
    画面に表示された具体的なエラー名（NotFound / VersionMismatch）を上の表から探す

### `InternalLibraryNotFoundError`

```text
class InternalLibraryNotFoundError(InternalLibraryError):
```

#### 説明

指定した社内ライブラリが見つからない

対処:
    社内 LAN 環境から、共有サーバ上の PYTHONPATH が通っているか確認し、
    指定したライブラリ名のフォルダが存在するか確かめる

#### `__init__`

```text
def __init__(self, library_name: str) -> None:
```

### `InternalLibraryVersionMismatchError`

```text
class InternalLibraryVersionMismatchError(InternalLibraryError):
```

#### 説明

指定したバージョンの社内ライブラリが見つからない

対処:
    共有サーバ上の対象ライブラリのバージョンを確認し、
    呼び出し側の指定と一致しているか確かめる

#### `__init__`

```text
def __init__(self, library_name: str, required_version: str) -> None:
```

### `AccessError`

```text
class AccessError(ComkenError):
```

#### 説明

Access に関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `AccessBackupError`

```text
class AccessBackupError(AccessError):
```

#### 説明

元 DB を開く前のバックアップに失敗した

対処:
    保存先の空き容量・書き込み権限・元 DB の読み取り権限を確認する

#### `__init__`

```text
def __init__(self, path: Path | str, backup_path: Path | str, detail: Exception) -> None:
```

### `AccessFileNotFoundError`

```text
class AccessFileNotFoundError(AccessError):
```

#### 説明

Access ファイルが見つからない

対処:
    ファイルの置き場所と名前を確認する

#### `__init__`

```text
def __init__(self, path: Path | str) -> None:
```

### `AccessLocalCopyError`

```text
class AccessLocalCopyError(AccessError):
```

#### 説明

Access ファイルを一時フォルダへコピーできない

対処:
    使用状況・読み取り権限・空き容量を確認する

#### `__init__`

```text
def __init__(self, path: Path | str, detail: Exception) -> None:
```

### `AccessRoutineError`

```text
class AccessRoutineError(AccessError):
```

#### 説明

Access マクロまたは VBA の実行に失敗した

対処:
    表示された名前と Access 側の内容を確認する

#### `__init__`

```text
def __init__(self, name: str, kind: str, detail: Exception) -> None:
```

### `AccessSourceNotFoundError`

```text
class AccessSourceNotFoundError(AccessError):
```

#### 説明

テーブルまたはクエリが見つからない

対処:
    エラーに表示された存在する名前を確認する

#### `__init__`

```text
def __init__(self, name: str, sources: list[str]) -> None:
```

### `ExcelError`

```text
class ExcelError(ComkenError):
```

#### 説明

Excel に関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `DataSheetAccessError`

```text
class DataSheetAccessError(ExcelError):
```

#### 説明

データシートと表示用シートの責務に反する操作をした。

対処:
    data_ で始まるシートは table()、それ以外はセル・範囲 API で操作する

#### `__init__`

```text
def __init__(self, sheet_name: str, operation: str) -> None:
```

### `ExcelFileNotFoundError`

```text
class ExcelFileNotFoundError(ExcelError):
```

#### 説明

Excel ファイルが見つからない

発生箇所: Excel.__init__() / ExcelCOMHandler.__init__()

対処:
    ファイルの置き場所と名前を確認する

#### `__init__`

```text
def __init__(self, path: Path | str) -> None:
```

### `ExcelApplicationNotAvailableError`

```text
class ExcelApplicationNotAvailableError(ExcelError):
```

#### 説明

Excel を起動できない

Excel が入っていない PC で、Excel 本体が要る操作をしようとした。
次のときに要る。

- 数式の計算結果を読む（計算結果がファイルに保存されていない場合）
- マクロを実行する、パスワード付きで保存する

**読み書きだけなら Excel は要らない**（openpyxl で動く）。

発生箇所: comken.toolbox.windows の ExcelCOMHandler

対処:
    この PC に Excel が入っているか確認する。入れられない PC で動かすなら、
    数式ではなく値で書いてもらう（管理表なら、数式の結果を貼り付けてもらう）

#### `__init__`

```text
def __init__(self, path: Path, error: Exception) -> None:
```

### `SheetNotFoundError`

```text
class SheetNotFoundError(ExcelError):
```

#### 説明

指定した名前のシートがない

発生箇所: Excel.sheet() / Excel.data_sheet()

対処:
    Excel を開いて、下のシート名（タブ）が変わっていないか確認する。変えた場合は元に戻す

#### `__init__`

```text
def __init__(self, name: str, sheets: list[str]) -> None:
```

### `SheetAlreadyExistsError`

```text
class SheetAlreadyExistsError(ExcelError):
```

#### 説明

同じ名前のシートが既にある

対処:
    別のシート名を指定するか、既存のシート名を変更する

#### `__init__`

```text
def __init__(self, name: str) -> None:
```

### `SheetNameError`

```text
class SheetNameError(ExcelError):
```

#### 説明

表示用シートに使えない名前を ``create_sheet`` に渡した

``PY_`` で始まる名前はデータシート用なので ``create_data_sheet`` で作る。

発生箇所: ``Excel.create_sheet()``

対処:
    予約接頭辞 ``PY_`` を除いた名前を ``create_sheet`` に渡すか、
    データシートとして作る場合は ``create_data_sheet`` を使う

#### `__init__`

```text
def __init__(self, name: str) -> None:
```

### `InvalidTableNameError`

```text
class InvalidTableNameError(ExcelError):
```

#### 説明

Excel で使えないテーブル名を指定した

対処:
    空白・数字始まり・セル参照のような名前を避ける

#### `__init__`

```text
def __init__(self, name: str) -> None:
```

### `TableAlreadyExistsError`

```text
class TableAlreadyExistsError(ExcelError):
```

#### 説明

同じ名前のテーブルが既にある

対処:
    別のテーブル名を指定する

#### `__init__`

```text
def __init__(self, name: str) -> None:
```

### `TableFormulaOverwriteError`

```text
class TableFormulaOverwriteError(ExcelError):
```

#### 説明

テーブル内の人が入れた数式を値で潰そうとした

数式セルがあると ``replace()`` / ``append()`` は既定で止まる。
黙って値で潰すと、依存セルや集計式が壊れたことに遅れて気づくため。

発生箇所: ExcelTable.replace() / ExcelTable.append()

対処:
    数式を保持したい場合は、``replace()`` のあとに該当セルへ元の数式を
    書き戻す。意図的に値で潰してよいときだけ ``allow_formula_overwrite=True`` を渡す

#### `__init__`

```text
def __init__(self, table_name: str, locations: Sequence[str]) -> None:
```

### `TableColumnMismatchError`

```text
class TableColumnMismatchError(ExcelError):
```

#### 説明

渡された Table の列が既存テーブルの見出しと一致しない

``replace()`` / ``append()`` は、渡された Table の列を既存の見出しと
名前で対応付ける。**既存の見出しに無い列名が含まれていた場合は例外**にし、
黙って無視や位置ズレで書き込まない（書き漏らしに気づくのが遅れるため）。

発生箇所: ExcelTable.replace() / ExcelTable.append()

対処:
    既存の見出しと一致するように渡す Table の列を修正する。
    数式で参照される列は渡さない（「金額」のように計算で決まる列を
    Table に含めない、または数式を保持する前提の列として残す）

#### `__init__`

```text
def __init__(self, table_name: str, missing: Sequence[str]) -> None:
```

### `TableNotFoundError`

```text
class TableNotFoundError(ExcelError):
```

#### 説明

指定したテーブルがシートにない

対処:
    エラーに表示された既存テーブル名を確認する

#### `__init__`

```text
def __init__(self, name: str, tables: list[str]) -> None:
```

### `MacroError`

```text
class MacroError(ExcelError):
```

#### 説明

Excel のマクロが失敗した

発生箇所: ExcelCOMHandler.run_macro()

対処:
    Excel をすべて閉じて再実行する。続く場合は管理者へ

#### `__init__`

```text
def __init__(self, name: str, detail: Exception) -> None:
```

### `EmptyHeaderCellError`

```text
class EmptyHeaderCellError(ExcelError):
```

#### 説明

Excel の見出しに空欄がある

発生箇所: Excel.read_computed_rows_as_dicts() / ExcelTable.read() /
         ExcelCOMHandler.read_rows_as_dicts()

対処:
    Excel の1行目の空欄を埋める

#### `__init__`

```text
def __init__(self, columns: list[int]) -> None:
```

### `DuplicateHeaderCellError`

```text
class DuplicateHeaderCellError(ExcelError):
```

#### 説明

Excel の見出し名が重複している

発生箇所: Sheet.read_rows_as_dicts()

対処:
    Excel の見出し名を重複しない名前に変更する

#### `__init__`

```text
def __init__(self, headers: Sequence[object]) -> None:
```

### `EmptyExcelTableError`

```text
class EmptyExcelTableError(ExcelError):
```

#### 説明

Excel テーブル定義はあるが、定義範囲を1行も読み取れない。

対処:
    Excel のテーブル定義範囲を確認する

#### `__init__`

```text
def __init__(self, sheet_name: str, reason: str) -> None:
```

### `ExcelHeadersTooFewError`

```text
class ExcelHeadersTooFewError(ExcelError):
```

#### 説明

指定した見出し数が列数より少ない

発生箇所: ExcelCOMHandler.read_rows_as_dicts()

対処:
    管理者へ連絡する

#### `__init__`

```text
def __init__(self, expected: int, actual: int) -> None:
```

### `ExcelMacroPreservationError`

```text
class ExcelMacroPreservationError(ExcelError):
```

#### 説明

保存予定のブックからVBAプロジェクトが欠落または変化した。

対処:
    元ファイルは保持される。管理者に連絡し、Excel実機で保存方法を確認する

#### `__init__`

```text
def __init__(self, path: Path | str) -> None:
```

### `ExcelReadOnlyOperationError`

```text
class ExcelReadOnlyOperationError(ExcelError):
```

#### 説明

read_only=True の Excel に書き込もうとした。

Excel(path, read_only=True) は読み取り専用なので、保存やシート作成を
行う create_sheet / create_data_sheet / run_macro 系の API は使えない。

発生箇所: Excel.create_data_sheet() / Excel.create_sheet() /
         Excel.run_macro()

対処:
    read_only=False で開き直すか、書き込みが要らない操作かを
    見直す（読み取りだけなら Excel(path, read_only=True) で十分）

#### `__init__`

```text
def __init__(self, operation: str) -> None:
```

### `ExcelSaveValidationError`

```text
class ExcelSaveValidationError(ExcelError):
```

#### 説明

保存予定のExcelファイルを再度開けず、安全に置き換えられない。

対処:
    元ファイルは保持される。空き容量とExcel形式を確認して再実行する

#### `__init__`

```text
def __init__(self, path: Path | str, detail: object) -> None:
```

### `FileFormatMismatchError`

```text
class FileFormatMismatchError(ExcelError):
```

#### 説明

保存拡張子と形式が合わない

発生箇所: ExcelCOMHandler.save_as()

対処:
    管理者へ連絡する

#### `__init__`

```text
def __init__(self, suffix: str) -> None:
```

### `CSVError`

```text
class CSVError(ComkenError):
```

#### 説明

CSV に関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `EncodingDetectionError`

```text
class EncodingDetectionError(CSVError):
```

#### 説明

CSV の文字コードを判定できない

発生箇所: CSV.read()

対処:
    CSV の保存形式を確認し、管理者へ連絡する

#### `__init__`

```text
def __init__(self, path: Path | str) -> None:
```

### `CSVFileNotFoundError`

```text
class CSVFileNotFoundError(CSVError):
```

#### 説明

読み込む CSV ファイルが存在しない

対処:
    パスを確認する。新規出力は columns を指定して write / replace する

#### `__init__`

```text
def __init__(self, path: Path | str) -> None:
```

### `CSVHeaderMissingError`

```text
class CSVHeaderMissingError(CSVError):
```

#### 説明

CSV に見出し行がない

対処:
    見出し行を追加するか、ヘッダーなし CSV なら columns を指定する

#### `__init__`

```text
def __init__(self, path: Path | str) -> None:
```

### `CSVInvalidHeaderError`

```text
class CSVInvalidHeaderError(CSVError):
```

#### 説明

CSV の見出しに空欄または重複がある

対処:
    CSV の1行目にある空欄または重複した見出しを直す

#### `__init__`

```text
def __init__(self, path: Path | str, reason: str) -> None:
```

### `CSVRowLengthError`

```text
class CSVRowLengthError(CSVError):
```

#### 説明

CSV のデータ行の列数が見出し数と一致しない

対処:
    表示された行の区切り文字と値の数を確認する

#### `__init__`

```text
def __init__(self, path: Path | str, line_number: int, expected: int, actual: int) -> None:
```

### `CSVColumnsRequiredError`

```text
class CSVColumnsRequiredError(CSVError):
```

#### 説明

空の新規 CSV に出力する列を決定できない

対処:
    CSV(columns=[...]) または Table(columns, []) で列を指定する

#### `__init__`

```text
def __init__(self, path: Path | str) -> None:
```

### `ColumnNotFoundError`

```text
class ColumnNotFoundError(ComkenError):
```

#### 説明

Excel・CSV・データ比較で列が見つからないエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `ExcelColumnNotFoundError`

```text
class ExcelColumnNotFoundError(ColumnNotFoundError):
```

#### 説明

Excel の列見出しが見つからない

非エンジニアが列名を変更したときに分かりやすいメッセージを出すために使う。

発生箇所: 利用側プロジェクトの列検証処理（comken 本体のソースからは
          送出されない。利用者プロジェクトから送出する想定）

使い方:
    from comken.exceptions import ExcelColumnNotFoundError

    REQUIRED_COLUMNS = ["日付", "担当者", "金額"]

    def validate_columns(rows: list[dict[str, str]], required: list[str]) -> None:
        missing = [column for column in required if column not in rows[0]]
        if missing:
            raise ExcelColumnNotFoundError(missing)

対処:
    Excel の1行目を確認する

#### `__init__`

```text
def __init__(self, columns: list[str]) -> None:
```

### `KeyColumnNotFoundError`

```text
class KeyColumnNotFoundError(ColumnNotFoundError):
```

#### 説明

比較に使うキー列が見つからない

発生箇所: diff_rows()

対処:
    Excel・CSV の列名を確認する

#### `__init__`

```text
def __init__(self, key: str, existing: list[str]) -> None:
```

### `TransferSourceColumnNotFoundError`

```text
class TransferSourceColumnNotFoundError(ColumnNotFoundError):
```

#### 説明

列名転記で、lookup の転記元列が見つからない

comken 本体のソースからは送出されない。利用者プロジェクトから送出する想定。
例外を定義して import するだけで使え、comken 内の利用は前提としない。
``ExcelColumnNotFoundError`` と同じ位置づけ。

発生箇所: 利用側プロジェクトの転記元列検証処理

対処:
    転記元データと config.ini のマッピング左側を確認する

#### `__init__`

```text
def __init__(self, columns: list[str], existing: list[str]) -> None:
```

### `InvalidColumnError`

```text
class InvalidColumnError(ComkenError):
```

#### 説明

列の指定が正しくない（打ち間違いなど）

対処:
    列は番号（1, 2, …）か列記号（"A", "AA"）で指定する

#### `__init__`

```text
def __init__(self, column: str) -> None:
```

### `ConfigError`

```text
class ConfigError(ComkenError):
```

#### 説明

config.ini に関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `ConfigFileNotFoundError`

```text
class ConfigFileNotFoundError(ConfigError):
```

#### 説明

config.ini が見つからない

発生箇所: Config.__init__() / generate_stub()

対処:
    config.ini.example が同じ場所にあるか確認する（あれば実行し直すだけで作られる）

#### `__init__`

```text
def __init__(self, path: Path | str) -> None:
```

### `ConfigCreatedFromExampleError`

```text
class ConfigCreatedFromExampleError(ConfigError):
```

#### 説明

config.ini が無かったので example から作った

発生箇所: Config.__init__()

対処:
    作られた config.ini の値を書き換えて、もう一度実行する

#### `__init__`

```text
def __init__(self, path: Path | str) -> None:
```

### `ConfigLowerCaseNameError`

```text
class ConfigLowerCaseNameError(ConfigError):
```

#### 説明

config.ini のセクション名・キー名に小文字がある

発生箇所: Config.__init__()

対処:
    表示された名前を大文字に書き換える（`[files]` → `[FILES]`）

#### `__init__`

```text
def __init__(self, path: Path | str, wrong: list[str]) -> None:
```

### `ConfigSectionNotFoundError`

```text
class ConfigSectionNotFoundError(ConfigError):
```

#### 説明

config.ini の必要な節がない

発生箇所: Config.__getattr__()

対処:
    メッセージに表示された **「読んだファイル」のパス** が、編集している
    config.ini と一致するかを確認する（2026-08-18 にプロジェクトの場所を
    基準にするように変えてから、起動方法によって別の config.ini を読む
    ことがあるため）。パスが正しければ、表示されたセクション名を
    config.ini に追加する。**見た目では原因が分からない場合**（行頭に
    空白が混入していた等）はエディタで行頭空白・全角スペースを確認する

#### `__init__`

```text
def __init__(self, name: str, existing: list[str], path: Path | str | None=None) -> None:
```

### `ConfigKeyNotFoundError`

```text
class ConfigKeyNotFoundError(ConfigError, AttributeError):
```

#### 説明

config.ini のセクションに必要なキーがない

発生箇所: Config 内の SimpleNamespace への属性アクセス

対処:
    メッセージに表示された **「読んだファイル」のパス** が、編集している
    config.ini と一致するかを確認する。パスが正しければ、表示された
    キー名を該当セクションへ追加する。**セクション名は合っているが
    キー名を 1 文字タイポした** とき（FILES.OUTPUT_FOLER 等）は、
    「もしかして」に近いキー名が出るので、それを config.ini に書き直す

#### `__init__`

```text
def __init__(self, section: str, name: str, existing: list[str], path: Path | str | None=None) -> None:
```

### `ConfigMappingEmptyValueError`

```text
class ConfigMappingEmptyValueError(ConfigError):
```

#### 説明

``[*_MAPPING]`` セクションの値が空欄

発生箇所: Config.__init__()（``*_MAPPING`` の ``_LenientDict`` 組み立て時）

対処:
    メッセージに表示された **「読んだファイル」のパス** が、編集している
    config.ini と一致するかを確認する。パスが正しければ、表示された
    キー名の両側に値を書いて config.ini を直す（``列名 = 値``）。
    ``=`` を付け忘れて ``キー`` のように書いた行もここで検出する
    （``cfg.get()`` が ``None`` を返すので空欄と同じ扱い）。
    通常セクションの空欄（``READ_PASSWORD =`` のように「設定しない」を
    示す書き方）はエラーにしないので、``*_MAPPING`` 以外では無視してよい

#### `__init__`

```text
def __init__(self, path: Path | str, section: str, empty_keys: list[str]) -> None:
```

### `UnsupportedFileSuffixError`

```text
class UnsupportedFileSuffixError(ComkenError):
```

#### 説明

対応外の拡張子が指定された

対処:
    CSV / Excel の対応する拡張子のファイルを指定する

#### `__init__`

```text
def __init__(self, path: Path, suffixes: tuple[str, ...]) -> None:
```

### `FileDeletionError`

```text
class FileDeletionError(ComkenError):
```

#### 説明

ファイルを削除できなかった

発生箇所: comken.core.files.delete_files()

対処:
    他のプロセスがファイルを掴んでいないか、読み取り専用になっていないかを確認して
    もう一度実行する。消せたファイルは消えている

Attributes:
    remaining: 削除できなかったファイルのパス一覧。

#### `__init__`

```text
def __init__(self, remaining: list[Path]) -> None:
```

### `FileSuffixMissingError`

```text
class FileSuffixMissingError(ComkenError):
```

#### 説明

ファイル名に拡張子が無い

発生箇所: comken.core.files.DateNameBuilder() / DateFileFinder.prefix() / DateFileFinder.dated()

対処:
    ファイル名に拡張子（例: ``.csv`` / ``.xlsx``）を含めて指定する。
    拡張子は名前の文字列にだけ書く。引数 ``ext`` / ``extension`` は廃止済みのため使えない。

#### `__init__`

```text
def __init__(self, name: str) -> None:
```

### `OutlookError`

```text
class OutlookError(ComkenError):
```

#### 説明

Outlook 関連エラーの分類

対処:
    下の個別エラーを確認する

### `ClassicOutlookNotAvailableError`

```text
class ClassicOutlookNotAvailableError(OutlookError):
```

#### 説明

Classic Outlook を利用できない

対処:
    Classic Outlook を使うか管理者に相談する

#### `__init__`

```text
def __init__(self) -> None:
```

### `OutlookFolderNotFoundError`

```text
class OutlookFolderNotFoundError(OutlookError):
```

#### 説明

指定したフォルダがない

対処:
    エラーに表示された存在するフォルダ名を確認する

#### `__init__`

```text
def __init__(self, folder: str, existing_folders: list[str]) -> None:
```

### `OutlookAttachmentNotFoundError`

```text
class OutlookAttachmentNotFoundError(OutlookError):
```

#### 説明

添付ファイルがない

対処:
    表示されたファイルパスを確認する

#### `__init__`

```text
def __init__(self, path: Path) -> None:
```

### `CredentialError`

```text
class CredentialError(ComkenError):
```

#### 説明

認証情報の保存・取得に関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `InvalidCredentialNameError`

```text
class InvalidCredentialNameError(CredentialError):
```

#### 説明

認証情報のキー名に使えない文字がある

発生箇所: comken.toolbox.credentials の Credentials() / save_credential() / 取り込み

対処:
    半角英数字とアンダースコアだけにする（漢字・スペース・記号は使えない）

#### `__init__`

```text
def __init__(self, label: str, name: str) -> None:
```

### `CredentialNotFoundError`

```text
class CredentialNotFoundError(CredentialError):
```

#### 説明

認証情報（パスワード・client_secret など）が登録されていない

発生箇所: comken.toolbox.credentials の load_credential() / Credentials の属性アクセス

対処:
    表示された登録済みキー名と見比べる。
    無ければ `python -m comken cred import 認証情報.json` で取り込む

#### `__init__`

```text
def __init__(self, name: str, registered: list[str]) -> None:
```

### `CredentialDecryptionError`

```text
class CredentialDecryptionError(CredentialError):
```

#### 説明

認証情報を復号できない

DPAPI は「登録したときの Windows ユーザー × PC」でしか復号できない。
別のアカウントで実行した・別の PC にファイルをコピーした場合がほとんど。

発生箇所: comken.toolbox.credentials の読み書き全般

対処:
    登録したときと**同じ Windows アカウント・同じ PC** で実行しているか確認する。
    タスクスケジューラの実行ユーザー違いが最も多い

#### `__init__`

```text
def __init__(self, path: Path, detail: Exception) -> None:
```

### `CredentialStoreCorruptedError`

```text
class CredentialStoreCorruptedError(CredentialError):
```

#### 説明

認証情報の中身が壊れている

復号できない（別ユーザー・別 PC）のとは対処が違う。こちらは実行アカウントを
直しても直らないので、ファイルを捨てて取り込み直すしかない。

発生箇所: comken.toolbox.credentials の読み書き全般

対処:
    実行アカウントの問題ではない。表示されたファイルを削除して、もう一度取り込み直す

#### `__init__`

```text
def __init__(self, path: Path, detail: str) -> None:
```

### `CredentialImportError`

```text
class CredentialImportError(CredentialError):
```

#### 説明

取り込む JSON が壊れている・形式が違う

発生箇所: comken.toolbox.credentials の import_json()

対処:
    表示された形式のとおりに書き直す。値は必ず `" "` で囲む

#### `__init__`

```text
def __init__(self, path: Path, detail: str) -> None:
```

### `SalesforceError`

```text
class SalesforceError(ComkenError):
```

#### 説明

Salesforce に関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `SalesforceAuthError`

```text
class SalesforceAuthError(SalesforceError):
```

#### 説明

Salesforce にログインできない

発生箇所: comken.toolbox.salesforce.SalesforceBase の認証時（初回・401 後の取り直し）

対処:
    表示された確認項目を上から順に見る。それでも直らなければ管理者へ連絡する

#### `__init__`

```text
def __init__(self, status_code: int, detail: str) -> None:
```

### `SalesforceConnectionError`

```text
class SalesforceConnectionError(SalesforceError):
```

#### 説明

Salesforce につながらない

発生箇所: comken.toolbox.salesforce.SalesforceBase の全リクエスト

対処:
    ネットワークの状態を確認して、少し待ってから再実行する

#### `__init__`

```text
def __init__(self, url: str, detail: Exception) -> None:
```

### `SalesforceRequestError`

```text
class SalesforceRequestError(SalesforceError):
```

#### 説明

Salesforce が処理を断った

発生箇所: comken.toolbox.salesforce.SalesforceBase の全リクエスト

対処:
    表示されたメッセージをそのまま添えて管理者へ連絡する（権限か項目名の問題が多い）

#### `__init__`

```text
def __init__(self, method: str, path: str, status_code: int, detail: str) -> None:
```

### `SalesforceExternalIDMissingError`

```text
class SalesforceExternalIDMissingError(SalesforceError):
```

#### 説明

upsert 用データに外部 ID がない

対処:
    管理者へ連絡する

#### `__init__`

```text
def __init__(self, object_name: str, external_id_field: str) -> None:
```

### `SalesforceCredentialRotationError`

```text
class SalesforceCredentialRotationError(SalesforceError):
```

#### 説明

consumer key / secret のローテーションを安全に完了できない

対処:
    Salesforce の ECA 設定・API レスポンス・DPAPI の保存先を確認する

#### `__init__`

```text
def __init__(self, detail: str) -> None:
```

### `SalesforceReportTruncatedError`

```text
class SalesforceReportTruncatedError(SalesforceError):
```

#### 説明

レポートが上限の 2000 行で切れた（**全件ではない**）

レポート API は同期・非同期とも 2000 行が上限。非同期にしても超えられない。
黙って欠けたデータで処理を続けないよう、既定ではこの例外で止める。

発生箇所: comken.toolbox.salesforce.ReportAPI.run() / run_async()

対処:
    期間を狭めて何回かに分けて実行する。1回で全部必要なら管理者へ連絡する

#### `__init__`

```text
def __init__(self, report_id: str, row_limit: int) -> None:
```

### `SalesforceReportFormatError`

```text
class SalesforceReportFormatError(SalesforceError):
```

#### 説明

レポートの形式が対応していない

集計（サマリ・マトリックス）形式は行の入れ物の構造が変わり、
そのまま読むと無言で空を返すため、明示的に弾く。

発生箇所: comken.toolbox.salesforce.ReportAPI.run() / run_async()

対処:
    レポートを明細形式にするか、管理者へ連絡する

#### `__init__`

```text
def __init__(self, report_id: str, report_format: str) -> None:
```

### `SalesforceReportIDNotFoundError`

```text
class SalesforceReportIDNotFoundError(SalesforceError):
```

#### 説明

レポートの URL からレポート ID を取り出せない

管理表にはレポートの URL をそのまま貼れるようにしてあるが、
貼られたものが Salesforce のレポート URL でないと ID を取り出せない。

発生箇所: comken.toolbox.salesforce.report.report_id_from_url()
         （comken.services.salesforce_downloader.master 経由）

対処:
    Salesforce でレポートを開いたときのアドレスを、そのまま貼り直す

#### `__init__`

```text
def __init__(self, text: str) -> None:
```

### `SalesforceReportExecutionError`

```text
class SalesforceReportExecutionError(SalesforceError):
```

#### 説明

Salesforce 側でレポート実行に失敗した

対処:
    Salesforce で同じレポートを直接実行し、表示された内容を管理者へ連絡する

#### `__init__`

```text
def __init__(self, report_id: str, detail: str) -> None:
```

### `SalesforceSiteNotFoundError`

```text
class SalesforceSiteNotFoundError(SalesforceError):
```

#### 説明

URL のドメインに対応する組織が登録されていない

管理表には複数の組織のレポート URL が混ざる。どの組織へつなぐかは
URL のドメインで決めるので、未登録のドメインでは接続先を選べない。

発生箇所: comken.toolbox.salesforce.sites.site_for()

対処:
    URL のドメインを見直す。新しい組織なら管理者へ連絡する
    （組織クラスの追加が要る）

#### `__init__`

```text
def __init__(self, url: str, known_domains: list[str]) -> None:
```

### `BrowserError`

```text
class BrowserError(ComkenError):
```

#### 説明

ブラウザ操作に関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `DriverStartError`

```text
class DriverStartError(BrowserError):
```

#### 説明

ブラウザを起動できない

発生箇所: Browsers.launch()

対処:
    エラーの本文にある確認事項をそのまま試す。
    Windows Update で Edge が更新された直後に起きやすい

#### `__init__`

```text
def __init__(self, driver_path: str, detail: Exception) -> None:
```

### `BrowsersNotStartedError`

```text
class BrowsersNotStartedError(BrowserError):
```

#### 説明

`with` を使わずに `Browsers` を使った

with を使わないと、処理の途中で例外が出たときにブラウザのプロセスが残り続ける。
残ったブラウザはドライバーの更新も邪魔するため、必ず with の中で使う。

    # 誤り
    browsers = Browsers()
    browsers.launch(Kintai)     # ← ここで送出される（ブラウザは起動しない）

    # 正しい
    with Browsers() as browsers:
        kintai = browsers.launch(Kintai)

対処:
    `with Browsers() as browsers:` の中で使う（ブラウザは起動していないので実害はない）

#### `__init__`

```text
def __init__(self, operation: str) -> None:
```

### `BrowsersClosedError`

```text
class BrowsersClosedError(BrowserError):
```

#### 説明

`with` を抜けた後の `Browsers` を使った

with の外へ browsers を持ち出すと起きる。with を抜けた時点で
ブラウザはすべて閉じているため、そこから起動や操作はできない。

対処:
    続けたい処理を `with` の中に入れる。外へ持ち出すのは取り出した値だけにする

#### `__init__`

```text
def __init__(self, operation: str) -> None:
```

### `SessionNotStartedError`

```text
class SessionNotStartedError(BrowserError):
```

#### 説明

`with` を使わずにブラウザを操作した

BrowserSession は with 文の中でだけ使える。with を使わないと、
処理の途中で例外が出たときにブラウザのプロセスが残り続けるため。

    # 誤り
    session = BrowserSession(...)
    session.open("https://example.com")     # ← ここで送出される

    # 正しい
    with Browsers() as browsers:
        kintai = browsers.launch(Kintai)
        kintai.session.open("https://example.com")

対処:
    `with Browsers() as browsers:` の中で使う

#### `__init__`

```text
def __init__(self, operation: str) -> None:
```

### `SessionClosedError`

```text
class SessionClosedError(BrowserError):
```

#### 説明

`with` を抜けた後のブラウザを操作した

with の外へセッションを持ち出すと起きる。取得したデータを with の外で使いたい場合は、
セッションではなく取り出した値（文字列やファイルパス）を返すようにする。

対処:
    `with` の外へ持ち出すのは、ブラウザではなく取り出した値にする

#### `__init__`

```text
def __init__(self, name: str, operation: str) -> None:
```

### `ConcurrentSessionUseError`

```text
class ConcurrentSessionUseError(BrowserError):
```

#### 説明

1つのブラウザを複数の処理から同時に操作した

WebDriver は1つの接続でコマンドを順番に処理するため、
同じセッションを2スレッドから同時に操作すると応答が入れ替わり、
「別の画面を操作していた」という追跡困難な不具合になる。
サイトごとにセッションを分けること（Browsers.launch で1サイト1セッション）。

対処:
    サイトごとに `launch` でブラウザを分ける

#### `__init__`

```text
def __init__(self, name: str, operation: str, holder_thread: str) -> None:
```

### `SessionNameConflictError`

```text
class SessionNameConflictError(BrowserError):
```

#### 説明

同じ名前で2回 `launch` した

発生箇所: Browsers.launch() / Browsers.launch_session()

対処:
    名前を変える（同一サイトの別アカウントなら `kintai_a` / `kintai_b` など）

#### `__init__`

```text
def __init__(self, name: str) -> None:
```

### `SessionNotFoundError`

```text
class SessionNotFoundError(BrowserError):
```

#### 説明

`launch` していない名前を取り出した

発生箇所: Browsers.__getitem__()

対処:
    先に `launch` する。エラーに起動済みの一覧が出ます

#### `__init__`

```text
def __init__(self, name: str, launched: list[str]) -> None:
```

### `SiteConfigError`

```text
class SiteConfigError(BrowserError):
```

#### 説明

`SiteBase` サブクラスの設定が不足している

ブラウザを起動する前に、必要なクラス定数が設定されていないとここで止まる。
起動してから「どのサイトか分からない」では遅いので、設定不足は呼び出し時点で
確実に発見する。

発生箇所: Browsers.launch(SiteBase)

対処:
    サブクラスに NAME を定義する（BASE_URL / OPTIONS も同じ）

#### `__init__`

```text
def __init__(self, site_cls: type, missing: str) -> None:
```

### `SiteAlreadyInLibraryError`

```text
class SiteAlreadyInLibraryError(BrowserError):
```

#### 説明

ライブラリ公認のサイトと同じ NAME のサイトをプロジェクト側で定義した

ライブラリ（`comken.toolbox.browser.sites`）に同じ NAME のクラスが
登録されているものを、プロジェクト側で再定義するとここで止まる。
「すでにライブラリにあるものを自作している」状態を自動で捕まえるのが目的。
どちらもプロジェクト側に置くと、片方を直してもう片方が追従できない事故になる。

発生箇所: SiteBase.__enter__() / Browsers.launch(SiteBase)

対処:
    ライブラリから `from comken.toolbox.browser.sites import <クラス名>` で取り出して使う。
    プロジェクト側の定義は消す。ライブラリへ昇格する基準は
    `docs/開発/ライブラリ開発規約.md` を参照。

#### `__init__`

```text
def __init__(self, site_cls: type, library_cls: type) -> None:
```

### `SiteNotStartedError`

```text
class SiteNotStartedError(BrowserError):
```

#### 説明

まだ起動していないサイトの画面を作ろうとした

`with` に入る前、または閉じた後に `to()` を呼ぶとここで止まる。
ブラウザが無い状態で画面クラスを作ると、最初の操作まで失敗が遅れる。

発生箇所: SiteBase.to() / SiteBase.downloads

対処:
    `with Kintai() as kintai:` の中で使う

#### `__init__`

```text
def __init__(self, site: type) -> None:
```

### `ElementNotFoundError`

```text
class ElementNotFoundError(BrowserError):
```

#### 説明

画面の部品が時間内に見つからない

selenium の TimeoutException を、どのセレクターで失敗したかが分かる形に包み直したもの。
素の TimeoutException はメッセージにセレクターが入らず、ログから原因を追えないため。

対処:
    もう一度実行する。サイトが重いだけのことが多い。毎回出るなら画面が変わった可能性があるので管理者へ（エラーに、どの部品を探していたかが出ます）

#### `__init__`

```text
def __init__(self, locator: object, seconds: int, condition: str) -> None:
```

### `PopupTabNotOpenedError`

```text
class PopupTabNotOpenedError(BrowserError):
```

#### 説明

別タブが開かない

発生箇所: BrowserSession.popup_tab()

対処:
    もう一度実行する。続く場合は、その画面の「別ウィンドウで開く」ボタンが変わった可能性があるので管理者へ

#### `__init__`

```text
def __init__(self, seconds: int) -> None:
```

### `DownloadTimeoutError`

```text
class DownloadTimeoutError(BrowserError):
```

#### 説明

ダウンロードが終わらない

発生箇所: DownloadDir.wait()

対処:
    ネットワークの状態を確認して再実行する。大きいファイルなら時間がかかっているだけのこともある

#### `__init__`

```text
def __init__(self, directory: object, seconds: int) -> None:
```

### `MasterTableError`

```text
class MasterTableError(ComkenError):
```

#### 説明

Excel の管理表に関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `MasterSheetNotDefinedError`

```text
class MasterSheetNotDefinedError(MasterTableError):
```

#### 説明

管理表の場所が決まっていない

`load()` を引数なしで呼ぶには、クラス変数 `PATH` に既定の場所を書いておく必要がある。

発生箇所: comken.services.salesforce_downloader.report_master の load()

対処:
    `load(パス)` のようにファイルを渡すか、クラスに PATH を書く（コードの直し方の話なので、
    非エンジニアが見た場合は管理者へ連絡する）

#### `__init__`

```text
def __init__(self, class_name: str) -> None:
```

### `MasterColumnNotFoundError`

```text
class MasterColumnNotFoundError(MasterTableError):
```

#### 説明

管理表に必要な列（見出し）が無い

見出しの行を書き換えた・列を消した・別のシートを見ている、のいずれか。
**プログラムは見出しの名前で列を探す**ので、見出しが変わると読めなくなる。

発生箇所: comken.services.salesforce_downloader.report_master の load()

対処:
    管理表の1行目（見出し）を元に戻す。消してしまった場合は、
    メッセージに出ている「今ある見出し」と見比べて足す

#### `__init__`

```text
def __init__(self, header: str, existing: list[str], path: Path, sheet_name: str) -> None:
```

### `MasterRowValueError`

```text
class MasterRowValueError(MasterTableError):
```

#### 説明

管理表の値が正しくない

数字を書く列に文字が入っている、決まった書き方以外を書いた、空にできない列が空、など。

発生箇所: comken.services.salesforce_downloader.report_master の load()

対処:
    メッセージに出ている行と列を、管理表で確認して直す

#### `__init__`

```text
def __init__(self, row_number: int, header: str, value: object, reason: str) -> None:
```

### `MasterDuplicateValueError`

```text
class MasterDuplicateValueError(MasterTableError):
```

#### 説明

一意であるべき列に、同じ値が2つ以上ある

管理番号のように「1つに決まる」ことが前提の列で重複すると、
どの行を指しているか決められない。

発生箇所: comken.services.salesforce_downloader.report_master の load()

対処:
    管理表を開いて、重複している値のどちらかを別の値に変える

#### `__init__`

```text
def __init__(self, header: str, value: object, path: Path) -> None:
```

### `StateError`

```text
class StateError(ComkenError):
```

#### 説明

state.ini に関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `StateFileCorruptedError`

```text
class StateFileCorruptedError(StateError):
```

#### 説明

state.ini が壊れていて読み取れない

対処:
    内容を直す。直せない場合は別名に変更して、空の状態から再実行する

#### `__init__`

```text
def __init__(self, path: Path | str) -> None:
```

### `StateLowerCaseNameError`

```text
class StateLowerCaseNameError(StateError):
```

#### 説明

state のキー名に小文字がある

対処:
    表示されたキー名を大文字に直す（`last_file` → `LAST_FILE`）

#### `__init__`

```text
def __init__(self, key: str) -> None:
```

### `StateValueTypeError`

```text
class StateValueTypeError(StateError):
```

#### 説明

state に保存できない型の値が渡された

対処:
    真偽値・整数・小数・文字列・文字列のリストのいずれかに変更する

#### `__init__`

```text
def __init__(self, value: object) -> None:
```

### `BusinessDayNotFoundError`

```text
class BusinessDayNotFoundError(HolidayCalendarError):
```

#### 説明

営業日が見つからなかった

月の途中で「指定した月の営業日数を超える n 番目」を求めたとき、
その月に営業日が 1 日も無いとき、祝日データ欠落などで 400 日探索しても
次の営業日にたどり着けなかったときに送る。
いずれも「カレンダー側がおかしい」または「指定値が暦と合わない」場合に
起き、業務ロジック側のミスではないので、呼び出し側で握り潰さずユーザーに
顕在化させる必要がある。

発生箇所: comken.core.holidays.calendar の HolidayCalendar
    - nth_business_day_of_month（n が月の営業日数超え、または n < 1）
    - first_business_day_of_month / last_business_day_of_month
      （その月に営業日が 1 日も無い）
    - business_day_after / business_day_before /
      business_day_on_or_after / business_day_on_or_before
      （400 日の探索上限に達した）

対処:
    n をその月の営業日数以下に直す、対象月の祝日に過不足がないか
    確認する、社内管理表（会社休日）が広範囲に登録されていないか確認する

#### `__init__`

```text
def __init__(self, detail: str) -> None:
```

### `HolidayCalendarError`

```text
class HolidayCalendarError(ComkenError):
```

#### 説明

祝日カレンダーに関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `HolidayCalendarFetchError`

```text
class HolidayCalendarFetchError(HolidayCalendarError):
```

#### 説明

内閣府の祝日 CSV を取得できない

オフライン環境・社内ネットワークの制約・内閣府サイトの保守などの理由で
ダウンロードが失敗する。**ただしキャッシュが残っている場合は警告ログのみで動く**
（cached フラグで運用側が検知できる）。

発生箇所: comken.toolbox.holidays.sources.cabinet_office の CabinetOfficeCSVSource

対処:
    ネットワーク接続と社内プロキシの設定を確認する。
    それでも直らない場合は、保存済みのキャッシュで当面動かすか、
    管理表（Excel）に会社休日を登録して代用する

#### `__init__`

```text
def __init__(self, url: str, reason: str) -> None:
```

### `HolidayCalendarSourceError`

```text
class HolidayCalendarSourceError(HolidayCalendarError):
```

#### 説明

祝日データの読み取りに失敗した

内閣府の CSV 形式が変わった・社内管理表のシート名が違う・列が無い・
文字化けしたなどの理由で、祝日を 1件も抽出できない場合に上げる。

発生箇所: comken.core.holidays の csv_source

対処:
    内閣府の CSV の場合: 内閣府の仕様変更。管理者へ連絡する

#### `__init__`

```text
def __init__(self, source: str, reason: str) -> None:
```

### `HolidayCalendarFormatError`

```text
class HolidayCalendarFormatError(HolidayCalendarSourceError):
```

#### 説明

内閣府 CSV 以外のファイルや壊れたファイルを内閣府 CSV として読み込もうとした

発生箇所: comken.core.holidays.csv_source の load_cabinet_office_csv

対処:
    内閣府の syukujitsu.csv を直接取得し直す。文字コードは CP932 (Shift_JIS)

#### `__init__`

```text
def __init__(self, path: Path | str, detail: str) -> None:
```

### `DownloaderError`

```text
class DownloaderError(ComkenError):
```

#### 説明

Salesforce レポートの集約取得に関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `HistoryWriteError`

```text
class HistoryWriteError(DownloaderError):
```

#### 説明

必須のダウンロード履歴を記録できなかった

対処:
    履歴CSVの保存先、共有サーバー接続、書込み権限を確認する

#### `__init__`

```text
def __init__(self, path: Path, reason: str, *, original: BaseException | None=None) -> None:
```

### `HistoryLockTimeoutError`

```text
class HistoryLockTimeoutError(DownloaderError):
```

#### 説明

ダウンロード履歴の排他ロックを待っても取得できなかった

対処:
    同時実行中の処理が終わるのを待って再実行する。繰り返す場合は共有サーバーを確認する

#### `__init__`

```text
def __init__(self, path: Path, timeout: float) -> None:
```

### `HistoryHeaderMismatchError`

```text
class HistoryHeaderMismatchError(DownloaderError):
```

#### 説明

ダウンロード履歴CSVの見出しが現在の定義と一致しない

対処:
    履歴CSVの1行目を確認する。列を手で変更していた場合は元へ戻し、
    古い形式の履歴なら別名へ退避してから再実行する

#### `__init__`

```text
def __init__(self, path: Path, actual: tuple[str, ...], expected: tuple[str, ...]) -> None:
```

### `CachedReportNotFoundError`

```text
class CachedReportNotFoundError(DownloaderError):
```

#### 説明

本日の定期取得キャッシュが見つからない

定期取得の時刻より前に呼ばれた、定期取得が失敗した、その日に管理表へ
追加されて今日の分に間に合わなかった、のいずれか。

**勝手に Salesforce へ取りに行かない。** cached_report() は
「取っておいたものを受け取る」関数で、取りに行く関数ではない。
ここで自動的に取りに行くと、定期取得が動いていないことに誰も気づかなくなる。

発生箇所: comken.services.salesforce_downloader の cached_report()

対処:
    Salesforce からCSVを手動取得し、画面に表示された正確なパス・ファイル名で置いて、
    同じ python main.py を再実行する

#### `__init__`

```text
def __init__(self, report_key: str, summary: str, cache_path: Path) -> None:
```

### `CachedReportNotRegisteredError`

```text
class CachedReportNotRegisteredError(DownloaderError):
```

#### 説明

定期取得の対象ではないレポートのキャッシュを読もうとした

cached_report() は「定期実行が取っておいた本日のデータを受け取る」関数。
管理表で「個別」になっているレポートは誰も取りに行かないので、いつまでも揃わない。

発生箇所: comken.services.salesforce_downloader の cached_report()

対処:
    毎日決まった時刻に取るなら、管理表の「実行方式」を「定期」にする。
    使うときに毎回取りに行くなら、download_report() を呼ぶ

#### `__init__`

```text
def __init__(self, report_key: str, summary: str, schedule: str, master_path: Path) -> None:
```

### `ReportNotRegisteredError`

```text
class ReportNotRegisteredError(DownloaderError):
```

#### 説明

指定した管理番号が管理表に無い

管理番号はコードに定数で書く（CUSTOMER_LIST = "1001"）。管理表から行を消したり、
番号を打ち間違えたりすると、どのレポートを指しているか決められない。

発生箇所: comken.services.salesforce_downloader の download_report()

対処:
    管理表を開いて、その管理番号の行があるか確認する。
    新しく使うレポートは、先に管理表へ登録する

#### `__init__`

```text
def __init__(self, report_key: str, registered: list[str], master_path: Path) -> None:
```

### `ReportDisabledError`

```text
class ReportDisabledError(DownloaderError):
```

#### 説明

管理表で「無効」になっているレポートを取ろうとした

使うのをやめたレポートは、行を消さずに「無効」にして履歴との対応を残す。
無効のものを黙って取りに行くと、やめたはずの取得が続いてしまう。

発生箇所: comken.services.salesforce_downloader の download_report()

対処:
    また使うなら管理表の「有効」を「有効」に戻す。
    使わないなら、呼び出し側のコードから消す

#### `__init__`

```text
def __init__(self, report_key: str, summary: str, master_path: Path) -> None:
```

### `InvalidReportURLError`

```text
class InvalidReportURLError(DownloaderError):
```

#### 説明

管理表の URL から Salesforce のレポート ID を取り出せない

貼られたものが Salesforce のレポート URL でないと、どのレポートか決められない。

発生箇所: comken.services.salesforce_downloader の管理表読み込み

対処:
    Salesforce でレポートを開いたときのアドレスを、そのまま貼り直す

#### `__init__`

```text
def __init__(self, report_key: str, url: str, reason: str) -> None:
```

### `EmptyReportError`

```text
class EmptyReportError(DownloaderError):
```

#### 説明

レポートは実行できたが明細が 0 行だった

空のファイルを置くと、使う側は「データが無い日」と「取得が失敗した日」を
区別できなくなる。0 行のときはファイルを作らず、失敗として扱う。

発生箇所: comken.services.salesforce_downloader の download_report()

対処:
    Salesforce の画面で同じレポートを開き、本当に 0 件か確認する。
    0 件が正常に起こるレポートなら、管理表の「0件あり」を「○」にする。

#### `__init__`

```text
def __init__(self, report_key: str, summary: str, url: str) -> None:
```

### `ReportFolderNotFoundError`

```text
class ReportFolderNotFoundError(DownloaderError):
```

#### 説明

管理表に書かれた保存先のフォルダが無い

無いフォルダを作らないのは、書き間違いのことが多いため。
勝手に作ると、誰も読まない場所へ置き続けることになる。

発生箇所: comken.services.salesforce_downloader の download_report()

対処:
    管理表の「保存先」を確認する。共有フォルダなら、
    つながっているか・権限があるかも確認する

#### `__init__`

```text
def __init__(self, report_key: str, folder: Path) -> None:
```

### `ScheduledDownloadFailedError`

```text
class ScheduledDownloadFailedError(DownloaderError):
```

#### 説明

定期取得で1件以上が失敗した

取得できたものは保存済み。**1件失敗しても残りは続けたうえで、最後にまとめて知らせる。**
ログだけに出して正常終了すると、スケジューラや RPA 基盤から見て成功と区別が付かず、
落ちていることに誰も気づかない。

発生箇所: comken.services.salesforce_downloader の download_scheduled()

対処:
    履歴（ダウンロード履歴.csv）の「エラー内容」で、失敗した理由を確認する。
    急いで必要なものは download_report() でその場で取得する

#### `__init__`

```text
def __init__(self, failed_keys: list[str], history_path: Path) -> None:
```

### `UnsupportedScheduleFrequencyError`

```text
class UnsupportedScheduleFrequencyError(DownloaderError):
```

#### 説明

管理表の「取得頻度」に、想定外の値が書かれている

許容される値は ``1時間ごと`` / ``毎日`` / ``毎週`` / ``毎月`` の4種類。
それ以外（手書きのタイポ・想定外の列挙値）が入っていると判定できない。

発生箇所: comken.services.salesforce_downloader.schedule の is_due()

対処:
    管理表の「取得頻度」列の値を ``1時間ごと`` / ``毎日`` / ``毎週`` /
    ``毎月`` のいずれかに修正する

#### `__init__`

```text
def __init__(self, frequency: str) -> None:
```

### `ScheduleIntervalMissingError`

```text
class ScheduleIntervalMissingError(DownloaderError):
```

#### 説明

「1時間ごと」の行で、開始・終了・間隔のどれかが抜けている

1時間おきの判定は「開始時刻から終了時刻までのあいだ、指定分間隔で動く」
という形なので、3つの情報がそろうまで動かない。

発生箇所: comken.services.salesforce_downloader.schedule の is_due()

対処:
    管理表の「取得開始時刻」「取得終了時刻」「取得間隔（分）」の3列を
    すべて埋める

#### `__init__`

```text
def __init__(self) -> None:
```

### `ScheduleRequiredValueMissingError`

```text
class ScheduleRequiredValueMissingError(DownloaderError):
```

#### 説明

管理表の必須列が空になっている

スケジュールキー・レポートキー・取得頻度のいずれかが空だと、
どのレポートをいつ取るか決められない。

発生箇所: comken.services.salesforce_downloader.schedule の ScheduleRule.from_row()

対処:
    管理表の該当行で、表示された列名（スケジュールキー / レポートキー /
    取得頻度）の値を埋める

#### `__init__`

```text
def __init__(self, column: str) -> None:
```

### `ScheduleWeekdayInvalidError`

```text
class ScheduleWeekdayInvalidError(DownloaderError):
```

#### 説明

管理表の「曜日」列に想定外の値が入っている

許容されるのは月〜日の漢字1文字（「月」「火」「水」「木」「金」「土」「日」）
または「〜曜日」の接尾辞付き表記。

発生箇所: comken.services.salesforce_downloader.schedule の ScheduleRule.from_row()

対処:
    管理表の「曜日」列の値を月〜日のいずれかに修正する（「曜日」を付ける
    形式でも可）

#### `__init__`

```text
def __init__(self, value: object) -> None:
```

### `TransferDestinationMultipleMatchError`

```text
class TransferDestinationMultipleMatchError(ComkenError):
```

#### 説明

転記先のキーに一致する行が複数ある

発生箇所: Transfer()

対処:
    mapping の先頭列に対応する転記先列の値を一意にする。
    キーが ``None`` か ``""`` の行は突合対象外なので、
    空欄のキーが複数あってもこの例外は出ない。

#### `__init__`

```text
def __init__(self, key_column: str, key: object) -> None:
```

### `TableNotOpenError`

```text
class TableNotOpenError(TableError):
```

#### 説明

表を with 文で開かずに操作した。

対処:
    ``with`` 文の中で使う（CSV / Excel などは ``__enter__`` で表を開く）

#### `__init__`

```text
def __init__(self, table_type: str) -> None:
```

### `TransferDestinationMissingError`

```text
class TransferDestinationMissingError(TableError):
```

#### 説明

Transfer.apply_mapping() に転記先が None で渡された

発生箇所: Transfer.apply_mapping(read_row, write_row)

対処:
    matched_rows() を使うか、``transfer_rows()`` の ``(read_row, None)``
    を ``if write_row is None:`` で分岐してから渡す。 新規行を追加する
    場合は ``Transfer`` の責務ではなく、``Table.append()`` 等で利用者側で
    対応する。

### `TableError`

```text
class TableError(ComkenError):
```

#### 説明

表データの読み書き・転記に関するエラー

発生箇所: Transfer

対処:
    画面に表示された具体的なエラー内容を確認する

### `InvalidTableInputError`

```text
class InvalidTableInputError(TableError):
```

#### 説明

Table API に対応しない入力が渡された。

発生箇所: Table / CSV / ExcelTable

対処:
    columns、rows、types の型と列名を確認する

### `InvalidTableOperationError`

```text
class InvalidTableOperationError(TableError):
```

#### 説明

Table API で実行できない操作が指定された。

発生箇所: Table / CSV / ExcelTable

対処:
    対象が読み取り専用でないか、指定したテーブル名が正しいか確認する

### `TableColumnNotFoundError`

```text
class TableColumnNotFoundError(TableError):
```

#### 説明

Table に指定された列が存在しない。

発生箇所: Table

対処:
    Table.columns を確認し、存在する列名を指定する

#### `__init__`

```text
def __init__(self, columns: list[str]) -> None:
```

### `TableDuplicateKeyError`

```text
class TableDuplicateKeyError(TableError):
```

#### 説明

Table の索引または比較に使うキーが重複している。

発生箇所: Table.index() / compare_tables()

対処:
    キー列の値を一意にしてから処理をやり直す

#### `__init__`

```text
def __init__(self, columns: list[str], key: object) -> None:
```

### `TableRowColumnsError`

```text
class TableRowColumnsError(TableError):
```

#### 説明

行の列名が Table.columns と一致しない

対処:
    不足列と余分な列を直す。列を絞る場合は select() を使う

#### `__init__`

```text
def __init__(self, row_number: int, missing: list[str], extra: list[str]) -> None:
```

### `TableTypeConversionError`

```text
class TableTypeConversionError(TableError):
```

#### 説明

Table の値を指定型へ変換できない

対処:
    表示された行番号・列名の値を、指定した型へ変換できる内容に直す

#### `__init__`

```text
def __init__(self, row_number: int, column: str, value: object) -> None:
```

### `LoggingAlreadyConfiguredError`

```text
class LoggingAlreadyConfiguredError(ComkenError):
```

#### 説明

root logger がすでに設定されている

対処:
    setup_logging() または setup_local_logging() はアプリの入口で1回だけ呼ぶ。
    実行基盤がログを設定する場合は呼ばない。

#### `__init__`

```text
def __init__(self) -> None:
```

### `LoggingConflictError`

```text
class LoggingConflictError(ComkenError):
```

#### 説明

root logger に comken 以外の handler が設定されている

他ライブラリが先に root logger を設定した状態で ``setup_logging()`` /
``setup_local_logging()`` を呼ぶと、comken が既存 handler の出力先や
レベルを勝手に変えてしまう。「何がどう混ざっているのか」を運用担当者に
そのまま見せられるよう、既存 handler の正体を判別できる範囲で
メッセージに並べる。

この例外は ``setup_logging()`` / ``setup_local_logging()`` の呼び方では
解決しない。利用者がコードを直しても他ライブラリの root logger 設定を
止められないので、上が運用側へ通知されることを前提にした例外。

対処:
    上の handler 一覧をそのままライブラリの管理者へ連絡してください
    （連絡先は環境ごとに異なるので、ここには書かない）。
    やむを得ず共存させたい場合は、呼び出し時に ``allow_existing=True``
    を指定すれば処理は続きますが、comken のハンドラーが追加されることで
    既存ライブラリのログが**二重**に出たり、出力先が想定と変わる可能性
    があります。

#### `__init__`

```text
def __init__(self, handlers: list[str]) -> None:
```

### `LogRootNotConfiguredError`

```text
class LogRootNotConfiguredError(ComkenError):
```

#### 説明

LoggerSite の LOG_ROOT が設定されていない

ファイルを作る前にここで止める。空のフォルダが現場へ残ると
「設定し忘れたのか、運用で消すのか」が判断できなくなるため。

対処:
    サブクラスに ``LOG_ROOT = "\\server\share\logs"`` を1行追加する
    （絶対パスまたは UNC 文字列。LOG_FOLDER_NAMES のフォルダ名はこの下に作られる）。

#### `__init__`

```text
def __init__(self, site_cls: type) -> None:
```

### `WindowNotFoundError`

```text
class WindowNotFoundError(ComkenError):
```

#### 説明

指定したウィンドウが見つからない

発生箇所: ``WindowHandler.__init__``

対処:
    対象ウィンドウが開いているか、タイトル（完全一致）が想定どおりかを確認する

#### `__init__`

```text
def __init__(self, title: str) -> None:
```


## `from comken.internal import ...`

### `InternalLibraryBase`

```text
class InternalLibraryBase:
```

#### 説明

社内ライブラリのモジュールを束ねるラッパークラス。

利用例::

    with InternalLibraryBase("example_libs.v0000.rpa") as rpa:
        rpa.backoffice(main, "project")

#### `__init__`

```text
def __init__(self, library_name: str) -> None:
```

#### `library_name`

```text
@property
def library_name(self) -> str:
```

##### 説明

社内ライブラリの正式名称(例: ``example_libs.v0000.rpa``)を返す。

#### `find_spec`

```text
def find_spec(self) -> bool:
```

##### 説明

社内ライブラリが import 可能なら True。

親パッケージ (``example_libs.v0000`` など) が見つからない場合も False を返す。

#### `load`

```text
def load(self) -> ModuleType:
```

##### 説明

社内ライブラリを import して返す。

「対象モジュール自身、またはその親パッケージが見つからない」ときだけ
``InternalLibraryNotFoundError`` に変換する。 モジュール内に別の依存が
あって ``ImportError`` / ``ModuleNotFoundError`` が出た場合はそのまま伝搬する
（依存不足を対象ライブラリの不在と誤変換しないため）。

### `InternalLibraryError`

```text
class InternalLibraryError(ComkenError):
```

#### 説明

社内ライブラリの呼び出しに失敗したときの基底例外

対処:
    画面に表示された具体的なエラー名（NotFound / VersionMismatch）を上の表から探す

### `InternalLibraryNotFoundError`

```text
class InternalLibraryNotFoundError(InternalLibraryError):
```

#### 説明

指定した社内ライブラリが見つからない

対処:
    社内 LAN 環境から、共有サーバ上の PYTHONPATH が通っているか確認し、
    指定したライブラリ名のフォルダが存在するか確かめる

#### `__init__`

```text
def __init__(self, library_name: str) -> None:
```

### `InternalLibraryVersionMismatchError`

```text
class InternalLibraryVersionMismatchError(InternalLibraryError):
```

#### 説明

指定したバージョンの社内ライブラリが見つからない

対処:
    共有サーバ上の対象ライブラリのバージョンを確認し、
    呼び出し側の指定と一致しているか確かめる

#### `__init__`

```text
def __init__(self, library_name: str, required_version: str) -> None:
```

### `is_internal_library_available`

```text
def is_internal_library_available(library_name: str) -> bool:
```

#### 説明

社内ライブラリが import 可能なら True。

親パッケージが見つからない場合 (``example_libs.v0000`` 自体が無いなど) も
False を返す。 ``find_spec`` が内部依存の不在を区別できないため、
この関数では「対象モジュール自体」の存在のみを判定する。

### `find_internal_library`

```text
def find_internal_library(library_name: str) -> ModuleType | None:
```

#### 説明

社内ライブラリを import して返す。無ければ None。

``load()`` と同じく、対象モジュール自身（またはその親）が存在しない場合のみ
None を返す。 モジュール内の依存不足は ImportError としてそのまま伝搬する。


## `from comken.services.salesforce_downloader import ...`

### `download_report`

定義を解決できませんでした。

### `download_report_path`

定義を解決できませんでした。

### `download_scheduled`

定義を解決できませんでした。

### `cached_report`

定義を解決できませんでした。

### `cached_report_path`

定義を解決できませんでした。

### `file_path_of`

定義を解決できませんでした。

### `load_master`

```text
@measure
def load_master(path: str | Path | None=None) -> dict[str, ReportEntry]:
```

#### 説明

管理表を読んで、管理番号をキーにした辞書を返す。

Args:
    path: 管理表（Excel）のパス。

Returns:
    {管理番号: ReportEntry}。管理表に並んでいる順を保つ。

### `shared_report_ids`

```text
def shared_report_ids(entries: dict[str, ReportEntry]) -> dict[str, list[str]]:
```

#### 説明

同じ Salesforce レポートを指している管理番号を返す。

**同じレポートを複数のプロジェクトが別々の管理番号で使っている**ことが分かる。
エラーにはしない——意図してそうしている場合（保存先を分けたい等）もあるため、
気づけるようにするだけにする。

Returns:
    {Salesforce のレポート ID: [管理番号, ...]}。2つ以上のものだけ。

### `ReportEntry`

```text
class ReportEntry(MasterRow):
```

#### 説明

レポート管理表の1行。

#### `report_id`

```text
@property
def report_id(self) -> str:
```

##### 説明

URL から取り出した Salesforce のレポート ID。

**行番号ではなく管理番号で示す。** 空行を飛ばして読むので行番号はズレうるが、
管理番号なら管理表を検索して一発で見つかる。

Raises:
    InvalidReportURLError: URL からレポート ID を取り出せない場合。

#### `is_scheduled`

```text
@property
def is_scheduled(self) -> bool:
```

##### 説明

定期取得の対象か。

### `ScheduleRule`

```text
class ScheduleRule:
```

#### 説明

取得スケジュール管理表の1行。

#### `from_row`

```text
@classmethod
def from_row(cls, row: Mapping[str, object]) -> 'ScheduleRule':
```

##### 説明

日本語カラム名の辞書からスケジュールを作る。

#### `is_due`

```text
def is_due(self, now: dt.datetime, *, holidays: set[dt.date] | frozenset[dt.date]=frozenset()) -> bool:
```

##### 説明

指定時刻にこのスケジュールを実行すべきか判定する。

#### `job_key`

```text
def job_key(self, target_date: dt.date) -> str:
```

##### 説明

履歴で取得済みか判定するキーを返す。


## `from comken.toolbox import ...`

### `Table`

```text
class Table:
```

#### 説明

列と辞書行をメモリで扱う表。

CSVやExcelに直接依存しないため、加工処理をファイルI/Oから分離できます。
``types`` は入力時に明示された列だけを変換し、暗黙の型推測は行いません。

#### `__init__`

```text
def __init__(self, columns: list[str] | tuple[str, ...], rows: list[dict[str, Any]], *, types: Mapping[str, Callable[[Any], Any]] | None=None) -> None:
```

#### `read`

```text
def read(self) -> list[dict[str, Any]]:
```

##### 説明

現在の行をコピーして返す。元のTableは変更しない。

#### `replace`

```text
def replace(self, rows: list[dict]) -> 'Table':
```

##### 説明

表の全行を置き換え、同じTableを返す。

#### `append`

```text
def append(self, rows: list[dict] | dict) -> 'Table':
```

##### 説明

1行または複数行を末尾へ追加する。

#### `count`

```text
def count(self) -> int:
```

##### 説明

行数を返す。

#### `select`

```text
def select(self, *columns: str) -> 'Table':
```

##### 説明

指定した列だけを持つ新しいTableを返す。

#### `filter`

```text
def filter(self, predicate: Callable[[dict], bool]) -> 'Table':
```

##### 説明

条件に一致する行だけを持つ新しいTableを返す。

#### `column`

```text
def column(self, name: str) -> list[Any]:
```

##### 説明

指定列の値を順番どおりに返す。

#### `index`

```text
def index(self, key: str) -> dict[Any, dict]:
```

##### 説明

指定列をキーにした辞書を返す。

#### `group_by`

```text
def group_by(self, key: str) -> dict[Any, 'Table']:
```

##### 説明

指定列の値ごとにTableを分けて返す。

#### `concat`

```text
def concat(self, other: 'Table') -> 'Table':
```

##### 説明

同じ列定義の表を縦に連結する。

列の順番は異なっていても構わないが、列名の集合が異なる表は
別のデータとして扱う。列不足を空欄で補うと、入力ミスに気づけず
データ欠落につながるため、ここでは明示的にエラーにする。

### `Transfer`

```text
class Transfer:
```

#### 説明

Table 間のキー突合と転記を行う。

基本的な用法は次のとおり。 ``mapping`` は「転記元の列名 → 転記先の列名」。
3つの取り出し口を使い分けて、read / write を行単位で加工する:

- ``matched_rows()``: 両方にキーが揃う行を ``(read_row, write_row)`` で返す
  （**両方とも作業 Table の実体行**）
- ``transfer_rows()``: read 全行を ``(read_row, write_row | None)`` で返す
  （write に無い行は ``None``、``read_row`` は **コピー**）
- ``unmatched()``: 突合しなかった行を ``UnmatchedRows`` で返す
  - ``only_in_read`` は **コピー**（``Table``）。書き換えても ``read`` にも
    ``result()`` にも影響しない
  - ``only_in_write`` は **作業 Table の実体行**（``list[Row]``）。書き換えると
    ``result()`` に反映される

Example:
    transfer = Transfer(read_table, write_table, mapping,
                        read_key="顧客ID", write_key="顧客ID")
    for read_row, write_row in transfer.matched_rows():
        if 条件:
            continue                       # この行は破棄
        transfer.apply_mapping(read_row, write_row)   # mapping の値をコピー
        # 必要なら write_row["備考"] = "..." のように追加加工
    # write に無い read 行は result() に追加していく（新規行の追加）
    for read_row in transfer.unmatched().only_in_read:
        transfer.result().append({
            "顧客ID": read_row["顧客ID"],
            "顧客名": read_row["取引先"],
            "請求額": read_row["金額"],
            "備考": "新規追加",
        })
    # read に無い write 行は「転記元に無し」と書き換える（result() に出るので別途 filter する）
    for write_row in transfer.unmatched().only_in_write:
        write_row["備考"] = "転記元に無し"

**条件は ``apply_mapping()`` より前に書くこと。** Python の ``for`` ループは
``continue`` したかどうかを呼び出し側に伝えないため、ループ内で
``apply_mapping()`` を呼ばずに ``continue`` した行は、作業 Table へ反映されない。
条件判定を ``apply_mapping()`` の後ろに書くと、``continue`` しても mapping が
適用済みとなり破棄できないので、判定は必ず ``apply_mapping()`` の前に置く。

**空キー (``None`` / ``""``) は突合対象外**。 値が無いキーは read 側・write 側の
どちらでも照合に使わず、``unmatched()`` 側へ流れる。 ``0`` や ``False`` は
空ではない（数値・bool の 0 落ち判定を避けるため）。 複合キーは **1要素でも空**
なら空とみなす。

#### `__init__`

```text
def __init__(self, read: Table, write: Table, mapping: Mapping[str, str], *, read_key: str | Sequence[str] | None=None, write_key: str | Sequence[str] | None=None) -> None:
```

#### `transfer_rows`

```text
def transfer_rows(self) -> Iterator[tuple[Row, Row | None]]:
```

##### 説明

転記元の全行を ``(read_row, write_row)`` で返す。

転記先に存在しない行は ``(read_row, None)`` として返す。新規行の追加が
必要かどうかは利用者が ``if write_row is None: ...`` で判定する。
書き込みは ``apply_mapping(read_row, write_row)`` を中心に行い、
必要な列だけを ``write_row[write_col] = read_row[read_col]`` の形で
個別に上書きする。 結果は ``result()`` で取り出す。

#### `matched_rows`

```text
def matched_rows(self) -> Iterator[tuple[Row, Row]]:
```

##### 説明

両方に存在する行だけを ``(read_row, write_row)`` で返す。

転記先に存在しない行（``destination`` が ``None``）は含まない。

#### `unmatched`

```text
def unmatched(self) -> UnmatchedRows:
```

##### 説明

突合しなかった行を ``UnmatchedRows`` で返す。

``only_in_read`` は write に対応が無い read 行（追加候補）。
``Table`` として返すので ``.read()`` / ``.filter()`` などの Table 標準の
インターフェースが使える。 戻り値は ``Table.read()`` と同じく **read 行の
コピー** で、書き換えても ``read`` にも ``result()`` にも影響しない。

``only_in_write`` は read に対応が無い write 行（破棄候補）。
戻り値は ``matched_rows()`` が返す ``write_row`` と同じく **作業 Table の
実体行**。 ``write_row["備考"] = "破棄予定"`` のように書き換えると
``result()`` の戻り値へ反映される。

空キー (``None`` / ``""``) の行も両側に含む。 キーが空なので照合に使えず、
必ず対応が無いため。

``transfer_rows()`` / ``matched_rows()`` を呼ばずに呼んでも動く。

#### `apply_mapping`

```text
def apply_mapping(self, read_row: Row, write_row: Row | None) -> None:
```

##### 説明

コンストラクタで渡された ``mapping`` どおりに値を ``write_row`` へコピーする。

mapping の read 列 / write 列は ``__init__`` で存在を検証済みなので、
ここで再びキー存在を確かめない。 ``write_row`` が ``None`` の場合
（``transfer_rows()`` の ``(read_row, None)`` をそのまま渡した場合など）は
転記先の行が無いので ``TransferDestinationMissingError`` で停止する。

入力 ``read`` / ``write`` には触れない。書き込みは Transfer 内部の
作業 Table に紐づいた ``write_row`` に対して行う。

Args:
    read_row: 転記元の行。
    write_row: 転記先の行。 ``matched_rows()`` の戻り値か、
        ``transfer_rows()`` の戻り値で ``None`` でないもの。

Raises:
    TransferDestinationMissingError: ``write_row`` が ``None`` のとき。

#### `result`

```text
def result(self) -> Table:
```

##### 説明

変更後の Table を返す。

``transfer_rows()`` / ``matched_rows()`` のイテレーション中に ``write_row``
に対して行った変更が反映された作業用 Table を返す。 イテレータを 1 度も
進めないうちに ``result()`` を呼ぶと ``write`` のコピー（変更なし）が返る。

``result()`` は同じ作業 Table インスタンスを返し続けるので、
``result().append(...)`` のように破壊的に加工した場合や、 ``result()`` を
呼んだ後に ``unmatched().only_in_write`` の ``write_row`` を書き換えた場合も、
後続の ``result().read()`` 呼び出しに反映される（``Table._iter_rows_for_update``
経由で実体 dict を共有しているため）。

Example:
    transfer = Transfer(source, destination, mapping,
                        read_key="顧客ID", write_key="顧客ID")
    for source_row, destination_row in transfer.matched_rows():
        transfer.apply_mapping(source_row, destination_row)
    final_table = transfer.result()  # 変更後の Table


## `from comken.toolbox.access import ...`

### `AccessDatabase`

```text
class AccessDatabase(FileBase):
```

#### 説明

Access データベースを COM で操作する。

既定ではネットワーク越しの遅延・排他・破損を避けるため、一時フォルダへコピーして開く。
コピー上の変更は元ファイルへ反映されない。元データベースを更新するマクロを実行する場合は
``local_copy=False`` を指定する。この場合は開く前に日時付きバックアップを作り、
既定で7日間残す。バックアップは成功後も削除せず、自動では書き戻さない。
復旧時は内容を確認した人が手でコピーする（自動復旧は正常なデータを古い控えで
上書きする危険があるため）。
バックアップ先は既定で元データベースと同じフォルダの ``backup``。
数百 MB 以上のデータベースでは、ネットワーク越しのコピーに時間がかかる。
``backup_dir`` にローカルフォルダを指定すれば速くなるが、顧客情報がローカルに
残ることを理解したうえで指定する。元データベースと同じ場所に控えを置くため、
サーバー障害や誤削除では一緒に失われる。本格的な世代保全はサーバー側の
バックアップに依存する。OneDrive などの同期フォルダでは控えも同期され、
容量と帯域を消費する。

数十万件を CSV に出す場合は、Python にデータを載せない ``export_csv()`` を使う。
``read_rows()`` は逐次処理用であり、結果を ``list`` にすると全件分のメモリを消費する。

#### `__init__`

```text
def __init__(self, path: str | Path, local_copy: bool=True, backup: bool | None=None, backup_days: int=DEFAULT_BACKUP_DAYS, backup_dir: str | Path | None=None) -> None:
```

#### `run_macro`

```text
@measure
def run_macro(self, name: str) -> None:
```

##### 説明

Access マクロを実行する。

元データベースを更新するマクロの場合は、初期化時に ``local_copy=False`` を指定する。
VBA のプロシージャ／関数を実行する場合は ``run_function()`` を使う。

#### `run_function`

```text
@measure
def run_function(self, name: str, *args: object) -> object | None:
```

##### 説明

VBA のプロシージャ／関数を実行する。

元データベースを更新する処理の場合は、初期化時に ``local_copy=False`` を指定する。
Access のマクロは別の仕組みなので、マクロには ``run_macro()`` を使う。
dry-run 時は実行せず ``None`` を返す。

#### `run_query`

```text
@measure
def run_query(self, name: str) -> None:
```

##### 説明

保存済みのアクションクエリを名前で実行する。

UPDATE・INSERT・DELETE・テーブル作成など、データを変更するクエリ向け。
元データベースへ変更を反映する場合は、初期化時に ``local_copy=False`` を指定する。
SELECT クエリの結果を読む場合は ``read_rows()``、CSVへ出す場合は ``export_csv()`` を使う。

#### `export_csv`

```text
@measure
def export_csv(self, source: str, dst: str | Path, encoding: str=Encoding.CP932) -> None:
```

##### 説明

テーブルまたはクエリを Access から直接 CSV に書き出す。

数十万件でも Python のメモリにデータを載せない、大量件数向けの方法。

#### `read_rows`

```text
def read_rows(self, source: str) -> Iterator[dict[str, object]]:
```

##### 説明

テーブルまたはクエリを辞書で1行ずつ返すジェネレータ。

COM 往復を減らすため小さなバッチで取得する。数十万件を ``list`` にすると
メモリを大量に使うため、CSV が目的なら ``export_csv()`` を使う。

#### `table_names`

```text
def table_names(self) -> list[str]:
```

##### 説明

利用可能なテーブルと保存済みクエリの名前を返す。


## `from comken.toolbox.browser import ...`

### `Browsers`

```text
class Browsers:
```

#### 説明

複数サイト分のブラウザをまとめて起動・終了する。**with 文の中でだけ使える。**

どこで例外が出ても、起動済みのブラウザはすべて閉じる。
1つのブラウザの終了に失敗しても、残りの終了は続行される。

with を使わずに launch すると BrowsersNotStartedError になる（ブラウザは起動しない）。
with を必須にしているのは、途中で例外が出たときにブラウザのプロセスが残り、
次の実行でドライバーの更新まで邪魔するのを防ぐため。

**run_task() で始めた処理が終わらないと、with も終わらない。** ブラウザを閉じる前に
裏の処理の終了を待つため（操作の途中でブラウザが消えると原因が分かりにくいエラーになる）。
終わらない可能性がある処理には、その中で待ち時間の上限を設けること。

Attributes:
    names: 起動済みのセッション名（起動した順）。

#### `__init__`

```text
def __init__(self) -> None:
```

#### `launch`

```text
def launch(self, site: type[SiteBase], download_dir: str | Path | None=None) -> SiteBase:
```

##### 説明

サイトクラスを渡してブラウザを1つ起動する（推奨経路）。

サブクラスの NAME と OPTIONS を読んで、内部で `launch_session()` を
呼び出す。呼び出し側に「名前」と「オプション」を別々に書かせないことで、
取り違えが起きにくく、固有の値が1か所に集まる。

Args:
    site: 起動する SiteBase サブクラス。`NAME` が必須（空だと SiteConfigError）。
    download_dir: ダウンロード先。省略時は OPTIONS.DOWNLOAD_DIR/<NAME>、
                  それも未設定なら一時フォルダを作り、終了時に削除する。

Returns:
    起動済みの SiteBase インスタンス。`.session` で BrowserSession に繋がる。

Raises:
    SiteConfigError: サブクラスに NAME が設定されていない場合。
    SessionNameConflictError: 同じ NAME ですでに起動している場合。
    DriverStartError: ブラウザを起動できなかった場合。

#### `launch_session`

```text
@measure
def launch_session(self, name: str, options: type[BrowserOptions] | BrowserOptions | None=None, download_dir: str | Path | None=None) -> BrowserSession:
```

##### 説明

名前とオプションを直接渡してブラウザを1つ起動する（低レベル経路）。

`launch(SiteBase)` の中から呼ばれる雑務用。SiteBase サブクラスが用意できない
場面（テスト・一時的な検証）で使う。通常は `launch(SiteBase)` を使う。

ダウンロードフォルダとログイン状態はこの名前ごとに分かれる。
同じサイトへ2つのアカウントでログインしたい場合も、
「kintai_a」「kintai_b」と名前を分ければ混ざらない。

Args:
    name: セッション名。ログとエラーメッセージに出るので、
          「kintai」「keiri」のようにサイトが分かる名前にする。
    options: 起動オプション。BrowserOptions のサブクラスをそのまま渡せる
             （セッションごとに別インスタンスを作るので、設定が混ざらない）。
             省略時は BrowserOptions の初期値で起動する。
    download_dir: ダウンロード先。省略時は options.DOWNLOAD_DIR/<name>、
                  それも未設定なら一時フォルダを作り、終了時に削除する。

Returns:
    起動済みの BrowserSession。この with を抜けるまで使える。

Raises:
    SessionNameConflictError: 同じ名前ですでに起動している場合。
    DriverStartError: ブラウザを起動できなかった場合。

#### `run_task`

```text
def run_task(self, task: Callable[[], T], label: str='') -> BackgroundTask[T]:
```

##### 説明

処理を裏で始めて、すぐ次の行へ進む。結果は wait() で受け取る。

普通に書けば上から順に動く。時間のかかる処理を待っている間に
別のことを進めたいときだけ、これで先に始めておく:

    kintai = browsers.run_task(lambda: KintaiFlow(kintai).search())
    KeiriFlow(keiri).login(user, password)   # 勤怠の読み込み中にこちらが進む
    days = kintai.wait()                        # 戻って結果を受け取る

**裏で動かす処理と、その後に自分で書く処理で、同じセッションを触らないこと。**
同じセッションを同時に触ると ConcurrentSessionUseError で止まる
（黙って別の画面を操作するより、早く気づけるほうが安全なため）。

Args:
    task: 引数を取らない呼び出し可能オブジェクト。lambda で包んで渡す。
    label: 何の処理か。省略するとセッション名の代わりに連番が付く。
           ログとエラーメッセージに出るので、付けておくと原因を追いやすい。

Returns:
    結果を受け取るための取っ手。wait() で結果、is_done で終了確認ができる。

#### `parallel`

```text
def parallel(self, *tasks: Callable[[], T]) -> list[T]:
```

##### 説明

複数の処理を同時に始めて、全部終わるまで待ち、渡した順に結果を返す。

run_task() で始めて wait() で受け取るのを、まとめて書けるようにしたもの。
「全部同時に始めて、全部の結果が欲しい」だけならこちらが短い:

    # 逐次（上から順に動く）
    a = KintaiFlow(kintai).fetch()
    b = KeiriFlow(keiri).fetch()

    # 同時（同じ呼び出しを lambda で包む）
    a, b = browsers.parallel(
        lambda: KintaiFlow(kintai).fetch(),
        lambda: KeiriFlow(keiri).fetch(),
    )

受け取るタイミングを自分で決めたい場合は run_task() を使う。

1つの処理では1つのセッションだけを触ること。同じセッションを2つの処理から
触ると ConcurrentSessionUseError で止まる。

Args:
    *tasks: 引数を取らない呼び出し可能オブジェクト。

Returns:
    各処理の戻り値を、渡した順に並べたリスト。

Raises:
    Exception: いずれかの処理で発生した例外。複数失敗した場合は、
               すべてをログに出したうえで、引数の並び順で最初に失敗したものを送出する
               （時間的に最初に失敗したものとは限らない）。

#### `names`

```text
@property
def names(self) -> list[str]:
```

##### 説明

起動済みのセッション名（起動した順）。

### `BrowserSession`

```text
class BrowserSession:
```

#### 説明

1サイト分の Edge ブラウザ。with 文の中でだけ使える。

with を必須にしているのは、処理の途中で例外が出たときに
ブラウザのプロセスと一時フォルダを確実に片付けるため。
with を使わずに操作すると SessionNotStartedError になる。

ダウンロード先・ログイン状態・起動オプションはこのセッションが専有する。
他のセッションと混ざらないので、サイトごとに違う設定を安心して使える。

Attributes:
    name: セッション名。ログとエラーメッセージに出るので、
          「kintai」「keiri」のようにサイトが分かる名前にする。
    download_dir: このセッション専用のダウンロードフォルダ。
                  完了待ちは download_dir.wait() を使う。
    wait_seconds: 要素待機のタイムアウト秒数。Page がこれを引き継ぐ。

#### `__init__`

```text
def __init__(self, name: str, options: BrowserOptions, download_dir: DownloadDir, profile_dir: Path | None=None) -> None:
```

##### 説明

直接呼ばず、Browsers.launch() から作る。

Args:
    name: セッション名。
    options: 起動オプション。セッションごとに別インスタンスを渡すこと。
    download_dir: このセッション専用のダウンロードフォルダ。
    profile_dir: ログイン状態を残すフォルダ。None なら毎回まっさらな状態で起動する。

#### `open`

```text
@measure
def open(self, url: str) -> None:
```

##### 説明

URL を開く。

#### `refresh`

```text
def refresh(self) -> None:
```

##### 説明

今のページを再読み込みする。

#### `back`

```text
def back(self) -> None:
```

##### 説明

ブラウザの「戻る」。

#### `current_url`

```text
@property
def current_url(self) -> str:
```

##### 説明

今開いている URL。

#### `title`

```text
@property
def title(self) -> str:
```

##### 説明

今開いているページのタイトル。

#### `page_source`

```text
@property
def page_source(self) -> str:
```

##### 説明

今開いているページの HTML。

#### `save_screenshot`

```text
@measure
def save_screenshot(self, prefix: str='screenshot') -> Path:
```

##### 説明

今の画面を logs/ に PNG で保存し、そのパスを返す。

Args:
    prefix: ファイル名の先頭。保存先は logs/{prefix}_{セッション名}_{日時}.png。

Returns:
    保存したファイルのパス。

#### `popup_tab`

```text
@contextmanager
def popup_tab(self, timeout: int | None=None) -> Iterator[BrowserSession]:
```

##### 説明

別タブで開いた画面を操作し、抜けるときに閉じて元のタブへ戻る。

リンクの target="_blank" や帳票 PDF のように、こちらの意図と関係なく
タブが増える場面のためのもの。タブを開く操作を済ませてから with に入る:

    page.click(PDF_LINK)              # ここで別タブが開く
    with session.popup_tab():         # 開いたタブへ移る
        session.save_screenshot("pdf")
    # ← 別タブを閉じて、元のタブへ戻る（中で例外が出ても戻る）

Args:
    timeout: 新しいタブが開くのを待つ秒数。省略時は 10 秒。

Yields:
    自分自身。中では今までどおり session と Page をそのまま使える。

Raises:
    PopupTabNotOpenedError: 時間内に新しいタブが開かなかった場合。

#### `load_many`

```text
def load_many(self, urls: Sequence[str], ready: Locator | None=None, max_open: int=_DEFAULT_MAX_OPEN_TABS, timeout: int | None=None) -> Iterator[str]:
```

##### 説明

同じサイトの複数ページをまとめて開き、**読み込めたものから順に**返す。

レポート一覧のように、同じサイトの大量の URL を見て回るときに使う。
1件ずつ開いて待つと「読み込み時間 × 件数」かかるが、先に何枚か開いておくと
待ち時間がブラウザ側で重なるため、全体が大幅に短くなる
（1件2分・90件なら、逐次で3時間、10枚開けば20分台）。

ログインは1回で済む。同じブラウザの中でタブを開くだけなので、
Cookie も二要素認証の記憶も共有される。

    for url in sf.load_many(report_urls, ready=ReportPage.TABLE, max_open=10):
        rows = ReportPage(sf).rows()     # そのページのタブに切り替わっている
        save(url, rows)
    # ← 抜けると、開いたタブは全部閉じて元のタブへ戻る

Args:
    urls: 開く URL。渡した順に開くが、**返る順番は読み込みが終わった順**になる。
    ready: 読み込み完了とみなす目印の要素。省略すると HTML の読み込み完了で判断する。
           画面を描いてから中身を入れるサイト（Salesforce など）では、
           表やヘッダーなど「出たら中身がある」要素を指定すること。
    max_open: 同時に開いておくタブの数。増やすほど速くなるが、
              メモリとサイト側の負荷も増える。
    timeout: 1ページあたりの待ち時間の上限（秒）。省略時はセッションの設定。
             超えたページは諦めて次へ進み、警告ログに残す。

Yields:
    読み込みが終わった URL。yield されている間、そのページのタブに切り替わっており、
    Page のメソッドがそのまま使える。

Raises:
    SessionNotStartedError: with に入る前に呼んだ場合。
    ConcurrentSessionUseError: 他のスレッドが同じセッションを操作している場合。

#### `raw`

```text
@property
def raw(self) -> webdriver.Edge:
```

##### 説明

selenium の WebDriver そのもの。

このクラスと Page に用意されていない機能を使うときの逃げ道。
ここから switch_to でタブを移動すると、セッションが今どのタブにいるかを
見失うことがあるので、タブ操作は popup_tab() を使うこと。

ここから直接操作すると、同時操作の見張り（operating）を通らない。
parallel の中で使う場合、他のスレッドと衝突しないことは呼び出し側の責任になる。

### `SiteBase`

```text
class SiteBase:
```

#### 説明

1サイト分の入口。サイトごとにサブクラスを作って固有の値を置く。

サブクラスで NAME / BASE_URL / OPTIONS / OWNER を上書きする。`session` 以外の状態
（current_url や cookie など）は持たない — 同じサイトを2アカウントで並列に
開けるようにするため。

使い方は2つ:
  - `with Kintai() as kintai:` … 1サイトだけ。Browsers を内側で抱えて起動する
  - `with Browsers() as browsers: kintai = browsers.launch(Kintai)` … 複数サイト

Attributes:
    session: このサイトに紐づく BrowserSession。Page に渡して操作する。

#### `__init__`

```text
def __init__(self, session: BrowserSession | None=None) -> None:
```

#### `downloads`

```text
@property
def downloads(self) -> DownloadDir:
```

##### 説明

このサイトのダウンロード先。完了待ちに使う。

    files = kintai.downloads.wait()   # .crdownload が消えるまで待つ

Raises:
    SiteNotStartedError: まだ起動していない場合。

#### `to`

```text
def to(self, page_class: type[P]) -> P:
```

##### 説明

このサイトの画面へ移る。

画面クラスは動かすのにブラウザ（`BrowserSession`）を要るが、
**それを呼ぶ側に書かせない**ためのもの。

    def go_login(self) -> LoginPage:
        return self.to(LoginPage).go("/login")

**行き先の型を切り替えるだけで、ブラウザは動かさない。** 実際に動かすのは
`Page.go("/path")` かリンクのクリックで、それを `go_〇〇()` の中に隠す。
こうしておくと、その画面から行ける先が `go_〇〇()` の一覧になる。

`Page.to()` と同じ名前にそろえてある。サイトから最初の画面へ移るのも、
画面から次の画面へ移るのも、利用側から見れば同じ「移る」なので、
覚える言葉を増やさない。

`LoginPage(self.session)` と書いても同じだが、そう書くと
「セッションとは何か」を知らないとサイトクラスを書けなくなる。

Args:
    page_class: 作りたい画面クラス（`Page` のサブクラス）。

Returns:
    そのサイトのブラウザに紐づいた画面クラスのインスタンス。

#### `close`

```text
def close(self) -> None:
```

##### 説明

Browsers から渡されたセッションは触らず、自分で起動したブラウザだけ閉じる。

`with Kintai() as kintai:` で起動したインスタンスを `close()` しても安全。
ただし `Browsers.launch()` から持たせてもらったインスタンスでは何もしない
（持ち主の Browsers が with を抜けるときに閉じるため、二重に閉じない）。

### `BrowserOptions`

```text
class BrowserOptions:
```

#### 説明

Edge の起動オプション。サブクラスで必要な属性だけ上書きして使う。

bool 属性は True で有効・False で無効、str 属性は None で無効。

#### `build`

```text
def build(self, profile_dir: Path | None=None) -> list[str]:
```

##### 説明

有効なオプションを Edge の起動引数リストに変換する。

Args:
    profile_dir: ログイン状態を残すプロファイルフォルダ。
                 指定するとシークレットモードは自動的に外れる
                 （シークレットは Cookie を残さないため、永続化と両立しない）。

Returns:
    webdriver に渡す起動引数のリスト。

### `Page`

```text
class Page:
```

#### 説明

1画面ぶんの操作をまとめる基底クラス。画面ごとに継承して使う。

要素は見つかるまで自動で待つ。時間内に見つからない場合は
ElementNotFoundError になり、どのセレクターで失敗したかがメッセージに出る。

Attributes:
    session: この画面が乗っているブラウザ。遷移先の画面クラスを作るときに渡す。

#### `__init__`

```text
def __init__(self, session: BrowserSession, wait_seconds: int | None=None) -> None:
```

##### 説明

Args:
    session: Browsers.launch() で起動したセッション。
    wait_seconds: 要素待機のタイムアウト秒数。
                  省略時はセッションの設定（BrowserOptions.WAIT_SECONDS）を引き継ぐ。

#### `to`

```text
def to(self, page_class: type[P]) -> P:
```

##### 説明

遷移先の画面クラスを作る（同じブラウザを引き継ぐ）。

画面が変わるメソッドの最後で使う。

    def login(self, user_id: str, password: str) -> HomePage:
        self.click(self.LOGIN_BUTTON)
        return self.to(HomePage)

`HomePage(self.session)` と書いても同じだが、そう書くと画面クラスを
1つ足すたびに「セッションとは何か」が顔を出す。画面の遷移を書きたい
だけの人が、ブラウザの持ち方まで知らずに済むようにする。

#### `open`

```text
def open(self, url: str) -> Self:
```

##### 説明

URL を開き、自分自身を返す。

#### `save_screenshot`

```text
def save_screenshot(self, prefix: str='screenshot') -> Path:
```

##### 説明

今の画面を logs/ に PNG で保存し、そのパスを返す。

#### `click`

```text
def click(self, locator: Locator, index: int=0) -> None:
```

##### 説明

要素をクリックする。クリックできる状態になるまで待つ。

Args:
    locator: 対象のセレクター。
    index: 同じセレクターに複数の要素が一致する場合、何番目か（0始まり）。
           まずはセレクター側で1つに絞り込み、index は最後の手段にする。

#### `input`

```text
def input(self, locator: Locator, text: str) -> None:
```

##### 説明

入力欄に文字を入れる。もとの値は消える。

#### `read_text`

```text
def read_text(self, locator: Locator) -> str:
```

##### 説明

要素の表示文字を返す。

#### `read_texts`

```text
def read_texts(self, locator: Locator) -> list[str]:
```

##### 説明

一致する全要素の表示文字をリストで返す（一覧表の全行を読むときなど）。

#### `read_attribute`

```text
def read_attribute(self, locator: Locator, name: str) -> str | None:
```

##### 説明

要素の属性値を返す（href やチェック状態など）。属性が無ければ None。

Args:
    locator: 対象のセレクター。
    name: 属性名（例: "href", "value", "checked"）。

#### `select_text`

```text
def select_text(self, locator: Locator, text: str) -> None:
```

##### 説明

プルダウンを、表示されている文字で選ぶ。

#### `select_value`

```text
def select_value(self, locator: Locator, option_value: str) -> None:
```

##### 説明

プルダウンを、option の value 属性で選ぶ。

#### `select_index`

```text
def select_index(self, locator: Locator, index: int) -> None:
```

##### 説明

プルダウンを、上から何番目かで選ぶ（0始まり）。

#### `drag_drop`

```text
def drag_drop(self, source: Locator, target: Locator) -> None:
```

##### 説明

要素を別の要素までドラッグして落とす。

#### `scroll_to`

```text
def scroll_to(self, locator: Locator) -> None:
```

##### 説明

要素が画面に入るまでスクロールする。

#### `scroll_bottom`

```text
def scroll_bottom(self) -> None:
```

##### 説明

ページの一番下までスクロールする（続きを読み込ませるときなど）。

#### `has_element`

```text
def has_element(self, locator: Locator) -> bool:
```

##### 説明

要素が HTML 上に在るかを返す（待たずにその場で確認する）。

「在れば押す」のような分岐に使う。表示されているかどうかは見ない。

#### `count_elements`

```text
def count_elements(self, locator: Locator) -> int:
```

##### 説明

一致する要素の数を返す（待たずにその場で数える。無ければ 0）。

#### `wait_visible`

```text
def wait_visible(self, locator: Locator) -> None:
```

##### 説明

要素が表示されるまで待つ（画面が開くのを待つときなど）。

#### `wait_invisible`

```text
def wait_invisible(self, locator: Locator) -> None:
```

##### 説明

要素が消えるまで待つ（読み込み中の表示が消えるのを待つときなど）。

#### `alert_accept`

```text
def alert_accept(self) -> None:
```

##### 説明

ブラウザの確認ダイアログで OK を押す。出るまで待つ。

#### `alert_dismiss`

```text
def alert_dismiss(self) -> None:
```

##### 説明

ブラウザの確認ダイアログでキャンセルを押す。出るまで待つ。

#### `read_alert_text`

```text
def read_alert_text(self) -> str:
```

##### 説明

ブラウザの確認ダイアログの文言を返す。出るまで待つ。

#### `frame`

```text
@contextmanager
def frame(self, locator: Locator) -> Iterator[Page]:
```

##### 説明

iframe の中を操作し、抜けるときに元の画面へ戻る。

iframe の中の要素は、切り替えないと見つからない。
ElementNotFoundError が出て、HTML 上には要素があるのに掴めないときは
たいていこれが原因:

    with page.frame(page.CONTENT_FRAME):
        page.click(page.SAVE_BUTTON)
    # ← 元の画面へ戻る（中で例外が出ても戻る）

Yields:
    自分自身。中では今までどおりメソッドを呼べる。

#### `find_element`

```text
def find_element(self, locator: Locator) -> WebElement:
```

##### 説明

selenium の WebElement をそのまま返す。

このクラスに用意されていない操作をするときの逃げ道。
よく使うものはこのクラスにメソッドとして足すこと。

#### `find_elements`

```text
def find_elements(self, locator: Locator) -> list[WebElement]:
```

##### 説明

一致する全要素を WebElement のリストで返す。1件見つかるまで待つ。

一覧表の行を1行ずつ処理するときに使う。行の中をさらに探すときは、
行の WebElement から find_element(*Locator) で絞り込む:

    for row in page.find_elements(page.ROWS):
        if "未提出" in row.text:
            row.find_element(*page.EDIT_BUTTON).click()

まず値を読むだけなら read_texts() のほうが簡単で、
「何番目かをクリックする」だけなら click(locator, index=...) で足りる。

Args:
    locator: 対象のセレクター。

Returns:
    見つかった要素のリスト（画面に並んでいる順）。

Raises:
    ElementNotFoundError: 1件も見つからないまま待ち時間が過ぎた場合。
                          0件がありうる場面では、表そのものが出るのを wait_visible() で
                          待ってから count_elements() で件数を確認する。
                          count_elements() は待たないので、
                          読み込み前に呼ぶと「まだ出ていない」を「0件」と読み違える。

#### `execute_script`

```text
def execute_script(self, script: str, *args: object) -> object:
```

##### 説明

JavaScript を実行して戻り値を返す。

Args:
    script: 実行する JavaScript。
    *args: スクリプト内で arguments[0], arguments[1] ... として参照できる値。

### `SitePage`

```text
class SitePage(Page):
```

#### 説明

1つのサイト共通の画面クラス。サイトごとにこれを継承する。

BASE_URL とログインなど、そのサイトのどの画面でも使う処理をここに書く。
画面ごとのクラスは、さらにこれを継承する:

    Page          … ブラウザ操作（click / input / select ...）
      └ SitePage  … サイト共通（BASE_URL / ログイン / 共通ヘッダー）
          └ LoginPage / HomePage / ...   … 各画面

BASE_URL は次の順で解決する:
  1. 自身（または親クラス）に `BASE_URL` が定義されていればそれ
  2. 無ければ、`browsers.launch(SiteBase)` で起動した `SiteBase` の `BASE_URL`

#### `go`

```text
def go(self, path: str='') -> Self:
```

##### 説明

BASE_URL からの相対パスへ移動し、自分自身を返す。

Args:
    path: BASE_URL からの相対パス（例: "/login"）。省略時は BASE_URL を開く。

### `Locator`

```text
class Locator(NamedTuple):
```

#### 説明

セレクター（探し方 + 値）。Locator.id(...) 等のファクトリで作る。

セレクターの優先順位（CONVENTIONS.md と同じ）:
    1. Locator.id      … id 属性
    2. Locator.name    … name 属性
    3. Locator.css     … CSS セレクター
    4. Locator.xpath   … XPath（最終手段。絶対パスは使わない）

#### `id`

```text
@classmethod
def id(cls, value: str) -> Self:
```

##### 説明

id 属性で探す（例: Locator.id("login-btn")）。

#### `name`

```text
@classmethod
def name(cls, value: str) -> Self:
```

##### 説明

name 属性で探す（例: Locator.name("username")）。

#### `css`

```text
@classmethod
def css(cls, value: str) -> Self:
```

##### 説明

CSS セレクターで探す（例: Locator.css("table tr .name")）。

#### `xpath`

```text
@classmethod
def xpath(cls, value: str) -> Self:
```

##### 説明

XPath で探す（最終手段。例: Locator.xpath("//button[text()='検索']")）。

### `DownloadDir`

```text
class DownloadDir:
```

#### 説明

ブラウザダウンロード用のフォルダ。作成・完了待ち・後片付けをまとめて扱う。

通常は Browsers.launch() がセッションごとに1つ用意するので、自分で作る必要はない
（session.download_dir で受け取り、session.download_dir.wait() で完了を待つ）。

一時フォルダの場合、セッションの with を抜けた時点で自動削除される（消し忘れ防止）。
必要なファイルは with の中で移動しておくこと。
ダウンロードしたものを残したい場合は、起動時に保存先を指定する
（固定フォルダは with を抜けても削除されない）:

    with Browsers() as browsers:
        kintai = browsers.launch(Kintai, download_dir=r"C:\作業\downloads")
        files = kintai.session.download_dir.wait()
    # ← C:\作業\downloads とファイルはそのまま残る

wait() は作成時点で既にあったファイルを無視し、新しく増えたファイルだけを完了対象にする。

#### `__init__`

```text
def __init__(self, prefix: str='comken_dl_', path: str | Path | None=None) -> None:
```

##### 説明

Args:
    prefix: 一時フォルダ名のプレフィックス（path 指定時は使われない）。
    path: 使用するフォルダのパス。指定するとそのフォルダを使う（なければ作成）。
          省略時は一時フォルダを新規作成する。

#### `wait`

```text
@measure
def wait(self, timeout: int=30) -> list[Path]:
```

##### 説明

ダウンロードが完了するまで待機し、完了したファイルの一覧を返す。

Edge/Chrome はダウンロード中のファイルを ".crdownload" 拡張子で保存する。
この拡張子のファイルが消えたらダウンロード完了と判断する。
DownloadDir 作成時点で既にあったファイルは対象外
（固定フォルダに前回のファイルが残っていても誤検出しない）。

Args:
    timeout: タイムアウトまでの秒数（デフォルト: 30秒）。

Returns:
    新しくダウンロードされたファイルのパスリスト（更新日時順）。

Raises:
    DownloadTimeoutError: timeout 秒以内にダウンロードが完了しなかった場合。

#### `remove`

```text
def remove(self, force: bool=False) -> None:
```

##### 説明

フォルダごと削除する。ファイルを残したい場合は呼ばなくてよい。

誤削除防止のため、path で指定した固定フォルダは削除せず警告を出す
（自動作成した一時フォルダだけを削除する）。
固定フォルダも本当に削除したい場合は force=True を指定する。

Args:
    force: True にすると path 指定した固定フォルダも削除する。

### `BackgroundTask`

```text
class BackgroundTask(Generic[T]):
```

#### 説明

裏で動いている処理の取っ手。Browsers.run_task() が返す。

Attributes:
    label: 何の処理か。ログとエラーメッセージに出る。

#### `__init__`

```text
def __init__(self, future: Future[T], label: str) -> None:
```

##### 説明

直接呼ばず、Browsers.run_task() から作る。

#### `wait`

```text
def wait(self, timeout: float | None=None) -> T:
```

##### 説明

終わるのを待って、結果を返す。

すでに終わっていれば、待たずにすぐ返る。
中で例外が起きていた場合は、ここで送出される
（裏で起きた失敗が黙って消えないよう、必ず受け取る側で表に出す）。

Args:
    timeout: 待つ秒数の上限。省略すると終わるまで待つ。

Returns:
    渡した処理の戻り値。

Raises:
    TimeoutError: timeout 秒以内に終わらなかった場合。処理自体は動き続ける。
    Exception: 処理の中で起きた例外をそのまま送出する。

#### `is_collected`

```text
@property
def is_collected(self) -> bool:
```

##### 説明

wait() で結果や例外を受け取り済みなら True。

#### `is_done`

```text
@property
def is_done(self) -> bool:
```

##### 説明

終わっていれば True。まだ動いていれば False。

待たずに様子だけ見たいときに使う。
True になっていても、結果や例外を受け取るには wait() を呼ぶ。


## `from comken.toolbox.browser.sites import ...`

### `SITES`

公開定数。

### `SampleSite`

```text
class SampleSite(SiteBase):
```

#### 説明

the-internet.herokuapp.com 用の SiteBase。

#### `go_login`

```text
def go_login(self) -> LoginPage:
```

##### 説明

ログイン画面を開く。


## `from comken.toolbox.browser.sites.ouju_site import ...`

### `OujuBrowserOptions`

```text
class OujuBrowserOptions(BrowserOptions):
```

#### 説明

ouju_site 用のブラウザオプション。

デフォルト（BrowserOptions）から変更したいものだけ上書きする。
全オプションのデフォルト値は comken/toolbox/browser/options.py を参照。

### `OujuSite`

```text
class OujuSite(SiteBase):
```

#### 説明

ouju_site 雛形用の SiteBase。

URL や要素セレクタは example の値のまま。利用プロジェクト側で継承して書き換える。

#### `go_login`

```text
def go_login(self) -> LoginPage:
```

##### 説明

ログイン画面を開く。


## `from comken.toolbox.browser.sites.sample import ...`

### `SampleBrowserOptions`

```text
class SampleBrowserOptions(BrowserOptions):
```

#### 説明

サンプルサイト用のブラウザオプション。

デフォルト（BrowserOptions）から変更したいものだけ上書きする。
全オプションのデフォルト値は comken/toolbox/browser/options.py を参照。

### `SampleSite`

```text
class SampleSite(SiteBase):
```

#### 説明

the-internet.herokuapp.com 用の SiteBase。

#### `go_login`

```text
def go_login(self) -> LoginPage:
```

##### 説明

ログイン画面を開く。


## `from comken.toolbox.browser.sites.table_site import ...`

### `TableBrowserOptions`

```text
class TableBrowserOptions(BrowserOptions):
```

#### 説明

table_site 用のブラウザオプション。

デフォルト（BrowserOptions）から変更したいものだけ上書きする。
全オプションのデフォルト値は comken/toolbox/browser/options.py を参照。

### `TableSite`

```text
class TableSite(SiteBase):
```

#### 説明

table_site 雛形用の SiteBase。

URL や要素セレクタは example の値のまま。利用プロジェクト側で継承して書き換える。

#### `go_login`

```text
def go_login(self) -> LoginPage:
```

##### 説明

ログイン画面を開く。


## `from comken.toolbox.credentials import ...`

### `CREDENTIALS_PATH`

公開定数。

### `Credentials`

```text
class Credentials:
```

#### 説明

システム名配下の認証情報に、属性アクセスでまとめてアクセスする。

キー名「システム名_項目名」のシステム名部分だけを指定し、項目名は属性で取り出す。
システム名を config.ini から渡せば、本番用・テスト用アカウントの切り替えが
config.ini の1行だけで済む（コード側にキー名の直書きが残らない）。

使い方:
    cred = Credentials("site_a")
    cred.client_id      # → load_credential("site_a_client_id") と同じ
    cred.client_secret  # → load_credential("site_a_client_secret") と同じ

    # config.ini で本番・テストを切り替える場合
    # [CREDENTIALS]
    # SITE_A = site_a          ← site_a_test にすると全項目が切り替わる
    cred = Credentials(config.CREDENTIALS.SITE_A)

Raises:
    InvalidCredentialNameError: システム名に使えない文字が含まれている場合。
    CredentialNotFoundError: 属性に対応するキーが未登録の場合。
    CredentialDecryptionError: 別のユーザー・PC で登録されていて復号できない場合。

#### `__init__`

```text
def __init__(self, prefix: str, path: Path | None=None) -> None:
```

##### 説明

Args:
    prefix: キー名のシステム名部分（例: "site_a", "site_a_test"）。
    path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。

### `load_credential`

```text
@measure
def load_credential(name: str, path: Path | None=None) -> str:
```

#### 説明

保存済みの認証情報を復号して返す。

Args:
    name: 登録時に指定したキー名。
    path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。

Raises:
    CredentialNotFoundError: キー名が未登録の場合。
    CredentialDecryptionError: 別のユーザー・PC で登録されていて復号できない場合。

### `save_credential`

```text
@measure
def save_credential(name: str, value: str, path: Path | None=None) -> None:
```

#### 説明

認証情報を1件、暗号化して保存する。同じキー名は上書きされる。

Args:
    name: キー名（例: "site_a_client_secret"）。取得時のキーになる。
        半角英数字とアンダースコアのみ使用できる。
    value: 保存する値（client_secret・パスワード・トークンなど）。
    path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。

Raises:
    InvalidCredentialNameError: キー名に使えない文字が含まれている場合。
    CredentialDecryptionError: 既存ファイルを復号できない場合。

### `save_credentials`

```text
@measure
def save_credentials(items: dict[str, str], path: Path | None=None) -> None:
```

#### 説明

認証情報をまとめて暗号化して保存する。同じキー名は上書きされる。

1件ずつ save_credential() を呼ぶと、件数ぶん復号と暗号化を繰り返し、
途中で失敗すると一部だけ入った状態になる。まとめて渡せば書き込みは1回で、
「全部入るか、1つも入らないか」のどちらかになる。

Args:
    items: キー名と値の対応（例: {"site_a_client_id": "..."}）。
    path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。

Raises:
    InvalidCredentialNameError: キー名に使えない文字が含まれている場合。
    CredentialDecryptionError: 既存ファイルを復号できない場合。
    TypeError: 値が文字列でない場合（呼び出し側のバグ）。

### `delete_credential`

```text
@measure
def delete_credential(name: str, path: Path | None=None) -> None:
```

#### 説明

登録済みの認証情報を1件削除する。

Raises:
    CredentialNotFoundError: キー名が未登録の場合。
    CredentialDecryptionError: 既存ファイルを復号できない場合。

### `list_names`

```text
@measure
def list_names(path: Path | None=None) -> list[str]:
```

#### 説明

登録済みのキー名一覧を返す（値そのものは返さない）。

Raises:
    CredentialDecryptionError: 別のユーザー・PC で登録されていて復号できない場合。

### `import_json`

```text
@measure
def import_json(json_path: str | Path, path: Path | None=None) -> list[str]:
```

#### 説明

平文 JSON を読み、暗号化ファイルへ取り込む。

取り込みは「全部入るか、1つも入らないか」のどちらかになる。
途中のキーが不正なら、1件も書き込まずに例外を送出する。

Args:
    json_path: 読み込む平文 JSON のパス。
    path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。

Returns:
    取り込んだキー名のリスト（値は含まない）。

Raises:
    CredentialImportError: JSON が見つからない・壊れている・形式が違う場合。
    InvalidCredentialNameError: 展開したキー名に使えない文字が含まれている場合。
    CredentialDecryptionError: 既存ファイルを復号できない場合。


## `from comken.toolbox.csv import ...`

### `CSV`

```text
class CSV:
```

#### 説明

CSV ファイルを1つのデータ領域として読み書きする。

Table と同じ「行の集合」として Transfer へ渡せる境界を提供する。
ヘッダーのないファイルは ``columns`` で列名を指定する。

#### `__init__`

```text
def __init__(self, source: str | Path, *, encoding: str=Encoding.AUTO, columns: list[str] | None=None, types: Mapping[str, Callable[[Any], Any]] | None=None, read_only: bool=False, dry_run: bool=False) -> None:
```

#### `read`

```text
@measure
def read(self) -> Table:
```

##### 説明

全行を読み、指定された列だけを変換したTableを返す。

#### `replace`

```text
def replace(self, rows: list[dict[str, Value]] | Table) -> None:
```

##### 説明

ファイルのデータ領域を全置換する。

#### `append`

```text
def append(self, rows: list[dict[str, Value]] | dict[str, Value] | Table) -> None:
```

##### 説明

行を保留中のTableへ追加する。確定はsaveまたはwith正常終了で行う。

#### `save`

```text
@measure
def save(self) -> None:
```

##### 説明

保留中のTableをCSVファイルへ保存する。

長い処理の途中で確定したいときに使う。``with`` を分けて閉じ開きすると、
共有サーバー上のファイルではロックや同期の問題を自分で作り出すことになるため、
この経路を残している。``save()`` の後は ``_pending = None`` を立て、
``with`` 終了時にもう一度書き込まないようにしている。

#### `count`

```text
def count(self) -> int:
```

##### 説明

データ行数を返す。


## `from comken.toolbox.excel import ...`

### `Excel`

```text
class Excel:
```

#### 説明

Excel ワークブックを開き、シート単位の操作を提供する。

#### `__init__`

```text
def __init__(self, source: str | Path, *, types: Mapping[str, Callable[[Any], Any]] | None=None, read_only: bool=False, local_copy: bool | None=None) -> None:
```

##### 説明

設定を保持する。**ブックは開かない**。

``with`` の中で ``__enter__`` が呼ばれたとき、はじめてブックを開く。
読み取り専用で開くか、書き込み用に開くかは引数 ``read_only`` で
切り替える。利用者がエンジンを選ぶ必要はない。通常操作はOpenPyXLを使い、
未計算の数式値の読取りとVBA実行だけ、一時的にExcel COMへ昇格する。
``local_copy=None`` の既定では、書き込み時にUNCパスのブックだけ
一時作業コピーを使う（読み取り専用では UNC でもコピーしない。保存が無いため
「作業中だけローカルを使い、保存時に元へ戻す」契約を適用する場面がない）。
``local_copy=True`` で強制、``local_copy=False`` で無効化でき、保存先は常に
元ファイルになる。

``read_only``、dry-run、またはwithブロックが例外で終わった場合は保存しない。

#### `sheet`

```text
def sheet(self, name: str | None=None) -> 'Sheet':
```

##### 説明

名前でシートを取得する。未存在の新規ブックでは最初のシートを改名する。

#### `find_sheet`

```text
def find_sheet(self, *candidates: str) -> str:
```

##### 説明

候補を順に試し、最初に見つかったシートの名前を返す。

「古いファイルと新しいファイルでシート名が違う」「テンプレ更新で
シート名が変わった」のように、**業務上よくある候補の違い**を 1 行で
吸収する。 ``Config`` 側で ``SHEET_NAME = [Sheet1, 一覧]`` のように
候補リストを持っておき、その順番に試したいときに使う。

戻り値は **シート名（``str``）**。``Sheet`` インスタンスが要るときは
戻ってきた名前を ``self.sheet(name)`` に渡す。

候補が全て見つからないときは、最後の試行の名前で ``SheetNotFoundError``
を送出する（メッセージにブックに実在するシート名一覧が入るので、
利用者が config を直せる）。 候補を 1 つも渡さなかったときも、
同じ例外（候補名が空文字・実在シート一覧入り）で止める。

``self.sheet(name)`` を経由せず ``sheetnames`` の所属判定で済ませる。
``sheet()`` は未存在の新規ブックで **自動でリネーム**する仕様なので、
候補違いのときに知らぬ間にブックが変わる事故を防ぐ。

#### `data_sheet`

```text
def data_sheet(self, name: str | None=None) -> 'Sheet':
```

##### 説明

データシートを取得する。名前を省略できるのは1枚のときだけ。

#### `create_data_sheet`

```text
def create_data_sheet(self, name: str) -> 'Sheet':
```

##### 説明

指定名の空のデータシートを作成する。

#### `create_sheet`

```text
def create_sheet(self, name: str) -> 'Sheet':
```

##### 説明

指定名の空の表示用シートを作成する。

``create_data_sheet`` は ``PY_`` プレフィックスを補ってデータシート専用
にするのに対し、こちらは入力名をそのまま使い、表示用の自由配置として
読み書きする。書式や自由セル配置が要る帳票は ``create_sheet``、
構造化テーブルとして読み書きするなら ``create_data_sheet``。

#### `list_data_sheets`

```text
def list_data_sheets(self) -> list[str]:
```

##### 説明

データシート名をブック内の順序で返す。

#### `close`

```text
def close(self, *, save: bool=True) -> None:
```

##### 説明

ブックを閉じる。通常はwithの正常終了時に変更を自動保存する。

#### `save`

```text
@measure
def save(self) -> None:
```

##### 説明

変更を元ファイルへ保存する。

長い処理の途中で確定したいときに使う。``with`` を分けて閉じ開きすると、
共有サーバー上のファイルではロックや同期の問題を自分で作り出すことになるため、
この経路を残している。``save()`` の後に変更がなければ ``with`` 終了時に
再保存はしない（``_is_dirty`` で判定）。

#### `run_macro`

```text
@measure
def run_macro(self, macro_name: str) -> None:
```

##### 説明

Excel COMへ一時的に昇格してVBAマクロを実行する。

COMには元ファイルではなく作業ファイルを渡す。ローカルコピー利用時にも、
例外終了なら元ファイルを変更しないというwithの契約を守るためである。

#### `read_computed_rows`

```text
@measure
def read_computed_rows(self, sheet_name: str, min_row: int=2) -> list[tuple[Any, ...]]:
```

##### 説明

数式の計算結果を行単位で読む。未計算の数式がある場合だけCOMへ昇格する。

#### `read_computed_rows_as_dicts`

```text
def read_computed_rows_as_dicts(self, sheet_name: str, header_row: int=1) -> list[dict[str, Any]]:
```

##### 説明

見出し行をキーに計算結果を読む。未計算時だけCOMへ昇格する。

### `Sheet`

```text
class Sheet:
```

#### 説明

Excel シートのデータ領域または表示領域を操作する。

#### `__init__`

```text
def __init__(self, excel: 'Excel', worksheet: Worksheet) -> None:
```

#### `is_data_sheet`

```text
@property
def is_data_sheet(self) -> bool:
```

##### 説明

プレフィックス付きのデータシートか返す。

#### `table`

```text
def table(self, name: str | None=None) -> ExcelTable:
```

##### 説明

データシート全体を扱うテーブルを返す。

#### `create_table`

```text
def create_table(self, name: str, table: 'Table', start_cell: str='A1') -> ExcelTable:
```

##### 説明

Python管理用の実テーブルを新規作成する。

``start_cell`` は見出しの左上セルです。作成直後の Table はメモリ上の
現在値で、Excel ファイルへの保存は Excel の save/with 契約で後から行います。

#### `write_value`

```text
def write_value(self, cell: str, value: Any) -> None:
```

##### 説明

セルへ値を書き込む。

#### `read_value`

```text
def read_value(self, cell: str, *, force_com: bool=False) -> Any:
```

##### 説明

セルの値を読む。数式は計算結果を返す。

ブックは ``data_only`` 以外の状態で開くため、メモリ上の ``cell.value`` は
数式セルでは ``"=SUM(A1:A3)"`` という文字列になる。``read_value`` は
数式セルでは保存済み計算値（無ければ COM で再計算）を返す。
``force_com=True`` でキャッシュを無視して Excel 実機で強制再計算させる。

#### `read_formula`

```text
def read_formula(self, cell: str) -> str:
```

##### 説明

セルの数式を読む。数式でなければ空文字を返す。

``read_value`` は計算結果を返すため、もう数式の判定には使えない。
ワークシートの生の値を直接見る。

#### `write_range`

```text
def write_range(self, cell_range: str, values: list[list[Any]]) -> None:
```

##### 説明

指定範囲へ二次元の値を書き込む。

#### `read_range`

```text
def read_range(self, cell_range: str, *, force_com: bool=False) -> list[dict[str, Any]]:
```

##### 説明

指定範囲の先頭行を見出しとして辞書のリストで読む。

数式セルがある範囲では保存済み計算値、無ければ COM で再計算した値を返す。
``force_com=True`` でキャッシュを無視して Excel 実機で強制再計算させる。

#### `get_used_range`

```text
def get_used_range(self) -> tuple[str, str]:
```

##### 説明

使用範囲の左上と右下のセル参照を返す。

#### `set_row_height`

```text
def set_row_height(self, row: int, height: float) -> None:
```

##### 説明

行の高さを設定する。

#### `set_column_width`

```text
def set_column_width(self, col: str, width: float) -> None:
```

##### 説明

列の幅を設定する。

#### `hide_row`

```text
def hide_row(self, row: int) -> None:
```

##### 説明

指定した行を非表示にする。

行の表示設定はデータ表の内容ではなく画面レイアウトなので、データシート
ではなく表示シートに限定している。

#### `show_row`

```text
def show_row(self, row: int) -> None:
```

##### 説明

指定した行の非表示を解除する。

#### `hide_column`

```text
def hide_column(self, col: str) -> None:
```

##### 説明

指定した列を非表示にする。

#### `show_column`

```text
def show_column(self, col: str) -> None:
```

##### 説明

指定した列の非表示を解除する。

#### `insert_row`

```text
def insert_row(self, row: int) -> None:
```

##### 説明

指定位置に表示用の行を挿入する。

#### `delete_row`

```text
def delete_row(self, row: int) -> None:
```

##### 説明

指定位置の表示用の行を削除する。

#### `insert_column`

```text
def insert_column(self, col: str) -> None:
```

##### 説明

指定位置に表示用の列を挿入する。

#### `delete_column`

```text
def delete_column(self, col: str) -> None:
```

##### 説明

指定位置の表示用の列を削除する。

#### `format`

```text
def format(self, cell: str, *, bold: bool | None=None, italic: bool | None=None, size: int | None=None, name: str | None=None, color: str | None=None, number_format: str | None=None) -> None:
```

##### 説明

セルのフォントと表示形式を設定する。

渡した引数だけ反映し、``None`` の項目は既存の値を変えない。**指定しない
項目がリセットされることはない**ので、``bold`` だけ書き換えるつもりで
``size`` が初期値に戻る、といった事故が起きない。

Args:
    cell: 対象のセル参照 (例: ``"A1"``)。
    bold: ``True`` で太字、``False`` で解除、``None`` で変更しない。
    italic: イタリック。``True`` / ``False`` / ``None``。
    size: フォントサイズ。``None`` のとき変更しない。
    name: フォント名。``None`` のとき変更しない。
    color: 16進数 6 桁の色 (``#`` 付きでも可)。``None`` のとき変更しない。
    number_format: セルの表示形式 (例: ``"0.00"``)。``None`` のとき変更しない。

Raises:
    TypeError: セル参照が不正な場合。

#### `set_background`

```text
def set_background(self, cell: str, color: str) -> None:
```

##### 説明

セルの背景色を設定する。

#### `set_border`

```text
def set_border(self, cell: str, *, style: BorderStyle='thin', color: str='000000') -> None:
```

##### 説明

セルの四辺に同じ境界線を設定する。

よく使う ``style``: ``"thin"`` / ``"medium"`` / ``"thick"`` /
``"dashed"`` / ``"double"``。全種類は ``BorderStyle`` 型を参照。

Args:
    cell: 対象のセル参照 (例: ``"A1"``)。
    style: 線の種類。 ``BorderStyle`` で定義したいずれかの値。
    color: 16進数 6 桁の色 (``#`` 付きでも可)。既定は ``"000000"``。

Raises:
    ValueError: ``style`` が ``BorderStyle`` のいずれにも該当しない
        (openpyxl の検証による)。

#### `merge_cells`

```text
def merge_cells(self, cell_range: str) -> None:
```

##### 説明

指定範囲のセルを結合する。

#### `unmerge_cells`

```text
def unmerge_cells(self, cell_range: str) -> None:
```

##### 説明

指定範囲のセル結合を解除する。

#### `freeze_panes`

```text
def freeze_panes(self, cell: str) -> None:
```

##### 説明

指定セルより上・左の領域を固定表示する。

### `ExcelTable`

```text
class ExcelTable:
```

#### 説明

データシート全体を1つのテーブルとして操作する。

Sheet の表示操作と分けることで、表データの読み書きがレイアウト変更へ
意図せず影響されないようにしている。

#### `__init__`

```text
def __init__(self, excel: 'Excel', worksheet: Worksheet, name: str | None=None) -> None:
```

#### `read`

```text
def read(self, *, force_com: bool=False) -> Table:
```

##### 説明

Excelテーブルの実際の定義範囲だけを読み、値を返す。

シートの使用範囲ではなく Excel が保持する ``ref`` を使うため、表の外に
ある無関係なセルを現在の Table に混ぜません。数式の計算結果が
保存されていない場合だけ内部でCOMへ切り替えます。``force_com=True``
はキャッシュを信頼できないブックをExcel実機で強制再計算します。

#### `replace`

```text
def replace(self, rows: list[dict[str, Value]] | Table, *, allow_formula_overwrite: bool=False) -> None:
```

##### 説明

データシート全体を置き換える。

既存データ部に人が入れた数式があると、既定では ``TableFormulaOverwriteError``
で止める。数式を値で潰すと依存セルや集計式が壊れたことに遅れて気づくため。
意図的に上書きしてよいときだけ ``allow_formula_overwrite=True`` を渡す。

渡された ``Table`` が **既存の数式列を含まない** 場合、その列はそのまま
保持される。行が増えたぶんは、既存の数式を
``openpyxl.formula.translate.Translator`` で下方向へずらして埋める。
行が減ったぶんは、数式セルの値を消す。

見出しの列は **既存の見出しと名前で対応付ける**。既存の見出しに無い
列名が含まれていた場合は ``TableColumnMismatchError``。

#### `append`

```text
def append(self, rows: list[dict[str, Value]] | dict[str, Value] | Table, *, allow_formula_overwrite: bool=False) -> None:
```

##### 説明

Table、1行、または行リストを既存テーブルの末尾へ追加する。

既存テーブルに数式列があっても、その列は保持される。渡された行に
数式列が含まれている場合は ``TableFormulaOverwriteError``
（``allow_formula_overwrite=True`` で上書き可能）。

#### `count`

```text
def count(self) -> int:
```

##### 説明

データ行数を返す。


## `from comken.toolbox.holidays import ...`

### `BusinessDayNotFoundError`

```text
class BusinessDayNotFoundError(HolidayCalendarError):
```

#### 説明

営業日が見つからなかった

月の途中で「指定した月の営業日数を超える n 番目」を求めたとき、
その月に営業日が 1 日も無いとき、祝日データ欠落などで 400 日探索しても
次の営業日にたどり着けなかったときに送る。
いずれも「カレンダー側がおかしい」または「指定値が暦と合わない」場合に
起き、業務ロジック側のミスではないので、呼び出し側で握り潰さずユーザーに
顕在化させる必要がある。

発生箇所: comken.core.holidays.calendar の HolidayCalendar
    - nth_business_day_of_month（n が月の営業日数超え、または n < 1）
    - first_business_day_of_month / last_business_day_of_month
      （その月に営業日が 1 日も無い）
    - business_day_after / business_day_before /
      business_day_on_or_after / business_day_on_or_before
      （400 日の探索上限に達した）

対処:
    n をその月の営業日数以下に直す、対象月の祝日に過不足がないか
    確認する、社内管理表（会社休日）が広範囲に登録されていないか確認する

#### `__init__`

```text
def __init__(self, detail: str) -> None:
```

### `CabinetOfficeCSVSource`

```text
class CabinetOfficeCSVSource(HolidaySource, RefreshableHolidaySource):
```

#### 説明

内閣府の ``syukujitsu.csv`` をダウンロードして ``Holiday`` の iterable を返す。

初回 ``load()`` 時にキャッシュ（= 同梱 CSV）が無ければダウンロードし、
あればキャッシュを返す。``refresh()`` を呼ぶと TTL に関係なく強制再取得する。

**既定の保存先はライブラリ同梱の CSV**（``BUNDLED_CSV_PATH``）。
共有サーバーの **読み取り専用チェックアウト** で ``load()`` /
``refresh()`` を呼ぶと ``PermissionError`` で落ちる。
そのときは **開発機で取得 → コミット → 共有サーバーへ checkout** で
配布する（年 1 回の手動更新）。

Args:
    url: 内閣府の CSV の URL。既定は ``syukujitsu.csv`` の配布 URL。
    cache_path: ダウンロードした CSV の保存先。既定は ``BUNDLED_CSV_PATH``
        （= ``comken/core/holidays/data/syukujitsu.csv``）。PC ごとの
        キャッシュは廃止したので、通常は変更しない。
    encoding: CSV の文字コード。CP932（Shift_JIS）のままで良い。
    fetch_timeout_seconds: requests.get() のタイムアウト秒数。
    refresh_timeout_seconds: refresh() で使う短いタイムアウト秒数（業務フロー停止を防ぐ）。

#### `__init__`

```text
def __init__(self, url: str=DEFAULT_URL, cache_path: Path | str | None=None, *, encoding: str='cp932', fetch_timeout_seconds: float=30.0, refresh_timeout_seconds: float=0.5) -> None:
```

#### `load`

```text
@measure
def load(self) -> list[Holiday]:
```

##### 説明

キャッシュがあればそれを、無ければダウンロードして ``Holiday`` を返す。

Returns:
    内閣府の祝日を日付順に並べた ``Holiday`` のリスト。

Raises:
    HolidayCalendarFetchError: ダウンロードもキャッシュも読めない場合。
        共有サーバーの読み取り専用チェックアウトで ``cache_path``
        （既定は同梱 CSV）への書き込みに失敗したときもここに来る。

#### `refresh`

```text
@measure
def refresh(self) -> list[Holiday]:
```

##### 説明

TTL を無視して内閣府から強制再取得する（業務フローを止めない短時間タイムアウト）。

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

### `ComputedHolidaySource`

```text
class ComputedHolidaySource(HolidaySource):
```

#### 説明

計算で祝日の和集合を返すソース。

``HolidaySource`` Protocol を実装する。``load()`` で ``Iterable[Holiday]`` を返す。
``CabinetOfficeCSVSource`` と並列に置いて、
``from_sources([Cabinet, Computed])`` のように和集合で運用する
（``HolidayCalendar`` 側の先勝ち WARNING ログが衝突をハンドリングする）。

このソースは **純粋計算のみ** — 外部通信・ファイル読み込みは一切しない。
社内 BO 環境（オフライン・pip 制限）でもそのまま動く。

Args:
    from_year: 対象範囲の開始年。省略時は ``DEFAULT_FROM_YEAR`` (1948)。
    to_year: 対象範囲の終了年。省略時は ``DEFAULT_TO_YEAR`` (2099)。
        範囲外でも祝日計算は走るが、春分／秋分の近似精度が下がる旨を
        WARNING ログで知らせる。

#### `__init__`

```text
def __init__(self, *, from_year: int | None=None, to_year: int | None=None) -> None:
```

#### `load`

```text
def load(self) -> list[Holiday]:
```

##### 説明

対象年の範囲について計算した祝日をまとめて返す。

Returns:
    日付順に並んだ ``Holiday`` のリスト。

### `EXPIRING_WARNING_DAYS`

公開定数。

### `Holiday`

```text
class Holiday:
```

#### 説明

祝日の1件。日付と名称だけを運ぶシンプルな箱。

Attributes:
    date: 祝日の日付（時刻・タイムゾーンは持たない業務日付）。
    name: 祝日の日本語名称（例: "建国記念の日"）。
    approximate: ``True`` なら、計算式など内閣府発表と ±1 日前後する
        可能性がある値。``HolidayCalendar.is_holiday`` などで該当 Holiday
        を返したときに WARNING ログを出して、業務フローを止めずに気づける
        ようにする。デフォルトは ``False``（内閣府 CSV 由来または確実な
        計算結果）。

### `HolidayCalendar`

```text
class HolidayCalendar:
```

#### 説明

祝日を保持し、営業日判定を行うカレンダー本体。

同じ日付に複数の祝日が登録された場合は**先勝ち**で採用する
（内閣府 CSV と会社の年末年始休暇など、複数 source の重複は珍しくない）。
名称が違う祝日が同じ日に重なっても黙って先を採用する。

期限切れの警告（``EXPIRING_WARNING_DAYS`` を切った日）は **同じ日に
1回だけ**出す。同じ日に ``is_business_day`` が何回呼ばれても
ログが埋もれないため。

#### `__init__`

```text
def __init__(self, holidays: Iterable[Holiday]) -> None:
```

##### 説明

``Holiday`` の iterable から ``{日付: Holiday}`` の索引を作る。

Args:
    holidays: 祝日の iterable。同じ日付が複数含まれていたら先勝ちで採用。

#### `from_csv`

```text
@classmethod
def from_csv(cls, path: str | Path, *, encoding: str='cp932') -> 'HolidayCalendar':
```

##### 説明

内閣府の ``syukujitsu.csv`` を直接読む最短ルート。

Args:
    path: CSV のパス。CP932（Shift_JIS）固定。
    encoding: 文字コード。通常は ``cp932`` のままで良い。

Returns:
    読み込み結果から作った ``HolidayCalendar``。

#### `from_sources`

```text
@classmethod
def from_sources(cls, sources: Iterable[HolidaySource]) -> 'HolidayCalendar':
```

##### 説明

複数の ``HolidaySource`` を合体させる（内閣府 + Computed + 会社休日 など）。

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

#### `is_holiday`

```text
def is_holiday(self, target: _dt.date) -> bool:
```

##### 説明

``target`` が祝日（または休日）なら ``True``。

ターゲットが今年/来年なら、内閣府 source への強制再取得を試みる
（今年中に 1 回だけ。失敗時はサイレント）。
計算式由来の暫定値（``approximate=True``）を返すときは WARNING ログ。

#### `holidays_in`

```text
def holidays_in(self, start: _dt.date, end: _dt.date) -> list[Holiday]:
```

##### 説明

``start <= 日付 <= end`` の範囲に入る祝日を、日付順に返す。

Args:
    start: 範囲開始（含む）。
    end: 範囲終了（含む）。

Returns:
    範囲内の ``Holiday`` を日付昇順で並べたリスト。
    該当が無ければ空リスト。

#### `expires_after`

```text
def expires_after(self, target: _dt.date) -> bool:
```

##### 説明

``target`` が収録済み最終日以降（＝「収録期限を過ぎた」）なら ``True``。

「収録済み最終日 <= target」を期限切れとみなす。等号を含めるのは、
「収録最終日ぴったり」を「期限の境目」として扱うため（最終日当日は
収録済みの祝日として判定できるが、それ以降は収録外）。

#### `days_until_expiry`

```text
def days_until_expiry(self, today: _dt.date) -> int:
```

##### 説明

``today`` から収録最終日までの日数。最終日を過ぎていれば負の値。

Args:
    today: 「今日」とみなす日付。

Returns:
    ``last_known - today`` の日数差。収録済み祝日が無いと ``-1``。

#### `last_known_date`

```text
def last_known_date(self) -> _dt.date | None:
```

##### 説明

収録済み祝日のうち最も新しい日付。無ければ ``None``。

#### `holiday_names`

```text
def holiday_names(self, target: _dt.date) -> Sequence[str]:
```

##### 説明

``target`` に登録された祝日名称のタプル（同日が複数あれば複数要素）。

#### `all_holidays`

```text
def all_holidays(self) -> list[Holiday]:
```

##### 説明

保持している祝日を日付順に並べたリストを返す。

### `HolidayCalendarError`

```text
class HolidayCalendarError(ComkenError):
```

#### 説明

祝日カレンダーに関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `HolidayCalendarFetchError`

```text
class HolidayCalendarFetchError(HolidayCalendarError):
```

#### 説明

内閣府の祝日 CSV を取得できない

オフライン環境・社内ネットワークの制約・内閣府サイトの保守などの理由で
ダウンロードが失敗する。**ただしキャッシュが残っている場合は警告ログのみで動く**
（cached フラグで運用側が検知できる）。

発生箇所: comken.toolbox.holidays.sources.cabinet_office の CabinetOfficeCSVSource

対処:
    ネットワーク接続と社内プロキシの設定を確認する。
    それでも直らない場合は、保存済みのキャッシュで当面動かすか、
    管理表（Excel）に会社休日を登録して代用する

#### `__init__`

```text
def __init__(self, url: str, reason: str) -> None:
```

### `HolidayCalendarFormatError`

```text
class HolidayCalendarFormatError(HolidayCalendarSourceError):
```

#### 説明

内閣府 CSV 以外のファイルや壊れたファイルを内閣府 CSV として読み込もうとした

発生箇所: comken.core.holidays.csv_source の load_cabinet_office_csv

対処:
    内閣府の syukujitsu.csv を直接取得し直す。文字コードは CP932 (Shift_JIS)

#### `__init__`

```text
def __init__(self, path: Path | str, detail: str) -> None:
```

### `HolidayCalendarSourceError`

```text
class HolidayCalendarSourceError(HolidayCalendarError):
```

#### 説明

祝日データの読み取りに失敗した

内閣府の CSV 形式が変わった・社内管理表のシート名が違う・列が無い・
文字化けしたなどの理由で、祝日を 1件も抽出できない場合に上げる。

発生箇所: comken.core.holidays の csv_source

対処:
    内閣府の CSV の場合: 内閣府の仕様変更。管理者へ連絡する

#### `__init__`

```text
def __init__(self, source: str, reason: str) -> None:
```

### `HolidaySource`

```text
class HolidaySource(Protocol):
```

#### 説明

祝日を 1セット取り出せる仕組みの共通インタフェース。

内閣府の ``CabinetOfficeCSVSource`` や ``ComputedHolidaySource`` / 会社の
``CompanyHolidaySource`` の両方がこれを実装するため、利用側は入手経路を
意識せずに ``from_sources`` に渡せる。

この Protocol はメソッドの型を ``Iterable[Holiday]`` に固定する。
``load()`` を呼んだその瞬間に取得が走る（キャッシュは実装側で持つ）のが
一貫していて読みやすい。実装が iterable を返したい場合は
中で ``list()`` してから返してもよい。

#### `load`

```text
def load(self) -> Iterable[Holiday]:
```

##### 説明

祝日セットを取り出して ``Iterable[Holiday]`` で返す。

### `RefreshableHolidaySource`

```text
class RefreshableHolidaySource(Protocol):
```

#### 説明

TTL を無視して強制再取得できる祝日 source（例: 内閣府の ``CabinetOfficeCSVSource``）。

``HolidayCalendar`` がターゲットが今年/来年のときに内閣府への
再取得を試みるためのフック。短いタイムアウト（既定 0.5 秒）で実装する。
必須ではなく、管理表など再取得が要らない source は実装しなくてよい。

#### `refresh`

```text
def refresh(self) -> Iterable[Holiday]:
```

##### 説明

TTL を無視して強制再取得する。

### `add_business_days`

```text
def add_business_days(target: _dt.date, n: int, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` から ``n`` 営業日後の日付（``n`` が負なら前）。``calendar`` 省略可。

### `business_day_after`

```text
def business_day_after(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` より後で最初の営業日（``target`` 自身を含まない）。

``calendar=None`` のときは**既定カレンダー**を使う。

### `business_day_before`

```text
def business_day_before(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` より前で最初の営業日（``target`` 自身を含まない）。

``calendar=None`` のときは**既定カレンダー**を使う。

### `business_day_on_or_after`

```text
def business_day_on_or_after(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` 以降で最初の営業日（``target`` を含む）。``calendar`` 省略可。

### `business_day_on_or_before`

```text
def business_day_on_or_before(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` 以前で最初の営業日（``target`` を含む）。``calendar`` 省略可。

### `first_business_day_of_month`

```text
def first_business_day_of_month(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` が属する月の最初の営業日。``calendar`` 省略可。

### `is_business_day`

```text
def is_business_day(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> bool:
```

#### 説明

``target`` が営業日なら ``True``。``calendar`` を省略できる簡易判定。

``calendar=None`` のときは**既定カレンダー**（``default_calendar()``）を使う。
アプリ側で ``set_default_calendar()`` を呼んでおけば、利用者は
``HolidayCalendar`` を組み立てなくても「今日が営業日か」を判定できる。

``calendar`` をキーワード専用にして、呼び出し側がうっかり位置引数で
日付とカレンダーを取り違える事故を防ぐ。

### `last_business_day_of_month`

```text
def last_business_day_of_month(target: _dt.date, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` が属する月の最後の営業日。``calendar`` 省略可。

### `load_cabinet_office_csv`

```text
@measure
def load_cabinet_office_csv(path: str | Path, *, encoding: str=DEFAULT_ENCODING) -> list[Holiday]:
```

#### 説明

内閣府の syukujitsu.csv を読み取り、祝日のリストを返す。

Args:
    path: CSV ファイルのパス。存在しない・読めない場合は ``HolidayCalendarFormatError``。
    encoding: CSV の文字コード。既定は ``cp932``（内閣府の配布形式）。

Returns:
    日付順に並んだ ``Holiday`` のリスト。

Raises:
    HolidayCalendarFormatError: ファイルが無い、壊れている、
        ヘッダーが内閣府のものではない、日付が解釈できないなどの理由で
        1件も抽出できなかった場合。

### `nth_business_day_of_month`

```text
def nth_business_day_of_month(target: _dt.date, n: int, *, calendar: HolidayCalendar | None=None, skip_weekends: bool=True) -> _dt.date:
```

#### 説明

``target`` が属する月の第 ``n`` 営業日（``n`` は 1 始まり）。``calendar`` 省略可。


## `from comken.toolbox.outlook import ...`

### `Outlook`

```text
class Outlook:
```

#### 説明

Classic Outlook を COM で操作する。

New Outlook は COM を持たないため利用できない。``read_messages()`` はメールの値を
読むだけで、既読・未読の状態を変更しない。送信機能は提供せず、確認可能な下書き
の作成だけを行う。

#### `__init__`

```text
def __init__(self) -> None:
```

#### `read_messages`

```text
def read_messages(self, subject_contains: str='', days: int=7, folder: str='') -> Iterator[MailMessage]:
```

##### 説明

受信メールを新しい順に逐次返す。既読・未読の状態は変更しない。

#### `save_draft`

```text
@measure
def save_draft(self, to: str | Sequence[str], subject: str, body: str, attachments: Sequence[str | Path] | None=None, cc: str | Sequence[str]='') -> None:
```

##### 説明

メールを送信せず、利用者が確認する下書きとして保存する。

### `MailMessage`

```text
class MailMessage:
```

#### 説明

受信メールから読み取った、変更されない値のセット。


## `from comken.toolbox.salesforce import ...`

### `SalesforceBase`

定義を解決できませんでした。

### `ReportAPI`

```text
class ReportAPI:
```

#### 説明

レポートを実行して明細行を取得する。

`SalesforceBase` が `report` 属性として持っている。単体では作らない。

    with Sandbox() as sf:
        rows = sf.report.run("00O000000000001")

#### `__init__`

```text
def __init__(self, client: SalesforceBase) -> None:
```

##### 説明

Args:
    client: このレポート API を使う Salesforce クライアント。

#### `run`

```text
@measure
def run(self, report_id: str, filters: list[dict] | None=None, allow_truncated: bool=False) -> list[dict]:
```

##### 説明

レポートを同期実行して明細行を返す（上限 2000 行）。

Args:
    report_id: レポート ID（レポートを開いたときの URL の末尾。15桁 or 18桁）。
    filters: 絞り込み条件（省略可）。レポート定義の条件を実行時に上書きする。
        例: [{"column": "CREATED_DATE",
              "operator": "greaterThan", "value": "2026-01-01"}]
    allow_truncated: True にすると、2000 行で切り捨てられても例外にせず
        警告ログだけを出して、取れた分を返す。**既定は False**
        （欠けたデータで処理が進むのを防ぐため）。

Returns:
    [{"列の表示名": "値", ...}, ...] のリスト。

Raises:
    SalesforceReportTruncatedError: 上限で切り捨てられた場合
        （allow_truncated=True のときは送出しない）。
    SalesforceReportFormatError: 明細（TABULAR）形式でない場合。

#### `run_async`

```text
@measure
def run_async(self, report_id: str, filters: list[dict] | None=None, allow_truncated: bool=False) -> list[dict]:
```

##### 説明

レポートを非同期実行して明細行を返す（**上限は同期と同じ 2000 行**）。

重いレポートで同期実行がタイムアウトするときに使う。
行数の上限は緩まないので、2000 行を超えるなら filters か SOQL で対処する。

Args:
    report_id: レポート ID。
    filters: 絞り込み条件（省略可）。
    allow_truncated: run() と同じ。

Raises:
    SalesforceReportTruncatedError: 上限で切り捨てられた場合。
    SalesforceReportFormatError: 明細（TABULAR）形式でない場合。
    SalesforceReportExecutionError: Salesforce 側で実行が失敗した場合。
    TimeoutError: 制限時間内に完了しなかった場合。

#### `describe`

```text
@measure
def describe(self, report_id: str) -> dict:
```

##### 説明

レポートを実行せず、定義（列・フィルタ・形式）を取得する。

`run()` / `run_async()` はどちらもレポートを**実行**するため 2000 行の
上限と実行枠を消費する。`describe` は実行しないので、上限・実行枠とも
気にせず何度でも叩ける。SOQL への移行を下書きするときの情報源として使う。

レスポンスは API の構造をそのまま返す（`run()` のように
`[{列名: 値}]` には畳まない）。用途が SOQL 化の下書きで、
必要な項目がまだ定まっていないため、API の返す構造をそのまま渡して
呼び出し側で必要な部分を取り出す方針にする。

Args:
    report_id: レポート ID。

Returns:
    パース済み dict。主要キーは次のとおり:

    - ``reportMetadata``: レポート定義本体
        - ``detailColumns``: 明細列（レポート用の名前。SOQL の
          フィールドパスとは1対1ではない）
        - ``reportFilters``: フィルタ条件
        - ``reportBooleanFilter``: フィルタの論理結合
        - ``reportFormat``: ``TABULAR`` / ``SUMMARY`` / ``MATRIX`` など
    - ``reportExtendedMetadata``: 列の表示名・ラベルなど
        - ``detailColumnInfo``: 各列の表示名

    API が dict 以外を返した場合（パース失敗時など）は空 dict。

Raises:
    SalesforceRequestError: 通信や認証に失敗した場合（`_client.request` 経由）。

### `ClientCredentialsAuth`

定義を解決できませんでした。

### `RefreshTokenAuth`

定義を解決できませんでした。

### `APIMetrics`

```text
class APIMetrics:
```

#### 説明

API 呼び出しの計測を貯める。

使い方:
    metrics = APIMetrics("sandbox")
    # …API を呼ぶ…
    metrics.log_summary()
    metrics.append_csv(Path("logs/salesforce_metrics.csv"))

#### `record_call`

```text
def record_call(self, component: str, elapsed_seconds: float, is_error: bool=False) -> None:
```

##### 説明

API 呼び出しを1件記録する。

#### `record_retry`

```text
def record_retry(self, component: str, reason: str) -> None:
```

##### 説明

リトライを1件記録する。reason は RetryReason の値を渡す。

#### `record_truncated_report`

```text
def record_truncated_report(self, report_id: str) -> None:
```

##### 説明

レポートが上限で切り捨てられたことを記録する。

止めずに続けた場合（allow_truncated=True）でも記録は残す。
あとから「どのレポートを SOQL へ移すか」を実測で決めるための材料になる。

#### `component_stats`

```text
def component_stats(self) -> dict[str, ComponentStat]:
```

##### 説明

呼び出し元別の集計を、読み取り用のコピーとして返す。

#### `retry_reason_counts`

```text
def retry_reason_counts(self) -> dict[str, int]:
```

##### 説明

リトライ理由別の回数を、読み取り用のコピーとして返す。

#### `update_api_usage`

```text
def update_api_usage(self, limit_info: str) -> None:
```

##### 説明

`Sforce-Limit-Info` ヘッダーの値から API 消費量を取り出して更新する。

Args:
    limit_info: "api-usage=1234/15000" の形式。
                解釈できない形式は無視する（計測のために本処理を止めない）。

#### `log_summary`

```text
def log_summary(self) -> None:
```

##### 説明

集計結果を INFO ログに出す。実行の最後に1回呼ぶ。

#### `append_csv`

```text
def append_csv(self, path: str | Path) -> None:
```

##### 説明

集計結果を CSV に1行ずつ追記する（呼び出し元ごとに1行）。

日ごとに追記していくと、API 消費量の推移と切り捨ての発生が追える。
ファイルが無ければ見出し行から作る。

### `APIUsage`

```text
class APIUsage:
```

#### 説明

組織の 24 時間 API 消費量（Sforce-Limit-Info ヘッダーの値）。

### `ComponentStat`

```text
class ComponentStat:
```

#### 説明

呼び出し元ごとの集計。

### `RetryReason`

```text
class RetryReason:
```

#### 説明

リトライの理由。どれが多いかで対処が変わるため区別して数える。

### `SalesforceCredentialRotator`

定義を解決できませんでした。


## `from comken.toolbox.salesforce.sites import ...`

### `SITES`

公開定数。

### `Sandbox`

```text
class Sandbox(SalesforceBase):
```

#### 説明

Sandbox 組織のクライアント。

使い方:
    with Sandbox() as sf:
        rows = sf.opportunities()

#### `opportunities`

```text
def opportunities(self) -> list[dict]:
```

##### 説明

案件一覧レポートの明細を返す。

2000 行を超えると SalesforceReportTruncatedError で止まる。
超えるようになったら、期間で区切るか SOQL へ移す。

### `Production`

```text
class Production(SalesforceBase):
```

#### 説明

Production 組織のクライアント。

使い方:
    with Production() as sf:
        rows = sf.opportunities()

#### `opportunities`

```text
def opportunities(self) -> list[dict]:
```

##### 説明

案件一覧レポートの明細を返す。

2000 行を超えると SalesforceReportTruncatedError で止まる。
超えるようになったら、期間で区切るか SOQL へ移す。

### `Developer`

```text
class Developer(SalesforceBase):
```

#### 説明

Developer 組織のクライアント。

使い方:
    with Developer() as sf:
        rows = sf.opportunities()

#### `opportunities`

```text
def opportunities(self) -> list[dict]:
```

##### 説明

案件一覧レポートの明細を返す。

2000 行を超えると SalesforceReportTruncatedError で止まる。
超えるようになったら、期間で区切るか SOQL へ移す。

### `site_for`

```text
def site_for(url: str) -> type[SalesforceBase]:
```

#### 説明

レポートの URL から、つなぐ組織のクラスを返す。

レポートの一覧表には**複数の組織の URL が混ざる**。どの組織のレポートかは
URL のドメイン（My Domain）で決まるので、表に行を足すだけで新しい組織の
レポートも取れるようにする。組織を人が選ぶ列を作ると、URL と食い違ったときに
別組織へ問い合わせて「レポートが見つからない」という分かりにくい失敗になる。

    site_for("https://example--sandbox.sandbox.my.salesforce.com/lightning/...")
    # → Sandbox

Args:
    url: レポートを開いたときのアドレス。**ドメインを含む URL であること**
        （レポート ID だけでは、どの組織のものか決められない）。

Raises:
    SalesforceSiteNotFoundError: 登録済みのどの組織にも当てはまらない場合。


## `from comken.toolbox.windows import ...`

### `ExcelCOMHandler`

```text
class ExcelCOMHandler(FileBase):
```

#### 説明

win32com を使った Excel 操作クラス。

openpyxl では対応できない以下の操作に使う:
    - 数式の計算結果を読む（CalculateFull で再計算してから取得）
    - VBA マクロを実行する
    - パスワード付きで保存する

#### `__init__`

```text
def __init__(self, path: str | Path, password: str='', headers: list[str] | None=None, local_copy_threshold_mb: float=10) -> None:
```

##### 説明

Args:
    path: Excel ファイルのパス。
    password: 読み取りパスワード（パスワード保護されたファイルを開く場合）。
    headers: ヘッダー行がない Excel の場合に、列名のリストをここで付ける。
             指定すると read_rows_as_dicts() は全行をデータとして読む。
    local_copy_threshold_mb: この MB 以上のファイルはローカルにコピーしてから開く。
        NAS やネットワークドライブのファイルが遅い・不安定な場合に有効。
        0 を指定するとローカルコピーを無効化できる
        （社内ルールでローカルコピーが禁止されている環境向け。
        Excel と挙動を揃えるためのオプトアウト）。
        マクロ起動が UNC / 共有サーバー上のファイルを参照する場合、
        コピー元では見つからないことがある。そのときは
        ``local_copy_threshold_mb=0`` を指定して元の場所で開く。

#### `read_cell`

```text
@measure
def read_cell(self, sheet_name: str, row: int, col: int | str) -> Any:
```

##### 説明

セルの値を返す（数式の計算結果）。

Args:
    sheet_name: シート名。
    row: 行番号（1始まり）。
    col: 列番号（1始まり）または列記号（"A" / "AA"）。

#### `write_cell`

```text
@measure
def write_cell(self, sheet_name: str, row: int, col: int | str, value) -> None:
```

##### 説明

セルに値を書き込む。

Args:
    sheet_name: シート名。
    row: 行番号（1始まり）。
    col: 列番号（1始まり）または列記号（"A" / "AA"）。
    value: 書き込む値。

#### `read_rows`

```text
@measure
def read_rows(self, sheet_name: str, min_row: int=2) -> list[tuple]:
```

##### 説明

指定シートの行データをタプルのリストで返す。

Args:
    sheet_name: シート名。
    min_row: 読み始める行番号（デフォルト: 2 でヘッダーをスキップ）。

Returns:
    各行を値のタプルにしたリスト。

#### `read_range`

```text
@measure
def read_range(self, sheet_name: str, min_col: int, min_row: int, max_col: int, max_row: int) -> list[tuple[Any, ...]]:
```

##### 説明

指定シートの矩形範囲だけを計算済みの値で返す。

#### `read_rows_as_dicts`

```text
@measure
def read_rows_as_dicts(self, sheet_name: str, header_row: int=1) -> list[dict]:
```

##### 説明

ヘッダー行をキーとした辞書のリストで返す。

ヘッダー行がないファイルは ExcelCOMHandler(path, headers=[...]) で列名を指定すること。

Args:
    sheet_name: シート名。
    header_row: ヘッダーが存在する行番号（デフォルト: 1）。
                __init__ で headers を指定した場合は無視される。

Returns:
    [{"列名": 値, ...}, ...] の形式のリスト。全セルが空の行は除外される。

Raises:
    ExcelError: ヘッダー行に空のセルがある場合（headers 未指定時のみ）、
                または headers の列数がシートの列数より少ない場合。

#### `count_non_empty_cells`

```text
@measure
def count_non_empty_cells(self, sheet_name: str, row: int) -> int:
```

##### 説明

指定行の空でないセル数を返す。

数式が入っていても "" を返すセルは空としてカウントされる。
行全体が空かどうかの判定（スキップ処理）に使う。

Args:
    sheet_name: シート名。
    row: 確認する行番号。

Returns:
    空でないセルの数。0 なら行全体が空。

#### `last_row`

```text
@measure
def last_row(self, sheet_name: str) -> int:
```

##### 説明

データが存在する最終行の行番号を返す。

UsedRange を使うため、数式が入ったセルも含めて正確に最終行を取得できる。

Args:
    sheet_name: シート名。

Returns:
    最終行の行番号（1始まり）。

#### `run_macro`

```text
@measure
def run_macro(self, macro_name: str) -> None:
```

##### 説明

VBA マクロを実行する。

Args:
    macro_name: 実行するマクロ名。"モジュール名.プロシージャ名" の形式で指定する。
                例: "Module1.UpdateData"

#### `save`

```text
@measure
def save(self) -> None:
```

##### 説明

元のファイルに上書き保存する。

NAS 上のファイルをローカルコピーして開いている場合も、保存先は元のファイル
（一時コピーに保存すると close() でコピーごと消えるため）。
動作は Excel.save() と同じ考え方（開いた場所ではなく、元の場所へ保存）。
close() は保存せずに閉じる（SaveChanges=False）ため、
write_cell での変更を残す場合は必ず呼ぶこと。

Raises:
    FileFormatMismatchError: 保存先の拡張子がワークブックの形式と食い違う場合。

#### `save_as`

```text
@measure
def save_as(self, path: str | Path, read_pw: str='', write_pw: str='', file_format: int | None=None) -> None:
```

##### 説明

ファイルを別名で保存する。パスワードを設定できる。

Args:
    path: 保存先のパス。
    read_pw: 読み取りパスワード（省略可）。
    write_pw: 書き込みパスワード（省略可）。
    file_format: FileFormat 定数（例: FileFormat.CSV）。
                 省略すると元ファイルと同じ形式で保存する。

Raises:
    ExcelError: 保存先の拡張子が元ファイルの形式と食い違う場合
                （file_format 未指定時のみ）。

#### `close`

```text
@measure
def close(self) -> None:
```

##### 説明

Excel を閉じる。with 文を使う場合は自動で呼ばれる。

Close が失敗しても Quit は必ず実行する（Excel プロセスを残さないため）。
2回呼んでも安全。

### `WindowHandler`

```text
class WindowHandler:
```

#### 説明

ウィンドウの検索・操作クラス。

タイトルでウィンドウを検索し、前面に表示する。

#### `__init__`

```text
def __init__(self, title: str) -> None:
```

##### 説明

Args:
    title: 検索するウィンドウのタイトル（完全一致）。

Raises:
    WindowNotFoundError: ウィンドウが見つからない場合。

#### `activate`

```text
@measure
def activate(self) -> None:
```

##### 説明

ウィンドウを前面に表示する。最小化されている場合は復元する。

#### `get_title`

```text
@measure
def get_title(self) -> str:
```

##### 説明

ウィンドウのタイトルを返す。

### `RegistryHandler`

```text
class RegistryHandler:
```

#### 説明

レジストリ値の読み取りクラス。with 文で確実にキーを閉じる。

#### `__init__`

```text
def __init__(self, hive: int, key_path: str) -> None:
```

##### 説明

Args:
    hive: レジストリのルートキー（例: win32con.HKEY_CURRENT_USER）。
    key_path: キーのパス（例: r"Software\MyApp"）。

#### `read`

```text
@measure
def read(self, value_name: str) -> str:
```

##### 説明

レジストリ値を読み取る。

Args:
    value_name: 読み取る値の名前。

Returns:
    レジストリ値の文字列。

#### `close`

```text
@measure
def close(self) -> None:
```

##### 説明

レジストリキーを閉じる。with 文を使う場合は自動で呼ばれる。

### `Paths`

```text
class Paths:
```

#### 説明

よく使うフォルダのパスを返すユーティリティ。インスタンス化せず静的メソッドで使う。

Desktop / Downloads は OneDrive の「既知のフォルダーの移動」で
C:\Users\xxx 直下にないことがあるため、レジストリから実際の場所を取得する。

**結果のキャッシュ**: ``downloads()`` / ``desktop()`` は **モジュールレベル**
で1度だけレジストリを引き、 以降は同じ ``Path`` を返す。 フォルダの場所は
プロセスが生きている間に変わらないので、 ループ内で ``Paths.downloads()``
が N 回呼ばれてもレジストリ I/O は最初の一度だけ。 テストで挙動を
入れ替えるときは内部関数 ``_reset_cached_shell_folders()`` を呼ぶ。

#### `downloads`

```text
@staticmethod
def downloads() -> Path:
```

##### 説明

ダウンロードフォルダのパスを返す（レジストリ解決、結果はキャッシュ）。

#### `desktop`

```text
@staticmethod
def desktop() -> Path:
```

##### 説明

デスクトップのパスを返す（OneDrive リダイレクトにも追従する、結果はキャッシュ）。

#### `temp_dir`

```text
@staticmethod
def temp_dir() -> Path:
```

##### 説明

システムの一時フォルダのパスを返す。

``tempfile.gettempdir()`` 自体が **プロセス内で1度だけ解決して
キャッシュ** しているので、ここではそれをそのまま ``Path`` に包むだけ。
標準ライブラリ側のキャッシュに乗せてもらっているので、 ラッパ側で
さらにキャッシュする必要は無い。

### `is_excel_running`

```text
@measure
def is_excel_running() -> bool:
```

#### 説明

EXCEL.EXE プロセスが存在するか返す。

画面に見えない孤立プロセスも、ユーザーが開いている Excel も区別せず検出する。

### `kill_excel`

```text
@measure
def kill_excel() -> bool:
```

#### 説明

すべての EXCEL.EXE プロセスを強制終了する。

※ ユーザーが開いている Excel も終了する（未保存の変更は失われる）。
  人が作業する PC では実行前に確認するか、is_excel_running() の警告に留めること。
  無人実行の PC で自動処理の開始前に呼ぶのが主な用途。

Returns:
    True: 終了に成功した。False: 起動していなかった、または終了に失敗した。


## `from comken.constants import ...`

### `Encoding`

```text
class Encoding:
```

#### 説明

CSV の encoding 引数に使う定数。

### `Color`

```text
class Color:
```

#### 説明

Excel でよく使う色の定数（RGB 16進値）。

### `FileFormat`

```text
class FileFormat:
```

#### 説明

Workbook.SaveAs に渡す Excel の保存形式定数。
