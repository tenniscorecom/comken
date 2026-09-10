# 認証情報

[README（ドキュメントの入口）へ戻る](../README.md)

README の「credentials」から移した、モジュールを使うときの詳しい説明です。

## credentials

client_secret・パスワード・トークンは config.ini に平文で書けない。
Windows 標準の **DPAPI** で暗号化して保管し、コードからは（サイト名, 項目名）で引く。
暗号鍵の管理は不要で、Windows がログオン中のアカウントに紐付けて暗号化・復号する。

### 登録（初回だけ）

**入口は2つある。どちらを使うかは「1台か、たくさんの PC か」で決める。**

| 入口 | 向いている場面 | 平文ファイル |
|---|---|---|
| `gui` | 自分の PC で登録する | **作らない** |
| `import` | 同じ値を何台にも配る | 一時的に要る |

プログラムが実行中に受け取った値（Salesforce のリフレッシュトークンなど）を保存するのは
コマンドではなく、`Credentials` の仕事で、人の操作は要らない。既に読み込み済みの
`Credentials` インスタンスがあれば `cred.save()`（[使う側](#使う側)参照）、まだ
インスタンスを持っていない場合だけ [`save_credential()` / `save_credentials()`](自動生成/API.md)
を直接使う。

#### gui — 画面から登録する

```
python -m comken cred gui
```

サイト名・項目名・値を入れて「登録する」を押す。**入力した文字は伏せ字で、平文の
ファイルも作らない。** 登録すると読み直して文字数を出すので、貼り間違いはそこで気づける。
登録済みの認証情報の一覧と削除も同じ画面にある（サイト名を親、項目名を子にした
ツリー表示）。平文 JSON を選んでまとめて取り込むボタンも同じ画面にある。

**画面の設計（一覧の並べ方・値を読み出す機能が無い理由・平文 JSON 削除前に
読み直しで確認する理由）は、ここでは重複させずコードの docstring
（`comken/toolbox/credentials/gui.py` のモジュール docstring・`CredentialsApp`
配下の各メソッド）を正とする。** `CredentialsApp` は GUI 内部の実装クラスで
自動生成/API.md には載らないため、ソースを直接開くか IDE の定義ジャンプで読む。

`templates/認証情報の登録.bat` をプロジェクトのフォルダへコピーしておけば、
**ダブルクリックで開く**。ターミナルを使わない人にはこれを渡す。

#### import — 平文 JSON を取り込む

平文の JSON を一時的に置いて、1回だけコマンドを実行する。
配る先が多いとき、1台ずつ手入力する工程を無くすために使う。

```json
{
  "site_a": {"client_id": "...", "client_secret": "..."},
  "site_b": {"client_id": "...", "client_secret": "..."}
}
```

```
python -m comken cred import 認証情報.json     取り込む
python -m comken cred list                      登録済みの認証情報をサイト名別に表示する
python -m comken cred delete site_a client_id   1件削除する
```

`{"site_a": {"client_id": ...}}` は同じ入れ子構造のまま
`%USERPROFILE%\.rpa\system-id.enc` へ保存される。保存時の挙動（展開・組み立て
直しをしない理由、JSON に無い既存キーの扱い）は `comken/toolbox/credentials/importer.py`
のモジュール docstring を正とする（ここでは重複させない）。

取り込んだら**平文の JSON は消す**。`--delete-source` の挙動と、既定では
自動削除しない理由は `comken/toolbox/credentials/cli.py` のモジュール
docstring を参照（モジュール docstring のため自動生成/API.md には載らない）。

### 使う側

```python
from comken.toolbox.credentials import Credentials, load_credential

cred = Credentials("site_a")
cred.client_id      # → site_a 配下の client_id の値
cred.client_secret  # → site_a 配下の client_secret の値

# 1件だけ直接取り出す場合は（サイト名, 項目名）の2引数で
password = load_credential("oju_sys", "password")
```

サイト名を config.ini から渡せば、本番とテストの切り替えが config.ini の1行で済む。

```python
# [CREDENTIALS]
# SITE_A = site_a          ← site_a_test にすると全項目が切り替わる
cred = Credentials(config.CREDENTIALS.SITE_A)
```

登録済みの値を更新したいときは、属性へ代入してから `cred.save()`。属性アクセス・
代入の仕組み（サイト名からの入れ子構造の解決、代入だけではディスクに書かない
理由、site 名を書き直さなくてよい理由）は、ここでは重複させずコードの
docstring（`Credentials` クラス・`Credentials.__setattr__()` ・
`Credentials.save()`）を正とする。`save()` は [自動生成 API.md](自動生成/API.md)
にも同じ docstring が載るが、`__setattr__()` は特殊メソッドのため載らない
（ソースを直接開くか IDE の定義ジャンプで読む）。

```python
cred.client_secret = new_secret
cred.save()
```

### パスワードの変更

ブラウザ自動化中にサイト側から強制的にパスワード変更を求められたとき、新しい
パスワードを **CLI で受け付け → DPAPI 認証情報ストアへ反映 → サイト側へも反映**、
の3つを一緒に行う。片方だけ更新すると次回以降ログインできなくなるため、
同じ値を両方に使う。

```python
from comken.toolbox.credentials import Credentials, change_password

cred = Credentials(config.CREDENTIALS.AMS)
result = login_page.login(cred.username, cred.password)   # 読みは cred から
if isinstance(result, ChangePasswordPage):
    # CLIで2回入力→サイトへ送信→DPAPI保存まで1行で完結する
    secure = change_password(cred, result.submit_new_password)
```

入力の伏せ字表示・確定タイミング・拒否時の自動再試行（既定3回、
`max_attempts=1` で無効化）・無人実行での `TimeoutError`（既定 300 秒、
`timeout_seconds` で変更可）といった挙動は、ここでは重複させずコードの
docstring（`comken/toolbox/credentials/prompt.py` のモジュール docstring・
`change_password()` ・`prompt_new_password()`）を正とする。後者2つは
[自動生成 API.md](自動生成/API.md) にも同じ docstring が載る
（モジュール docstring 自体は載らない）。

単に受け付けて保存するだけでよく、サイトへの送信も拒否時の再試行も不要なら
`prompt_new_password(cred)` を直接使う。

強制的に変更画面へ飛ばされたことの検知方法（URL の変化で判定するのが基本）は
[ブラウザ操作のログイン失敗まわり](browser.md#ログイン失敗まわり期限切れ認証エラー非同期の揺れ)を参照。

### 登録したユーザー・PC でしか復号できない

DPAPI は **Windows アカウント × PC** に紐付く。復号できない場合の挙動・
最も多い事故（タスクスケジューラの実行ユーザーが登録時と違う）・壊れている
場合との違いは `CredentialDecryptionError` / `CredentialStoreCorruptedError`
の docstring（[エラー対応ガイド](ERRORS.md)）を参照。

読んで足して書き戻す作りなので、**同時に2つのプロセスから書かない**こと
（取り込みは人が1回だけ実行する前提で、排他制御は無い）。

複数台へ配る必要が出てきたら公開鍵ハイブリッド方式を足す余地がある
（準備は [docs/salesforce.md](salesforce.md) の付録）。
まずローカル保管で動かし、配布が現実の問題になってから入れる。

---

## 関連

- [README](../README.md) — ライブラリ全体の概要と環境構築
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
