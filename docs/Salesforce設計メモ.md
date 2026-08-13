# Salesforce 連携 設計メモ

作成日: 2026-08-12（更新: 2026-08-13）
背景: 複数の Salesforce 組織（3組織）から、レポートとレコードを API で取得したい。
一度作って撤去した経緯があるため、**なぜ今の形にするか**を残す。
関連: [プロジェクト規約](プロジェクト規約.md)、[ライブラリ開発規約](ライブラリ開発規約.md)

> [!note] 組織名の書き方
> このリポジトリは公開しているため、**実際の組織名・サイト名は書かない**。
> 本書では `SiteA` / `SiteB` / `SiteC` の仮名を使い、配置時に書き換える
> （社内ライブラリの実名を書かないのと同じ扱い）。

---

## 経緯 — 一度作って撤去した

| 時期 | 出来事 |
|---|---|
| 〜2026-07 | `SfApiClient` / `SfRestClient` / `SfReportClient` と DPAPI 保管を実装 |
| 2026-07-29 | **撤去**（社内の既存の仕組みを使う方針になったため） |
| 2026-08-12 | 社内の仕組みを作り直すことになり、**再開**。requests も利用可になった |
| 2026-08-13 | 認証情報の DPAPI 保管（`comken.credentials`）を復活。入口を JSON 取り込みに変更 |

撤去前の実装は履歴に残っている。土台として読める。

```
git show adc3d92^:comken/salesforce/api.py     # 認証+SOQL+CRUD+レポート+Bulk 2.0
git show adc3d92^:comken/credentials/store.py  # DPAPI 保管
```

前回からの変更点は3つ。**認証を差し替え可能にする**、**組織ごとのサブクラスを持つ**、
**計測を入れる**。

---

## 認証フロー — クライアントクレデンシャル

### 決定と理由

**OAuth 2.0 クライアントクレデンシャルフロー**を採る。判断の決め手は運用制約3つ。

| 制約 | クライアントクレデンシャルでどうなるか |
|---|---|
| パスワードを平文で保存できない | 保存するのは client_id / client_secret のみ。パスワード不要 |
| リフレッシュトークンを中央集権で管理できない | **そもそも発行されない** |
| 無人実行（人がブラウザ操作できない） | 対話ログインなし |

公式ドキュメントに明記されている。

