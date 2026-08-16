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

#### `__init__`

```text
def __init__(self, path: str | Path='config.ini') -> None:
```

##### 説明

Args:
    path: config.ini のパス。省略するとカレントディレクトリの config.ini を読む。

#### `mapping`

```text
def mapping(self, section: str) -> dict[str, str]:
```

##### 説明

マッピングセクションを列名が書かれたままの辞書で返す。

Args:
    section: `MAPPING` で終わるセクション名。

Returns:
    転記元の列名をキー、転記先の列名を値とする辞書。

Raises:
    ConfigSectionNotFoundError: 指定したマッピングセクションがない場合。

### `config`

定義を解決できませんでした。

### `debug`

```text
@contextmanager
def debug(enabled: bool=True) -> Iterator[None]:
```

#### 説明

ブロック内だけデバッグモードを指定した状態にする。

有効にすると、ライブラリの主要処理（Excel 読み込み・転記・保存、CSV 読み書き、
zip 等）の所要時間が DEBUG ログに記録される。どこが遅いかの調査に使う。

Args:
    enabled: True で有効（デフォルト）。False ならブロック内だけ無効。

### `dry_run`

```text
@contextmanager
def dry_run(enabled: bool=True) -> Iterator[None]:
```

#### 説明

ブロック内だけ dry-run モードを指定した状態にする。

有効にすると、外部に影響する操作を実行せず、何をするはずだったかを
INFO ログ（[DRY-RUN] プレフィックス付き）に出す。本番実行前の動作確認に使う。

対象の操作:
    - move_file / copy_file（ファイルの移動・コピー）
    - ExcelWriter.save / CsvWriter の書き込み
    - State.set（state.ini の書き込み）

読み取り（CSV・Excel の読み込み、SOQL クエリ等）は通常どおり実行される。

Args:
    enabled: True で有効（デフォルト）。False ならブロック内だけ無効。
             外側が dry-run 中でも、このブロックでは通常どおり書き込む。

### `is_debug`

```text
def is_debug() -> bool:
```

#### 説明

デバッグモードが有効か返す。

### `is_dry_run`

```text
def is_dry_run() -> bool:
```

#### 説明

dry-run モードが有効か返す。

### `setup_logging`

```text
def setup_logging(to_file: bool=True) -> None:
```

#### 説明

単体実行向けに、コンソールと日付別ファイルへのログ出力を設定する。

社内 RPA 基盤がログを設定する実行では呼び出す必要はない。すでに root logger に
ハンドラがある場合は、既存の出力先・書式・レベルを変更せず、そのまま返る。

Args:
    to_file: True なら ``logs/YYYY-MM-DD.log`` にも UTF-8 で出力する。


## `from comken.core import ...`

### `DateNameBuilder`

```text
class DateNameBuilder:
```

#### 説明

今日の日付を付けたファイル名を組み立てる。

日付はファイル名の属性ではなく「付け方」なので、コンストラクタではなく
prefix() / suffix() の呼び出し時に決める。

#### `__init__`

```text
def __init__(self, name: str, ext: str='.xlsx') -> None:
```

##### 説明

Args:
    name: ファイル名（拡張子なし）。
    ext: 拡張子（デフォルト: ".xlsx"）。ドットなしで渡しても補完される。

#### `plain`

```text
def plain(self) -> str:
```

##### 説明

日付なしのファイル名を返す。

#### `prefix`

```text
def prefix(self, date_format: str='%Y%m%d') -> str:
```

##### 説明

今日の日付を前に付けたファイル名を返す（例: 20260711_売上レポート.xlsx）。

#### `suffix`

```text
def suffix(self, date_format: str='%Y%m%d') -> str:
```

##### 説明

今日の日付を後ろに付けたファイル名を返す（例: 売上レポート_20260711.xlsx）。

### `DiffResult`

```text
class DiffResult:
```

#### 説明

diff_rows の結果。

### `FileFinder`

```text
class FileFinder:
```

#### 説明

フォルダからファイルを探して取得する。

見つからないときは既定で FileNotFoundError を投げる
（業務スクリプトでは「ファイルがない＝処理を止める」がほとんどのため）。
処理を続けたい場合は required=False を指定すると None または空リストを返す。

#### `__init__`

```text
def __init__(self, folder: str | Path) -> None:
```

#### `today`

```text
def today(self, pattern: str='*.xlsx', date_format: str='%Y%m%d', required: bool=True) -> Path | None:
```

##### 説明

ファイル名に今日の日付を含むファイルを返す。

複数ある場合は更新日時が最も新しいもの。年月で探すなら date_format="%Y%m"。

Raises:
    FileNotFoundError: required=True で該当ファイルがない場合。

#### `latest`

```text
def latest(self, pattern: str='*.xlsx', by: str=SortBy.NAME, required: bool=True) -> Path | None:
```

##### 説明

最新のファイルを返す。既定はファイル名の辞書順で最後のもの。

"20260711_売上.xlsx" のような日付プレフィックス命名を想定しており、
コピーや再保存で更新日時が変わっても影響を受けない。

注意: 文字列比較のため、ゼロ埋めしていない連番（report_9 と report_10）は
9 の方が「最新」と判定される。連番命名なら by=SortBy.UPDATED を使うこと。

Raises:
    FileNotFoundError: required=True で該当ファイルがない場合。
    ValueError: by に SortBy.NAME / SortBy.UPDATED 以外を指定した場合。

#### `dated`

```text
def dated(self, pattern: str='*.xlsx', required: bool=True) -> list[Path]:
```

##### 説明

ファイル名に日付が入っているファイルを、日付の新しい順で返す。

日付として認識するのは 20260729 / 2026-07-29 / 2026_07_29 / 2026.07.29。
実在しない日付や、前後を数字で挟まれた数字（伝票番号の一部など）は対象外。
同じ日付なら更新日時の新しい順。詳しくは date_in_name を参照。

Raises:
    FileNotFoundError: required=True で該当ファイルがない場合。

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
    path: state.ini のパス。省略すると実行フォルダ直下の state.ini。

#### `__init__`

```text
def __init__(self, path: str | Path='state.ini') -> None:
```

#### `get`

```text
def get(self, key: str, default: StateValue | None=None) -> StateValue | None:
```

##### 説明

保存済みの値を返す。無い場合は default を返す。

#### `set`

```text
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

### `copy_file`

```text
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

ファイル名に含まれる最初の日付を返す。日付が無ければ None。

1つのファイル名に日付が複数あるときは、先に出てくる方を使う。
ファイル名の日付とファイル内容の日付を突き合わせる業務で使うため公開している。

### `diff_row`

```text
def diff_row(before: dict, after: dict) -> dict[str, tuple]:
```

#### 説明

1行同士を比較し、値が異なる列だけを {列名: (変更前, 変更後)} で返す。

CSV の str と Excel の数値は同一視する（"1000" と 1000 は差分にならない）。
片方にしか存在しない列は、もう片方を None として比較する。

先頭ゼロ付きの文字列（社員番号 "0001" 等）は数値化しない。
"0001" と 1 は別の値として差分になる（先頭ゼロの消失を検出できる）。
Args:
    before: 変更前の行（辞書）。
    after: 変更後の行（辞書）。

Returns:
    {列名: (変更前の値, 変更後の値)} の辞書。値は元の型のまま返す。

### `diff_rows`

```text
def diff_rows(before: list[dict], after: list[dict], key: str) -> DiffResult:
```

#### 説明

2つのデータセットをキー列で突合し、差分を返す。

CSV と Excel をまたいだ比較にも使える（"1000" と 1000 は同一視される）。
キーが重複する場合は後の行が優先される。
Args:
    before: 変更前のデータ（辞書のリスト）。
    after: 変更後のデータ（辞書のリスト）。
    key: 行を一意に識別するキー列名。

Returns:
    DiffResult（added / removed / changed）。

Raises:
    ColumnNotFoundError: key で指定した列が存在しない場合。

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

デバッグモード時だけ処理時間を DEBUG ログに出すデコレータ。

ライブラリの主要処理に付いており、with comken.debug(): の範囲では
「どの処理に何秒かかったか」を DEBUG ログに出す。
プロジェクト側の関数に付けてもよい。

