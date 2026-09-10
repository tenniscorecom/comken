"""comken/toolbox/salesforce/auth/callback_server.py — OAuthリダイレクトの自動受け取り

Salesforceの認可コード（``code=...``）は、利用者がブラウザで承認したあと
ブラウザが ``redirect_uri`` へリダイレクトすることで渡される。``redirect_uri``
が localhost の場合だけ、そのポートで1回だけ待ち受けて ``code`` / ``state``
を自動で取り出せる（URLからの手動コピペを無くす。長い認可コードは ``=``
を含むことが多く、途中で切れて貼り付けるミスが起きやすいため）。

localhost 以外（社内で公開した callback URL 等）はこのマシンでは受け取れない
ため、``is_localhost_callback()`` で判定し、呼び出し側で手動のcode入力に
切り替える。
"""

import http.server
import logging
import urllib.parse
from dataclasses import dataclass
from typing import cast

from comken.exceptions import SalesforceAuthError

logger = logging.getLogger(__name__)

# リダイレクトを待つ上限秒数の既定値。ブラウザでの承認操作は人が行うため、
# 待たせすぎない範囲で余裕を持たせている。
DEFAULT_TIMEOUT_SECONDS = 300.0
_LOCALHOST_NAMES = ("localhost", "127.0.0.1")


@dataclass(frozen=True)
class CallbackResult:
    """リダイレクトから受け取った認可コードと state。"""

    code: str
    state: str


def is_localhost_callback(redirect_uri: str) -> bool:
    """redirect_uri が、このマシン上で待ち受け可能な localhost URL かどうか。"""
    return urllib.parse.urlsplit(redirect_uri).hostname in _LOCALHOST_NAMES


def parse_redirect_url(url: str) -> CallbackResult:
    """リダイレクトされた URL 全体から code / state を取り出す（手動貼り付け用）。

    ``code=`` の後ろだけを切り出させると、認可コードに含まれることが多い
    ``=`` 等の記号で貼り間違いが起きやすい。ブラウザのアドレスバーから
    URL 全体をそのままコピペさせ、ここで安全に解析する。

    Raises:
        SalesforceAuthError: URL に code が含まれない（承認を拒否した・
            違う URL を貼り付けた等）場合。
    """
    result, error = _parse_query(urllib.parse.urlsplit(url).query)
    if error is not None:
        raise SalesforceAuthError(200, f"URL に認可コードが含まれていません: {error}")
    return CallbackResult(code=result["code"], state=result.get("state", ""))


def wait_for_callback(
    redirect_uri: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
) -> CallbackResult:
    """redirect_uri のポートで1回だけ待ち受け、リダイレクトの code / state を受け取って返す。

    1件受け取ったら（またはタイムアウトしたら）即座に止まる。listenし続けない。

    Args:
        redirect_uri: ECA に登録した callback URL（``is_localhost_callback()``
            が True であること）。
        timeout_seconds: リダイレクトを待つ上限秒数。

    Returns:
        受け取った code / state。

    Raises:
        OSError: ポートを既に他プロセスが使っている等、待ち受けを開始できない場合。
        TimeoutError: timeout_seconds 以内にリダイレクトが来なかった場合。
        SalesforceAuthError: 利用者が承認を拒否した等、Salesforce 側がエラーを返した場合。
    """
    split = urllib.parse.urlsplit(redirect_uri)
    path = split.path or "/"
    server = _CallbackServer((split.hostname or "localhost", split.port or 80), path)
    try:
        logger.debug("OAuthリダイレクトの待ち受けを開始します: path=%s", path)
        server.timeout = timeout_seconds
        server.handle_request()
    finally:
        server.server_close()

    outcome = server.oauth_outcome
    if outcome is None:
        logger.debug("OAuthリダイレクトがタイムアウトしました: timeout_seconds=%s", timeout_seconds)
        raise TimeoutError(
            f"{timeout_seconds:.0f}秒以内にリダイレクトを受け取れませんでした"
            "（ブラウザでの承認が完了していない可能性があります）"
        )
    result, error = outcome
    if error is not None:
        logger.debug("OAuth認可がエラーになりました: error=%s", error)
        raise SalesforceAuthError(200, f"認可が拒否またはエラーになりました: {error}")
    logger.debug("OAuthリダイレクトを受け取りました")
    return CallbackResult(code=result["code"], state=result.get("state", ""))


class _CallbackServer(http.server.HTTPServer):
    """認可コードを1件受け取るためだけの、使い捨てのローカルサーバー。"""

    def __init__(self, address: tuple[str, int], path: str) -> None:
        super().__init__(address, _CallbackHandler)
        self.oauth_path = path
        # (結果, エラーメッセージ) のタプル。 リクエストを受けるまで None のまま
        # （タイムアウトしたかどうかを None かどうかで区別する）。
        self.oauth_outcome: tuple[dict[str, str], str | None] | None = None


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """OAuthリダイレクトの1件だけを受け取り、結果を server 側へ書き込む。"""

    def do_GET(self) -> None:
        """GETリクエストを1件処理し、code/state（またはエラー）を server 側へ書き込む。"""
        # http.server の基底クラスでは self.server は BaseServer 型だが、
        # 実際に渡ってくるのは wait_for_callback() が組み立てた _CallbackServer。
        server = cast("_CallbackServer", self.server)
        request_path, _, query = self.path.partition("?")
        if request_path != server.oauth_path:
            self.send_response(404)
            self.end_headers()
            return
        result, error = _parse_query(query)
        server.oauth_outcome = (result, error)
        body = (
            f"認可に失敗しました: {error}"
            if error
            else "認可を受け取りました。このタブは閉じて構いません。"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format: str, *args: object) -> None:
        """アクセスログの出力先を標準エラーから comken の logger（debug）へ差し替える。"""
        logger.debug(format, *args)


def _parse_query(query: str) -> tuple[dict[str, str], str | None]:
    """クエリ文字列を解析する。

    Returns:
        (結果, エラーメッセージ) のタプル。``code`` があれば結果に
        ``code`` / ``state`` を入れてエラーは ``None``。無ければエラー
        メッセージ（Salesforce が返した error_description 等）を返す。
    """
    params = urllib.parse.parse_qs(query)
    if "code" in params:
        return {"code": params["code"][0], "state": params.get("state", [""])[0]}, None
    error = params.get("error_description", params.get("error", ["不明なエラー"]))[0]
    return {}, error


__all__ = ["CallbackResult", "is_localhost_callback", "parse_redirect_url", "wait_for_callback"]
