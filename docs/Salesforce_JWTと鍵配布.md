# JWT ベアラーフローと認証情報の鍵配布（準備）

作成日: 2026-08-12
背景: `cryptography` をオフライン環境へ持ち込める見込みが立ったため、
[Salesforce 連携 設計メモ](Salesforce設計メモ.md) で「後回し」にした2つを先に用意する。

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

[設計メモ](Salesforce設計メモ.md)のとおり、認証は `SalesforceBase` が**持つ**部品にする。
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