Timer との使い分け:
    - Timer: 常にログに出したい・経過秒数を値として使いたい場合
    - measure: 普段は出さず、調査のときだけ with debug(): で出したい場合

### `move_file`

```text
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

### `normalize`

```text
def normalize(text: str) -> str:
```

#### 説明

文字列を NFKC 形式に正規化する。

主な変換:
    - 全角英数字・記号 → 半角（ａ→a, １→1, （→(, ．→.）
    - 半角カタカナ     → 全角カタカナ（ｱ→ア, ｶﾞ→ガ）
    - 合字             → 展開（㌔→km, ㍉→mm）

Args:
    text: 正規化する文字列。

Returns:
    正規化後の文字列。

### `now`

```text
def now() -> datetime.datetime:
```

#### 説明

タイムゾーン付きの現在時刻（この PC のローカル時刻）を返す。

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
    on: リトライ対象の例外のタプル（デフォルト: すべての例外）。
        ここに含まれない例外は即座にそのまま出る。

Raises:
    最後の実行で出た例外（times 回すべて失敗した場合）。

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

### `wait`

```text
class wait:
```

#### 説明

待機ユーティリティ。インスタンス化せず静的メソッドで使う。

#### `seconds`

```text
@staticmethod
def seconds(n: float) -> None:
```

##### 説明

指定した秒数だけ待つ。

Args:
    n: 待機秒数。小数も指定できる（例: 0.5）。

#### `minutes`

```text
@staticmethod
def minutes(n: float) -> None:
```

##### 説明

指定した分数だけ待つ。

Args:
    n: 待機分数。小数も指定できる（例: 0.5 → 30秒）。

#### `until`

```text
@staticmethod
def until(condition: Callable[[], bool], timeout: float=60, interval: float=1.0) -> bool:
```

##### 説明

条件が True になるまで繰り返し確認する。

Args:
    condition: 引数なしで呼び出せる callable。True を返したら待機終了。
    timeout: 最大待機秒数（デフォルト: 60秒）。
    interval: 確認間隔（秒）（デフォルト: 1秒）。

Returns:
    True: 条件が満たされた。
    False: タイムアウトした（条件は満たされなかった）。

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

### `FileFinder`

```text
class FileFinder:
```

#### 説明

フォルダからファイルを探して取得する。

見つからないときは既定で FileNotFoundError を投げる
（業務スクリプトでは「ファイルがない＝処理を止める」がほとんどのため）。
処理を続けたい場合は required=False を指定すると None または空リストを返す。

#### `__init__`

```text
def __init__(self, folder: str | Path) -> None:
```

#### `today`

```text
def today(self, pattern: str='*.xlsx', date_format: str='%Y%m%d', required: bool=True) -> Path | None:
```

##### 説明

ファイル名に今日の日付を含むファイルを返す。

複数ある場合は更新日時が最も新しいもの。年月で探すなら date_format="%Y%m"。

Raises:
    FileNotFoundError: required=True で該当ファイルがない場合。

#### `latest`

```text
def latest(self, pattern: str='*.xlsx', by: str=SortBy.NAME, required: bool=True) -> Path | None:
```

##### 説明

最新のファイルを返す。既定はファイル名の辞書順で最後のもの。

"20260711_売上.xlsx" のような日付プレフィックス命名を想定しており、
コピーや再保存で更新日時が変わっても影響を受けない。

注意: 文字列比較のため、ゼロ埋めしていない連番（report_9 と report_10）は
9 の方が「最新」と判定される。連番命名なら by=SortBy.UPDATED を使うこと。

Raises:
    FileNotFoundError: required=True で該当ファイルがない場合。
    ValueError: by に SortBy.NAME / SortBy.UPDATED 以外を指定した場合。

#### `dated`

```text
def dated(self, pattern: str='*.xlsx', required: bool=True) -> list[Path]:
```

##### 説明

ファイル名に日付が入っているファイルを、日付の新しい順で返す。

日付として認識するのは 20260729 / 2026-07-29 / 2026_07_29 / 2026.07.29。
実在しない日付や、前後を数字で挟まれた数字（伝票番号の一部など）は対象外。
同じ日付なら更新日時の新しい順。詳しくは date_in_name を参照。

Raises:
    FileNotFoundError: required=True で該当ファイルがない場合。

### `date_in_name`

```text
def date_in_name(name: str) -> datetime.date | None:
```

#### 説明

ファイル名に含まれる最初の日付を返す。日付が無ければ None。

1つのファイル名に日付が複数あるときは、先に出てくる方を使う。
ファイル名の日付とファイル内容の日付を突き合わせる業務で使うため公開している。

### `move_file`

```text
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

### `copy_file`

```text
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

### `DateNameBuilder`

```text
class DateNameBuilder:
```

#### 説明

今日の日付を付けたファイル名を組み立てる。

日付はファイル名の属性ではなく「付け方」なので、コンストラクタではなく
prefix() / suffix() の呼び出し時に決める。

#### `__init__`

```text
def __init__(self, name: str, ext: str='.xlsx') -> None:
```

##### 説明

Args:
    name: ファイル名（拡張子なし）。
    ext: 拡張子（デフォルト: ".xlsx"）。ドットなしで渡しても補完される。

#### `plain`

```text
def plain(self) -> str:
```

##### 説明

日付なしのファイル名を返す。

#### `prefix`

```text
def prefix(self, date_format: str='%Y%m%d') -> str:
```

##### 説明

今日の日付を前に付けたファイル名を返す（例: 20260711_売上レポート.xlsx）。

#### `suffix`

```text
def suffix(self, date_format: str='%Y%m%d') -> str:
```

##### 説明

今日の日付を後ろに付けたファイル名を返す（例: 売上レポート_20260711.xlsx）。


## `from comken.core.files.naming import ...`

### `DateNameBuilder`

```text
class DateNameBuilder:
```

#### 説明

今日の日付を付けたファイル名を組み立てる。

日付はファイル名の属性ではなく「付け方」なので、コンストラクタではなく
prefix() / suffix() の呼び出し時に決める。

#### `__init__`

```text
def __init__(self, name: str, ext: str='.xlsx') -> None:
```

##### 説明

Args:
    name: ファイル名（拡張子なし）。
    ext: 拡張子（デフォルト: ".xlsx"）。ドットなしで渡しても補完される。

#### `plain`

```text
def plain(self) -> str:
```

##### 説明

日付なしのファイル名を返す。

#### `prefix`

```text
def prefix(self, date_format: str='%Y%m%d') -> str:
```

##### 説明

今日の日付を前に付けたファイル名を返す（例: 20260711_売上レポート.xlsx）。

#### `suffix`

```text
def suffix(self, date_format: str='%Y%m%d') -> str:
```

##### 説明

今日の日付を後ろに付けたファイル名を返す（例: 売上レポート_20260711.xlsx）。


## `from comken.exceptions import ...`

### `ComkenError`

```text
class ComkenError(Exception):
```

#### 説明

comken が出す固有エラー全体

対処:
    画面に表示された具体的なエラー名を上の表から探す

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

### `ExcelFileNotFoundError`

```text
class ExcelFileNotFoundError(ExcelError):
```

#### 説明

Excel ファイルが見つからない

発生箇所: ExcelBase.__init__()

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

発生箇所: comken.toolbox.windows の ExcelComHandler

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

発生箇所: ExcelBase._sheet() / ExcelComHandler._sheet()

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

### `LastSheetDeletionError`

```text
class LastSheetDeletionError(ExcelError):
```

#### 説明

ブックの最後のシートを削除しようとした

対処:
    先に別のシートを追加してから削除する

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

発生箇所: ExcelComHandler.run_macro()

対処:
    Excel をすべて閉じて再実行する。続く場合は管理者へ

#### `__init__`

```text
def __init__(self, name: str, detail: Exception) -> None:
```

### `RowTransferError`

```text
class RowTransferError(ExcelError):
```

#### 説明

Excel の行転記に失敗した

発生箇所: ExcelComHandler.transfer_by_mapping()

対処:
    表示された行番号のデータを確認する

#### `__init__`

```text
def __init__(self, row: int, detail: Exception) -> None:
```

### `EmptyHeaderCellError`

```text
class EmptyHeaderCellError(ExcelError):
```

#### 説明

Excel の見出しに空欄がある

発生箇所: ExcelBase.read_rows_as_dicts() / ExcelComHandler.read_rows_as_dicts()

対処:
    Excel の1行目の空欄を埋める

#### `__init__`

```text
def __init__(self, columns: list[int]) -> None:
```

### `ExcelHeadersTooFewError`

```text
class ExcelHeadersTooFewError(ExcelError):
```

#### 説明

指定した見出し数が列数より少ない

発生箇所: ExcelBase.read_rows_as_dicts() / ExcelComHandler.read_rows_as_dicts()

対処:
    管理者へ連絡する

#### `__init__`

```text
def __init__(self, expected: int, actual: int) -> None:
```

### `FileFormatMismatchError`

```text
class FileFormatMismatchError(ExcelError):
```

#### 説明

保存拡張子と形式が合わない

発生箇所: ExcelComHandler.save_as()

対処:
    管理者へ連絡する

#### `__init__`

```text
def __init__(self, suffix: str) -> None:
```

### `CsvError`

```text
class CsvError(ComkenError):
```

#### 説明

CSV に関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `EncodingDetectionError`

```text
class EncodingDetectionError(CsvError):
```

#### 説明

CSV の文字コードを判定できない

発生箇所: CsvReader._read_text()

対処:
    CSV の保存形式を確認し、管理者へ連絡する

#### `__init__`

```text
def __init__(self, path: Path | str) -> None:
```

### `CsvHeadersTooFewError`

```text
class CsvHeadersTooFewError(CsvError):
```

#### 説明

指定した見出し数が CSV の列数より少ない

発生箇所: CsvReader._load()

対処:
    管理者へ連絡する

#### `__init__`

```text
def __init__(self, expected: int, path: Path | str) -> None:
```

### `CsvNoDataRowsError`

```text
class CsvNoDataRowsError(CsvError):
```

#### 説明

CSV に見出し以外のデータ行がない

発生箇所: CsvReader.first()

対処:
    見出し行の下にデータが1行以上あるか確認する

#### `__init__`

```text
def __init__(self, path: Path | str) -> None:
```

### `CsvRowNotFoundError`

```text
class CsvRowNotFoundError(CsvError):
```

#### 説明

キーに一致する行が CSV に無い

発生箇所: CsvReader.find()

対処:
    探している値の書き方（前後の空白・全角半角・ゼロ埋め）を元データと見比べる

#### `__init__`

```text
def __init__(self, key_col: str, value: str, path: Path | str) -> None:
```

### `CsvRowDuplicateKeyError`

```text
class CsvRowDuplicateKeyError(CsvError):
```

#### 説明

キーにする列に同じ値が複数ある

発生箇所: CsvReader.index()

対処:
    表示された値の行を元データで確認し、重複を取り除く。重複が正しいデータなら管理者へ連絡する

#### `__init__`

```text
def __init__(self, key_col: str, duplicates: dict[str, int], path: Path | str) -> None:
```

### `CsvCellReferenceError`

```text
class CsvCellReferenceError(CsvError):
```

#### 説明

CSV のセル位置（例: A2）の指定が正しくない、または範囲外

発生箇所: CsvReader.cell()

対処:
    表示されたセル位置と、CSV の行数・列数を確認する

#### `__init__`

```text
def __init__(self, ref: str, path: Path | str, detail: str) -> None:
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

