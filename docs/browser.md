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
| 土台（直接は使わない） | `SalesforceBase` | `SiteBase` |
| 対象ごとのクラス | `Sandbox(SalesforceBase)` | `Kintai(SiteBase)` |
| 固有の値の置き場 | `DOMAIN_URL` / `CREDENTIAL_PREFIX` / `OWNER` | `NAME` / `BASE_URL` / `OPTIONS` / `OWNER` |
| 機能は継承せず持たせる | `.auth` / `.report` / `.metrics` | `.to(画面クラス)` で画面を作る |
| 単体で使う入口 | `with Sandbox() as sf:` | `with Kintai() as kintai:` |
| 複数まとめて扱う入口 | `sites/` の `site_for()` | `Browsers` |
| 画面／機能の分割 | `.report` / `.metrics` | `Page` のサブクラス |

`OWNER` は「プロジェクト名 / 担当者」の形式で必ず書く（起動時に検査される）。
ライブラリへ昇格したクラスは `OWNER = "comken"` にする。昇格の基準は
[ライブラリ開発規約](開発/ライブラリ開発規約.md#サイト組織クラスを昇格させる基準) を参照。

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
    with Kintai() as kintai:
        login_page = kintai.go_login()
        home = login_page.login("user01", "password")
        print(home.unfilled_days())
```

`go_login()` でログイン画面へ、`login(...)` で次の画面へ。
**変数名も画面の名前になる**ので、いまどこにいるかが読める。
`LoginPage(session)` のように画面クラスへセッションを渡し直す必要はない。
起動の形は Salesforce の `with Sandbox() as sf:` と同じ。

1行に繋げてもよい。一度きりの流れなら、こちらが短い。

```python
with Kintai() as kintai:
    print(kintai.go_login().login("user01", "password").unfilled_days())
```

途中の画面を変数に取れば、そこから何度も操作できる。

```python
with Kintai() as kintai:
    home = kintai.go_login().login("user01", "password")
    unfilled = home.unfilled_days()
    home.enter_attendance(unfilled[0]).save()
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
    kintai = browsers.launch(Kintai)
    keiri = browsers.launch(Keiri)          # ← 増えるのはこの行だけ

    unfilled = kintai.go_login().login(USER, PW).unfilled_days()
    pending = keiri.go_login().login(USER, PW).pending_rows()
```

サイトが2つ以上になったら `Browsers` を使う。1つだけなら `with Kintai() as kintai:` で足りる。

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
    kintai = browsers.launch(Kintai)
    keiri = browsers.launch(Keiri)

    kintai_task = browsers.run_task(lambda: kintai.go_login().login(USER, PW).unfilled_days(), label="勤怠")

    pending = keiri.go_login().login(USER, PW).pending_rows()   # 勤怠の読み込み中にこちらが進む

    unfilled = kintai_task.wait()                       # 戻って結果を受け取る
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
unfilled, pending = browsers.parallel(
    lambda: kintai.go_login().login(USER, PW).unfilled_days(),
    lambda: keiri.go_login().login(USER, PW).pending_rows(),
)
```

結果は**渡した順**で返る（終わった順ではない）。

### 守ること

**裏で動かしている処理と、自分で書いている処理で、同じブラウザを触らないこと。**
同じブラウザを同時に触ると `ConcurrentSessionUseError` で止まる。
待たされるのではなく即エラーにしているのは、黙って壊れる（別の画面を操作していた）より、
早く気づけるほうが安全なため。

```python
kintai_task = browsers.run_task(lambda: kintai.go_login().login(USER, PW).unfilled_days())
keiri.go_login().login(USER, PW).pending_rows()   # ⭕ 別のブラウザなので問題ない
kintai.go_login().login(USER, PW)                  # ❌ 裏で使っている勤怠を触っている
```

`wait()` を呼び忘れたまま `with` を抜けても、ブラウザを閉じる前に処理の終了は待つ。
その処理が失敗していた場合はログに残る（黙って消えることはない）。

---

## 新しい社内システムを追加する手順

### 1. ファイルを作る

**1サイト＝1フォルダにして、そのサイトのものを全部その中に入れる。**

```
src/
  sites/
    kintai/                 ← このフォルダだけ見れば勤怠のことが分かる
      site.py               ← サイトクラス＋このサイトの BrowserOptions
      pages/
        kintai_page.py      ← このサイトの画面に共通（セレクター・共通処理）
        login_page.py       ← 画面ごと
        home_page.py
    keiri/                  ← 別のサイトはまるごと別フォルダ
      site.py
      pages/
```

サイト名が出てくるのは**フォルダ名の1回だけ**。`sites/` と `pages/` を並べて
サイト名を2箇所に書く形にすると、増やすときも消すときも2箇所を触ることになる。
**サイトを1つ消すなら、フォルダを1つ消せば終わり**にしておく。

`comken init` が作る雛形には `src/sites/` は**含まれていない**。ブラウザ操作を使う
プロジェクトでは、この節の形に合わせて `src/sites/<サイト名>/` を自分で追加する
（書き方の見本はライブラリ側の `comken/toolbox/browser/sites/sample/` にある）。
サイトを増やすには、`src/sites/<サイト名>/` を隣にもう1つ作るだけ。

**サイトクラスと画面共通クラスは別物。** サイトクラスは「どのサイトか」を表し、
画面共通クラスは「その画面群に共通の操作」を持つ。

### 2. サイトクラスを ``site.py`` に書く

**起動オプション（``OPTIONS``）は既定のままでよければ書かなくてよい。**
変えたいときだけ、同じ ``site.py`` に ``〇〇SiteOptions`` を作って
``OPTIONS = 〇〇SiteOptions`` を ``〇〇Site`` に置く（フォルダが同じなら
ファイルを分ける理由が無い）。設定できる項目は ``print(BrowserOptions())`` で
一覧できる（既定値との差分に `*` が付く）。

ブラウザ設定は **config.ini ではなくこのファイル（サイト側の Python）** に書く。
「環境で変わる非機密の値」ではなく「コードの一部」として扱うため。

**ここが利用側の入口になる。** 固有の値と、最初にやる操作をここへ集める。

```python
from comken.toolbox.browser import SiteBase

from .pages.login_page import LoginPage


class Kintai(SiteBase):
    """勤怠システム。"""

    NAME = "kintai"
    BASE_URL = "https://kintai.example.co.jp"
    OWNER = "勤怠 / 担当者"

    # 画面の操作はここに書かない。画面クラスの仕事にする
```

オプションを変えたいとき（ダウンロード先・待ち時間・ログイン状態の保持など）は
同じ ``site.py`` に ``KintaiOptions`` を足す:

```python
from comken.toolbox.browser import BrowserOptions, SiteBase

from .pages.login_page import LoginPage


class KintaiOptions(BrowserOptions):
    """このサイトの BrowserOptions。変えたい項目だけ上書きする。"""

    DOWNLOAD_DIR = r"C:\作業\downloads"
    WAIT_SECONDS = 20


class Kintai(SiteBase):
    """勤怠システム。"""

    NAME = "kintai"
    BASE_URL = "https://kintai.example.co.jp"
    OPTIONS = KintaiOptions
    OWNER = "勤怠 / 担当者"
```

**行ける画面は `go_〇〇()` で書く。**

```python
class Kintai(SiteBase):
    NAME = "kintai"
    BASE_URL = "https://kintai.example.co.jp"
    OWNER = "勤怠 / 担当者"

    def go_login(self) -> LoginPage:
        """ログイン画面を開く。"""
        return self.to(LoginPage).go("/login")
```

`go_〇〇()` があるものにしか行けない、と**コードが遷移図になる**。
書く量は増えるが、増えた分だけ「ここからどこへ行けるか」が確定する。

飛び方（URL を直接開くか、画面のリンクを押すか）はメソッドの中に隠す。
呼ぶ側からはどちらも同じに見える。

### 3. 画面に共通のクラスを作る

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

### 4. 画面ごとのクラスを作る

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
        return self.to(HomePage)
```

遷移先の import をメソッドの中に置いているのは、画面クラス同士が互いを参照して
循環インポートになるため（型注釈でも名前を使うなら `from __future__ import annotations` と
`TYPE_CHECKING` を合わせる）。

**画面が変わるメソッドは、遷移先の画面クラスを返す。** 呼ぶ側が画面の流れを
コードのまま追えるようになる。

画面から画面へのリンクも `go_〇〇()` で書く。**その画面から行ける先だけが並ぶ**ので、
補完を見れば「ここから次はどこへ行けるか」が分かる:

```python
class HomePage(KintaiPage):
    ATTENDANCE_MENU = Locator.css("a[href='/attendance']")

    def go_attendance(self) -> "AttendancePage":
        """勤怠入力画面へ移る。"""
        from .attendance_page import AttendancePage

        self.click(self.ATTENDANCE_MENU)
        return self.to(AttendancePage)
```

`to()` は行き先の型を切り替えるだけで、ブラウザは動かさない。
実際に動かすのは `go("/path")` かリンクのクリックで、**それを `go_〇〇()` の中に隠す**。
呼ぶ側は「URL で飛ぶのか、押して飛ぶのか」を知らなくてよい。

```python
home = LoginPage(session).login(user_id, password)
days = home.go_attendance().unfilled_days()
```

### ボタン遷移の書き方

**社内システムの画面遷移は、ほとんどがボタン／リンクのクリックで、URL 直アクセスは少数派。**
セッション付きの遷移用トークンが URL に乗っている、遷移が POST や JS で行われる、
そもそもパスが公開されていない、といった理由で `go("/path")` が使えないことが多い。
`go_〇〇()` の中身は**既定でクリック、URL がわかっていて安定しているときだけ `go()`** で組み立てる。

型は「まず動かす」節の `go_login()`（URL 直アクセス）と同じ形だが、中身がクリックに変わるだけ:

```python
class HomePage(KintaiPage):
    ATTENDANCE_MENU = Locator.css("a[href='/attendance']")

    def go_attendance(self) -> "AttendancePage":
        """メニューの「勤怠」を押して遷移する。"""
        from .attendance_page import AttendancePage

        self.click(self.ATTENDANCE_MENU)
        return self.to(AttendancePage)
```

**書き方の骨格は3行で固定**: ①押す対象を `Locator` で用意（クラス先頭）→
②`self.click(LOC)` で押す → ③遷移先の画面クラスを `self.to(NextPage)` で返す。
ボタンがリンク（`<a>`）でもフォーム送信ボタンでも書き方は変わらない
（`click()` は押すだけで、遷移方式の違いは意識しなくてよい）。

**`go()` を使ってよいのは、URL 自体が入口として安定しているとき**（ログイン画面・
ブックマーク可能なトップページなど）。それ以外（一覧の詳細行・確認ダイアログの
「はい」・タブ切り替えなど）は基本クリックにする。判断に迷ったら**押して確かめられる
ボタンがあるならクリックを選ぶ**——URL は実装都合で変わりやすいが、ボタンは
画面がある限り押せる。

遷移後の読み込みが重い画面では、`click()` の直後に `to()` を返すだけでよい。
次の画面の最初の操作（`login()` の `input()` など）が対象要素を自動で待つため、
`go_〇〇()` 側で明示的に `wait_visible()` を挟む必要は基本的にない。
遷移そのものの完了を確認したいとき（次の画面を使わずに終わる場合など）だけ、
`go_〇〇()` の中で目印の要素を `wait_visible()` してから返す。

### セレクターの選び方

上から順に、使えるものを使う。

| 順 | 書き方 | 備考 |
|---|---|---|
| 1 | `Locator.id("userId")` | いちばん壊れにくい |
| 2 | `Locator.name("userId")` | 入力欄はこれが使えることが多い |
| 3 | `Locator.css("table tr .name")` | id / name が無いとき |
| 4 | `Locator.link_text("検索")` | `<a>` をリンクテキスト完全一致で探すとき |
| 5 | `Locator.partial_link_text("検索")` | `<a>` をリンクテキスト部分一致で探すとき |
| 6 | `Locator.xpath("//button[text()='検索']")` | 最終手段。`<a>` 以外を文字で探すときや、それでも無理なとき |

`link_text` / `partial_link_text` は `<a>` の可視テキスト全体（子要素込み）を比較する。
`xpath("//a[text()='...']")` は直下のテキストノードにしか一致しないため、
`<a><span>検索</span></a>` のように文字が子要素に入っていると素通りする。
リンクを文字で探すときは xpath より先にこちらを検討する。

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
    return self.to(HomePage)
```

---

## ファイルをダウンロードする

ダウンロードフォルダはセッションごとに分かれている。完了待ちは `download_dir.wait()`。

```python
from comken.core import move_file

with Browsers() as browsers:
    kintai = browsers.launch(Kintai)

    kintai.to(HomePage).export_csv()
    files = kintai.downloads.wait()                     # .crdownload が消えるまで待つ
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
    session.save_screenshot("report.png")
# ← 別タブを閉じて、元のタブへ戻る
```

### ブラウザが起動しない（`DriverStartError`）

Windows Update で Edge だけが新しくなり、`msedgedriver.exe` が取り残されると起きる。

comken は自動更新を行わない。**バージョンが合わなくなった場合は、利用者側で
`DRIVER_PATH` の `msedgedriver.exe` を Edge のバージョンに合わせて差し替えてから、
もう一度実行する。**

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
    kintai = browsers.launch(Kintai)
    keiri = browsers.launch(Keiri)      # ← 増えるのはこの行だけ

    kintai_days = kintai.go_login().login(USER, PW).unfilled_days()
    keiri_rows = keiri.go_login().login(USER, PW).pending_rows()
```

`SiteBase.NAME` が、ダウンロードフォルダ・ログイン状態・ログのファイル名を分ける鍵になる。
同じサイトを2アカウントで開く場合も、NAME を変えれば混ざらない。

| メソッド | 何をするか |
|---|---|
| `launch(SiteBase, download_dir=None)` | SiteBase サブクラスを渡してブラウザを1つ起動し、SiteBase インスタンスを返す |
| `launch_session(name, options=None, download_dir=None)` | 低レベル経路。`Browsers` を使わずに名前とオプションで直接起動する |
| `start(処理, label="")` | 処理を裏で始めて、すぐ次の行へ進む。`BackgroundTask` を返す |
| `parallel(*tasks)` | 複数の処理を同時に実行し、渡した順に結果を返す |
| `names` | 起動済みのセッション名（起動した順） |
| `browsers["kintai"]` | 名前でセッションを取り出す |

**待ち時間を使って別のことを進める**: 書いた順に動くのが基本で、
待ちたくないところだけ `start()` にする。

```python
with Browsers() as browsers:
    kintai = browsers.launch(Kintai)
    keiri = browsers.launch(Keiri)

    kintai_task = browsers.run_task(lambda: kintai.go_login().login(USER, PW).unfilled_days(), label="勤怠")

    pending = keiri.go_login().login(USER, PW).pending_rows()   # 勤怠の読み込み中にこちらが進む

    unfilled = kintai_task.wait()                       # 戻って結果を受け取る
```

重い画面を待っている間、ブラウザは何も消費しないので他方がその時間を使えます。
読み込みが終われば、そちらも自分で続きを始めます（「優先する」指示は不要）。

| `BackgroundTask` | 何をするか |
|---|---|
| `wait(timeout=None)` | 終わるのを待って結果を返す。中で起きた例外はここで送出される |
| `is_done` | 終わったかどうかだけ見る（待たない） |

**全部同時でよければ** `parallel` が短く書けます（`start` と `wait` を並べるのと同じ）:

```python
unfilled, pending = browsers.parallel(
    lambda: kintai.go_login().login(USER, PW).unfilled_days(),
    lambda: keiri.go_login().login(USER, PW).pending_rows(),
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
session.save_screenshot()                       # logs/screenshot_セッション名_日時.png に保存
session.save_screenshot("login.png")            # logs/login.png に保存（ファイル名を直接指定）
session.save_screenshot(directory="errors")     # errors/screenshot_セッション名_日時.png に保存
session.download_dir.wait()                     # ダウンロード完了まで待つ

with session.popup_tab():            # 別タブへ移り、抜けるときに閉じて戻る
    session.save_screenshot("report.png")

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
| `PROFILE_ROOT` | ログイン状態を残すフォルダ。指定するとシークレットモードは自動で外れる |
| `DOWNLOAD_DIR` | ダウンロード先。セッション名のサブフォルダに自動で分かれる |
| `WAIT_SECONDS` | 要素待機のタイムアウト秒数 |
| `HEADLESS` | `True` で画面を出さずに動かす |
| `SUPPRESS_EXTERNAL_LOGS` | ドライバーと Edge の標準出力を抑える。調査時だけ `False` にする |

**よく変える項目の書き方**:

```python
from comken.toolbox.browser import BrowserOptions
from comken.toolbox.windows import Paths


class KintaiOptions(BrowserOptions):
    HEADLESS = True                       # 画面を出さずに動かす
    DOWNLOAD_DIR = r"C:\作業\downloads"   # サイト名のサブフォルダへ自動で分かれる
    # 標準のフォルダへ入れるなら Paths を使う（OneDrive で場所が移されていても
    # 実際の場所に付いていける）
    # DOWNLOAD_DIR = Paths.downloads()    # ほかに desktop() / temp_dir()
    WAIT_SECONDS = 20                     # 要素待機のタイムアウト秒

    # 指定するとログイン状態が次回も残る（サイトごとに別フォルダへ自動で分かれる）
    PROFILE_ROOT = r"C:\作業\browser_profiles"
```

設定できる項目の一覧と現在値は `print()` で確認できる:

```python
print(BrowserOptions())    # 既定値を表示
print(KintaiOptions())     # 既定値からの変更箇所に * が付く
```

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
    kintai = browsers.launch(Kintai)

    kintai.to(HomePage).export_csv()
    files = kintai.downloads.wait()                     # .crdownload が消えるまで待つ
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
        return self.to(DashboardPage)           # 遷移先の画面クラスを返す
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
| スクリーンショット | `save_screenshot(filename=None, *, directory=None, prefix="screenshot")` |
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

`comken/toolbox/browser/sites/sample/` にサイト実装の見本がある
（実行スクリプトの例は examples/README.md 参照）。

**上の「1サイト＝1フォルダ」で書いてある**ので、形の見本としてそのまま真似できる。

```
comken/toolbox/browser/sites/sample/
├── site.py                 # サイトクラス＋このサイトの BrowserOptions
└── pages/
    ├── app_page.py         # このサイトの画面に共通
    ├── login_page.py       # ログイン画面
    └── secure_page.py      # ログイン後の画面
```

プロジェクト側でサイトを増やすときは `sites/<サイト名>/` をもう1つ作るだけで、
既にあるサイトのファイルには触らない。

実行スクリプトの例は `examples/README.md` を参照（Edge + msedgedriver が必要）。

---

## 関連

- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
- [エラー対応ガイド](ERRORS.md#ブラウザedge-自動操作のエラー) — エラー名から対処を引く
- `comken/toolbox/browser/sites/sample/` — サイト実装の見本
