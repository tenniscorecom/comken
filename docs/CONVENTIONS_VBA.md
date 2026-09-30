# コーディング規約（VBA）

[CONVENTIONS_COMMON.md](CONVENTIONS_COMMON.md)（共通） を読んだ前提で、VBA（Excel マクロ）固有のルールを書きます。
[CONVENTIONS_PYTHON.md](CONVENTIONS_PYTHON.md) と同じ考え方で作っているので、章の並びもできるだけ揃えています。

---

## 目次

1. [基本方針](#1-基本方針)
2. [命名規則](#2-命名規則)
3. [型の宣言](#3-型の宣言)
4. [定数とマジックナンバー](#4-定数とマジックナンバー)
5. [分岐の書き方](#5-分岐の書き方)
6. [エラー処理](#6-エラー処理)
7. [利用者への知らせ方とログ](#7-利用者への知らせ方とログ)
8. [コメント](#8-コメント)
9. [設定（設定シート）](#9-設定設定シート)
10. [後片付け](#10-後片付け)
11. [値のまとめ方（Enum・Type）](#11-値のまとめ方enumtype)
12. [モジュール内の並び順](#12-モジュール内の並び順)
13. [プロシージャの大きさ](#13-プロシージャの大きさ)
14. [ブック・シート・セルの指定](#14-ブックシートセルの指定)
15. [日付の扱い](#15-日付の扱い)
16. [動作確認](#16-動作確認)
17. [ファイルとコードの管理](#17-ファイルとコードの管理)
18. [エディターの設定](#18-エディターの設定)

---

## 1. 基本方針

- すべてのモジュールの1行目に `Option Explicit` を書く
- 変数は必ず型を付けて宣言する（[3 章](#3-型の宣言)）
- `Select` / `Activate` を使わない（[14 章](#14-ブックシートセルの指定)）
- 字下げは半角スペース4つ。1行に1つの命令だけ書く（`:` で複数の命令をつなげない）

`Option Explicit` は、宣言していない変数を使うとエラーにしてくれる設定です。
これが無いと、変数名を1文字打ち間違えただけで「空の新しい変数」として動き続け、間違いに気付けません。
[18 章](#18-エディターの設定)の設定をすれば、新しいモジュールに自動で入ります。

## 2. 命名規則

| 種類 | 書き方 | 例 |
|---|---|---|
| プロシージャ（Sub / Function） | PascalCase（単語の頭を大文字） | `ReadRows`, `SaveReport` |
| 変数・引数 | camelCase（最初だけ小文字） | `matchedCount`, `outputPath` |
| 定数 | UPPER_SNAKE_CASE（大文字＋`_`） | `SHEET_NAME`, `COL_AMOUNT` |
| モジュール | PascalCase で役割が分かる名前 | `SalesReport`, `Formatting` |
| ユーザーフォーム | 頭に `frm` | `frmSearch` |
| 名前付き範囲（設定シート） | UPPER_SNAKE_CASE | `INPUT_FOLDER` |
| VBA が書き換えるシート（データシート） | 頭に `VBA_` | `VBA_顧客` |
| VBA が作る・書き換える Excel のテーブル | 頭に `VBA_T_` | `VBA_T_顧客` |
| 人が見る表示用シート（帳票・設定） | 接頭辞なし | `集計`, `設定` |

シートとテーブルの接頭辞は、Python（comken）の `PY_` / `PY_T_` と対になる決まりです
（理由と「相手の接頭辞のシートは読むだけ」のルールは [共通規約 4 章](CONVENTIONS_COMMON.md#プログラムが管理するシートテーブルの名前)）。
comken と違って自動では付かないので、名前は定数にして必ず接頭辞込みで書きます。

```vba
Private Const SHEET_CUSTOMER As String = "VBA_顧客"
Private Const TABLE_CUSTOMER As String = "VBA_T_顧客"

Dim customerTable As ListObject
Set customerTable = ThisWorkbook.Worksheets(SHEET_CUSTOMER).ListObjects(TABLE_CUSTOMER)
```

- `Module1` / `Sheet1` / `CommandButton1` のような自動で付いた名前のままにしない
- シートには「オブジェクト名」（プロパティウィンドウの `(Name)`）も付ける（例: `shtSetting`）。
  コードからはタブの見出しではなくこの名前で呼ぶと、見出しを変えられても動く
- 動詞は Python と揃える（`Read` / `Save` / `Find` / `Create` / `Run`）

**Python と書き方が違う理由**: Python は関数・変数を snake_case にしますが、VBA では
プロシージャ名・変数名に `_` を入れません（シート名・テーブル名は Excel 側の名前なので `VBA_` を使ってよい）。VBA は `Worksheet_Change` や `CommandButton1_Click` のように
「`_` の左がオブジェクト、右がイベント」という決まりで `_` を使っているため、
自分の名前に `_` を入れると区別がつかなくなります。定数だけは大文字で目立たせたいので、Python と同じ UPPER_SNAKE_CASE にします。

**注意**: VBA のエディターは、同じ綴りの名前の大文字・小文字をブック全体で勝手に揃えます。
変数に `name` と付けると、あちこちの `.Name` が `.name` に変わってしまいます。
`Name` / `Value` / `Range` など Excel がもともと使っている単語は、そのまま変数名にしないでください。

## 3. 型の宣言

すべての変数・引数・Function の戻り値に型を付けます。
Python の型ヒントと同じく、型が書いてあれば中身を読まなくても使い方が分かります。

```vba
' 悪い（型が無いと、何が入るか分からない）
Function FindLastRow(ws)

' 良い
Private Function FindLastRow(ByVal targetSheet As Worksheet) As Long
```

| ルール | 理由 |
|---|---|
| 整数は `Integer` ではなく `Long` を使う | `Integer` は 32,767 までしか入らず、行番号で簡単にあふれる |
| 1行に1つずつ宣言する | `Dim a, b As Long` と書くと、`b` だけが `Long` で `a` は型無しになる |
| 引数には `ByVal` を明記する | 何も書かないと `ByRef` になり、呼ばれた側で書き換えた値が呼び出し元まで変わってしまう |
| `ByRef` は「呼び出し元の変数を書き換えるのが目的」のときだけ明記して使う | 書き換わることを読む人に知らせる |
| 変数は使う直前で宣言する | 宣言と使う場所が近いほうが読みやすい |
| `Variant` は原則使わない | 何でも入るため、間違った値が入っても気付けない |

`Variant` を使ってよいのは、セルの値をそのまま受け取るときと、範囲をまとめて配列に読み込むとき（[14 章](#14-ブックシートセルの指定)）だけです。

## 4. 定数とマジックナンバー

VBA では特に**列番号・行番号・セル番地**がマジックナンバーになりがちです。

```vba
' 悪い（5 列目が何か分からない。列が1つ増えたら全部ずれる）
Cells(i, 5).Value = Cells(i, 3).Value * 1.1

' 良い
Private Const COL_PRICE As Long = 3
Private Const COL_PRICE_WITH_TAX As Long = 5
Private Const TAX_RATE As Double = 0.1

dataSheet.Cells(rowIndex, COL_PRICE_WITH_TAX).Value = _
    dataSheet.Cells(rowIndex, COL_PRICE).Value * (1 + TAX_RATE)
```

- 定数はモジュールの先頭にまとめる
- そのモジュールの中でしか使わない定数は `Private Const`、他のモジュールでも使う定数は `Public Const`
- 列の並びが変わりやすい表では、列番号を定数にするより、**見出しの文字で列を探す**ほうが壊れにくい

```vba
Private Const HEADER_ROW As Long = 1

' 見出しの文字から列番号を探す。見つからなければ 0 を返す
Private Function FindColumn(ByVal targetSheet As Worksheet, ByVal headerText As String) As Long
    Dim foundCell As Range
    Set foundCell = targetSheet.Rows(HEADER_ROW).Find( _
        What:=headerText, LookIn:=xlValues, LookAt:=xlWhole)
    If foundCell Is Nothing Then
        FindColumn = 0
        Exit Function
    End If
    FindColumn = foundCell.Column
End Function
```

## 5. 分岐の書き方

| 場面 | 書き方 |
|---|---|
| 前提条件・エラー条件 | 最初に弾いて `Exit Sub` / `Exit Function` で抜ける（ガード節） |
| 決まった値の中から1つを選ぶ | `Select Case` |
| 2通りに分けるだけ | `If` / `Else` |

```vba
' 良い（おかしい場合を先に片付けると、本筋が深く字下げされない）
Public Sub FormatReport()
    If dataSheet.Cells(2, 1).Value = "" Then
        MsgBox "データがありません。貼り付けてから実行してください。", vbExclamation
        Exit Sub
    End If

    ' ここから本筋
End Sub
```

`If` の中に `If` を何段も重ねず、分岐が増えたら別のプロシージャへ切り出してください。

## 6. エラー処理

Python の `try` / `except` / `finally` にあたる形を、決まった型で書きます。
**利用者がボタンで直接動かすプロシージャには、必ずこの型を入れます。**

```vba
Public Sub FormatReport()
    On Error GoTo ErrHandler
    Application.ScreenUpdating = False

    ' 本処理

Cleanup:
    ' ここは成功しても失敗しても必ず通る（Python の finally）
    Application.ScreenUpdating = True
    Exit Sub

ErrHandler:
    MsgBox "書式の設定に失敗しました。" & vbCrLf & _
        "場所: FormatReport" & vbCrLf & _
        "理由: " & Err.Description, vbCritical
    Resume Cleanup
End Sub
```

| ルール | 理由 |
|---|---|
| エラーが起きたら `Resume Cleanup` で後片付けへ飛ぶ | 画面更新を止めたまま終わると、Excel が固まったように見える |
| `On Error Resume Next` を付けっぱなしにしない | 以降のエラーがすべて無視され、失敗しても成功したように見える（Python の `except: pass` と同じ） |
| `On Error Resume Next` を使うなら、直後で `Err.Number` を確かめて、すぐ `On Error GoTo 0` で戻す | 無視してよいのはその1行だけに限る |
| エラーメッセージには何が・どこで・なぜを入れる | [共通規約 7 章](CONVENTIONS_COMMON.md#7-エラーを隠さない) |

```vba
' 「シートが無ければ Nothing」を調べたいときの、許される On Error Resume Next
Dim targetSheet As Worksheet
On Error Resume Next
Set targetSheet = ThisWorkbook.Worksheets(SHEET_NAME)
On Error GoTo 0
If targetSheet Is Nothing Then
    MsgBox "シート「" & SHEET_NAME & "」が見つかりません。", vbExclamation
    Exit Sub
End If
```

自分でエラーを起こすときは `Err.Raise` を使い、番号は `vbObjectError + 番号` にします。

## 7. 利用者への知らせ方とログ

| 用途 | 使うもの |
|---|---|
| 処理の結果・エラーを利用者に伝える | 最後に `MsgBox` を**1回だけ** |
| 開発中に値を確かめる | `Debug.Print`（確かめ終わったら消す） |
| あとから追えるように記録を残す | 「ログ」シートへ1行ずつ書き足す |

- ループの中で `MsgBox` を出さない（100 件あれば 100 回押させることになる）
- 終わったら件数を伝える（「52 件を転記しました。スキップ 3 件」）。件数が分かれば、利用者が結果を確かめられる
- `Debug.Print` を残したまま配らない（Python の `print` 禁止と同じ理由で、残すと本当に必要な情報が埋もれる）

## 8. コメント

「なぜ」を書きます（[共通規約 6 章](CONVENTIONS_COMMON.md#6-コメントにはなぜを書く)）。

- コメントは `'` で書く（`Rem` は使わない）
- 公開するプロシージャ（`Public`）の上には、何をするかを1行で書く

```vba
' 売上表の書式を整える。貼り付け直後のデータに対してボタンから実行する
Public Sub FormatReport()
```

## 9. 設定（設定シート）

非エンジニアが触る値・頻繁に変わる値は、ブック内の「設定」シートへ出します（Python の `config.ini` にあたる）。

- A 列に項目名、B 列に値を書く。値のセルには**名前付き範囲**（例: `INPUT_FOLDER`）を付ける
- コードからは名前付き範囲で読む。セル番地（`B3` など）で読まない（行を挿入されても壊れない）
- 設定シートにはパスワード・個人情報を書かない（[共通規約 10 章](CONVENTIONS_COMMON.md#10-パスワード個人情報を書かない)）

```vba
Dim inputFolder As String
inputFolder = ThisWorkbook.Names("INPUT_FOLDER").RefersToRange.Value
```

## 10. 後片付け

開いたもの・切り替えた設定は、成功しても失敗しても必ず元に戻します。
[6 章](#6-エラー処理)の `Cleanup:` にまとめて書きます。

| 変えたもの | 元に戻す |
|---|---|
| `Workbooks.Open` で開いたブック | `.Close SaveChanges:=False`（保存するなら明示して `True`） |
| `Application.ScreenUpdating = False` | `True` に戻す |
| `Application.Calculation = xlCalculationManual` | `xlCalculationAutomatic` に戻す |
| `Application.EnableEvents = False` | `True` に戻す |
| `Application.DisplayAlerts = False` | `True` に戻す |
| `CreateObject` で作ったオブジェクト | 閉じてから `Set 変数 = Nothing` |

```vba
Cleanup:
    If Not sourceBook Is Nothing Then sourceBook.Close SaveChanges:=False
    Application.ScreenUpdating = True
    Application.EnableEvents = True
    Exit Sub
```

`DisplayAlerts = False` は「上書きしますか？」などの確認を全部消すので、必要な1行の前後だけで使います。

## 11. 値のまとめ方（Enum・Type）

| やりたいこと | 使うもの | 例 |
|---|---|---|
| 関連する数値の定数（列番号など）に名前を付けて並べる | `Enum` | 表の列番号の一覧 |
| 1つだけの定数 | `Const` | `SHEET_NAME` |
| 複数の値をひとまとめにして持ち運ぶ | `Type` | 集計結果 |

```vba
Private Enum OrderColumn
    COL_ORDER_ID = 1
    COL_CUSTOMER = 2
    COL_AMOUNT = 3
End Enum
```

Python 規約では `Enum` を使いませんが、VBA の `Enum` はただの数値の定数として書けて `.value` のような付け足しも要らないので使ってかまいません。
Function から返したい値が3個以上になったら、`ByRef` 引数を増やさずに `Type` にまとめてください。

## 12. モジュール内の並び順

1. `Option Explicit`
2. モジュールの説明コメント（何のためのモジュールか1〜2行）
3. 定数・`Enum`・`Type`
4. モジュール全体で使う変数（必要なときだけ）
5. `Public` のプロシージャ（ボタンから呼ばれる入口）
6. `Private` のプロシージャ（それを使うプロシージャのすぐ下に置く）

- 他のモジュールから呼ばないプロシージャは必ず `Private` にする（Python の `_` 始まりにあたる）。
  `Public` の一覧が、そのモジュールの使い方の一覧になる
- 1つのモジュールには1つの役割だけを入れる（書式・転記・集計などで分ける）
- シートモジュール・`ThisWorkbook` にはイベント処理（`Worksheet_Change` など）だけを書き、本体は標準モジュールに置く

## 13. プロシージャの大きさ

- 1つのプロシージャは1つの仕事だけをする。名前に「と」が入りそうなら分ける
- 目安は画面に収まる長さ（50 行程度）。字下げが4段を超えたら、ガード節か切り出しで浅くする
- 引数は多くても5個まで。それ以上なら `Type` にまとめる
- `GoTo` はエラー処理（`ErrHandler` / `Cleanup`）以外で使わない

## 14. ブック・シート・セルの指定

**どのブックの、どのシートの、どのセルか**を毎回はっきり書きます。

| ルール | 理由 |
|---|---|
| `Select` / `Activate` / `Selection` を使わない | 実行中にクリックされると、別のシートへ書き込んでしまう。遅くもなる |
| `ActiveSheet` / `ActiveWorkbook` に頼らない | どれがアクティブかは実行するたびに変わる |
| 自分のブックは `ThisWorkbook` で指す | マクロが入っているブックを確実に指せる |
| シートは変数に入れてから使う | 毎回の長い指定が消えて読みやすくなる |
| `Cells` / `Range` の前には必ずシートを付ける | 何も付けないと、アクティブなシートを指してしまう |

```vba
' 悪い
Sheets("売上").Select
Range("A1").Select
Selection.Value = "合計"

' 良い
Dim salesSheet As Worksheet
Set salesSheet = ThisWorkbook.Worksheets(SHEET_SALES)
salesSheet.Range("A1").Value = "合計"
```

**大量のセルを扱うときは配列でまとめて読み書きします。** セルを1つずつ読み書きすると、
1万行で数分かかることがあります。範囲をまとめて配列に入れて、計算してから一度に書き戻せば数秒で終わります。

```vba
Dim values As Variant
values = salesSheet.Range("A2:E" & lastRow).Value  ' まとめて読む

Dim rowIndex As Long
For rowIndex = 1 To UBound(values, 1)
    values(rowIndex, COL_PRICE_WITH_TAX) = values(rowIndex, COL_PRICE) * (1 + TAX_RATE)
Next rowIndex

salesSheet.Range("A2:E" & lastRow).Value = values  ' まとめて書き戻す
```

最終行は `Cells(Rows.Count, 列).End(xlUp).Row` で求めます。`UsedRange` は書式が残っているだけの行まで含むので使いません。

## 15. 日付の扱い

- 日付は `Date` 型で扱い、文字列のまま計算・比較しない
- 表示やファイル名にするときだけ `Format(日付, "yyyy-mm-dd")` で文字列にする。書式は定数にする
- セルから読んだ値が日付か確かめるときは `IsDate` を使う

## 16. 動作確認

- 変更したら、必ず**コピーしたブック**で動かして確かめる（マクロの変更は Ctrl+Z で戻せない）
- 確かめる観点を書いておく: 普通のデータ・データが0件・想定外の値が入った行・最後の行
- 何を確かめたかを、変更の記録（[17 章](#17-ファイルとコードの管理)）に残す

## 17. ファイルとコードの管理

- マクロ入りのブックは `.xlsm` で保存する
- 配る前に「デバッグ」→「VBAProject のコンパイル」を実行し、エラーが出ないことを確かめる
- 変更の履歴を残したいときは、モジュールを右クリック →「ファイルのエクスポート」で `.bas` に書き出し、Git で管理する。
  ブック（`.xlsm`）はそのままでは中身の差分が見えないため
- 大きく変える前に、ブックのコピーを日付付きで残す（例: `売上集計_2026-09-30.xlsm`）

## 18. エディターの設定

VBA のエディター（Alt+F11）で「ツール」→「オプション」を開き、次の設定にします。

| 設定 | 値 | 理由 |
|---|---|---|
| 変数の宣言を強制する | オン | 新しいモジュールに `Option Explicit` が自動で入る |
| 自動構文チェック | オフ | 1行打つたびにエラーの窓が出るのを止める（間違いは赤字で分かる） |
| タブ間隔 | 4 | 字下げを半角スペース4つに揃える |