発生箇所: 利用側プロジェクトの列検証処理（現在 comken 内からは未送出）

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

### `CsvColumnNotFoundError`

```text
class CsvColumnNotFoundError(ColumnNotFoundError):
```

#### 説明

CSV の列見出しが見つからない

非エンジニアが列名を変更したときに分かりやすいメッセージを出すために使う。

発生箇所: CsvReader._validate_columns()

使い方:
    from comken.exceptions import CsvColumnNotFoundError

    REQUIRED_COLUMNS = ["日付", "担当者", "金額"]

    def validate_columns(rows: list[dict[str, str]], required: list[str]) -> None:
        existing = list(rows[0])
        missing = [column for column in required if column not in existing]
        if missing:
            raise CsvColumnNotFoundError(missing, existing)

対処:
    CSV の1行目を確認する

#### `__init__`

```text
def __init__(self, columns: list[str], existing: list[str]) -> None:
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

### `TransferKeyColumnNotFoundError`

```text
class TransferKeyColumnNotFoundError(ColumnNotFoundError):
```

#### 説明

列名転記で、Excel のキー列が見つからない

発生箇所: Sheet.transfer_by_mapping()

対処:
    Excel のヘッダー行と key_col の列名を確認する

#### `__init__`

```text
def __init__(self, column: str, existing: list[str]) -> None:
```

### `TransferDestinationColumnNotFoundError`

```text
class TransferDestinationColumnNotFoundError(ColumnNotFoundError):
```

#### 説明

列名転記で、Excel の転記先列が見つからない

発生箇所: Sheet.transfer_by_mapping()

対処:
    Excel のヘッダー行と config.ini のマッピング右側を確認する

#### `__init__`

```text
def __init__(self, columns: list[str], existing: list[str]) -> None:
```

### `TransferSourceColumnNotFoundError`

```text
class TransferSourceColumnNotFoundError(ColumnNotFoundError):
```

#### 説明

列名転記で、lookup の転記元列が見つからない

発生箇所: Sheet.transfer_by_mapping()

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
    config.ini.example をコピーして config.ini を作る

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
    表示されたセクション名を config.ini に追加する

#### `__init__`

```text
def __init__(self, name: str, existing: list[str]) -> None:
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

### `RpaError`

```text
class RpaError(ComkenError):
```

#### 説明

社内 RPA 基盤の呼び出しに関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `RpaLibraryNotFoundError`

```text
class RpaLibraryNotFoundError(RpaError):
```

#### 説明

社内ライブラリを読み込めない

発生箇所: comken.toolbox.rpa.backoffice() / comken.toolbox.rpa.intranet()

対処:
    実行.bat の PYTHONPATH に社内ライブラリが入っているか確認する。
    バージョンが変わった場合は管理者へ連絡する

#### `__init__`

```text
def __init__(self, module_path: str, detail: Exception) -> None:
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
    無ければ `python -m comken.toolbox.credentials import 認証情報.json` で取り込む

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

### `SalesforceExternalIdMissingError`

```text
class SalesforceExternalIdMissingError(SalesforceError):
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

発生箇所: comken.toolbox.salesforce.ReportApi.run() / run_async()

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

発生箇所: comken.toolbox.salesforce.ReportApi.run() / run_async()

対処:
    レポートを明細形式にするか、管理者へ連絡する

#### `__init__`

```text
def __init__(self, report_id: str, report_format: str) -> None:
```

### `SalesforceReportIdNotFoundError`

```text
class SalesforceReportIdNotFoundError(SalesforceError):
```

#### 説明

レポートの URL からレポート ID を取り出せない

管理表にはレポートの URL をそのまま貼れるようにしてあるが、
貼られたものが Salesforce のレポート URL でないと ID を取り出せない。

発生箇所: comken.toolbox.salesforce.report_id_from_url()

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
    browsers.launch("kintai")     # ← ここで送出される（ブラウザは起動しない）

    # 正しい
    with Browsers() as browsers:
        browsers.launch("kintai")

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
        session = browsers.launch("kintai")
        session.open("https://example.com")

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

発生箇所: Browsers.launch()

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

発生箇所: comken.toolbox.master_table の load()

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

発生箇所: comken.toolbox.master_table の load()

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

発生箇所: comken.toolbox.master_table の load()

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

発生箇所: comken.toolbox.master_table の load()

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

### `DownloaderError`

```text
class DownloaderError(ComkenError):
```

#### 説明

Salesforce レポートの集約取得に関するエラー

対処:
    画面に表示された具体的なエラー名を上の表から探す

### `ReportNotRegisteredError`

```text
class ReportNotRegisteredError(DownloaderError):
```

#### 説明

指定した管理番号が管理表に無い

