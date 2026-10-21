# Access 操作

[README（ドキュメントの入口）へ戻る](../../README.md)

README の「Access」から移した、モジュールを使うときの詳しい説明です。

## Access

Access がインストールされた Windows PC で、マクロや VBA による整形結果を CSV に出力する。
数十万件では `rows()` の結果をリスト化せず、Python のメモリを使わない `export_csv()` を使う。
既定の文字コードは Excel で開きやすい CP932。`utf-8-sig` も指定できる（`utf8-sig` / `utf-8-bom` などの表記ゆれは `comken.core.encoding.normalize_encoding` が吸収する）。
既定では DB を一時フォルダへコピーして開き、終了時にコピーとロックファイルを削除する。
NAS・共有フォルダ・クラウド同期フォルダを直接開かないため、速度・排他・破損リスクを抑えられる。

```python
from comken.toolbox.access import AccessDatabase

with AccessDatabase(r"C:\作業\顧客.accdb") as db:
    db.run_macro("日次整形")  # Access マクロ
    db.run_function("集計処理", "東日本")  # VBA のプロシージャ／関数
    db.run_query("QA_日次更新")  # 保存済みの更新・追加・削除・テーブル作成クエリ
    db.export_csv("T_出力", r"C:\作業\顧客.csv", encoding="cp932")

    for row in db.iter_rows("T_出力"):  # Python 側で逐次処理するときだけ
        ...
```

`table_names()` で利用可能なテーブルと保存済みクエリを確認できる。外部に影響する
マクロ・VBA・CSV 出力は `dry_run()` 中には実行されない。

---

## SQL は Access の保存済みクエリに置く

Access で使う SQL は、**すべて Access の保存済みクエリに置く**（パススルークエリも
Access に保存する）。Python には SQL 文字列を書かず、**クエリの名前と、値（日付など）
だけ**を渡す。保存済みクエリが SQL を持ち、`AccessDatabase` のメソッドは名前を受け取る。

理由:

- **Access のクエリデザイナーで見て直せる。** SQL を Access に置いておけば、条件を
  確かめる場所も直す場所も 1 つにまとまる
- **Python で文字列をつなぎ直さなくてよい。** 値を埋め込むための引用符・日付の書式・
  NULL の扱いを Python 側で持たずに済む
- **置き場の揺れをなくす。** SQL は Access、Python は「どのクエリを使うか・何の値を
  渡すか」だけを持つ、という分け方が 1 つに決まる

## クエリの名前の付け方（推奨）

名前の**先頭は大文字の種別 + `_`**、そのあとに内容を日本語か英語で書く。

| 種別 | 先頭 | 例 | 使う comken のメソッド |
|---|---|---|---|
| テーブル | `T_` | `T_売上` | `read_table` / `export_csv` / `iter_rows` |
| 選択クエリ（読み取りだけ） | `Q_` | `Q_売上_期間` | `read_table` / `export_csv` / `iter_rows` |
| アクションクエリ（追加・更新・削除・テーブル作成） | `QA_` | `QA_売上_日次追加` | `run_query` |
| パススルークエリ（社内 DB 側の書き方の SQL） | `QP_` | `QP_Oracle_売上` | `read_table` / `export_csv` / `iter_rows` |
| マクロ | `M_` | `M_日次整形` | `run_macro` |

