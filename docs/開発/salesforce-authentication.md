# Salesforce authentication decisions

この文書は、`comken.toolbox.salesforce` の認証方式を社内で説明するための判断記録です。
Salesforce の公式発表・仕様と、それを受けた comken 側の判断を分けて記載します。

最終確認日: 2026-08-13

## 結論

- 新規の連携アプリには **External Client App（ECA）** を使う。
- 無人バッチの認証は **Authorization Code + Refresh Token Flow**。**これが既定**で、
  組織クラスをそのまま使えばこの方式になる（`with Sandbox() as sf:`）。
- **Client Credentials Flow は本番で使わない。** ECA 側でも無効にする。
  `client_secret` だけでアクセストークンを取れてしまい、漏えいすると実行ユーザーとして
  操作されるため（→ 次の節）。開発中に手元で動かすときだけ
  `Sandbox(auth=ClientCredentialsAuth(...))` と**明示的に渡す**。
- 実行専用ユーザーを割り当て、権限はそのユーザー側で最小限にする。
- `client_id` / `client_secret` / `refresh_token` はコードや `config.ini` に書かず、
  Windows DPAPI で保管する。
- アクセストークンの期限を予測せず、401 を受けたときだけ再取得して1回再試行する。
- JWT Bearer Flow は将来の移行候補として残す。

## 最重要: secretが漏えいしたときの違い

comken は両方を実装しているが、**既定は Refresh Token Flow**
（`client.py` が `oauth_refresh` を import している）。
Client Credentials Flow は、開発中に `auth=` で明示的に渡したときだけ使われる。
下の表がその理由で、**この差だけで既定を決めている**。

| 有効な認証フロー | `client_id + client_secret`だけが漏えい | 結果 |
|---|---|---|
| Client Credentials Flow | 2値だけでトークンを要求できる | **危険。実行ユーザーとしてアクセス可能** |
| Web Server / Authorization Code Flow + Refresh Token | `refresh_token`か新しい認可コードが別途必要 | 2値だけでは通常アクセスできない |
| JWT Bearer Flow | `client_secret`を使わず、秘密鍵署名が必要 | 2値だけではアクセスできない |

Refresh Token方式へ切り替える場合は、**Client Credentials Flowを無効にする**。同じECAで
Client Credentials Flowを有効にしたままでは、Refresh Tokenを併用しても、漏えいした
`client_id + client_secret`だけでアクセストークンを取得できる入口が残る。

社内要件が「ICSによるsecret更新を減らし、こちらでtokenを管理する」ことであれば、候補は次の構成。

1. Web Server / Authorization Code Flowを有効にする。
2. Client Credentials Flowを無効にする。
3. Refresh Token Rotationを有効にする。
4. `Require Secret for Refresh Token Flow`を有効にする。
5. client secretとrefresh tokenを別々に保護する。

この構成では、secret単独またはrefresh token単独の漏えいでは更新できず、両方が必要になる。
ただし、社内90日規定がclient secret自体に適用される場合の更新義務は別問題として残る。

Refresh Token Rotationは、使用するたびに古いrefresh tokenを無効化して新しいtokenへ交換する
仕組みであり、漏えいしたtokenの再利用期間を短くできる。一方、アクセストークンやrefresh tokenの
有効期限ポリシーはSalesforce管理者側の設定で決まり、クライアントプログラムが任意の秒数を指定
するものではない。