管理番号はコードに定数で書く（CUSTOMER_LIST = 1001）。管理表から行を消したり、
番号を打ち間違えたりすると、どのレポートを指しているか決められない。

発生箇所: comken.services.salesforce_downloader の download_report()

対処:
    管理表を開いて、その管理番号の行があるか確認する。
    新しく使うレポートは、先に管理表へ登録する

#### `__init__`

```text
def __init__(self, report_key: int, registered: list[int], master_path: Path) -> None:
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
def __init__(self, report_key: int, summary: str, master_path: Path) -> None:
```

### `InvalidReportUrlError`

```text
class InvalidReportUrlError(DownloaderError):
```

#### 説明

管理表の URL から Salesforce のレポート ID を取り出せない

貼られたものが Salesforce のレポート URL でないと、どのレポートか決められない。

発生箇所: comken.services.salesforce_downloader の管理表読み込み

対処:
    Salesforce でレポートを開いたときのアドレスを、そのまま貼り直す

#### `__init__`

```text
def __init__(self, report_key: int, url: str, reason: str) -> None:
```

### `ScheduledReportNotRegisteredError`

```text
class ScheduledReportNotRegisteredError(DownloaderError):
```

#### 説明

定期取得の対象として登録されていないレポートを、定期取得済みとして受け取ろうとした

get_scheduled_report() は「決まった時刻に取っておいたものを受け取る」関数。
管理表で「個別」になっているレポートは誰も取りに行かないので、いつまでも揃わない。

発生箇所: comken.services.salesforce_downloader の get_scheduled_report()

対処:
    毎日決まった時刻に取るなら、管理表の「実行方式」を「定期」にする。
    使うときに毎回取りに行くなら、download_report() を呼ぶ

#### `__init__`

```text
def __init__(self, report_key: int, summary: str, schedule: str, master_path: Path) -> None:
```

### `ScheduledReportNotDownloadedError`

```text
class ScheduledReportNotDownloadedError(DownloaderError):
```

#### 説明

本日の定期取得がまだ済んでいない

定期取得の時刻より前に呼ばれた、定期取得が失敗した、その日に管理表へ
追加されて今日の分に間に合わなかった、のいずれか。

**勝手に Salesforce へ取りに行かない。** get_scheduled_report() は
「取っておいたものを受け取る」関数で、取りに行く関数ではない。
ここで自動的に取りに行くと、定期取得が動いていないことに誰も気づかなくなる。

発生箇所: comken.services.salesforce_downloader の get_scheduled_report()

対処:
    定期取得の実行結果を確認する。急ぐ場合は download_report() で
    その場で取得する（そのぶん Salesforce への呼び出しが増える）

#### `__init__`

```text
def __init__(self, report_key: int, summary: str, history_path: Path) -> None:
```

### `ReportFileMissingError`

```text
class ReportFileMissingError(DownloaderError):
```

#### 説明

履歴では取得済みだが、保存先にファイルが無い

取得の後で人が消した・移動した・保存先の設定を変えた、のいずれか。

発生箇所: comken.services.salesforce_downloader の get_scheduled_report()

対処:
    保存先のフォルダを確認する。消してしまった場合は
    download_report() で取り直す

#### `__init__`

```text
def __init__(self, report_key: int, path: Path) -> None:
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
    本当に 0 件の日であれば、空の CSV を保存先へ手で置く

#### `__init__`

```text
def __init__(self, report_key: int, summary: str, url: str) -> None:
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
def __init__(self, report_key: int, folder: Path) -> None:
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
def __init__(self, failed_keys: list[int], history_path: Path) -> None:
```


## `from comken.services.salesforce_downloader import ...`

### `download_report`

```text
def download_report(report_key: int, project: str='') -> CsvReader:
```

#### 説明

今すぐ Salesforce から取得して保存し、そのファイルを `CsvReader` で返す。

**必ず Salesforce へ問い合わせる。** 今日すでに取っていても取り直す。

Args:
    report_key: 管理表の管理番号（例: 1001）。
    project: 呼び出し元の名前。履歴に残るので、入れておくと後から追える。

Returns:
    保存したファイルを読み取る `CsvReader`。ファイルパスは `.path` で取れる。

Raises:
    ReportNotRegisteredError: 管理表に無い管理番号の場合。
    ReportDisabledError: 管理表で無効になっている場合。
    ReportFolderNotFoundError: 保存先のフォルダが無い場合。
    EmptyReportError: 明細が 0 行だった場合。

### `get_scheduled_report`

```text
def get_scheduled_report(report_key: int, project: str='') -> CsvReader:
```

#### 説明

定期取得しておいたファイルを `CsvReader` で返す。**取りに行かない。**

Args:
    report_key: 管理表の管理番号（例: 1001）。
    project: 呼び出し元の名前（履歴には残さないが、例外の調査に使えるよう受け取る）。

Returns:
    定期取得で保存されたファイルを読み取る `CsvReader`。ファイルパスは `.path` で取れる。

Raises:
    ReportNotRegisteredError: 管理表に無い管理番号の場合。
    ScheduledReportNotRegisteredError: 管理表で「個別」になっている場合。
    ScheduledReportNotDownloadedError: 本日の定期取得がまだ済んでいない場合。
    ReportFileMissingError: 履歴では取得済みだが、ファイルが無い場合。

### `download_scheduled`

```text
def download_scheduled(project: str='定期実行') -> list[Path]:
```

#### 説明

管理表で「定期」かつ有効なレポートをまとめて取得する。

定期実行のプロジェクトから呼ぶ。**1件失敗しても残りは続ける** ——
5本のうち1本が落ちたときに全部やり直すと、手で用意する手間が5本ぶんになる。

戻り値は `list[Path]` のままで **`CsvReader` を返さない**。定期取得の呼び出し側は
中身を読まず「取らせる」のが目的なので、reader を並べても使い道がないため
（役割の違いが戻り値の型に出ている）。

Args:
    project: 履歴に残す呼び出し元の名前。

Returns:
    取得できたファイルのパス。

Raises:
    ScheduledDownloadFailedError: 1件でも取得できなかった場合。
        **取得できたものは保存したうえで**送出する。ログだけに出して正常終了すると、
        スケジューラや RPA 基盤から見て成功と区別が付かない。

### `file_path_of`

```text
def file_path_of(entry: ReportEntry) -> Path:
```

#### 説明

そのレポートを保存するパス。

ファイル名は「管理番号_概要_日付」。**管理番号を先頭に置く**のは、概要や
参照先の Salesforce レポートが変わっても、番号は変わらないため。概要を入れるのは、
保存先を人が直接見たときに何のファイルか分かるようにするため。

### `load_master`

```text
def load_master(path: str | Path | None=None) -> dict[int, ReportEntry]:
```

#### 説明

管理表を読んで、管理番号をキーにした辞書を返す。

Args:
    path: 管理表（Excel）のパス。

Returns:
    {管理番号: ReportEntry}。管理表に並んでいる順を保つ。

### `shared_report_ids`

```text
def shared_report_ids(entries: dict[int, ReportEntry]) -> dict[str, list[int]]:
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
    InvalidReportUrlError: URL からレポート ID を取り出せない場合。

#### `is_scheduled`

```text
@property
def is_scheduled(self) -> bool:
```

##### 説明

定期取得の対象か。


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
def run_macro(self, name: str) -> None:
```

##### 説明

Access マクロを実行する。

元データベースを更新するマクロの場合は、初期化時に ``local_copy=False`` を指定する。
VBA のプロシージャ／関数を実行する場合は ``run_function()`` を使う。

#### `run_function`

```text
def run_function(self, name: str, *args: object) -> object | None:
```

##### 説明

VBA のプロシージャ／関数を実行する。

元データベースを更新する処理の場合は、初期化時に ``local_copy=False`` を指定する。
Access のマクロは別の仕組みなので、マクロには ``run_macro()`` を使う。
dry-run 時は実行せず ``None`` を返す。

#### `run_query`

```text
def run_query(self, name: str) -> None:
```

##### 説明

保存済みのアクションクエリを名前で実行する。

UPDATE・INSERT・DELETE・テーブル作成など、データを変更するクエリ向け。
元データベースへ変更を反映する場合は、初期化時に ``local_copy=False`` を指定する。
SELECT クエリの結果を読む場合は ``read_rows()``、CSVへ出す場合は ``export_csv()`` を使う。

#### `export_csv`

```text
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
def launch(self, name: str, options: type[BrowserOptions] | BrowserOptions | None=None, download_dir: str | Path | None=None) -> BrowserSession:
```

##### 説明

名前を付けてブラウザを1つ起動する。

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

    勤怠 = browsers.run_task(lambda: KintaiFlow(kintai).search())
    KeiriFlow(keiri).login(user, password)   # 勤怠の読み込み中にこちらが進む
    days = 勤怠.wait()                        # 戻って結果を受け取る

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
        kintai = browsers.launch("kintai", download_dir=r"C:\作業\downloads")
        files = kintai.download_dir.wait()
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
def delete_credential(name: str, path: Path | None=None) -> None:
```

