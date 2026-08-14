# 認証情報

[README（ドキュメントの入口）へ戻る](../README.md)

README の「credentials」から移した、モジュールを使うときの詳しい説明です。

## credentials

client_secret・パスワード・トークンは config.ini に平文で書けない。
Windows 標準の **DPAPI** で暗号化して保管し、コードからはキー名で引く。
暗号鍵の管理は不要で、Windows がログオン中のアカウントに紐付けて暗号化・復号する。

### 登録（初回だけ）

**入口は2つある。どちらを使うかは「1台か、たくさんの PC か」で決める。**

| 入口 | 向いている場面 | 平文ファイル |
|---|---|---|
| `gui` | 自分の PC で登録する | **作らない** |
| `import` | 同じ値を何台にも配る | 一時的に要る |

プログラムが実行中に受け取った値（Salesforce のリフレッシュトークンなど）を保存するのは
コマンドではなく [`save_credential()` / `save_credentials()`](自動生成/API.md) の仕事で、
人の操作は要らない。

#### gui — 画面から登録する

```
python -m comken.toolbox.credentials gui
```

システム名・項目名・値を入れて「登録する」を押す。**入力した文字は伏せ字で、平文の
ファイルも作らない。** 登録すると読み直して文字数を出すので、貼り間違いはそこで気づける。
登録済みのキー名の一覧と削除も同じ画面にある（**値を読み出す機能は無い**——画面に出せば
覗き見やスクリーンショットで漏れる経路が増えるため）。

`templates/認証情報の登録.bat` をプロジェクトのフォルダへコピーしておけば、
**ダブルクリックで開く**。ターミナルを使わない人にはこれを渡す。

平文 JSON を選んでまとめて取り込むボタンも同じ画面にある。取り込んだ全件を読み直せたら、
その場で平文 JSON の削除を聞く（読み直せることを確かめてから消すので、
実行アカウント違いで元の値を失わない）。

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
python -m comken.toolbox.credentials import 認証情報.json    取り込む
python -m comken.toolbox.credentials list                     登録済みの認証情報を接頭辞別に表示する
python -m comken.toolbox.credentials delete site_a_client_id  1件削除する
```

`{"site_a": {"client_id": ...}}` は `site_a_client_id` というキー名に展開されて
`%USERPROFILE%\.comken\credentials.dat` に保存される。JSON に無いキーはそのまま残るので、
組織ごとに JSON を分けて何回かに分けて取り込める。

取り込んだら**平文の JSON は消す**。`--delete-source` を付けると成功時に自動で消えるが、
既定では消さない。実行アカウントで読めることを `list` で確かめてから消すのが安全なため。

### 使う側

```python
from comken.toolbox.credentials import Credentials

cred = Credentials("site_a")
cred.client_id      # → site_a_client_id の値
cred.client_secret  # → site_a_client_secret の値
```

システム名を config.ini から渡せば、本番とテストの切り替えが config.ini の1行で済む
（コード側にキー名の直書きが残らない）。

```python
# [CREDENTIALS]
# SITE_A = site_a          ← site_a_test にすると全項目が切り替わる
cred = Credentials(config.CREDENTIALS.SITE_A)
```

### 登録したユーザー・PC でしか復号できない

DPAPI は **Windows アカウント × PC** に紐付く。ファイルを他人にコピーされても中身は
読めない代わりに、**自分でも別アカウント・別 PC では読めない**（`CredentialDecryptionError`）。

**タスクスケジューラの実行ユーザーが登録時と違う**のが最も多い事故。
バッチを動かす運用アカウントで取り込むこと。

守っているのは**中身が読まれないこと**だけで、ファイルを消される・差し替えられることは
防いでいない（`CredentialStoreCorruptedError` になり、取り込み直しで復旧する）。
また、読んで足して書き戻す作りなので**同時に2つのプロセスから書かない**こと。
取り込みは人が1回だけ実行する前提。

複数台へ配る必要が出てきたら公開鍵ハイブリッド方式を足す余地がある
（準備は [docs/salesforce.md](salesforce.md) の付録）。
まずローカル保管で動かし、配布が現実の問題になってから入れる。

---

## 関連

- [README](../README.md) — ライブラリ全体の概要と環境構築
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