- [Rotate Refresh Tokens](https://help.salesforce.com/s/articleView?id=release-notes.rn_security_refresh_token_rotation.htm&language=en_US&type=5)
- [Manage OAuth Access Policies](https://help.salesforce.com/s/articleView?id=sf.connected_app_manage_oauth.htm&language=en_US&type=5)

## 1. なぜ External Client App なのか

### Salesforce の公式発表・仕様

Salesforce は Spring '26 から新規 Connected App の作成を制限しています。既存の Connected App
は継続利用できますが、新規開発では External Client App が推奨されています。

- [Enable OAuth Settings for API Integration](https://help.salesforce.com/s/articleView?id=connected_app_create_api_integration.htm&language=en_US)
- [New Connected Apps Can No Longer Be Created in Spring '26](https://help.salesforce.com/s/articleView?id=005228017&language=en_US&type=1)
- [External Client Apps](https://help.salesforce.com/s/articleView?id=xcloud.external_client_apps.htm&language=en_US&type=5)

ECA は、開発者が決めるOAuth設定と、各組織の管理者が決める実行ユーザー・セッションなどの
ポリシーを分離する仕組みです。

- [Secure Your Org with External Client Apps（Salesforce Developers Blog）](https://developer.salesforce.com/blogs/2025/01/secure-your-org-with-external-client-apps)

### comken 側の判断

今回の連携アプリは新規作成するため、旧方式を前提にせずECAを標準にします。組織ごとの管理者が
実行ユーザーとポリシーを管理できる点も、3組織へ同じライブラリを配る構成と合っています。

補助解説:

- [External Client Apps in Salesforce Spring '26: A Practical Migration Guide](https://dev.to/dipojjal/external-client-apps-in-salesforce-spring-26-a-practical-migration-guide-37o0)

## 2. なぜ Refresh Token Flow を既定にするのか

### 一度は Client Credentials Flow を選び、撤回した

当初はこちらを採用していた。無人実行に最も素直に合うためで、判断の材料はこの表だった。

| 要件 | Client Credentials Flow での扱い |
|---|---|
| 夜間・無人実行 | ブラウザーでのログインや同意操作が不要 |
| Salesforce パスワードを保存しない | `client_id` / `client_secret` だけを使う |
| リフレッシュトークンを管理しない | 保管・失効監視・再同意の運用が不要 |
| 操作権限を説明できる | ECA に指定した実行ユーザーの権限として監査できる |

**この表は今も正しい。運用の手間だけで見れば Client Credentials Flow の方が軽い。**
撤回したのは、手間ではなく**漏えいしたときに何が起きるか**で決め直したため。

`client_id` と `client_secret` の2値が漏れた場合の違い:

| 有効なフロー | 2値だけが漏れたとき |
|---|---|
| Client Credentials Flow | **その2値だけでアクセストークンが取れる**。実行ユーザーとして操作できる |
| Refresh Token Flow のみ | `refresh_token` か新しい認可コードが別途要る。2値だけでは通常アクセスできない |

comken は秘密の値を DPAPI に置くが、**DPAPI は同じ Windows ユーザーなら復号できる**。
運用担当者の PC が侵害されたとき、被害が「値を読まれる」で止まるか
「Salesforce を操作される」まで届くかの差になる。ここは運用の手間より重いと判断した。

### 引き換えに受け入れたもの

- 初回に**対話的な認可が1回だけ必要**（`authorization_url()` で URL を作り、
  ブラウザーで承認して `exchange_code()` に渡す）
- `refresh_token` の保管と失効監視が増える
- 設定によっては更新時にも `client_secret` が要る

いずれも初回と例外時の作業で、日々の無人実行には出てこない。
Refresh Token Rotation を有効にすると、更新のたびに新しい token へ入れ替わる。
comken は受け取った新しい token を DPAPI へ**自動で書き戻す**ので、
運用としてやることは増えない。

### Client Credentials Flow を残してある理由

**開発中に手元で動かすときだけ**使う。初回の対話的な認可を挟まずに済むため、
動作確認の回転が速い。使うときは既定を上書きして明示的に渡す。

```python
from comken.toolbox.salesforce import ClientCredentialsAuth

with Sandbox(auth=ClientCredentialsAuth(cid, secret, domain)) as sf:
    ...
```

**本番では使わない。ECA 側でも無効にする。** 有効なまま残すと、
Refresh Token Flow を併用していても、漏えいした2値で入れる入口が残る。

### Salesforce の公式仕様

Client Credentials Flow は、ユーザーが画面でログインしないサーバー間連携用です。Salesforceでは
ECAに実行ユーザーを指定し、そのユーザーとしてアクセストークンを発行します。

- [Configure a Client Credentials Flow](https://help.salesforce.com/s/articleView?id=xcloud.configure_client_credentials_flow_for_external_client_apps.htm&language=en_US&type=5)
- [Configure Client Credential Flow Policies](https://help.salesforce.com/s/articleView?id=xcloud.policies_configure_client_credentials_flow_for_external_client_apps.htm&language=en_US&type=5)
- [OAuth 2.0 Client Credentials Flow for Server-to-Server Integration](https://help.salesforce.com/s/articleView?id=xcloud.remoteaccess_oauth_client_credentials_flow_ca.htm&language=en_US&type=5)

Salesforceのトークン資料では、リフレッシュトークンを要求できるフローとしてUser-Agent Flowと
Web Server Flowが説明されています。Client Credentials Flowは、必要時に同じ認証フローを再実行して
新しいアクセストークンを得る設計です。

- [OAuth Tokens and Scopes](https://help.salesforce.com/s/articleView?id=remoteaccess_oauth_tokens_scopes.htm&language=en_US&type=5)

## 3. なぜ Username-Password Flow ではないのか

Username-Password Flow は、Salesforce ユーザーのパスワードを自動処理環境へ置く必要が
あります。「パスワードを保管しない」という要件に反するため採用しません。

Refresh Token Flow を選んだ代償（長期トークンの保護・失効ポリシー・初回の対話的な認可）は
2章に書いたとおりで、設定によっては更新時にも client secret が必要です。

- [Manage OAuth Access Policies for a Connected App](https://help.salesforce.com/s/articleView?id=sf.connected_app_manage_oauth.htm&language=en_US&type=5)
- [Require Secret for Refresh Token Flow](https://help.salesforce.com/s/articleView?id=xcloud.shr_security_require_secret_for_refresh_token_flow.htm&language=en_US&type=5)

### 社内の90日変更規定との関係

SalesforceはClient Credentials Flowの公式説明で、consumer keyとconsumer secretを持つ者が
アクセストークンを取得できることと、secretを定期的に変更し、漏えい時は直ちに変更する必要を
案内しています。また、公式リリースノートでkey / secretのローテーション機能を公開しています。

- [OAuth 2.0 Client Credentials Flow for Server-to-Server Integration](https://help.salesforce.com/s/articleView?id=xcloud.remoteaccess_oauth_client_credentials_flow.htm&language=en_US&type=5)
- [Rotate the Consumer Key and Consumer Secret](https://help.salesforce.com/s/articleView?id=release-notes.rn_security_consumer_details_rotate.htm&language=en_US&type=5)

補助解説:

- [How to configure a Connected App for the OAuth 2.0 Client Credentials Flow?](https://www.sfdc-lightning.com/2023/08/How-to-configure-a-Connected-App-for-the-OAuth-2.0-Client-Credentials-Flow.html)

Salesforceは「定期的に」としており、90日という周期までは指定していません。社内規定の
「パスワード等を90日ごとに変更」がclient secretにも適用されるかは、社内の情報セキュリティ
担当へ確認する必要があります。適用される場合、comkenでも90日以内のローテーションが必要です。

Refresh Token Flowへ変更しても、この問題が必ず消えるわけではありません。Salesforceの
`Require Secret for Refresh Token Flow`を有効にした構成では、アクセストークンの更新時に
次の3つが必要です。

- `client_id`（consumer key）
- `client_secret`（consumer secret）
- `refresh_token`

つまり、アクセストークンとリフレッシュトークンだけでは更新できず、client secretを90日で
変える規定が適用されるなら、Refresh Token Flowでも同じローテーション作業が残ります。

ただし、これはSalesforce側の設定に依存します。`Require Secret for Refresh Token Flow`を無効に
できる構成ではrefresh時のsecretを省略できます。また、JWT Bearer Flowは`client_id`を使いますが、
共有`client_secret`の代わりに秘密鍵で署名します。したがって「全OAuth方式でclient secretが
絶対必須」ではなく、「現在のClient Credentials Flowと、secret必須設定のRefresh Token Flowでは
必須」と説明するのが正確です。

## 4. なぜJWT Bearer Flowを今すぐ使わないのか

JWT Bearer Flowもサーバー間連携に適しており、共有client secretの代わりに証明書と秘密鍵を
使えます。SalesforceはECA向けの設定手順を公開しています。

- [Configure OAuth 2.0 JWT Bearer Flow for External Client Apps](https://help.salesforce.com/s/articleView?id=xcloud.meta_configure_oauth_jwt_flow_external_client_apps.htm&language=en_US&type=5)

comkenでは認証処理を独立部品にしているため、将来JWTへ交換できます。ただし現時点では、
秘密鍵の配布・更新・失効、証明書の期限管理、オフライン環境への暗号ライブラリ導入について
社内運用が確定していません。まず既に利用可能な依存関係でClient Credentials Flowを運用し、
鍵管理の体制が決まった時点でJWT移行を再評価します。

## 5. secretの保管とローテーション

`client_secret` はコード、Git、`config.ini`、ログへ書きません。`comken.toolbox.credentials` がWindows
DPAPIで暗号化し、登録したWindowsユーザーとPCに紐付けて保存します。これは共有配布の仕組み
ではないため、実行PCごとに登録が必要です。

Salesforceはconsumer key / secretのローテーション機能を提供しています。ECAではConnect REST
APIからstaged credentialsを作成できるため、新旧資格情報を切り替える実装が可能です。

- [OAuth Staged Credentials — Connect REST API](https://developer.salesforce.com/docs/atlas.en-us.chatterapi.meta/chatterapi/connect_resources_oauth_credentials_staged_credentials.htm)
- [OAuth Credentials by Consumer ID — Connect REST API](https://developer.salesforce.com/docs/atlas.en-us.chatterapi.meta/chatterapi/connect_resources_credentials_by_app_and_consumer_id.htm)
- [Use REST API for Access to External Client App OAuth Credentials](https://help.salesforce.com/s/articleView?id=release-notes.rn_security_eca_use_rest_api_for_creds_ru.htm&language=en_US&type=5)

実装では「新しい資格情報を発行 → DPAPIへ保存 → 新資格情報で認証確認 → 旧資格情報を失効」の
順を守ります。保存や認証確認に失敗した場合は旧資格情報を残し、無人処理が同時に止まることを
避けます。

補助解説:

- [Salesforce External Client App key and secret rotation via REST API](https://lekkimworld.com/2025/09/24/salesforce-external-client-app-key-and-secret-rotation-via-rest-api/)

## 6. 管理者へ依頼する内容

1. 組織ごとにECAを作成する。
2. OAuthスコープは必要最小限にする。
3. Client Credentials Flowを有効化する。
4. API専用の実行ユーザーを指定する。
5. 実行ユーザーへ必要なオブジェクト・項目・レポートだけを許可する。
6. secretの共有方法とローテーション担当を決める。

## 関連文書

- [salesforce.md](../salesforce.md) — Salesforce連携全体の設計と使い方
- [credentials.md](../credentials.md) — comkenでの認証情報保管

---

# Refresh Token 認証のやり方 (how to)

開発環境で **Refresh Token Flow** の認証を通すまでの手順。
本番の無人実行に入る前に 1 度だけ実行する対話的なフロー。

## 0. 前提

- comken がインストールされている (本ドキュメントが同封の v0.10.0 以降)
- Salesforce 側で **External Client App (ECA)** が作成済み
  - 「OAuth 設定」ページで **Authorization Code + Refresh Token Flow を有効化**
  - 「Client Credentials Flow」は **無効化** (既定) — 共存させると secret 単独漏えいの入口が残る
  - 「Refresh Token Rotation」を有効化 (推奨)
  - 「Require Secret for Refresh Token Flow」を **無効化** (comken の既定)
  - Callback URL に `http://localhost:8080/callback` を設定 (後述の `http_server` 方式)
- comken を実行する Windows ユーザーと、ECA を作成した管理者が別の場合は事前に連携

## 1. ECA の client_id / client_secret を DPAPI に登録

まず `client_id` と `client_secret` を comken の資格情報ストアに入れる。

```powershell
python -m comken cred gui
```

- **キー名**: `<prefix>_client_id` (例: `sandbox_client_id`)
- **値**: ECA の「Consumer Key」 (Salesforce 画面でコピー)
- 続けて **`<prefix>_client_secret`** を「Consumer Secret」で登録
- **prefix** は組織クラス (例: `Sandbox`) の `CREDENTIAL_PREFIX` と揃える
  - デフォルトは組織名そのまま (`sandbox` / `production` など)

登録したかは `python -m comken cred list` で確認できる。

## 2. 初回認可 (authorization_url)

ブラウザで ECA に「comken がこの組織にアクセスしていい」と 1 回だけ承認する。

```powershell
python -c "from comken.toolbox.credentials import Credentials; from comken.toolbox.salesforce.oauth_refresh import RefreshTokenOAuth; from comken.toolbox.salesforce.sites import Sandbox; prefix = Sandbox.CREDENTIAL_PREFIX; client_id = Credentials(prefix).client_id; url, _ = RefreshTokenOAuth.authorization_url(client_id, 'http://localhost:8080/callback', Sandbox.DOMAIN_URL); print(url)"
```

- 表示された URL をブラウザで開く
- Salesforce のログイン画面で ECA を許可する組織のユーザーでログイン
- 「Allow」 (許可) をクリック
- ブラウザを `http://localhost:8080/callback?code=...` にリダイレクト
- **その callback URL の `code=` 以降の文字列**をメモ

この `code` は 10 分で失効する。すぐ次の手順で使う。

## 3. code を refresh_token に交換

```powershell
python -c "from comken.toolbox.credentials import Credentials; from comken.toolbox.salesforce.oauth_refresh import RefreshTokenOAuth; from comken.toolbox.salesforce.sites import Sandbox; from comken.toolbox.credentials import save_credential; prefix = Sandbox.CREDENTIAL_PREFIX; creds = Credentials(prefix); auth = RefreshTokenOAuth.exchange_code(creds.client_id, creds.client_secret, input('code: '), 'http://localhost:8080/callback', Sandbox.DOMAIN_URL, on_refresh_token=lambda t: save_credential(f'{prefix}_refresh_token', t)); print('refresh_token を DPAPI に保存しました')"
```

- `code:` プロンプトに 2 でメモした文字列を貼り付け
- 出力は **refresh_token を含む JSON** になる (`access_token`, `refresh_token`, `instance_url`)

## 4. refresh_token を DPAPI に登録

```powershell
python -m comken cred gui
```

- **キー名**: `<prefix>_refresh_token`
- **値**: 3 で取得した `refresh_token` フィールド

## 5. 動作確認

```powershell
python -m comken sf check
```

- 0 エラーなら OK
- 401 が返ったら、`<prefix>_refresh_token` が **古い/期限切れ**の可能性。
  手順 2 からやり直す (Refresh Token Rotation を有効にしていれば、再認可時に **新しい refresh_token** が返るので 4 も更新する)

## 6. 無人実行への移行

ここまでの設定が完了すれば、`Sandbox()` をそのまま使うスクリプトは
**誰もログインしていない状態でも** 動く:

```python
from comken.toolbox.salesforce.sites import Sandbox

with Sandbox() as sf:
    rows = sf.query("SELECT Id, Name FROM Account LIMIT 10")
```

`client_id` / `client_secret` / `refresh_token` のいずれかが **コードに現れない** ことが
この手順のゴール。**Windows DPAPI** に守られた値だけが、組織を操作する。

## 7. 失効時の対応

`refresh_token` を revoke / 失効させたい:

1. ECA 画面で「Revoke」操作
2. もしくは ECA を作り直す
3. **手順 2 からやり直す**

Refresh Token Rotation を有効にしている場合、**`comken` が新しい `refresh_token` を
受け取ったタイミングで DPAPI に自動で書き戻す** (`oauth_refresh.py` 内の `save_credential()`)。
運用としてやることは増えない。

## 8. Client Credentials Flow を使う場合 (開発中だけ)

Refresh Token Flow の **対になる形**で、初回認可が要らない代わりに
`client_secret` 単独で操作できる (本番で使わない理由は
`docs/開発/salesforce-authentication.md` の冒頭を参照):

```python
from comken.toolbox.salesforce import ClientCredentialsAuth
from comken.toolbox.salesforce.sites import Sandbox

with Sandbox(auth=ClientCredentialsAuth(
    client_id=...,
    client_secret=...,
    domain_url="login.salesforce.com",
)) as sf:
    ...
```

**本番では使わない。** 動作確認の回転を速くしたい開発中だけ。

## 9. トラブルシュート

| 症状 | 確認 |
|---|---|
| `INVALID_CLIENT_ID` | `python -m comken cred list` で `<prefix>_client_id` を確認。ECA の Consumer Key と一致するか |
| `INVALID_CLIENT_SECRET` | 同様に `<prefix>_client_secret` を確認 |
| `INVALID_AUTH_CODE` | authorization_url で取得した `code` を 10 分以上放置した。手順 2 からやり直す |
| `UNSUPPORTED_GRANT_TYPE` | ECA のフロー設定で Authorization Code + Refresh Token Flow を有効にしているか |
| `INVALID_REFRESH_TOKEN` | refresh_token を revoke 済み。手順 2 からやり直す |
| 401 が返る (refresh_token は新しい) | ECA で「Manage Refresh Tokens」を開き、過去トークンの状態を確認 |
| 連携アプリが見つからない | ECA のパッケージ / 組織を確認。`Sandbox.DOMAIN_URL` と一致するか |

