# Excel の表を設定として使う（master_table）

[README（ドキュメントの入口）へ戻る](../README.md)

「どのレポートを取るか」「どのファイルをコピーするか」のように、**行が増えていく設定**は
config.ini より Excel の表のほうが扱いやすい（並べ替え・フィルタ・コピーができ、
非エンジニアが慣れている）。その表を**型付きの行**として読み込む仕組み。

---

## 使い方

**1列につき1行を宣言するだけ。** そのまま貼って使えます。

```python
from dataclasses import dataclass
from pathlib import Path

from comken.toolbox.master_table import MasterRow, column


@dataclass(frozen=True)
class Item(MasterRow):
    """コピー一覧の1行。"""

    SHEET_NAME = "一覧"
    PATH = Path(r"\\server\share\コピー一覧.xlsx")   # 省略可（load(パス) で渡してもよい）

    key: int = column("ID", unique=True, help="社内で決める管理番号")
    name: str = column("名前", help="人が読んで分かる名前")
    source: Path = column("コピー元", help="共有サーバー上のファイル")
    mode: str = column("方式", choices=("毎日", "手動"), help="毎日は自動で取ります")
    enabled: bool = column("有効", default=True, help="使わなくなったら「無効」")
```

```python
Item.create_template(path)      # 記入例と「記入方法」シート付きの雛形を作る

for item in Item.load():        # 読む（型変換・検証込み）
    print(item.name, item.source)
```

**Python の名前は英語、Excel の見出しは日本語**にできます。`column()` の第1引数が
見出しで、`Salesforce URL` のように**スペースを含む見出し**（識別子にできない名前）も扱えます。

| Python 側 | Excel 側 |
|---|---|
| `item.name` | 「名前」列 |
| `item.source`（`Path` 型） | 「コピー元」列 |

---

## `column()` に書けること

| 引数 | 何をするか |
|---|---|
| 第1引数 | **Excel の見出し**（必須） |
| `help` | 何を書く列かの説明。**「記入方法」シートとエラーメッセージに出る** |
| `unique` | 同じ値が2つ以上あればエラー（管理番号など） |
| `choices` | 書ける値を限る（`("毎日", "手動")`） |
| `default` | 空欄のときの値。**省略すると空欄はエラー** |

**型は注釈から決まります**（`int` / `str` / `bool` / `Path`）。`bool` は「有効」「○」「yes」などを
True として読みます。

---

## なぜこの形か

**列の定義を1か所にする。** 以前は「読み込み結果の dataclass」と「列名の定数」を別々に持っていて、
**片方だけ直すとズレました**（Excel を編集したのに読まれない、という分かりにくい失敗になる）。
宣言を1つにすれば、雛形・読み込み・検証・記入方法シートが**必ず同じ列**を見ます。

**辞書で読まない。** `read_rows_as_dicts()` でも読めますが、使う側が毎回 `row["名前"]` と
文字列で書くことになり、**打ち間違いが実行時まで分かりません**。宣言しておけば `item.name` で
補完が効きます。

**エラーは行と列を示す。** 非エンジニアが編集する表なので、「どこが、なぜ駄目か」を出します。

```
管理表 3 行目の「方式」が正しくありません: '毎週'
「毎日」か「手動」と書いてください。
```

---

## 雛形（`create_template`）

- 記入例を入れられる（**空の表を渡されるより、1行埋まっているほうが何をどう書くか伝わる**）
- **「記入方法」シート**が付く。列ごとに `help` と「空欄にできるか／書ける値」が並ぶ
- Excel のテーブルにする・列幅を整える・見出しを固定する

```python
Item.create_template(path, examples=[{"key": 1001, "name": "受注一覧", ...}])
```

---

## エラー

| エラー | いつ | 対処 |
|---|---|---|
| `MasterColumnNotFoundError` | 宣言した見出しが表に無い | 1行目の見出しを元に戻す |
| `MasterRowValueError` | 値が型・選択肢に合わない、空にできない列が空 | メッセージの行と列を直す |
| `MasterDuplicateValueError` | `unique` の列に同じ値がある | どちらかを変える |
| `MasterSheetNotDefinedError` | `load()` を引数なしで呼んだが `PATH` が無い | `load(パス)` を使うか `PATH` を書く |

---

## 使っているところ

- [Salesforce レポートの集約取得](salesforce-downloader.md) — `ReportEntry` が
  管理表（ID / 概要 / Salesforce URL / 実行方式 / 保存先 / 有効）を宣言している

---

## 関連

- [README](../README.md) — ライブラリ全体の概要
- [Excel](excel.md) — この仕組みが使っている読み書きの部品
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