#### 説明

登録済みの認証情報を1件削除する。

Raises:
    CredentialNotFoundError: キー名が未登録の場合。
    CredentialDecryptionError: 既存ファイルを復号できない場合。

### `list_names`

```text
def list_names(path: Path | None=None) -> list[str]:
```

#### 説明

登録済みのキー名一覧を返す（値そのものは返さない）。

Raises:
    CredentialDecryptionError: 別のユーザー・PC で登録されていて復号できない場合。

### `import_json`

```text
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

### `CsvReader`

```text
class CsvReader(CsvBase):
```

#### 説明

CSV ファイルの読み込みユーティリティ。

ヘッダー行をキーにした辞書のリストとして扱う。
読み込みは最初のメソッド呼び出し時に行い、同じインスタンス内では結果を再利用する。

#### `__init__`

```text
def __init__(self, path: str | Path, encoding: str=Encoding.AUTO, headers: list[str] | None=None) -> None:
```

##### 説明

Args:
    path: CSV ファイルのパス。
    encoding: 文字コード。Encoding.AUTO（デフォルト）は UTF-8（BOM付き含む）→
              CP932（Shift-JIS）の順に自動判定する。
              明示したい場合は Encoding.UTF8_SIG / Encoding.CP932 を指定する。
    headers: ヘッダー行がない CSV の場合に、列名のリストをここで付ける。
             指定すると1行目からデータとして読む。
             例: CsvReader("data.csv", headers=["注文番号", "金額", "担当者"])

#### `read_rows`

```text
@measure
def read_rows(self, columns: list[str] | None=None) -> list[dict[str, str]]:
```

##### 説明

全行を返す。

Args:
    columns: 取得する列名のリスト。省略すると全列を返す。

Returns:
    辞書のリスト。columns 指定時は指定列のみ含む。

#### `cell`

```text
def cell(self, ref: str) -> str:
```

##### 説明

Excel 風のセル参照で、CSV の1セルを返す。

ヘッダー付き辞書を作る ``_load()`` とは別に生の行を読むため、
列名や ``headers`` の指定には依存しない。ヘッダー行も1行目として数える。
列の位置に依存するため、上流で列が増減すると別の値を読む可能性がある。
ヘッダーがある CSV では、列の位置が変わっても壊れない ``first()`` を推奨する。

Args:
    ref: A1、B2 のような1始まりのセル参照。

Returns:
    セルの文字列。空セルの場合は空文字。

Raises:
    CsvCellReferenceError: 参照が不正、またはCSVの範囲外の場合。

#### `first`

```text
def first(self, column: str) -> str:
```

##### 説明

ヘッダー名で列を指定し、最初のデータ行の値を返す。

ヘッダーがある CSV では、列の位置が変わっても壊れないこのメソッドを推奨する。
ヘッダーがない、または位置で決まっている CSV では ``cell("A2")`` を使う。

Args:
    column: 取得する列名。

Returns:
    最初のデータ行にある指定列の文字列。空セルの場合は空文字。

Raises:
    CsvColumnNotFoundError: 指定した列名が存在しない場合。
    CsvNoDataRowsError: データ行が1行もない場合。

#### `find`

```text
def find(self, key_col: str, value: str, required: bool=True) -> dict[str, str] | None:
```

##### 説明

key_col が value に一致する最初の行を返す。

見つからないときは既定で CsvRowNotFoundError。
「無くても処理を続けたい」場合だけ required=False にすると None を返す。

Raises:
    CsvRowNotFoundError: required=True で該当行がない場合。

#### `filter`

```text
def filter(self, key_col: str, value: str) -> list[dict[str, str]]:
```

##### 説明

key_col が value に一致する全行を返す。

Args:
    key_col: 検索対象の列名。
    value: 検索する値。

Returns:
    一致した行の辞書のリスト。一致しない場合は空リスト。

#### `column`

```text
def column(self, col_name: str) -> list[str]:
```

##### 説明

指定列の値一覧を返す。

Args:
    col_name: 取得する列名。

Returns:
    列の値のリスト（ヘッダー行を除く）。

#### `index`

```text
def index(self, key_col: str) -> dict[str, dict[str, str]]:
```

##### 説明

key_col をキーにした {キー: 行} の辞書を返す。

Excel との突合（transfer_by_mapping の lookup）など、キーで1行を引く用途に使う。
キーが重複していれば CsvRowDuplicateKeyError。重複が普通のデータは group_by() を使う。

Raises:
    CsvRowDuplicateKeyError: キーが重複している場合。

#### `group_by`

```text
def group_by(self, key_col: str) -> dict[str, list[dict[str, str]]]:
```

##### 説明

key_col をキーにした {キー: 行のリスト} の辞書を返す。

同じキーの行が複数あるデータを、キーごとにまとめたいときに使う。
1件だけ引きたい（重複しないはずの）データは index() を使う。

### `CsvWriter`

```text
class CsvWriter(CsvBase):
```

#### 説明

CSV ファイルへの書き込みユーティリティ。

#### `__init__`

```text
def __init__(self, path: str | Path, fieldnames: list[str], encoding: str=Encoding.UTF8_SIG) -> None:
```

##### 説明

Args:
    path: 書き込み先の CSV ファイルパス。親フォルダがなければ書き込み時に自動作成される。
    fieldnames: ヘッダー行の列名リスト。書き込み順に影響する。
    encoding: 文字コード。Excel で開く場合は Encoding.UTF8_SIG（デフォルト）。
              Shift-JIS が必要な場合は Encoding.CP932 を指定する。
              Encoding.AUTO は自動判定できない（読み込み専用）ため UTF8_SIG として扱う。

#### `write_rows`

```text
def write_rows(self, rows: list[dict]) -> None:
```

##### 説明

ファイルを新規作成（または上書き）して全行を書き込む。

既存ファイルがある場合は上書きされる。

Args:
    rows: 書き込む行のリスト（辞書のリスト）。

#### `append_row`

```text
def append_row(self, row: dict) -> None:
```

##### 説明

既存ファイルの末尾に1行追記する。

ファイルが存在しない場合はヘッダー付きで新規作成する。

Args:
    row: 追記する行の辞書。

Notes:
    複数の PC から同じ CSV へ同時に追記する使い方は想定していない。

#### `append_rows`

```text
def append_rows(self, rows: list[dict]) -> None:
```

##### 説明

既存ファイルの末尾に複数行追記する。

ファイルが存在しない場合はヘッダー付きで新規作成する。

Args:
    rows: 追記する行のリスト（辞書のリスト）。

Notes:
    複数の PC から同じ CSV へ同時に追記する使い方は想定していない。


## `from comken.toolbox.excel import ...`

### `ExcelReader`

```text
class ExcelReader(ExcelBase):
```

#### 説明

Excel ブックを読み取り専用で開くクラス。

read_only=True で開くため、大きなブックもメモリ効率よく速く読み取れる。
書き込みメソッドを持たないので、誤って元ファイルを書き換える事故を防げる。

#### `__init__`

```text
def __init__(self, path: str | Path, data_only: bool=False, local_copy_threshold_mb: float=10, headers: list[str] | None=None) -> None:
```

##### 説明

Args:
    path: Excel ファイルのパス。
    data_only: True にすると数式セルのキャッシュ値を読む（read_computed_rows 推奨）。
    local_copy_threshold_mb: この MB 以上のファイルはローカルにコピーしてから開く。
        NAS・ネットワークドライブのファイルが遅い・不安定な場合に有効。
        0 を指定するとローカルコピーを無効化できる。
    headers: ヘッダー行がない Excel の場合に、列名のリストをここで付ける。
        指定すると read_rows_as_dicts() は全行をデータとして読む。

### `ExcelWriter`

```text
class ExcelWriter(ExcelBase):
```

#### 説明

Excel ブックの読み取り・書き込み・保存を行うクラス。

読み取りメソッドも継承しているため、データを読んでから Sheet で
書き換える処理を1つのブックで完結できる。

#### `__init__`

```text
def __init__(self, path: str | Path, data_only: bool=False, local_copy_threshold_mb: float=10, headers: list[str] | None=None) -> None:
```

##### 説明

Args:
    path: Excel ファイルのパス。
    data_only: True にすると数式セルのキャッシュ値を読む（read_computed_rows 推奨）。
    local_copy_threshold_mb: この MB 以上のファイルはローカルにコピーしてから開く。
        NAS・ネットワークドライブのファイルが遅い・不安定な場合に有効。
        0 を指定するとローカルコピーを無効化できる。
    headers: ヘッダー行がない Excel の場合に、列名のリストをここで付ける。
        指定すると read_rows_as_dicts() は全行をデータとして読む。

#### `sheet`

```text
def sheet(self, name: str) -> Sheet:
```

##### 説明

シートの高レベルラッパーを返す（シート単位でセル・行を書き込む）。

Args:
    name: シート名。

Raises:
    SheetNotFoundError: 指定したシートが存在しない場合。

#### `add_sheet`

```text
def add_sheet(self, name: str, index: int | None=None) -> Sheet:
```

##### 説明

シートを追加し、そのまま書き込める Sheet を返す。

Args:
    name: 追加するシート名。
    index: 挿入位置（0始まり）。省略時は末尾。

Raises:
    SheetAlreadyExistsError: 同名のシートが既に存在する場合。

#### `rename_sheet`

```text
def rename_sheet(self, old_name: str, new_name: str) -> None:
```

##### 説明

シート名を変更する。

#### `delete_sheet`

```text
def delete_sheet(self, name: str) -> None:
```

##### 説明

シートを削除する。

シートを削除すると、そのシートを参照している数式が ``#REF!`` になる。
削除する前に、他のシートから参照されていないか確認すること。

#### `create`

```text
@classmethod
def create(cls, path: str | Path, sheet_name: str='Sheet1') -> Self:
```

##### 説明

新規ブックを作る（ファイルはまだ作られず、save() で path に保存される）。
Args:
    path: save() で保存されるパス。親フォルダがなければ保存時に自動作成される。
    sheet_name: 最初のシートの名前（デフォルト: "Sheet1"）。

#### `save`

```text
@measure
def save(self, path: str | Path | None=None) -> None:
```

##### 説明

ファイルを保存する。

ローカルコピーで開いている場合も、省略時の保存先は元のファイル
（一時コピーに保存すると close() でコピーごと消えてしまうため）。

Args:
    path: 保存先のパス。省略すると開いた元のファイルに上書き保存する。

#### `run_macro`

```text
def run_macro(self, macro_name: str, save: bool=True) -> None:
```

##### 説明

VBA マクロを実行する。内部で win32com（pywin32）を使用する。

COM は保存せずに閉じる仕様のため、save=True（デフォルト）で実行後に
元ファイルへ保存する。マクロがブックを変更しても保存しないと結果は破棄される。

WARNING: このメソッドは COM で元ファイルを直接編集する。openpyxl 側
    （Sheet で行った書き込み等）の未保存の変更とは独立で、run_macro の後に f.save() を
    呼ぶと openpyxl の内容で上書きされマクロの結果が消える。
    マクロと openpyxl 書き込みを混在させないこと。

Args:
    macro_name: 実行するマクロ名。"モジュール名.プロシージャ名" の形式で指定する。
                例: "Module1.UpdateData"
    save: True（デフォルト）ならマクロ実行後に元ファイルへ保存する。

### `Sheet`

```text
class Sheet:
```

#### 説明

1枚のワークシートのラッパー。ExcelWriter.sheet() から取得する。

ここにないシート操作は .ws から生の openpyxl Worksheet を使える。

#### `__init__`

```text
def __init__(self, ws: Worksheet) -> None:
```

#### `write_cell`

```text
def write_cell(self, row: int, col: int | str, value) -> None:
```

##### 説明

行番号と列番号・列記号を指定してセルに値を書き込む。

#### `write_row`

```text
def write_row(self, row: int, values: list, start_col: int=1) -> None:
```

##### 説明

1行に値を横並びで書き込む。

Args:
    row: 行番号（1始まり）。
    values: 書き込む値のリスト（左から順に並ぶ）。
    start_col: 開始列番号（1始まり。デフォルト: A列から）。

#### `write_rows`

```text
def write_rows(self, start_row: int, rows: list[list], start_col: int=1) -> None:
```

##### 説明

複数行をまとめて書き込む。

Args:
    start_row: 開始行番号（1始まり）。
    rows: 行のリスト（値のリストのリスト）。
    start_col: 開始列番号（1始まり）。

#### `append_row`

```text
def append_row(self, values: list) -> None:
```

##### 説明

最終行の下に1行追記する（空シートなら1行目に書く）。

#### `write_table`

```text
def write_table(self, rows: list[dict], start_row: int=1, headers: list[str] | None=None) -> None:
```

##### 説明

ヘッダー行 + データ行の値を書き込む（構造化テーブルにはしない）。

CsvReader.read_rows() や read_rows_as_dicts() の結果をそのまま渡せる。
Excel の構造化テーブルにする場合は、書き込み後に add_table() を呼ぶ。

Args:
    rows: 辞書のリスト（キーが列名になる）。
    start_row: ヘッダー行の行番号（1始まり）。
    headers: 列の並び順。省略すると最初の行のキー順。

#### `transfer_by_letter`

```text
@measure
def transfer_by_letter(self, key_col: int | str, lookup: dict[str, dict], mapping: dict[str, int | str], start_row: int=2) -> int:
```

##### 説明

列記号で転記先を指定し、キーが一致した行へ値を転記する。

ヘッダーがない、または列位置が仕様として固定された Excel に使う。
ヘッダー名で列を指定できる帳票には transfer_by_mapping() を使う。
mapping は両メソッド共通で ``{転記元の列名: 転記先}`` の向き。

#### `transfer_by_mapping`

```text
@measure
def transfer_by_mapping(self, key_col: str, lookup: dict[str, dict], mapping: dict[str, str], header_row: int=1) -> int:
```

##### 説明

列名で転記先を指定し、キーが一致した行へ値を転記する。

config.mapping("..._MAPPING") の戻り値を変換せずに渡せる。
mapping の向きは ``{転記元の列名: 転記先の列名}`` で、左が元、右が先。
ヘッダーがない、または列位置が固定された帳票には transfer_by_letter() を使う。
転記を始める前にキー列・転記先列・転記元列をすべて検証する。

Args:
    key_col: 転記先 Excel で照合に使う列名。
    lookup: キーから転記元の行データを引く辞書。
    mapping: 転記元の列名から転記先の列名への対応表。
    header_row: 転記先 Excel のヘッダー行番号（1始まり）。

#### `add_table`

```text
def add_table(self, name: str, ref: str) -> None:
```

##### 説明

指定範囲を Excel の構造化テーブルにする。

write_table() は値だけを書き、このメソッドは既存の値をテーブルにする。
スタイルを変えたい場合は .ws から openpyxl を直接使用する。

#### `append_to_table`

```text
def append_to_table(self, name: str, rows: list[dict]) -> None:
```

##### 説明

構造化テーブルの末尾にデータ行を追記する。

openpyxl は計算列を自動入力しない。数式の列がある場合は、
``{"税込": "=[@金額]*1.1"}`` のように行データへ数式文字列を含める。
``[@列名]`` の構造化参照はテーブル内のセルでのみ有効。

#### `clear_table`

```text
def clear_table(self, name: str) -> None:
```

##### 説明

構造化テーブルのデータ行だけを消す（見出し行は残す）。

#### `replace_table`

```text
def replace_table(self, name: str, rows: list[dict]) -> None:
```

##### 説明

構造化テーブルのデータ行をすべて入れ替える。

openpyxl は計算列を自動入力しない。数式の列がある場合は、
``{"税込": "=[@金額]*1.1"}`` のように行データへ数式文字列を含める。
``[@列名]`` の構造化参照はテーブル内のセルでのみ有効。

#### `set_fill`

```text
def set_fill(self, row: int, col: int | str, color: str) -> None:
```

##### 説明

セルの背景色を16進 RGB（# なし）で設定する。

#### `set_column_width`

```text
def set_column_width(self, col: int | str, width: float) -> None:
```

##### 説明

列番号または列記号を指定して列幅を設定する。

#### `set_number_format`

```text
def set_number_format(self, row: int, col: int | str, fmt: str) -> None:
```

##### 説明

セルの数値フォーマットを設定する。

#### `set_bold`

```text
def set_bold(self, row: int, col: int | str, bold: bool=True) -> None:
```

##### 説明

セルの太字を設定または解除する。

#### `auto_width`

```text
def auto_width(self, min_width: float=8, max_width: float=60) -> None:
```

##### 説明

全列の幅を内容に合わせて調整する（全角文字は2文字ぶんで計算）。

Args:
    min_width: 最小の列幅（内容が短くても これより狭くしない）。
    max_width: 最大の列幅（長文があっても これより広げない）。

#### `freeze_header`

```text
def freeze_header(self, rows: int=1) -> None:
```

##### 説明

ヘッダー行を固定する（スクロールしても見出しが消えない）。

Args:
    rows: 固定する行数（デフォルト: 1行目のみ）。

#### `last_row`

```text
@property
def last_row(self) -> int:
```

##### 説明

データがある最終行の番号（1始まり）。空シートでも 1 が返る点に注意。

#### `is_empty`

```text
@property
def is_empty(self) -> bool:
```

##### 説明

シートに値が1つもないか返す。


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

```text
class SalesforceBase:
```

#### 説明

Salesforce の 1 組織に対する API クライアント（組織クラスの土台）。

DOMAIN_URL と CREDENTIAL_PREFIX を持つサブクラスを作って使う。
認証情報は DPAPI から読むので、呼び出し側のコードに秘密の値が現れない。

使い方:
    with Sandbox() as sf:
        records = sf.query("SELECT Id, Name FROM Account")
        rows = sf.report.run("00O000000000001")
        sf.metrics.log_summary()

Attributes:
    report: レポート API（sf.report.run(...)）。
    metrics: API 呼び出しの計測（sf.metrics.log_summary()）。

#### `__init__`

```text
def __init__(self, *, prefix: str='', domain_url: str='', org_name: str='', auth: _OAuth | None=None) -> None:
```

##### 説明

DPAPI に保管した認証情報を読み、選択中の OAuth 方式で接続する。

読み込む項目は client.py が import している OAuth 方式で決まる。
Client Credentials 方式は client_id / client_secret、Refresh Token 方式は
client_id / client_secret / refresh_token を使う。

Args:
    prefix: 認証情報のシステム名。省略時はクラスの CREDENTIAL_PREFIX。
        本番とテストを切り替えるときだけ渡す。
    domain_url: My Domain の URL。省略時はクラスの DOMAIN_URL。
    org_name: 計測ログに出す組織の呼び名。省略時はクラス名を使う。
    auth: 認証方式を差し替えるとき（テスト・JWT 等）に渡す。
        指定時は prefix / domain_url を使わない。

Raises:
    InvalidCredentialNameError: システム名が空、または使えない文字を含む場合。
    CredentialNotFoundError: 選択方式に必要な認証情報が未登録の場合。
    CredentialDecryptionError: 別のユーザー・PC で登録されていて復号できない場合。
    SalesforceAuthError: 認証に失敗した場合。
    SalesforceConnectionError: ネットワークの問題で接続できない場合。

#### `close`

```text
def close(self) -> None:
```

##### 説明

HTTP セッションを閉じる。with を使う場合は自動で呼ばれる。

#### `query`

```text
def query(self, soql: str) -> list[dict]:
```

##### 説明

SOQL クエリを実行してレコードを返す（全件取得・ページ送り自動）。

レポート API と違って**行数の上限がない**ので、
2000 行を超えるデータはこちらで取る。

Args:
    soql: 実行する SOQL クエリ文字列。

Returns:
    レコードの辞書のリスト。

#### `get`

```text
def get(self, object_name: str, record_id: str) -> dict:
```

##### 説明

レコードを1件取得する。

Args:
    object_name: オブジェクトの API 参照名（例: "Account"）。
    record_id: レコードの Id。

#### `insert`

```text
def insert(self, object_name: str, data: dict) -> str:
```

##### 説明

レコードを作成して Id を返す。

Args:
    object_name: オブジェクトの API 参照名。
    data: 作成するレコードの項目と値。

#### `update`

```text
def update(self, object_name: str, record_id: str, data: dict) -> None:
```

##### 説明

レコードを更新する。

Args:
    object_name: オブジェクトの API 参照名。
    record_id: 更新するレコードの Id。
    data: 更新する項目と値。

#### `upsert`

```text
def upsert(self, object_name: str, external_id_field: str, data: dict) -> None:
```

##### 説明

外部 ID で upsert する（一致すれば更新、なければ作成）。

Args:
    object_name: オブジェクトの API 参照名。
    external_id_field: 外部 ID 項目の API 参照名（例: "ExternalId__c"）。
    data: 項目と値。external_id_field の値を含めること。

Raises:
    SalesforceExternalIdMissingError: data に external_id_field が無い場合。

#### `delete`

```text
def delete(self, object_name: str, record_id: str) -> None:
```

##### 説明

レコードを削除する。

Args:
    object_name: オブジェクトの API 参照名。
    record_id: 削除するレコードの Id。

#### `request`

```text
def request(self, method: str, path: str, body: dict | None=None, component: str='other') -> tuple[dict | list | str | None, dict]:
```

##### 説明

REST API を呼び、(レスポンス本文, レスポンスヘッダー) を返す。

すべての API 呼び出しがここを通る。計測と、401 のときの再認証もここで行う。
通常は query() / get() 等を使い、このメソッドは
ライブラリに無い API を叩くときだけ使う。

Args:
    method: HTTP メソッド（GET / POST / PATCH / DELETE）。
    path: "/services/data/..." から始まるパス。
    body: JSON で送る辞書（省略可）。
    component: 計測での呼び出し元の区別（"query" / "crud" / "report"）。

Raises:
    SalesforceRequestError: API がエラーを返した場合。
    SalesforceConnectionError: ネットワークの問題で接続できない場合。

#### `data_path`

```text
def data_path(self, path: str) -> str:
```

##### 説明

REST API のバージョン付きパスを組み立てる。

ライブラリに無い API を request() で叩くときに使う。

    sf.request("GET", sf.data_path("/limits"))

### `ReportApi`

```text
class ReportApi:
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

