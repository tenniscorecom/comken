# Salesforce 連携 設計メモ

[README（ドキュメントの入口）へ戻る](../README.md)

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

---

# Claude が書いた新方針セクション（Codex はこれを統合先へ組み込む）

以下は 2026-08-13 に決めた新しい方針。上記の従来判断を
**上書きするのではなく、変更点として追記する**（Brain の方針: 過去を書き換えず履歴として残す）。

---

## 2026-08-13 の変更: 接続アプリ → External Client App

### 何が変わったか

**接続アプリ（Connected App）は新規に作れなくなった。** Spring '26 以降、UI・Metadata API の
両方で作成が既定で禁止され、再有効化には Salesforce サポートへの依頼が要る。
新規は **External Client App（ECA）** を使う。既存の接続アプリは動き続ける。

- 出典: [New connected apps can no longer be created in Spring '26](https://community.servicemax.com/s/article/Announcement-Salesforce---New-connected-apps-can-no-longer-be-created-in-Spring-26)
- 出典: [External Client Apps in Salesforce Spring '26: A Practical Migration Guide](https://dev.to/dipojjal/external-client-apps-in-salesforce-spring-26-a-practical-migration-guide-37o0)

**この案件のアプリはこれから作るもの**なので、選択の余地なく ECA になる。

### 認証フローは変えない

ECA でも **OAuth 2.0 クライアントクレデンシャルフロー**が使える。
2026-08-12 に決めた3つの運用制約（パスワードを平文で保存できない／リフレッシュトークンを
中央集権で管理できない／無人実行）は今も有効で、判断は変わらない。

- 出典: [Configure an External Client App for OAuth 2.0 Client Credentials Flow](https://help.salesforce.com/s/articleView?id=xcloud.meta_configure_client_credentials_flow_for_external_client_apps.htm&language=en_US&type=5)

トークン取得のエンドポイントと手順は接続アプリと同じなので、`comken/salesforce/oauth.py` は
そのまま使える。

---

## secret ローテーションを自分で回す

### なぜ要るか

Salesforce は consumer secret を**定期的に変更すること**を推奨している。
「90日」のような具体的な数字は公式には無く、「periodically（定期的に）」とだけ書かれている。

- 出典: [View and Rotate the Consumer Key and Consumer Secret of a Connected App](https://help.salesforce.com/s/articleView?id=xcloud.connected_app_rotate_consumer_details.htm&language=en_US&type=5)

問題は数字ではなく**運用**にある。四半期であれ半年であれ、そのたびに情シスへ連絡して
新しい secret を発行してもらう必要があり、決裁が要る。これが実務上の負担になる。

### 解決: ECA は REST API でローテーションできる

Winter '26（API v65.0）で、ECA の consumer key / secret を REST API から
ローテーションできるようになった。

```
GET   /services/data/v67.0/apps/oauth/credentials/{appId}
POST  /services/data/v67.0/apps/oauth/credentials/{appId}/{consumerId}/staged
PATCH /services/data/v67.0/apps/oauth/credentials/{appId}/{consumerId}/staged/{stagedId}
      {"command": "rotate"}
```

- 新旧2セットが**同時に有効**なので、無停止で切り替わる
- ローテーション後、旧セットは **30日後に自動削除**される
- 前提: Setup の Apps/External Client Apps で
  **「Allow access to External Client App consumer secrets via REST API」を有効化**する

- 出典: [Salesforce External Client App key and secret rotation via REST API](https://lekkimworld.com/2025/09/24/salesforce-external-client-app-key-and-secret-rotation-via-rest-api/)

**情シスへの依頼はこの有効化1回だけ**で、以後のローテーションは comken が自分で実行できる。
これが「定期的に情シスへ連絡する」負担を消す。

### なぜ JWT ではないのか

JWT ベアラーフローなら client_secret 自体が無くなるので、ローテーション問題は根本から消える。
それでも採らないのは、**`cryptography` を社内オフライン環境へ持ち込めないため**（pip が使えず、
持ち込みには決裁が要る。2026-08-13 時点で未決）。

ECA のローテーション API は `requests` だけで叩ける。`requests` は既に解禁済みなので、
**追加の決裁なしで実装できる**のが決め手。

決裁が通れば JWT に移る価値は残る（secret がネットワークを流れない）。認証は独立クラスに
してあるので、`_oauth` の差し替えで移れる。

### なぜリフレッシュトークンではないのか

2026-08-13 に検討して**採らなかった**。理由は3つ。

1. **痛みが消えない。** リフレッシュトークンフローでも client_secret は要る
   （接続アプリ/ECA 側の「Require Secret for Refresh Token Flow」を管理者がオフにしない限り）
2. **「ユーザー側で更新しやすい」が成り立たない。** リフレッシュトークンの有効期限は
   Refresh Token Policy で**管理者が**決める（即時失効／N日未使用で失効／N日後に失効／
   取り消されるまで有効）。使う側では決められないし、期間が一意に決まらない
3. **無人実行という前提を壊す。** リフレッシュトークンの初回取得には、ブラウザで人が
   同意する操作が必須。組織が3つあれば3回、失効のたびに再実行が要る

- 出典: [Manage OAuth Access Policies for a Connected App](https://help.salesforce.com/s/articleView?language=en_US&id=sf.connected_app_manage_oauth.htm&type=5)

---

## ローテーション実装の設計

### 実行順序（この順序でないと詰む）

1. `POST .../staged` で新しい資格情報を作る。**レスポンスに新しい key / secret が入る**
2. **先に DPAPI へ保存する**（この時点で新旧どちらも有効なので、まだ壊れない）
3. `PATCH .../staged/{stagedId}` で `{"command": "rotate"}` を実行し、新しい方を有効にする
4. 旧セットは 30日後に Salesforce 側で自動削除される

2 と 3 を逆にすると、rotate 済みなのに新しい secret を保存できていない状態が起こりうる。
**保存が先**。保存に失敗しても rotate していなければ、旧 secret のまま何も壊れない。

### いつ実行するか

最終ローテーション日を DPAPI に一緒に保存し、`config.ini` で指定した日数
（既定は 60日程度）を過ぎていたら実行する。旧セットの猶予が30日なので、
猶予より短い間隔で回す必要はない。

### 落とし穴: DPAPI は他の PC と共有できない（最重要）

`comken/credentials/store.py` は認証情報を `Path.home()/.comken/credentials.dat` に
**Windows DPAPI** で暗号化して保存する。DPAPI は**登録した Windows ユーザーと PC に
紐付く**ので、別ユーザー・別 PC では復号できない（これは意図した設計）。

つまり **ローテーションを実行した PC だけが新しい secret を持つ**。
他の PC は古い secret を持ったまま 30日後に動かなくなり、しかも新しい secret を
受け取る手段がない。

したがって次の制約を置く。

- **同じ ECA の資格情報を複数の PC で使っている場合、ローテーションを有効にしてよいのは1台だけ。**
- 複数台で動かす必要があるなら、PC ごとに別の ECA（別の consumer）を用意する
- ローテーションは既定で**無効**にし、`config.ini` で明示的に有効化した環境だけが実行する
  （知らないうちに他の PC を壊さないため）

この制約はコードのコメントと docstring に必ず書く。半年後に読む人が
「なぜ1台だけなのか」を追えるようにするため。

### 検証できていないこと

REST API のレスポンス本文の正確なスキーマは、公開されている記事から読み取ったもので、
**Salesforce 公式のリファレンスで確認できていない**（ヘルプが JS レンダリングのため未取得）。
実装は社内環境で実際に叩いて確認する必要がある。
フィールド名が違っていた場合に備え、レスポンスの取り出しは1箇所にまとめる。

---

## API バージョンを 60.0 → 67.0 へ

現在 `comken/salesforce/client.py` の `API_VERSION = "60.0"`（Spring '24）。
**ローテーション API が v65.0 以降でしか使えない**ため、上げる必要がある。

最新は **v67.0（Summer '26）**。

- 出典: [Salesforce Summer '26 Release API Updates: API Version 67.0](https://www.conemis.com/news/salesforce-summer-26-release-api-updates-version-67-0)

### 廃止スケジュールとの関係（v60.0 は危険ではない）

- **Platform API v31.0〜40.0** — Summer '27 に非推奨、**Summer '28 に廃止**。v60.0 は対象外
- **SOAP API の `login()` 呼び出し（v31.0〜64.0）** — Summer '27 に廃止。
  ただし comken は **REST + OAuth** なので `login()` を使っておらず、**無関係**
- v21.0〜30.0 は既に廃止済み（HTTP 410 GONE）

- 出典: [Salesforce SOAP API Retirement: Before Summer '27](https://www.apexhours.com/salesforce-soap-api-retirement-everything-you-need-to-know-before-summer-27/)

v67.0 の主な変更は「Apex のセキュリティ既定が user mode に」「`WITH SECURITY_ENFORCED` の削除」だが、
これは **Apex の話**で、REST API を外から叩く comken には影響しない。

---

# 付録: JWT ベアラーフローと認証情報の鍵配布

# JWT ベアラーフローと認証情報の鍵配布（準備）

作成日: 2026-08-12
背景: `cryptography` をオフライン環境へ持ち込める見込みが立ったため、
[Salesforce 連携 設計メモ](salesforce.md) で「後回し」にした2つを先に用意する。

1. **JWT ベアラーフロー** — client_secret をネットワークに流さない認証
2. **公開鍵ハイブリッド暗号での認証情報配布** — 複数台へ機密を一括で配る

> [!important] まだ入れていない
> `cryptography` は決裁待ちで、**comken の依存には追加していない**。
> 本書のコードは動作確認済みだが、置き場所を用意しただけの段階。
> 通った時点で `comken/salesforce/` と `comken/credentials/` に落とす。

本書のコードは**すべて実際に実行して確認した**（末尾の「検証結果」参照）。

---

## パート1: JWT ベアラーフロー

### 仕様（一次情報）

[OAuth 2.0 JWT Bearer Flow for Server-to-Server Integration](https://help.salesforce.com/s/articleView?id=sf.remoteaccess_oauth_jwt_flow.htm&language=ja) より。

| 項目 | 値 |
|---|---|
| `iss`（発行者） | 接続アプリの client_id（Consumer Key） |
| `sub`（主体） | 成り代わるユーザーの username |
| `aud`（対象） | `https://login.salesforce.com`（本番） / `https://test.salesforce.com`（Sandbox） |
| `exp`（期限） | UTC エポック秒。**時計ずれの許容は3分** |
| 署名 | **RSA SHA256（RS256）** |
| `grant_type` | `urn:ietf:params:oauth:grant-type:jwt-bearer` |

> **This flow never issues a refresh token.**

クライアントクレデンシャルと同じく、**リフレッシュトークンの管理問題は発生しない**。

> [!warning] `aud` と接続先を混同しない
> クライアントクレデンシャルは **My Domain 必須**（`login.salesforce.com` 不可）だったが、
> JWT の `aud` は逆に **`login.salesforce.com` / `test.salesforce.com`** を書く。
> `aud` は「認可サーバーの識別子」であって POST 先の URL とは別物。
> 前のフローの知識をそのまま持ち込むとここで詰まる。

### PyJWT は要らない

`cryptography` だけで JWT を組み立てられる。**持ち込む wheel が1つ減る**ので、
オフライン環境ではこれが効く。生成した JWT が PyJWT で検証できることも確認済み
（他実装と相互運用できる ＝ 独自形式になっていない）。

### 鍵と証明書を作る

接続アプリには**公開鍵証明書（X.509）**をアップロードする。自己署名でよい。

```python
import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

KEY_SIZE_BITS = 2048
CERT_VALID_DAYS = 365


def create_key_and_certificate(common_name: str, out_dir: Path) -> tuple[Path, Path]:
    """秘密鍵と自己署名証明書を作り、(秘密鍵パス, 証明書パス) を返す。

    証明書は接続アプリへアップロードする。秘密鍵は外に出さない。
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE_BITS)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)  # 自己署名なので発行者は自分
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=CERT_VALID_DAYS))
        .sign(private_key, hashes.SHA256())
    )

    key_path = out_dir / f"{common_name}.key.pem"
    cert_path = out_dir / f"{common_name}.crt"
    key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return key_path, cert_path
```

**秘密鍵は平文で置かない。** 作ったら DPAPI で包んで保管する（パート2と同じ方式）。
証明書の有効期限が切れると認証が止まるので、期限は台帳で管理すること。

### トークンを取る

```python
import base64
import json
import time

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

TOKEN_PATH = "/services/oauth2/token"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"
ASSERTION_LIFETIME_SECONDS = 180  # 時計ずれの許容が3分なので、それに合わせる
TIMEOUT_SECONDS = 30


def _b64url(raw: bytes) -> str:
    """JWT で使う、パディングなしの base64url に変換する。"""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def build_assertion(
    client_id: str, username: str, audience: str, private_key_pem: bytes
) -> str:
    """署名済みの JWT を組み立てて返す。

    Args:
        client_id: 接続アプリの Consumer Key。
        username: 成り代わるユーザーの username。
        audience: 本番なら "https://login.salesforce.com"。
        private_key_pem: 証明書と対になる秘密鍵の PEM。
    """
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": client_id,
        "sub": username,
        "aud": audience,
        "exp": int(time.time()) + ASSERTION_LIFETIME_SECONDS,
    }
    segments = [
        _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("ascii")
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{'.'.join(segments)}.{_b64url(signature)}"


def fetch_token(assertion: str, login_url: str) -> tuple[str, str]:
    """JWT を渡してアクセストークンと instance_url を取得する。"""
    response = requests.post(
        f"{login_url.rstrip('/')}{TOKEN_PATH}",
        data={"grant_type": GRANT_TYPE, "assertion": assertion},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    return body["access_token"], body["instance_url"]
```

`padding.PKCS1v15()` + `hashes.SHA256()` が RS256 の実体。ここを OAEP や PSS に
間違えると Salesforce 側で無言の `invalid_grant` になる。

### 管理者に依頼すること

1. 接続アプリ（新規は External Client App 推奨）を作り、OAuth を有効化
2. **「デジタル署名を使用」に上で作った `.crt` をアップロード**
3. スコープに `api` を入れる
4. **実行ユーザーを事前承認する** — 「管理者が承認したユーザーは事前承認済み」に設定し、
   プロファイルまたは権限セットを割り当てる。ここが抜けると `invalid_grant` になる
5. 実行ユーザーに「API の有効化（API Enabled）」を付与

### 差し替え方

[設計メモ](salesforce.md)のとおり、認証は `SalesforceBase` が**持つ**部品にする。
クライアントクレデンシャル版と JWT 版が同じ形（トークンと instance_url を返す）を
満たしていれば、入れ替えるだけで移行できる。

```python
class SfJwtOAuth:
    """JWT ベアラーフローでトークンを取る。SfOAuth と同じ形を満たす。"""

    def __init__(self, client_id: str, username: str, login_url: str, private_key_pem: bytes):
        self._client_id = client_id
        self._username = username
        self._login_url = login_url
        self._private_key_pem = private_key_pem

    def fetch(self) -> tuple[str, str]:
        """(アクセストークン, instance_url) を返す。401 のたびに呼び直してよい。"""
        assertion = build_assertion(
            self._client_id, self._username, self._login_url, self._private_key_pem
        )
        return fetch_token(assertion, self._login_url)
```

---

## パート2: 公開鍵ハイブリッド暗号での配布

### 何を解決するか

DPAPI は**同じ Windows ユーザー × 同じ PC** でしか復号できない。
だから「管理サーバーで暗号化して各PCへ配る」が原理的にできない。
各PCに鍵ペアを持たせ、**公開鍵で包んで配る**とこれが解ける。

```
管理サーバー                共有フォルダ              実行PC
────────────           ──────────         ────────────
機密を登録                 public_keys/          [初回] setup:
    │                      ├ PC01.pem  ◀──────  鍵ペア生成・公開鍵を提出
    │                      └ PC02.pem            秘密鍵は DPAPI で保護
    ▼
pack: 全公開鍵で暗号化 ──▶ bundle.json ──────▶  [毎回] pull:
                                                  秘密鍵で開いてローカルへ取り込み
```

**肝は「配布＝ローカル保管の同期」と捉えること。** 実行PC側は開いたら既存の保存関数で
登録するだけなので、コード側の読み出し（`Credentials("site_a")`）は一切変わらない。

### なぜハイブリッドか

RSA は長いデータを直接暗号化できない。そこで**共通鍵で本文を1回だけ暗号化し、
その共通鍵だけを台数分 RSA で包む**。台数が増えても本文は1つで済む。

| 部品 | 選定 | 理由 |
|---|---|---|
| 本文の暗号化 | Fernet（AES + HMAC） | 認証付き。**改ざんが復号時に必ず露見する** |
| 共通鍵の包み | RSA-OAEP（SHA-256）・3072bit | `cryptography` 標準 |
| 秘密鍵の保管 | PEM を DPAPI で暗号化 | 鍵管理が不要 |

### bundle を作る（管理サーバー）

```python
import base64
import json

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

BUNDLE_VERSION = 1


def _oaep() -> padding.OAEP:
    return padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None
    )


def pack_bundle(secrets: dict, public_key_pems: dict) -> dict:
    """機密一式を、登録済みの全公開鍵で開ける bundle にする。

    Args:
        secrets: {"site_a_client_id": "...", ...} の平文辞書。
        public_key_pems: {"PC01": 公開鍵PEM, ...}。
    """
    fernet_key = Fernet.generate_key()
    payload = Fernet(fernet_key).encrypt(json.dumps(secrets, ensure_ascii=False).encode("utf-8"))

    wrapped_keys = {}
    for name, public_pem in public_key_pems.items():
        public_key = serialization.load_pem_public_key(public_pem)
        wrapped = public_key.encrypt(fernet_key, _oaep())
        wrapped_keys[name] = base64.b64encode(wrapped).decode("ascii")

    return {
        "version": BUNDLE_VERSION,
        "payload": base64.b64encode(payload).decode("ascii"),
        "wrapped_keys": wrapped_keys,
    }
```

### bundle を開く（実行PC）

```python
def open_bundle(bundle: dict, machine_name: str, private_key_pem: bytes) -> dict:
    """自分あての共通鍵を取り出して本文を復号する。

    Raises:
        KeyError: この PC が bundle に登録されていない場合。
    """
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    fernet_key = private_key.decrypt(
        base64.b64decode(bundle["wrapped_keys"][machine_name]), _oaep()
    )
    raw = Fernet(fernet_key).decrypt(base64.b64decode(bundle["payload"]))
    return json.loads(raw.decode("utf-8"))
```

### 秘密鍵を DPAPI で保管する

```python
import os
from pathlib import Path

import win32crypt

KEY_DESCRIPTION = "comken dist key"


def save_private_key(private_key_pem: bytes, path: Path) -> None:
    """秘密鍵を DPAPI で暗号化して保存する。

    一時ファイル経由で置き換え、書き込み中のクラッシュで鍵が壊れるのを防ぐ。
    """
    encrypted = win32crypt.CryptProtectData(
        private_key_pem, KEY_DESCRIPTION, None, None, None, 0
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f".{os.getpid()}.tmp")
    tmp_path.write_bytes(encrypted)
    os.replace(tmp_path, path)


def load_private_key(path: Path) -> bytes:
    """DPAPI で保管した秘密鍵を復号して返す。"""
    _, private_key_pem = win32crypt.CryptUnprotectData(
        path.read_bytes(), None, None, None, 0
    )
    return private_key_pem
```

### 運用の注意

| 論点 | 対応 |
|---|---|
| **公開鍵のすり替えが唯一の本質的な弱点** | 攻撃者が偽の公開鍵を置くと次回の pack から機密を受け取れる。共有フォルダの**書き込み権限を絞る**、pack 時に包んだ PC 名をログに出して台帳と照合する |
| DPAPI はユーザー単位 | setup と実行を**同じ Windows アカウント**で行う。一番ハマりやすい |
| 管理サーバーには平文が集まる | どの配布方式でも同じ。サーバー自体の保護が本丸 |
| ログに値を出さない | 出してよいのはキー名と件数まで |
| bundle と公開鍵は秘密でない | 読まれても安全。**守るのは書き込みだけ** |

---

## 検証結果

本書のコードを実行して確認した内容。

| 確認 | 結果 |
|---|---|
| JWT を組み立てて PyJWT で検証 | 成功（iss / sub / aud が意図どおり） |
| `cryptography` だけで署名検証 | 成功（PyJWT なしで完結する） |
| 3台ぶんの bundle を作り全台で復号 | 成功（bundle 1891 バイト） |
| 未登録の鍵で復号を試みる | 失敗する（`ValueError`）＝ 意図どおり |
| payload を1バイト改ざんして復号 | 検出される（`InvalidToken`）＝ 意図どおり |
| 秘密鍵を DPAPI で保存して復号 | 成功（2484 → 2740 バイト） |
| 自己署名証明書の生成 | 成功（CN・有効期限・鍵長を確認） |

## 次にやること

- [ ] `cryptography` の決裁を通す（これが全ての前提）
- [ ] 通ったら `pyproject.toml` と `requirements.txt` に追加し、本書のコードを実装に落とす
- [ ] JWT は接続アプリの設定（証明書アップロード・事前承認）が要るので、管理者依頼と並行する
- [ ] 配布方式は、実際に複数台構成になってから入れる（1台なら DPAPI 直接登録で足りる）

---

## 実装を使うときの早見

前半の設計判断を、利用側から引ける形にまとめる。背景と制約の説明は前半を正とする。

1インスタンスが1組織を受け持つ。認証は OAuth 2.0 クライアントクレデンシャルフローで、
**ユーザー名・パスワード・セキュリティトークン・リフレッシュトークンを使わない**
（このフローはリフレッシュトークンを発行しないため、保管も更新も発生しない）。

```python
from comken.salesforce import Salesforce

with Salesforce(
    client_id="接続アプリの Consumer Key",
    client_secret="接続アプリの Consumer Secret",
    domain_url="https://your-domain.my.salesforce.com",   # My Domain 必須
    org_name="site_a",                                     # 計測ログでの呼び名
) as sf:
    accounts = sf.query("SELECT Id, Name FROM Account")    # 行数の上限なし・ページ送り自動
    new_id = sf.insert("Account", {"Name": "新規取引先"})
    sf.update("Account", record_id=new_id, data={"Name": "更新後"})

    rows = sf.report.run("00O000000000001")                # レポートは上限 2000 行

    sf.metrics.log_summary()                               # 使用量を最後にまとめて出す
```

`domain_url` は組織の **My Domain** を渡す。`login.salesforce.com` ではこのフローは動かない。

### 事前に管理者へ依頼すること

1. RPA 専用のインテグレーションユーザーを作る（「API の有効化」権限）
2. 接続アプリを作り、OAuth 有効化・スコープ `api`・
   **「クライアントクレデンシャルフローを有効化」**にチェック
3. 接続アプリのポリシーで**実行ユーザー（Run As）**に 1 のユーザーを指定
   （未指定だと `invalid_grant` になる）
4. Consumer Key / Consumer Secret を受け取る

### レポートの 2000 行制限

レポート API は**同期・非同期のどちらも 2000 行が上限**で、非同期にしても超えられない。
上限で切り捨てられた場合は既定で `SalesforceReportTruncatedError` を送出して**止める**
（欠けたデータのまま処理が進むのを防ぐため）。

```python
# 期間で区切って回避する
rows = sf.report.run(
    "00O000000000001",
    filters=[{"column": "CREATED_DATE", "operator": "greaterThan", "value": "2026-01-01"}],
)

# それでも足りないときは SOQL に置き換える（行数の上限がない）
rows = sf.query("SELECT Name, Amount FROM Opportunity WHERE CreatedDate > 2026-01-01T00:00:00Z")
```

### 組織（サイト）ごとのクラス

組織は My Domain の URL が違うので、1組織につき1クラスにする。
3組織ぶんの雛形が `comken/salesforce/sites/` に入っている。

```python
from comken.salesforce.sites import SITES, SiteA

with SiteA.from_credentials(config.SITE_A.DOMAIN_URL) as sf:
    rows = sf.案件一覧()

# 3組織をまとめて回す
for site_class in SITES:
    domain_url = getattr(config, site_class.CONFIG_SECTION).DOMAIN_URL
    with site_class.from_credentials(domain_url) as sf:
        rows = sf.案件一覧()
```

`from_credentials()` は `CREDENTIAL_PREFIX` を頭に付けたキー名で、DPAPI に保管した
client_id / client_secret を読む（後述の [credentials](credentials.md#credentials)）。
コードにも config.ini にも秘密の値が現れない。

各クラスには `CREDENTIAL_PREFIX`（認証情報のキー名の頭）・`CONFIG_SECTION`
（My Domain を書く config.ini のセクション名）・`REPORT_*`（その組織のレポート ID）を持たせる。
共通の操作は `Salesforce` にあるので、書くのは**その組織でしか通じないもの**だけ。
計測の組織名は指定しなければクラス名になるので、ログで組織を見分けられる。

**`SiteA` / `SiteB` / `SiteC` は仮名。** このリポジトリは公開しているため、
実際の組織名は書かず、配置時にクラス名・`CREDENTIAL_PREFIX`・`CONFIG_SECTION` を
書き換える（`comken/run.py` の `example_libs.v0000` と同じ扱い）。

書き込み系（`insert` / `update` / `upsert` / `delete`）は `dry_run` を尊重する。
使い方の一覧は [docs/機能カタログ.md](機能カタログ.md)、
設計の背景は [docs/salesforce.md](salesforce.md) を参照。

---

## 関連

- [README](../README.md) — ライブラリ全体の概要と環境構築
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
