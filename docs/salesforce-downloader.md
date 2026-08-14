# Salesforce レポートの集約取得（salesforce_downloader）

[README（ドキュメントの入口）へ戻る](../README.md)

各プロジェクトが個別に Salesforce からレポートを落としていると、**どのプロジェクトが
どのレポートを、どれくらいの頻度で取っているのか**が分からなくなる。取得をここへ集約し、
何を取っているかは**管理表（Excel）**に、いつ何を取ったかは**履歴（CSV）**に集める。

```
レポート管理表.xlsx（人が編集）        ダウンロード履歴.csv（プログラムが追記）
        ↓                                      ↑
  comken.services.salesforce_downloader  ──→ Salesforce
        ↓
  各プロジェクト（download_report / get_scheduled_report）
```

---

## 使う側

```python
from comken.services.salesforce_downloader import download_report, get_scheduled_report
from comken.toolbox.csv import CsvReader

CUSTOMER_LIST = 1001      # 管理表の「ID」。意味の分かる名前を付ける
SALES_RESULT = 1003

rows = CsvReader(download_report(CUSTOMER_LIST, "案件集計")).read_rows()
```

**プロジェクトのコードに Salesforce の URL もレポート ID も書かない。** 書くのは管理番号だけ。
参照先の Salesforce レポートを差し替えても、`CUSTOMER_LIST = 1001` はそのままでよい。

### 2つの関数の使い分け

| | 意味 | Salesforce へ問い合わせるか |
|---|---|---|
| `download_report(ID)` | **今この瞬間に取りに行く** | **必ず行く**（今日すでに取っていても取り直す） |
| `get_scheduled_report(ID)` | **定期取得しておいたものを受け取る** | **行かない**（無ければ例外） |

`get_scheduled_report()` は取りに行く関数ではない。まだ取れていなければ
`ScheduledReportNotDownloadedError` で止まる。**ここで自動的に取りに行くと、定期取得が
動いていないことに誰も気づかなくなる**ため。急ぐときは `download_report()` を呼ぶ。

1日に何度も最新が必要なプロジェクトは、`download_report()` を必要なときに呼ぶ。
Downloader 側に複雑なスケジュール（土日祝を除く等）は持たせない——それは
**呼び出す側のスケジュールにもともとある**ので、二重に持つと必ずズレる。

---

## 管理表（Excel）

**設定の正は Excel。** 内部 DB は持たず、呼ばれるたびに読み直す。

### 雛形を作る

```bat
python -m comken.services.salesforce_downloader init レポート管理表.xlsx
```

記入例2行と、各列の書き方をまとめた**「記入方法」シート**が入った状態で作られる。
**すでにあるファイルは上書きしない**（記入済みの管理表を消さないため）。

### 編集したあとに確かめる

```bat
python -m comken.services.salesforce_downloader check レポート管理表.xlsx
```

```
読めました: レポート管理表.xlsx
  登録 12 件（定期 8 件 / 無効 1 件）

同じ Salesforce レポートを指している管理番号があります:
  00O5g00000FGHIJ: 1002（売上実績）、1005（売上実績・別集計）
```

書き方の誤り（管理番号の重複、URL からレポート ID を取り出せない等）は取得のときにも
止まるが、**編集した直後にその場で分かる**ほうが直すのが早い。

> どちらも**保守用のコマンド**で、業務の定期実行ではない。毎日の取得は個別プロジェクトから
> `download_scheduled()` を呼ぶ（ライブラリには実行される単位を置かない）。

### 列

シート名は `管理表`。1行目が見出し。

| ID | 概要 | Salesforce URL | 実行方式 | 保存先 | 有効 |
|---|---|---|---|---|---|
| 1001 | 顧客一覧 | https://.../Report/00O5g00000ABCDE/view | 定期 | `\\server\A\input` | 有効 |
| 1002 | 売上実績 | https://.../Report/00O5g00000FGHIJ/view | 個別 | `\\server\B\input` | 有効 |

| 列 | 何を書くか |
|---|---|
| **ID** | 社内で決める管理番号（1001, 1002…）。**Salesforce のレポート ID ではない** |
| **概要** | 人が読んで分かる説明。保存するファイル名にも使う |
| **Salesforce URL** | レポートを開いたときのアドレスを**そのまま貼る** |
| **実行方式** | `定期`（毎日まとめて取る）か `個別`（呼ばれたときだけ） |
| **保存先** | 落としたファイルを置くフォルダ |
| **有効** | 使わなくなったら `無効`。行は消さない（履歴との対応が残る） |

### Salesforce のレポート ID は入力させない

URL を貼れば `report_id_from_url()` が取り出す。ID を人が抜き出す工程を挟むと**そこで
写し間違いが起きる**うえ、「どのレポートか」を確かめるには結局 URL を開くことになる。

### ID は Salesforce のレポートが変わっても変えない

`1001 → Report X` を `1001 → Report Y` に差し替えても、**利用側のコードは変えない**。
管理番号は「同じ意味のデータ」を指す論理的な番号で、参照先とは独立している。

### 同じレポートを複数の管理番号が指している場合

