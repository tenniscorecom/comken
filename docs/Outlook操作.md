# Outlook 操作

[README（ドキュメントの入口）へ戻る](../README.md)

Outlook の受信メールを読み取り、確認用の下書きを作るための仕組み。

---

## 最初に確認すること

**従来版（Classic）Outlook でしか動かない。**

新しい Outlook（New Outlook）は COM の窓口を持たないため、このモジュールからは操作できない。
起動できない場合は `ClassicOutlookNotAvailableError` になる。

| できること | できないこと |
|---|---|
| 受信メールを読む（件名・差出人・本文・受信日時） | **メールの送信**（下書き保存まで） |
| 添付ファイルの有無を調べる | 受信メールの添付ファイルを保存する |
| 下書きを作る（添付つき） | New Outlook の操作 |
| 受信トレイの直下フォルダを指定する | 2階層以上のサブフォルダの指定 |

**送信機能は意図的に用意していない。** 誤送信は取り返しがつかないため、
下書きまでを自動化し、送信ボタンは人が押す。

Outlook を「開いている人のもの」として扱うため、`with` を抜けても Outlook は閉じない
（Excel や Access と違い、`Quit()` を呼ばない）。

---

## 基本の形

```python
import logging

from comken.outlook import Outlook

logger = logging.getLogger(__name__)

with Outlook() as mail:
    for message in mail.messages(subject_contains="日次データ", days=7):
        logger.info("%s / %s", message.received_at, message.subject)
```

---

## メールを探す

```python
mail.messages(subject_contains="", days=7, folder="")
```

| 引数 | 意味 |
|---|---|
| `subject_contains` | 件名に含まれる文字。省略すると件名で絞らない |
| `days` | 何日前まで遡るか。既定は7日 |
| `folder` | 受信トレイ直下のフォルダ名。省略すると受信トレイそのもの |

**新しい順**に1件ずつ返る。**既読・未読の状態は変えない**（読んでも未読のまま）。

```python
with Outlook() as mail:
    # 受信トレイ直下の「日次連携」フォルダから、3日以内の該当メールを探す
    for message in mail.messages(subject_contains="売上データ", days=3, folder="日次連携"):
        if message.has_attachments:
            logger.info("添付あり: %s", message.subject)
```

### 絞り込みは Outlook 側で行われる

受信箱に数万件あっても、Python 側で全件を読むことはない。
Outlook に条件を渡して絞り込ませてから受け取っている。そのため、

- `days` は必ず指定する（既定の7日のままでもよい）。大きくするほど遅くなる
- `days=0` は「今この瞬間以降」の意味になり、ほぼ0件になる
- 件名の絞り込みは**部分一致**。前方一致や正規表現は使えない

件名以外（差出人など）で絞りたい場合は、取り出してから Python 側で判定する:

```python
with Outlook() as mail:
    for message in mail.messages(days=7):
        if message.sender_address.endswith("@example.co.jp"):
            logger.info("%s", message.subject)
```

### 最初の1件だけ欲しいとき

1件ずつ返る作りなので、見つけた時点で止めれば残りは読まない。

```python
def latest_report(mail: Outlook) -> str:
    """「日次レポート」の最新メールの本文を返す。無ければ空文字。"""
    for message in mail.messages(subject_contains="日次レポート", days=7):
        return message.body
    return ""
```

---

## 読み取れる項目（MailMessage）

| 項目 | 型 | 内容 |
|---|---|---|
| `subject` | `str` | 件名 |
| `sender` | `str` | 差出人の表示名（例: 山田 太郎） |
| `sender_address` | `str` | 差出人のメールアドレス |
| `received_at` | `datetime` | 受信日時（タイムゾーンつき） |
| `body` | `str` | 本文。HTML メールでも、文字だけを取り出したものが入る |
| `has_attachments` | `bool` | 添付ファイルがあるか |

`MailMessage` は読み取り専用で、書き換えられない。
値を読むだけのものなので、これを変更しても Outlook 側のメールは変わらない。

`received_at` は必ずタイムゾーンつきなので、`comken.utils.now()` とそのまま比較できる。

> **添付ファイルの中身は取り出せない。** `has_attachments` で有無は分かるが、
> 保存するメソッドは用意していない。添付を取り込む必要が出たら、
> `comken.outlook` に機能を足すことを検討する（各プロジェクトで COM を直接触らない）。

---

## 下書きを作る

```python
with Outlook() as mail:
    mail.save_draft(
        to="taro@example.co.jp",
        subject="日次レポート",
        body="添付をご確認ください。",
        attachments=[r"C:\作業\report.csv"],
    )
```

| 引数 | 内容 |
|---|---|
| `to` | 宛先。1件なら文字列、複数ならリスト |
| `subject` | 件名 |
| `body` | 本文（文字のみ。HTML は使えない） |
| `attachments` | 添付ファイルのパスのリスト。省略可 |
| `cc` | CC。1件なら文字列、複数ならリスト。省略可 |

宛先を複数にする場合:

```python
with Outlook() as mail:
    mail.save_draft(
        to=["taro@example.co.jp", "hanako@example.co.jp"],
        cc=["jiro@example.co.jp"],
        subject="日次レポート",
        body="ご確認ください。",
    )
```

- 保存先は Outlook の**下書きフォルダ**。送信はされない
- 添付に指定したファイルが無い場合は `OutlookAttachmentNotFoundError` になる
  （空の添付で下書きが作られ、誰も気づかないまま送られるのを防ぐため）
- 動作確認モード（dry run）のときは、実際には作らずログにだけ出す

---

## よくあるつまずき

### `ClassicOutlookNotAvailableError` が出る

New Outlook が使われている。従来版（Classic）Outlook に切り替えるか、管理者に相談する。
Outlook が起動していない場合も起きるので、まず Outlook を開いてから実行する。

### `OutlookFolderNotFoundError` が出る

エラーに**実際に存在するフォルダ名の一覧**が出るので、そこから正しい名前を選ぶ。
よくある原因:

- 全角・半角、空白の有無が違う
- **受信トレイの2階層下**にある（`folder` に指定できるのは受信トレイの直下だけ）

### メールが見つからない

1. `days` が短すぎないか（既定は7日）
2. 件名の文字が実際のメールと一致しているか（部分一致・大文字小文字は区別される）
3. 探しているフォルダが合っているか（受信トレイに振り分けルールが効いていないか）

### 動きが遅い

`days` を小さくする。Outlook 側の絞り込みは受信日時が最も効く。

---

## 概要コード例

README に掲載していた概要とコード例です。

詳しい使い方は [docs/Outlook操作.md](Outlook操作.md) を参照。

```python
import logging

from comken.outlook import Outlook

logger = logging.getLogger(__name__)

with Outlook() as mail:
    for message in mail.messages(subject_contains="日次データ", days=7):
        logger.info("%s / %s", message.received_at, message.subject)

    mail.save_draft(
        to="taro@example.co.jp",
        subject="日次レポート",
        body="添付をご確認ください。",
        attachments=[r"C:\作業\report.csv"],
    )
```

受信メールは新しい順に逐次読み取り、既読・未読の状態を変えません。誤送信を防ぐため
送信機能はなく、下書き保存までです。COM に対応する従来版（Classic）Outlook 専用で、
New Outlook は利用できません。Graph API は認証とネットワークが必要なため、
オフライン環境向けの代替として提供しません。

## 関連

- [機能カタログ](機能カタログ.md) — 用途別の API 一覧
- [エラー対応ガイド](../ERRORS.md#outlook-のエラー) — エラー名から対処を引く