### `report_id_from_url`

```text
def report_id_from_url(text: str) -> str:
```

#### 説明

レポートの URL からレポート ID を取り出す。ID をそのまま渡してもよい。

管理表（レポート一覧の CSV・Excel）には**画面のアドレスをそのまま貼れる**ようにする。
人が ID の部分だけを抜き出す工程を挟むと、そこで写し間違いが起きるため。

    https://example.my.salesforce.com/lightning/r/Report/00O5g00000ABCDEfgh/view
    → 00O5g00000ABCDEfgh

Args:
    text: レポートの URL、またはレポート ID。前後の空白は無視する。

Returns:
    レポート ID（15 桁または 18 桁）。

Raises:
    SalesforceReportIdNotFoundError: レポート ID が見つからない場合。

### `ClientCredentialsAuth`

公開定数。

### `RefreshTokenAuth`

公開定数。

### `CredentialsOAuth`

```text
class OAuth:
```

#### 説明

client_id と client_secret でアクセストークンを取得する。

#### `__init__`

```text
def __init__(self, client_id: str, client_secret: str, domain_url: str) -> None:
```

#### `from_credentials`

```text
@classmethod
def from_credentials(cls, domain_url: str, prefix: str) -> Self:
```

##### 説明

DPAPIに保存したclient_idとclient_secretから認証を作る。