**クエリの名前に番号は付けない。** 連番を付けると「`QA_01` → `QA_02` → `QA_03`」を実行順に
読むことになるが、**実行順はマクロ側に書く**ため、番号は並び替えたいときに足枷になる（→ [次の節](#クエリを動かす順番マクロに書く)）。

理由:

- **大文字 + `_` なら種別がひと目で分かる。** Access は大文字小文字を区別しないので
  並び順には影響しない
- **`Q_` なら、内容語が `Q` で始まるクエリ（`Q_Quarterly_売上`）と混ざらない**
- **`QA_` だけを実行するとデータが変わる。** `run_query` に渡すクエリが、名前だけで
  「この実行はデータを変更する」と分かる
- **`QP_` は Access の SQL ではなく社内 DB の書き方**なので、管理する対象が違う。
  `Q_` と同じ扱いにすると「どちらの SQL を読むクエリか」が分からなくなる
- **Access が自動的に付ける `クエリ1` / `Query1` のままにしない**（種別も内容も読めない）
- **空白・記号を避ける。** `~` で始まる名前は Access の内部用
- **値を渡すクエリは、使う TempVars の名前をクエリの説明（プロパティの説明）に書いておく**
  （`Q_売上_期間` の説明に「開始日・終了日」と書けば、Python 側を見なくても分かる）

## クエリを動かす順番（マクロに書く）

**Access の中で完結する連続実行は、すべて Access のマクロ（`M_`）に書く。Python は
`run_macro("M_...")` を呼ぶだけ。** Python の側でクエリを 1 本ずつ順に動かさない。

理由:

- **RPA が止まったとき、人間が Access を開いてマクロを実行すれば同じ結果になる。**
  RPA（タスクスケジューラから走らせる Python）は便利だが、止まるときは必ず止まる。
  止まった後に **人が同じ手順で同じ結果を出せなければ、復旧できない**
- **実行順を見るとき、マクロを開けば上から読める**。順番を変えるときはマクロの行を
  入れ替えるだけ。クエリの名前に番号を振って依存させる必要がない
- **値の既定をマクロの中に置ける。** 「開始日が未設定なら `Date()-1`」のような既定を
  マクロ側で決めているため、Python から値を渡さなくても手で動く

### マクロの書き方

- **先頭で警告の表示を切る**: 1 行目に `SetWarnings` を「いいえ」にする。
  切らないと、追加・更新クエリの確認ダイアログで止まる
- **Python からマクロの途中経過が見えない**: マクロ全体としての所要時間しか外から見えない。
  工程ごとの件数をログに出したくなったら、その工程だけを Python のリストに戻す
- **エラーを握りつぶさない**: マクロ内に `OnError` で「次へ」相当の設定を入れない。
  Python が失敗を検知できなくなる
- **マクロ名・説明に「何をするか」と「手で動かしてよいか」を書く**:
  名前: `M_日次`, 説明: `日次の売上取り込み〜重複削除まで。RPA から呼ばれる。手で動かしても同じ結果になる`

```text
擬似コード:
  SetWarnings いいえ
  開始日 が未設定なら → TempVars!開始日 = Date() - 1
  QA_売上取り込み を実行
  QA_重複削除 を実行
  QA_集計 を実行
```

### Python から呼ぶ

```python
from datetime import date
from comken.toolbox.access import AccessDatabase

with AccessDatabase(r"C:\作業\顧客.accdb") as db:
    # 既定のままでよいとき（マクロが Date()-1 を使う）
    db.run_macro("M_日次")

    # 過去分をやり直すときだけ、値を上書きして渡す
    db.set_temp_vars({"開始日": date(2026, 9, 1), "終了日": date(2026, 9, 30)})
    db.run_macro("M_月次")
```

### 例外: Python から直接呼んでよい

- **読み取り**（`read_table("Q_...")` / `export_csv` / `iter_rows`）は Python から直接呼んでよい
- **単発の更新クエリ 1 本**を `run_query` で動かすのもよい
- **RPA から動かしにくい連続処理**（分岐・ループを挟むもの）は Python に残してよい。
  その場合、工程ごとの所要時間を Python のログに書ける

### マクロの変更を Git で追えないこと

`.accdb` はバイナリなので、マクロの差分は Git で見えない。**マクロを変更したら、
マクロの説明欄に「YYYY-MM-DD: 〇〇を追加 / 〇〇を修正」のように日付と内容を 1 行追記する**
運用にする（マクロ一覧を `accdb` から CSV に書き出してコミットする運用でもよい）。

## 値を渡す（TempVars）

**マクロが値の既定を決めるため、Python 側からは「上書きしたいときだけ」
`set_temp_vars()` を呼ぶ。** 未指定の値はマクロ側で決めるので、Python が値を渡さなくても
マクロは手で動かしても RPA から動かしても同じ結果になる。

`set_temp_vars()` で Access の `TempVars` に名前と値を設定し、保存済みクエリは
`[TempVars]![名前]` で参照する。

```python
from datetime import date

with AccessDatabase(r"C:\作業\顧客.accdb") as db:
    db.set_temp_vars({"開始日": date(2026, 10, 1), "終了日": date(2026, 10, 31)})
    table = db.read_table("Q_売上_期間")
```

条件は Access 側のクエリに書く（Python には書かない）:

```sql
WHERE 日付 >= [TempVars]![開始日] AND 日付 <= [TempVars]![終了日]
```

- 渡せる型は `str` / `int` / `float` / `bool` / `date` / `datetime`
- `date` は **その日の 0 時の日時** として渡す（COM が `date` を受け取れないため）。
  `datetime` は変換せずそのまま渡す
- **`None` は渡せない。** Access の `TempVars` は null も配列も持てない
- 同名の名前をもう一度設定すると上書きされる。すべて取り除くには `clear_temp_vars()`
- 設定した値は `AccessDatabase` を閉じると消える（ファイルには残らない）
- **値そのものはログにも例外メッセージにも出さない**（顧客情報になりうるため）。
  エラーになったときのメッセージには名前と型だけが載る
- `dry_run()` 中も実行する（セッション内の設定で、外部には影響しない）

## 実機で未確認の点

**保存済みクエリが `TempVars` を `OpenRecordset` / `DoCmd.TransferText` の中で解決できるかは、
Access が入った PC で未確認**（この機能を組み立てた PC には Access が入っていないため）。
最初に使う前に、次の手順で確かめる。

1. Access に `T_確認` テーブルと、`[TempVars]![値]` を条件に使う `Q_確認` を作る
2. `db.set_temp_vars({"値": 1})` のあと、`db.read_table("Q_確認")` と
   `db.export_csv("Q_確認", CSV のパス)` を実行する
3. 期待した行だけが返ることを確認する

うまくいかなかったときは、値を `TempVars` 経由ではなく Access のマクロ・VBA 側へ渡す形に
切り替える。**そのままにせず、comken の担当者へ連絡する**（Access のバージョンと
クエリの定義が分かると切り分けられる）。

---

## 関連

- [README](../../README.md) — ライブラリ全体の概要と環境構築
- 公開 API — 型ヒント付き署名・引数・戻り値・例外（`python tools\export_for_chat.py` で生成。git では管理しない）