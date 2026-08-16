# ブラウザ操作

[README（ドキュメントの入口）へ戻る](../README.md)

Edge を自動で動かして、社内システムから情報を取ったり入力したりするための仕組み。

**この文書の読み方**
- 「まず動かす」だけ読めば、1サイトの自動化は書ける
- サイトが増えたら「サイトを増やす」へ
- エラーが出たら「よくあるつまずき」へ

---

## 考え方

**1サイトにつき1ブラウザを起動する。タブでは分けない。**

タブで複数サイトを扱うと、次のものがすべてブラウザ単位で共有されてしまう:

- ダウンロード先フォルダ → サイトAのCSVがサイトBのフォルダに落ちる
- 起動オプション（証明書の扱い、ヘッドレス）→ サイトごとに変えられない
- ログイン状態 → 同じサイトを2アカウントで開けない

ブラウザを分ければ、これらはすべてサイトごとに独立する。
メモリは1つあたり 200〜400MB 増えるが、社内システムを数個扱う程度なら問題にならない。

### Salesforce の組織クラスと同じ形

サイトごとにクラスを作って固有の値をそこへ集める、という骨格は
[Salesforce の組織クラス](salesforce.md#クラス設計)とまったく同じ。
片方を読んでいれば、もう片方は形を知っているだけで読める。

| | Salesforce | ブラウザ |
|---|---|---|
| 土台（直接は使わない） | `SalesforceBase` | `Site` |
| 対象ごとのクラス | `Sandbox(SalesforceBase)` | `Kintai(Site)` |
| 固有の値の置き場 | `DOMAIN_URL` / `CREDENTIAL_PREFIX` | `NAME` / `BASE_URL` / `OPTIONS` |
| 機能は継承せず持たせる | `.auth` / `.report` / `.metrics` | `.session`（`BrowserSession`） |
| 単体で使う入口 | `with Sandbox() as sf:` | `with Kintai() as kintai:` |
| 複数まとめて扱う入口 | `sites/` の `site_for()` | `Browsers` |
| 画面／機能の分割 | `.report` / `.metrics` | `Page` のサブクラス |

**ブラウザ自体は継承しない。** サイトクラスがブラウザを継承する書き方
（`class 勤怠(Chrome)` のような形）もあるが、そうすると
ログイン状態や現在のページといった**状態がクラス側に載る**。
同じサイトを2つ同時に開いた瞬間に壊れるので、並列で動かせなくなる。
`SitePage` はセッションを**持つ**だけなので、同じサイトの2アカウントでも並べられる。

---

## まず動かす

1サイトだけなら、**サイトクラスをそのまま `with` に置く**。

```python
from .sites.kintai import Kintai


def main() -> None:
    with Kintai() as 勤怠:
        print(勤怠.login("user01", "password").unfilled_days())
```

`勤怠.login(...)` が返すのはログイン後の画面クラスなので、**そのまま次の操作へ繋がる**。
`LoginPage(session)` のように画面クラスへセッションを渡し直す必要はない。
Salesforce の `with Sandbox() as sf:` と同じ形。

途中の画面を変数に取れば、そこから何度も操作できる。

```python
with Kintai() as 勤怠:
    ホーム = 勤怠.login("user01", "password")
    未入力 = ホーム.unfilled_days()
    ホーム.勤怠入力(未入力[0]).保存()
```

**変数は「そこから何度も呼ぶとき」だけ作る。** 一度きりなら繋げて書く。
どの画面にいるかはメソッド名と戻り値の型で分かるので、変数名で管理しなくてよい。

`with` を抜けるとブラウザは必ず閉じる。途中でエラーが出ても閉じる。

**`with` は必須。** 使わずに書くとエラーで止まる。

```python
browsers = Browsers()
browsers.launch(Kintai)   # ← BrowsersNotStartedError（ブラウザは起動しない）
```

`with` を忘れるとエラーで落ちたときにブラウザのプロセスが残り続け、
次の実行で「ドライバーを上書きできない」といった別の問題を生むため。
弾かれた時点ではまだ何も起きていないので、`with` を付けて書き直せばよい。

---

## サイトを増やす

`launch` を1行足すだけ。ほかは何も変わらない。

```python
with Browsers() as browsers:
    勤怠 = browsers.launch(Kintai)
    経理 = browsers.launch(Keiri)          # ← 増えるのはこの行だけ

    未入力 = 勤怠.login(USER, PW).unfilled_days()
    未処理 = 経理.login(USER, PW).pending_rows()
```

サイトが2つ以上になったら `Browsers` を使う。1つだけなら `with Kintai() as 勤怠:` で足りる。

サイトクラスの `NAME`（`"kintai"`）は、次の3つを分ける鍵になる:

| 分かれるもの | 置き場所 |
|---|---|
| ダウンロードフォルダ | `DOWNLOAD_DIR/kintai/` |
| ログイン状態 | `PROFILE_ROOT/kintai/` |
| ログ・エラー画面 | `logs/error_kintai_20260803_101500.png` |

同じサイトに2つのアカウントでログインしたいときも、名前を分ければ混ざらない:

```python
class KintaiAdmin(Kintai):
    NAME = "kintai_admin"


class KintaiMember(Kintai):
    NAME = "kintai_member"


with Browsers() as browsers:
    admin = browsers.launch(KintaiAdmin)
    member = browsers.launch(KintaiMember)
```

`NAME` だけ変えたサブクラスを作る。URL もセレクターも継承されるので、書くのは1行。

---

## 待ち時間を使って別のことを進める

**書いた順に上から動くのが基本。** 何も指定しなければ、1行ずつ順番に終わってから次へ進む。

重い画面の読み込みを待っている間に別のことを進めたいときだけ、`start()` で先に始めておく。
結果が必要になったところで `wait()` で受け取る。

```python
with Browsers() as browsers:
    勤怠 = browsers.launch(Kintai)
    経理 = browsers.launch(Keiri)

    勤怠タスク = browsers.run_task(lambda: 勤怠.login(USER, PW).unfilled_days(), label="勤怠")

    未処理 = 経理.login(USER, PW).pending_rows()   # 勤怠の読み込み中にこちらが進む

    未入力 = 勤怠タスク.wait()                       # 戻って結果を受け取る
```

実際にこうなる（勤怠の open が8秒かかる場合）:

```
 0.0秒  勤怠   open（重い画面）…
 0.0秒  経理   ID入力
 1.0秒  経理   パスワード入力
 2.0秒  経理   ログインボタン
 3.0秒  経理   一覧取得
 4.0秒  経理   取得おわり
 8.0秒  勤怠   ★読み込み完了 → すぐ検索へ
 9.0秒  勤怠   取得おわり

合計 9.0秒（順番に書いたら 13.0秒）
```

勤怠が待っている間、ブラウザは何も消費していないので経理がその時間を使える。
そして読み込みが終わった瞬間、勤怠は誰の指示も待たずに自分で続きを始める。
**「終わったほうを優先する」ような指示を書く必要はない。**

| メソッド | 何をするか |
|---|---|
| `browsers.run_task(処理, label="名前")` | 裏で始めて、すぐ次の行へ進む。取っ手を返す |
| `取っ手.wait()` | 終わるのを待って結果を受け取る。すでに終わっていればすぐ返る |
| `取っ手.is_done` | 終わったかどうかだけ見る（待たない） |

`label` はログとエラーに出るので、付けておくと原因を追いやすい。

### 全部同時でよければ parallel が短い

「全部いっぺんに始めて、全部の結果が欲しい」だけなら、`start` と `wait` を並べる代わりに
1つにまとめられる。やっていることは同じ。

```python
未入力, 未処理 = browsers.parallel(
    lambda: 勤怠.login(USER, PW).unfilled_days(),
    lambda: 経理.login(USER, PW).pending_rows(),
)
```

結果は**渡した順**で返る（終わった順ではない）。

### 守ること

**裏で動かしている処理と、自分で書いている処理で、同じブラウザを触らないこと。**
同じブラウザを同時に触ると `ConcurrentSessionUseError` で止まる。
待たされるのではなく即エラーにしているのは、黙って壊れる（別の画面を操作していた）より、
早く気づけるほうが安全なため。

```python
勤怠タスク = browsers.run_task(lambda: 勤怠.login(USER, PW).unfilled_days())
経理.login(USER, PW).pending_rows()   # ⭕ 別のブラウザなので問題ない
勤怠.login(USER, PW)                  # ❌ 裏で使っている勤怠を触っている
```

`wait()` を呼び忘れたまま `with` を抜けても、ブラウザを閉じる前に処理の終了は待つ。
その処理が失敗していた場合はログに残る（黙って消えることはない）。

---

## 新しい社内システムを追加する手順

### 1. ファイルを作る

```
src/
  browser_options.py        ← サイトごとのオプションクラスを足す
  sites/
    kintai.py               ← サイトクラス（NAME・BASE_URL・入口の操作）
  pages/
    kintai/
      kintai_page.py        ← このサイトの画面に共通（セレクター・共通処理）
      login_page.py         ← 画面ごと
      home_page.py
```

**サイトクラスと画面共通クラスは別物。** サイトクラスは「どのサイトか」を表し、
画面共通クラスは「その画面群に共通の操作」を持つ。

### 2. オプションクラスを足す

```python
from comken.toolbox.browser import BrowserOptions


class KintaiOptions(BrowserOptions):
    DOWNLOAD_DIR = r"C:\作業\downloads"
    WAIT_SECONDS = 20
```

設定できる項目は `print(KintaiOptions())` で一覧できる（既定値との差分に `*` が付く）。

### 3. サイトクラスを作る

**ここが利用側の入口になる。** 固有の値と、最初にやる操作をここへ集める。

```python
from comken.toolbox.browser import Site

from ..browser_options import KintaiOptions
from ..pages.kintai.login_page import LoginPage


class Kintai(Site):
    """勤怠システム。"""

    NAME = "kintai"
    BASE_URL = "https://kintai.example.co.jp"
    OPTIONS = KintaiOptions

    def login(self, user_id: str, password: str) -> "HomePage":
        """ログインして、ログイン後の画面を返す。"""
        return LoginPage(self.session).login(user_id, password)
```

**入口の操作だけをサイトクラスに置く。** 画面ごとの操作は画面クラスへ。
ここに全部書くと、画面が増えるたびにこのクラスが膨らむ。

### 4. 画面に共通のクラスを作る

```python
from comken.toolbox.browser import Locator, SitePage


class KintaiPage(SitePage):
    """勤怠システムの画面に共通。全画面クラスはこれを継承する。"""

    BASE_URL = "https://kintai.example.co.jp"

    ERROR_MESSAGE = Locator.css(".alert-danger")

    def error_message(self) -> str:
        """画面上部のエラー表示を返す。"""
        return self.read_text(self.ERROR_MESSAGE)
```

### 5. 画面ごとのクラスを作る

セレクターは**クラスの先頭にまとめる**。画面の HTML が変わったとき、直す場所が一箇所に集まる。

```python
from comken.toolbox.browser import Locator

from .kintai_page import KintaiPage


class LoginPage(KintaiPage):
    USER_ID = Locator.id("userId")
    PASSWORD = Locator.id("password")
    LOGIN_BUTTON = Locator.css("button[type='submit']")

    def login(self, user_id: str, password: str) -> "HomePage":
        """ログインして HomePage を返す。"""
        from .home_page import HomePage

        self.go("/login")
        self.input(self.USER_ID, user_id)
        self.input(self.PASSWORD, password)
        self.click(self.LOGIN_BUTTON)
        return HomePage(self.session)
```

遷移先の import をメソッドの中に置いているのは、画面クラス同士が互いを参照して
循環インポートになるため（型注釈でも名前を使うなら `from __future__ import annotations` と
`TYPE_CHECKING` を合わせる）。

**画面が変わるメソッドは、遷移先の画面クラスを返す。** 呼ぶ側が画面の流れを
コードのまま追えるようになる:

```python
home = LoginPage(session).login(user_id, password)
days = home.open_attendance().unfilled_days()
```

### セレクターの選び方

上から順に、使えるものを使う。

| 順 | 書き方 | 備考 |
|---|---|---|
| 1 | `Locator.id("userId")` | いちばん壊れにくい |
| 2 | `Locator.name("userId")` | 入力欄はこれが使えることが多い |
| 3 | `Locator.css("table tr .name")` | id / name が無いとき |
| 4 | `Locator.xpath("//button[text()='検索']")` | 最終手段。文字で探すときだけ |

絶対 XPath（`/html/body/div[3]/...`）は使わない。画面に1つ要素が増えただけで壊れる。

### 一覧表を扱う

上から順に、やりたいことに合うものを選ぶ。

| やりたいこと | 書き方 |
|---|---|
| 全行の値を読む | `page.read_texts(page.ROW_NAMES)` |
| 件数だけ知りたい | `page.count_elements(page.ROWS)`（0件でもエラーにならない） |
| 何番目かをクリック | `page.click(page.EDIT_BUTTONS, index=2)` |
| 行ごとに中身を見て操作する | `page.find_elements(page.ROWS)` |

行の中をさらに探すときだけ `elements()` を使う。行の WebElement から絞り込む:

```python
def submit_unfilled_rows(self) -> int:
    """未提出の行だけ提出ボタンを押し、押した件数を返す。"""
    submitted = 0
    for row in self.find_elements(self.ROWS):
        if "未提出" in row.text:
            row.find_element(*self.SUBMIT_BUTTON).click()
            submitted += 1
    return submitted
```

`elements()` は1件も無いと `ElementNotFoundError` になる。
0件がありうる場面では、**表そのものが出るのを待ってから件数を数える**:

```python
def unfilled_names(self) -> list[str]:
    """未提出者の名前を返す。1件も無ければ空リストを返す。"""
    self.wait_visible(self.TABLE)      # 表が描画されるまで待つ
    if self.count_elements(self.ROWS) == 0:     # count は待たないので、先に上の行が要る
        logger.info("対象の行がありません")
        return []
    return self.read_texts(self.ROW_NAMES)
```

`count()` と `has()` は**その場で数えるだけで待たない**。
読み込みが終わる前に呼ぶと、「まだ描画されていない」を「0件だった」と読み違える。

なお、行が動的に増減する画面では、クリックのたびに一覧が作り直されて
掴んでいた WebElement が無効になることがある（`StaleElementReferenceException`）。
その場合は毎回取り直す形にする:

```python
for index in range(page.count_elements(page.ROWS)):
    page.click(page.EDIT_BUTTONS, index=index)
```

---

## ログイン状態を残す

`PROFILE_ROOT` を指定すると、Cookie とログイン状態がフォルダに残り、
次回の実行でログインを省ける。

```python
class KintaiOptions(BrowserOptions):
    PROFILE_ROOT = r"C:\作業\browser_profiles"
```

- 実際に使われるのは `PROFILE_ROOT/<セッション名>/` で、サイトごとに自動で分かれる
- シークレットモードは自動的に無効になる（Cookie を残さないため両立しない）
- ログインが必要かどうかは画面で判定する。「ログイン画面が出ていたらログインする」と書く

```python
def ensure_login(self, user_id: str, password: str) -> "HomePage":
    """ログイン済みならそのまま、未ログインならログインして HomePage を返す。"""
    from .home_page import HomePage

    self.go("/")
    if self.has_element(self.USER_ID):
        return self.login(user_id, password)
    return HomePage(self.session)
```

---

## ファイルをダウンロードする

ダウンロードフォルダはセッションごとに分かれている。完了待ちは `download_dir.wait()`。

```python
from comken.core import move_file

with Browsers() as browsers:
    kintai = browsers.launch("kintai", KintaiOptions)

    HomePage(kintai).export_csv()
    files = kintai.download_dir.wait()          # .crdownload が消えるまで待つ
    move_file(files[0], r"C:\作業\output")       # with の中で移動する
```

`DOWNLOAD_DIR` を指定していない場合は一時フォルダが使われ、**`with` を抜けると消える**。
残したいファイルは `with` の中で移動しておくこと。

---

## よくあるつまずき

### 要素が見つからない（`ElementNotFoundError`）

エラー本文に、どのセレクターで失敗したかが出る。上から順に疑う。

1. **画面が変わった** — F12 で実際の HTML を見て、セレクターを直す
2. **iframe の中にある** — `with page.frame(LOC):` で切り替える
3. **前の画面から遷移しきっていない** — `wait_visible` で目印の要素を待つ
4. **単に遅い** — `WAIT_SECONDS` を伸ばす

```python
with page.frame(page.CONTENT_FRAME):
    page.click(page.SAVE_BUTTON)
# ← 抜けると元の画面へ戻る（中でエラーが出ても戻る）
```

### 別タブが開いてしまう

帳票の印刷画面や「別ウィンドウで開く」リンクの場合。開いてから `popup_tab()` に入る。

```python
page.click(page.REPORT_LINK)         # ここで別タブが開く
with session.popup_tab():            # 開いたタブへ移る
    session.save_screenshot("report")
# ← 別タブを閉じて、元のタブへ戻る
```

### ブラウザが起動しない（`DriverStartError`）

Windows Update で Edge だけが新しくなり、`msedgedriver.exe` が取り残されると起きる。

`DRIVER_SOURCE_DIR` に社内の配布フォルダを設定しておけば、
起動に失敗したときに自動でコピーして直し、もう一度起動を試みる。

```python
class KintaiOptions(BrowserOptions):
    DRIVER_SOURCE_DIR = r"\\共有サーバー\ツール\msedgedriver"
```

配布フォルダは、次のどちらの置き方でもよい:

- 直下に `msedgedriver.exe` を1つ置く（最新をここに上書きする運用）
- `131.0.2903.86\msedgedriver.exe` のようにバージョン別フォルダに置く

「上書きできません」と出る場合は、別の実行が `msedgedriver.exe` を掴んだままになっている。
実行中の自動化をすべて終了してから、もう一度実行する。

---

## やってはいけないこと

| やらないこと | 代わりに |
|---|---|
| `time.sleep(3)` で待つ | `wait_visible(LOC)` で待つ。速くて確実 |
| `selenium` を直接 import する | `Page` のメソッドを使う。無ければ `Page` に足す |
| `with` を使わずに起動する | 必ず `with Browsers() as browsers:` の中で使う |
| セレクターをメソッドの中に直接書く | クラス先頭の `Locator` 定数にまとめる |
| 絶対 XPath を使う | id / name / css で指定する |
| ID・パスワードをコードに書く | config.ini に置き、config.ini は git に入れない |

---

## API・機能早見

ここまでの説明で使ったクラスとメソッドを、実装時に引ける形でまとめる。

### Browsers（入口）

**1サイトにつき1ブラウザを起動する。タブでは分けない。**
ダウンロード先・起動オプション・ログイン状態はすべてブラウザ単位で決まるため、
タブで分けるとサイト間で取り違えが起きる。

サイトが1つでも複数でも書き方は同じで、増やすときは `launch` を1行足すだけ:

```python
from comken.toolbox.browser import Browsers

with Browsers() as browsers:
    kintai = browsers.launch("kintai", KintaiOptions)
    keiri = browsers.launch("keiri", KeiriOptions)      # ← 増えるのはこの行だけ

    kintai_days = KintaiFlow(kintai).unfilled_days()
    keiri_rows = KeiriFlow(keiri).pending_rows()
```

`launch` に付けた名前で、ダウンロードフォルダ・ログイン状態・ログのファイル名が自動的に分かれる。
同じサイトを2アカウントで開く場合も、名前を変えれば混ざらない。

| メソッド | 何をするか |
|---|---|
| `launch(name, options=None, download_dir=None)` | 名前を付けてブラウザを1つ起動し、`BrowserSession` を返す |
| `start(処理, label="")` | 処理を裏で始めて、すぐ次の行へ進む。`BackgroundTask` を返す |
| `parallel(*tasks)` | 複数の処理を同時に実行し、渡した順に結果を返す |
| `names` | 起動済みのセッション名（起動した順） |
| `browsers["kintai"]` | 名前でセッションを取り出す |

**待ち時間を使って別のことを進める**: 書いた順に動くのが基本で、
待ちたくないところだけ `start()` にする。

```python
with Browsers() as browsers:
    勤怠 = browsers.launch(Kintai)
    経理 = browsers.launch(Keiri)

    勤怠タスク = browsers.run_task(lambda: 勤怠.login(USER, PW).unfilled_days(), label="勤怠")

    未処理 = 経理.login(USER, PW).pending_rows()   # 勤怠の読み込み中にこちらが進む

    未入力 = 勤怠タスク.wait()                       # 戻って結果を受け取る
```

重い画面を待っている間、ブラウザは何も消費しないので他方がその時間を使えます。
読み込みが終われば、そちらも自分で続きを始めます（「優先する」指示は不要）。

| `BackgroundTask` | 何をするか |
|---|---|
| `wait(timeout=None)` | 終わるのを待って結果を返す。中で起きた例外はここで送出される |
| `is_done` | 終わったかどうかだけ見る（待たない） |

**全部同時でよければ** `parallel` が短く書けます（`start` と `wait` を並べるのと同じ）:

```python
未入力, 未処理 = browsers.parallel(
    lambda: 勤怠.login(USER, PW).unfilled_days(),
    lambda: 経理.login(USER, PW).pending_rows(),
)
```

裏で動かしている処理と、自分で書いている処理で、同じセッションを触らないこと。
同時に触ると `ConcurrentSessionUseError` で即座に止まります
（黙って別の画面を操作するより安全なため）。

---

### BrowserSession（1サイト分のブラウザ）

`with` の中でだけ使える。使わずに操作すると `SessionNotStartedError` になる
（エラーで落ちたときにブラウザのプロセスが残り続けるのを防ぐため）。

```python
session.open(url)                    # URL を開く
session.current_url                  # 現在の URL
session.title                        # ページタイトル
session.refresh() / session.back()   # 再読み込み / 戻る
session.save_screenshot("prefix")    # logs/prefix_セッション名_日時.png に保存
session.download_dir.wait()          # ダウンロード完了まで待つ

with session.popup_tab():            # 別タブへ移り、抜けるときに閉じて戻る
    session.save_screenshot("report")

session.raw.set_window_size(1200, 800)   # ここにない機能は raw（生の WebDriver）から
```

**エラー時の自動スクリーンショット**: `with` の中で例外が発生すると、
その時点の画面が `logs/error_セッション名_YYYYMMDD_HHMMSS.png` に自動保存される。

---

### BrowserOptions（起動オプション）

サイトごとにサブクラスを作り、変えたい項目だけ上書きする。
`Browsers.launch` にクラスのまま渡せば、セッションごとに別インスタンスが作られる。

```python
# src/browser_options.py（プロジェクト側）
from comken.toolbox.browser import BrowserOptions

class KintaiOptions(BrowserOptions):
    DRIVER_PATH = r"C:\tools\msedgedriver.exe"
    WAIT_SECONDS = 15
    INCOGNITO = False
    START_MAXIMIZED = False          # WINDOW_SIZE と併用不可
    WINDOW_SIZE = "1600,1024"
```

| 項目 | 役割 |
|---|---|
| `DRIVER_PATH` | 使う msedgedriver.exe のパス |
| `DRIVER_SOURCE_DIR` | ドライバーの配布フォルダ。起動に失敗したとき、ここから自動でコピーして直す |
| `PROFILE_ROOT` | ログイン状態を残すフォルダ。指定するとシークレットモードは自動で外れる |
| `DOWNLOAD_DIR` | ダウンロード先。セッション名のサブフォルダに自動で分かれる |
| `WAIT_SECONDS` | 要素待機のタイムアウト秒数 |
| `SUPPRESS_EXTERNAL_LOGS` | ドライバーと Edge の標準出力を抑える。調査時だけ `False` にする |

設定できる項目の一覧と現在値は `print()` で確認できる:

```python
print(BrowserOptions())    # 既定値を表示
print(KintaiOptions())     # 既定値からの変更箇所に * が付く
```

**ドライバーの自動更新**: Windows Update で Edge だけが新しくなると
`msedgedriver.exe` が取り残されて起動できなくなる。`DRIVER_SOURCE_DIR` を設定しておくと、
起動に失敗した時点で配布フォルダから合うバージョンをコピーし、もう一度起動を試みる。
配布フォルダは直下に置く形でも、バージョン別サブフォルダでもよい。

---

### ダウンロード（DownloadDir）

ダウンロードフォルダはセッションごとに分かれている。
Edge がダウンロード中に作る `.crdownload` を監視して完了を判定する。

**`DOWNLOAD_DIR` を指定しない場合は一時フォルダになり、`with` を抜けると消える。**
残したいファイルは `with` の中で移動しておく。

```python
from comken.core import move_file
from comken.toolbox.browser import Browsers

with Browsers() as browsers:
    kintai = browsers.launch("kintai", KintaiOptions)

    HomePage(kintai).export_csv()
    files = kintai.download_dir.wait()          # .crdownload が消えるまで待つ
    move_file(files[0], r"C:\作業\output")       # with の中で移動する
```

- `wait()` は前回のファイルが残っていても誤検出しない（新しく増えた分だけを返す）
- 時間内に終わらなければ `DownloadTimeoutError` になる

---

### Page / SitePage（画面クラス）

画面ごとに `Page`（サイト共通の処理があれば `SitePage`）を継承したクラスを作る。
セレクターは `Locator` のクラス変数としてクラスの先頭にまとめる。

```python
from comken.toolbox.browser import Locator, SitePage

class LoginPage(SitePage):
    BASE_URL = "https://example.com"

    USERNAME = Locator.id("username")
    PASSWORD = Locator.id("password")
    LOGIN_BTN = Locator.css("#login-btn")

    def login(self, username: str, password: str) -> "DashboardPage":
        from .dashboard_page import DashboardPage

        self.go("/login")
        self.input(self.USERNAME, username)
        self.input(self.PASSWORD, password)
        self.click(self.LOGIN_BTN)
        return DashboardPage(self.session)      # 遷移先の画面クラスを返す
```

**操作メソッド一覧**（すべて `Locator` を受け取る）:

| したいこと | メソッド |
|---|---|
| クリック | `click(LOC, index=0)` |
| 文字入力（既存の値は消える） | `input(LOC, text)` |
| テキスト取得 | `text(LOC)` / `texts(LOC)` |
| 属性取得（href, value 等） | `attribute(LOC, name)` |
| プルダウン選択 | `select_text(LOC, 表示名)` / `select_value(LOC, v)` / `select_index(LOC, i)` |
| 表示・非表示を待つ | `wait_visible(LOC)` / `wait_invisible(LOC)` |
| 存在確認・件数（待たない） | `has(LOC)` / `count(LOC)` |
| スクロール | `scroll_to(LOC)` / `scroll_bottom()` |
| ドラッグ＆ドロップ | `drag_drop(source, target)` |
| 確認ダイアログ | `alert_accept()` / `alert_dismiss()` / `alert_text()` |
| iframe の中を操作 | `with page.frame(LOC):` |
| スクリーンショット | `save_screenshot(prefix)` |
| 一覧の各行を処理する | `elements(LOC)`（WebElement のリスト） |
| 最終手段 | `element(LOC)`（生の WebElement） / `js(script, *args)` |

要素は自動で待機する（既定10秒）。時間内に見つからない場合は `ElementNotFoundError` になり、
**どのセレクターで失敗したか**がメッセージに出る。`time.sleep` で待たないこと。

セレクターは `Locator.id` > `Locator.name` > `Locator.css` > `Locator.xpath` の順で選ぶ。
値は Edge の開発者ツール（F12）で確認する。絶対 XPath は使わない。

複数一致する場合の優先順位:

1. **セレクター側で一意に絞り込む（原則）** — 例: `Locator.css("table tr:nth-child(2) .edit-btn")`
2. リストで取得して選ぶ — `texts(LOC)` / `count(LOC)`
3. 何番目かを直接指定（最終手段） — `click(LOC, index=1)`（0始まり）

---

### サンプル実装

`examples/sample_login/` に動作するサンプルがある（他モジュールのサンプルは examples/README.md 参照）。

```
examples/sample_login/
├── pages/
│   ├── login_page.py # ログイン画面
│   └── secure_page.py # ログイン後の画面
├── browser_options.py # BrowserOptions のカスタマイズ
├── config.ini.example # 設定ファイルのテンプレート
├── config.py # config のシングルトン（config = Config()）
└── run.py # 実行スクリプト
```

実行:

```bash
# リポジトリのルートで
python -m examples.sample_login.run
```

---

## 関連

- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
- [エラー対応ガイド](ERRORS.md#ブラウザedge-自動操作のエラー) — エラー名から対処を引く
- `examples/sample_login/` — 動くサンプル一式