> **This flow doesn't support refresh tokens.**
>
> — [OAuth 2.0 Client Credentials Flow for Server-to-Server Integration](https://help.salesforce.com/s/articleView?id=sf.remoteaccess_oauth_client_credentials_flow.htm&language=ja)

**「リフレッシュトークンをどう管理するか」という論点自体が消える**のが最大の利点。
リフレッシュトークンが要るのは OAuth Web サーバーフロー（人がブラウザで同意する）だけで、
これは無人・複数組織の運用と相性が最悪になる。

### 落とし穴

- **My Domain の URL 必須。** 同じドキュメントに
  「`login.salesforce.com` と `test.salesforce.com` はサポートされない」と明記がある
- 接続アプリ側で「クライアントクレデンシャルフローを有効化」＋
  **実行ユーザー（Run As）の指定**が要る。未指定だと `invalid_grant` になる
- 実行ユーザーに「API の有効化（API Enabled）」権限が要る
- 接続アプリの作成直後は反映まで数分かかる

### アクセストークンの有効期限は「測らない」

有効期限は固定値ではなく、**接続アプリのセッションポリシー → 未設定ならユーザーのプロファイル
→ それも未設定なら組織のセッション設定**、の順で決まる
（[Manage Session Policies for a Connected App](https://help.salesforce.com/s/articleView?id=xcloud.connected_app_manage_session_policies.htm&language=ja)）。

つまり**コード側で残り秒数を計算する意味がない**。次の方針にする。

1. 起動時に1回トークンを取る
2. `401`（`INVALID_SESSION_ID`）が返ったら、**その場で1回だけ取り直して同じリクエストを再送**
3. `expires_in` は見ない・保存しない

再送は1回だけに限る（2回連続で 401 なら設定不備なので、リトライで隠さず落とす）。

### 将来 JWT に移る場合

JWT ベアラーフローも**リフレッシュトークンを発行しない**ので、上の制約は同じく満たす。
違いは「client_secret がネットワークを流れない」点と、`cryptography` / `PyJWT` が要る点。
オフライン環境への持ち込み可否が未確定のため**今は採らない**が、
認証を独立クラスにしておき、通った時点で差し替えられるようにする。

---

## クラス設計

### 方針: 認証とレポートは「持たせる」、組織は「継承する」

```
SalesforceBase                     HTTP の土台。_request() が唯一の通り道
  ._oauth   : SfOAuth              トークン取得（JWT 版に差し替え可）
  ._metrics : SfMetrics            計測
  .report   : SfReport             レポート API
  .query() / .get() / .insert() …  SOQL・CRUD
  │
  ├─ SiteA(SalesforceBase)         組織固有の処理を書き加える
  ├─ SiteB(SalesforceBase)
  └─ SiteC(SalesforceBase)
```

**なぜレポートを継承にしないか。** `SfReport` を `SalesforceBase` のサブクラスにすると、
`SiteA` は `SfReport` ではないためレポートを呼べず、多重継承に追い込まれる。
持たせる形なら `site_a.report.run(...)` と `site_a.query(...)` が同じインスタンスから出る。

**なぜ認証を継承にしないか。** OAuth は「Salesforce の一種」ではなく「トークンを取る部品」。
継承すると `SfReport` まで認証コードを引き継いで責務が混ざる。
合成にしておけば JWT 版の差し替えが `_oauth` の入れ替えだけで済む。

**なぜ組織は継承にするか。** 3組織は URL と認証情報が違うだけでなく、
多少の処理差があると分かっている。差分の置き場としてサブクラスが要る。
差が無い組織は素の `SalesforceBase` を使えばよい。

### 使い方のイメージ

```python
from comken.salesforce import SiteA
from comken.credentials import Credentials

cred = Credentials("site_a")
with SiteA(
    client_id=cred.client_id,
    client_secret=cred.client_secret,
    domain_url="https://example.my.salesforce.com",
) as sf:
    rows = sf.report.run("00O000000000001")
    ...
```

---

## レポート — 2000行の壁

### 事実

同期・非同期の**どちらも 2000 行が上限**。

> **The API returns up to the first 2,000 report rows. You can narrow results using filters.**
>
> — [Requirements and Limitations — Reports and Dashboards REST API](https://developer.salesforce.com/docs/atlas.en-us.api_analytics.meta/api_analytics/sforce_analytics_rest_api_limits_limitations.htm)

**非同期にすれば 2000 行を超えられる、というのは誤り。**
撤去前の実装の docstring にこの誤りが入っていたので、作り直しでは持ち込まない。
非同期の利点は「重いレポートで HTTP タイムアウトしない」ことと実行枠
（同期 500 回/時、非同期 1200 回/時）であって、行数制限の解除ではない。

### 方針: 3段構え

| 段 | やること | 適用 |
|---|---|---|
| 1. 検知して止める | レスポンスの `allData` が偽なら**例外で止める** | 常時・全レポート |
| 2. フィルタ分割 | 日付等で区切って複数回実行し結合 | 1区間が 2000 行に収まるうち |
| 3. SOQL へ書き換え | 1区間でも超えるものだけ `query()` に置換 | 出てきたものから1本ずつ |

**1段目を既定で例外にするのが肝。** 件数が日によって変わるため、
「今日は 1998 件で通り、明日 2001 件で黙って 3 件欠ける」が最も危ない。
欠損した帳票が出るより、止まって気づく方が安い。
承知の上で切り捨てたい場面だけ、引数で警告に落とせるようにする。

公式が「filters で絞れ」と書いているとおり、2段目は正攻法。
3段目を先回りで全部やる必要はない。**計測（後述）が移行対象を教えてくれる**。

### レポート形式

明細（TABULAR）以外は `factMap` の構造が変わり、そのまま読むと**無言で空を返す**。
`reportFormat` を見て、明細以外は明示的にエラーにする（撤去前の実装と同じ扱い）。
実際にどの形式かは触れば分かるので、事前に決め打ちしない。

---

## 計測

`_request()` が唯一の通り道なので、そこ1点で全部拾える。

| 取るもの | 用途 |
|---|---|
| 呼び出し回数（組織別・呼び出し元別） | 使用量の把握 |
| 呼び出し元コンポーネント | どこが API を食っているか。`component` 引数で分類する |
| リトライ回数（401 再認証 / 5xx / 制限超過を区別） | 不安定さの検知 |
| 所要時間 | 呼び出し元ごとの合計秒数 |
| **レポートの切り捨て発生** | **SOQL 化すべきレポートの洗い出し** |

> [!note] リトライは実際に行う
> 「リトライ回数」を数えるからには、数えるだけで終わらせない。
> **401 は取り直して1回だけ**やり直し（2回目の 401 は設定不備なので隠さずエラーにする）、
> **5xx と 429 は待ち時間を伸ばしながら最大3回**やり直す。4xx はやり直しても
> 直らないので即エラー。数えているのに一度もやり直していない、という嘘の計測を作らない。

もう1つ、自前カウントより信頼できる情報源がある。レスポンスヘッダーの
`Sforce-Limit-Info: api-usage=1234/15000` で、**組織の 24 時間 API 消費量が実測で取れる**。
上限に対する割合が分かるので、自前カウントと併せて記録する。

出力は**ログのサマリと CSV 追記の両方**。CSV があると、消費量の推移と切り捨て発生を
日次で追えるようになり、「どのレポートから SOQL 化するか」が実測で決まる。

---

## 認証情報の保存（2026-08-13 実装）

平文 JSON を置いて読む形にはできないため、**DPAPI で暗号化した 1 ファイル**に取り込む。
撤去前の `credentials.dat`（DPAPI で暗号化した JSON）と同じ形式なので、
**保存側はそのまま流用し、入口だけ差し替えた**（`comken.credentials`）。

```
平文の JSON      →  取り込みコマンド  →  DPAPI 暗号化ファイル  →  コードから読む
（一時的に置く）      （暗号化して取込）    （ユーザー×PC に紐付く）   Credentials("site_a")
                      平文は確認後に削除
```

- 撤去前は対話式 CLI で 1 件ずつ登録していた。**JSON を食わせる**形に変えた。
  配布時に手入力を挟まないため
- JSON はシステム名ごとに項目をまとめる形式（`{"site_a": {"client_id": ...}}`）にして、
  `site_a_client_id` というキー名に展開する。組織ごとに client_id / client_secret が
  別なので、システム名で分けられる形が要る
- 取り込みは**まとめて 1 回書く**。1 件ずつ保存すると件数ぶん復号と暗号化を繰り返し、
  途中で失敗すると一部だけ入った状態になる
- **平文 JSON は既定では消さない。** `--delete-source` を付けたときだけ消す。
  DPAPI は登録したユーザーでしか復号できないので、実行アカウントが違うと
  「読めない」と気づく前に元の値を失う。`list` で読めることを確かめてから消す
- DPAPI は**同じ Windows ユーザー × 同じ PC** でしか復号できない。
  登録した本人と実行アカウントが違うとハマる（一番多い事故）。
  原因を区別できないので、確認する順番を書いた `CredentialDecryptionError` にまとめた
- `Salesforce.from_credentials()` を入口にした。組織クラスの `CREDENTIAL_PREFIX` から
  client_id / client_secret を読むので、**呼び出し側のコードに秘密の値が現れない**。
  `credentials` の import はこのメソッドの中だけ（遅延 import）。認証情報を直接渡す
  使い方をする人に DPAPI 依存を持ち込まないため

### 何を守っていて、何を守っていないか

- **機密境界は DPAPI であって、ファイルの ACL ではない。** 保存先はユーザープロファイル内
  （`%USERPROFILE%\.comken\`）で、ACL は明示的に絞っていない。暗号文をコピーされても
  中身は読めないが、**消す・差し替えるのは防げない**（可用性は守っていない）
- **書き手が1つであることが前提。** 読んで足して書き戻す流れなので、2つのプロセスが
  同時に書くと後から書いたほうが勝つ。取り込みは人が1回だけ実行する運用なので、
  ロックは持たせていない。アトミック置換が守るのは「途中で落ちても壊れない」ことだけ
- **「復号できない」と「中身が壊れている」は別の例外に分けた**
  （`CredentialDecryptionError` / `CredentialStoreCorruptedError`）。
  前者は実行アカウントを直す、後者は取り込み直す、と対処が違うため

複数台への配布が必要になったら、公開鍵ハイブリッド方式を足す余地がある。
ただし `cryptography` 依存が JWT と同じ関門に当たるため、
**まずローカル保管で動かし、配布が現実の問題になってから**にする。

---

## 未確定事項

- [ ] `cryptography` / `PyJWT` をオフライン環境へ持ち込めるか（決裁待ち）
      → 通れば JWT フローと公開鍵配布の両方が解禁される
- [ ] 3組織の処理差が実際にどこまであるか（サブクラスに何を書くか）
- [ ] 2000 行を超えるレポートが実在するか・どれか（計測で洗い出す）
- [ ] レポートが明細形式か集計形式か（触れば分かる）
- [ ] 接続アプリを 3 組織それぞれで作成できるか（管理者への依頼ルート）

---

## 参考（一次情報）

- [OAuth 2.0 Client Credentials Flow for Server-to-Server Integration](https://help.salesforce.com/s/articleView?id=sf.remoteaccess_oauth_client_credentials_flow.htm&language=ja)
- [Requirements and Limitations — Reports and Dashboards REST API](https://developer.salesforce.com/docs/atlas.en-us.api_analytics.meta/api_analytics/sforce_analytics_rest_api_limits_limitations.htm)
- [Manage Session Policies for a Connected App](https://help.salesforce.com/s/articleView?id=xcloud.connected_app_manage_session_policies.htm&language=ja)
- [Run Reports Synchronously or Asynchronously](https://developer.salesforce.com/docs/atlas.en-us.api_analytics.meta/api_analytics/sforce_analytics_rest_api_get_reportdata.htm)