#### `fetch`

```text
def fetch(self) -> tuple[str, str]:
```

##### 説明

アクセストークンと instance_url を取得する。

### `RefreshOAuth`

```text
class OAuth:
```

#### 説明

保存済み refresh_token でアクセストークンを更新する。

#### `__init__`

```text
def __init__(self, client_id: str, refresh_token: str, domain_url: str, *, client_secret: str | None=None, on_refresh_token: Callable[[str], None] | None=None) -> None:
```

#### `from_credentials`

```text
@classmethod
def from_credentials(cls, domain_url: str, prefix: str) -> Self:
```

##### 説明

DPAPIに保存したOAuth資格情報から認証を作る。

#### `fetch`

```text
def fetch(self) -> tuple[str, str]:
```

##### 説明

refresh_token を使ってアクセストークンを取得する。

#### `authorization_url`

```text
@staticmethod
def authorization_url(client_id: str, redirect_uri: str, domain_url: str, *, scope: str='api refresh_token', state: str | None=None) -> tuple[str, str]:
```

##### 説明

利用者がブラウザで開く認可 URL と CSRF 検証用 state を返す。

#### `exchange_code`

```text
@classmethod
def exchange_code(cls, client_id: str, client_secret: str, code: str, redirect_uri: str, domain_url: str, *, on_refresh_token: Callable[[str], None] | None=None) -> Self:
```