エラーにはせず、定期取得のときにログへ出す（意図している場合もあるため）。
コードから調べることもできる。

```python
from comken.services.salesforce_downloader import load_master, shared_report_ids

shared_report_ids(load_master(MASTER_PATH))
# → {"00O5g00000FGHIJ": [1002, 1003]}   1002 と 1003 が同じレポートを見ている
```

---

## 保存されるファイル

```
<保存先>\1001_顧客一覧_20260814.csv
```

**管理番号が先頭**なのは、概要や参照先の Salesforce レポートが変わっても番号は変わらないため。
概要を入れるのは、保存先を人が直接見たときに何のファイルか分かるようにするため。

- **0 行のときはファイルを作らない。** 空のファイルを置くと、使う側が「データが無い日」と
  「取得が失敗した日」を区別できなくなる
- **保存先のフォルダが無ければ作らない。** 書き間違いのことが多く、勝手に作ると
  誰も読まない場所へ置き続けることになる
- 書き込みは一時ファイル（`~` で始まる）経由で置き換える。複数のプロジェクトが同時に
  呼んでも、読んでいる最中のファイルが半端な状態にならない

---

## 履歴（CSV）

**管理表とは別のファイルにする。** 管理表は人が Excel で編集し、履歴はプログラムが
書き足す。同じファイルにすると、人が開いている間はプログラムが保存できず、履歴が飛ぶか
管理表が壊れる。**書く主体が違うものは分ける。**

記録する列: 実行日時 / 管理番号 / 概要 / レポートID / URL / プロジェクト / 実行方式 /
成否 / Salesforce取得 / 保存先 / ファイル名 / 取得件数 / 処理秒数 / エラー内容

この履歴から、あとで次のことが分かる。

- **どのプロジェクトが、どのレポートを、どれくらいの頻度で使っているか**
- **同じ Salesforce レポートを複数のプロジェクトが取りに行っていないか**
- Salesforce へ実際に何回問い合わせたか（＝ API をどれだけ使っているか）
- 失敗がいつ・何回起きているか

「本日の定期取得が済んでいるか」も履歴で判定する。保存先に今日の日付のファイルがあっても、
**それが定期取得で置かれたのか、誰かが個別に取ったのか、手で置いたのかは分からない**ため。

---

## 定期取得

**定期実行そのものは comken に置かない。** 実行される単位は個別プロジェクトの仕事で、
comken に置くのは呼ばれる側だけにする。

定期実行のプロジェクト側で、これを呼ぶだけでよい。

```python
from comken.services.salesforce_downloader import download_scheduled

def run() -> None:
    download_scheduled("定期実行")   # 管理表で「定期」かつ有効なものを全部取る
```

**1件失敗しても残りは続ける。** 5本のうち1本が落ちたときに全部やり直すと、手で用意する
手間が5本ぶんになる。失敗は履歴とログに残る。

---

## エラー

| エラー | いつ | 対処 |
|---|---|---|
| `ReportNotRegisteredError` | 管理番号が管理表に無い | 管理表に登録する |
| `ReportDisabledError` | 管理表で「無効」になっている | 使うなら「有効」に戻す |
| `DuplicateReportKeyError` | 管理表に同じ管理番号が2つある | どちらかの番号を変える |
| `InvalidReportEntryError` | 行の書き方が正しくない | メッセージの行と列を直す |
| `ScheduledReportNotRegisteredError` | 「個別」のものを定期取得済みとして受け取ろうとした | 「定期」にするか `download_report()` を使う |
| `ScheduledReportNotDownloadedError` | 本日の定期取得がまだ | 定期取得の結果を確認する |
| `ReportFileMissingError` | 履歴は取得済みだがファイルが無い | `download_report()` で取り直す |
| `EmptyReportError` | 明細が 0 行 | 本当に 0 件なら空の CSV を手で置く |
| `ReportFolderNotFoundError` | 保存先のフォルダが無い | 管理表の「保存先」を確認する |
| `ScheduledDownloadFailedError` | 定期取得で1件以上が失敗した | 履歴の「エラー内容」で理由を確認する |

`ScheduledDownloadFailedError` は**取得できたものを保存したうえで**送出する。
1件失敗しても残りは続けるが、ログだけ出して正常終了すると**スケジューラから見て成功と
区別が付かない**ので、最後に必ず知らせる。直したあと再実行すれば、残りだけが落ちる。

---

## 配置するときの設定

管理表と履歴の場所は **`comken/settings.py`** に書く。社内の値を持つファイルはここ1つだけ。

```python
# comken/settings.py
MASTER_PATH = Path(r"\\実際のサーバー\share\tools\salesforce\レポート管理表.xlsx")
HISTORY_PATH = Path(r"\\実際のサーバー\share\tools\salesforce\ダウンロード履歴.csv")
```

**設定を ini に分けない。** 設定がコードと ini に散ると、どちらを見ればよいか
分からなくなる。探す場所は1つにする（→ 仕様書「配置時に書き換える2ファイル」）。

---

## 関連

- [README](../README.md) — ライブラリ全体の概要
- [comken.salesforce](salesforce.md) — Salesforce API クライアント（この機能が使っている部品）
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