##### 説明

認可コードを交換し、取得した refresh_token を持つ認証部品を返す。

### `ApiMetrics`

```text
class ApiMetrics:
```

#### 説明

API 呼び出しの計測を貯める。

使い方:
    metrics = ApiMetrics("sandbox")
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

### `ApiUsage`

```text
class ApiUsage:
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

```text
class SalesforceCredentialRotator:
```

#### 説明

ECA の資格情報を、期限到来時だけ安全な順序でローテーションする。

``is_enabled`` は config.ini の明示設定から渡す。既定で無効なのは、DPAPI が
Windows ユーザーと PC に紐付き、同じ ECA を使う他 PC へ新 secret を配れないため。
同じ ECA を複数 PC で使う場合、有効にしてよいのは1台だけである。

#### `__init__`

```text
def __init__(self, client: SalesforceBase, app_id: str, credential_prefix: str, is_enabled: bool=False, interval_days: int=DEFAULT_ROTATION_INTERVAL_DAYS, credential_path: Path | None=None) -> None:
```

#### `rotate_if_due`

```text
def rotate_if_due(self, today: datetime.date | None=None) -> bool:
```

##### 説明

有効かつ指定日数を過ぎていれば実行し、実行したかを返す。


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
        rows = sf.案件一覧()

#### `案件一覧`

```text
def 案件一覧(self) -> list[dict]:
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

### `ExcelComHandler`

```text
class ExcelComHandler(FileBase):
```

#### 説明

win32com を使った Excel 操作クラス。

openpyxl では対応できない以下の操作に使う:
    - 数式の計算結果を読む（CalculateFull で再計算してから取得）
    - VBA マクロを実行する
    - パスワード付きで保存する

#### `__init__`

```text
def __init__(self, path: str | Path, password: str='', headers: list[str] | None=None) -> None:
```

##### 説明

Args:
    path: Excel ファイルのパス。
    password: 読み取りパスワード（パスワード保護されたファイルを開く場合）。
    headers: ヘッダー行がない Excel の場合に、列名のリストをここで付ける。
             指定すると read_rows_as_dicts() は全行をデータとして読む。

#### `read_cell`

```text
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
def read_rows(self, sheet_name: str, min_row: int=2) -> list[tuple]:
```

##### 説明

指定シートの行データをタプルのリストで返す。

Args:
    sheet_name: シート名。
    min_row: 読み始める行番号（デフォルト: 2 でヘッダーをスキップ）。

Returns:
    各行を値のタプルにしたリスト。

#### `read_rows_as_dicts`

```text
def read_rows_as_dicts(self, sheet_name: str, header_row: int=1) -> list[dict]:
```

##### 説明

ヘッダー行をキーとした辞書のリストで返す。

ヘッダー行がないファイルは ExcelComHandler(path, headers=[...]) で列名を指定すること。

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
def last_row(self, sheet_name: str) -> int:
```

##### 説明

データが存在する最終行の行番号を返す。

UsedRange を使うため、数式が入ったセルも含めて正確に最終行を取得できる。

Args:
    sheet_name: シート名。

Returns:
    最終行の行番号（1始まり）。

#### `transfer_by_mapping`

```text
def transfer_by_mapping(self, sheet_name: str, key_col: str, lookup: dict[str, dict], mapping: dict[str, str], header_row: int=1) -> int:
```

##### 説明

列名で指定し、キーが一致した行に値を転記する（XLOOKUP 的転記）。

Excel の各行についてキー列の値を lookup のキーと突合し、
一致したら mapping に従って値を書き込む。
空行・キーが空の行・lookup に存在しないキーの行はスキップする。

Sheet.transfer_by_mapping() と同じ引数・対応表の向きであり、数式の再計算や
パスワード付き保存など COM が必要なブックに限ってこちらを使う。
ヘッダーがない、または列位置が固定された帳票には transfer_by_letter() を使う。
Args:
    sheet_name: シート名。
    key_col: 転記先 Excel で照合に使う列名。
    lookup: {キーの値: {列名: 値}} の辞書。CsvReader.index() 等で作る。
    mapping: {転記元の列名: 転記先の列名} の辞書。
    header_row: 転記先 Excel のヘッダー行番号（1始まり）。

Returns:
    転記した行数。

Raises:
    ExcelError: 行の処理に失敗した場合（メッセージに行番号を含む）。

#### `transfer_by_letter`

```text
def transfer_by_letter(self, sheet_name: str, key_col: int | str, lookup: dict[str, dict], mapping: dict[str, int | str], start_row: int=2) -> int:
```

##### 説明

列記号で指定し、キーが一致した行へ値を転記する。

ヘッダーがない、または列位置が仕様として固定された Excel に使う。
ヘッダー名で指定できる帳票には transfer_by_mapping() を使う。
mapping は両メソッド共通で ``{転記元の列名: 転記先}`` の向き。

#### `run_macro`

```text
def run_macro(self, macro_name: str) -> None:
```

##### 説明

VBA マクロを実行する。

Args:
    macro_name: 実行するマクロ名。"モジュール名.プロシージャ名" の形式で指定する。
                例: "Module1.UpdateData"

#### `save`

```text
def save(self) -> None:
```

##### 説明

元のファイルに上書き保存する。

close() は保存せずに閉じる（SaveChanges=False）ため、
write_cell や transfer_by_mapping での変更を残す場合は必ず呼ぶこと。

#### `save_as`

```text
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
    RuntimeError: ウィンドウが見つからない場合。

#### `activate`

```text
def activate(self) -> None:
```

##### 説明

ウィンドウを前面に表示する。最小化されている場合は復元する。

#### `get_title`

```text
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

#### `downloads`

```text
@staticmethod
def downloads() -> Path:
```

##### 説明

ダウンロードフォルダのパスを返す。

#### `desktop`

```text
@staticmethod
def desktop() -> Path:
```

##### 説明

デスクトップのパスを返す（OneDrive リダイレクトにも追従する）。

#### `temp_dir`

```text
@staticmethod
def temp_dir() -> Path:
```

##### 説明

システムの一時フォルダのパスを返す。

### `is_excel_running`

```text
def is_excel_running() -> bool:
```

#### 説明

EXCEL.EXE プロセスが存在するか返す。

画面に見えない孤立プロセスも、ユーザーが開いている Excel も区別せず検出する。

### `kill_excel`

```text
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

CsvReader / CsvWriter の encoding 引数に使う定数。

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

### `SortBy`

```text
class SortBy:
```

#### 説明

FileFinder.latest() の by 引数に使う定数。
