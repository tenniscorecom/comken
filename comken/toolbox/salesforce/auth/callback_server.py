"""comken/toolbox/salesforce/auth/callback_server.py — OAuthリダイレクトの自動受け取り

Salesforceの認可コード（``code=...``）は、利用者がブラウザで承認したあと
ブラウザが ``redirect_uri`` へリダイレクトすることで渡される。``redirect_uri``
が localhost の場合だけ、そのポートで待ち受けて ``code`` / ``state`` を
自動で取り出せる（URLからの手動コピペを無くす。長い認可コードは ``=``
を含むことが多く、途中で切れて貼り付けるミスが起きやすいため）。
favicon.ico の取得など無関係なリクエストは無視して待ち続け、本物の
リダイレクト（パス一致・expected_state 一致）を受け取るか、
合計の timeout_seconds を使い切ったら止まる。

localhost 以外（社内で公開した callback URL 等）はこのマシンでは受け取れない
ため、``is_localhost_callback()`` で判定し、呼び出し側で手動のcode入力に
切り替える。
"""

import http.server
import logging
import time
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
    redirect_uri: str,
    expected_state: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> CallbackResult:
    """redirect_uri のポートで待ち受け、リダイレクトの code / state を受け取って返す。

    ブラウザは favicon.ico の取得など、callback とは無関係な GET をこのポートへ
    送ってくることがある。無関係なパス・expected_state と一致しない code は
    そのリクエストだけを無視して**待ち受けを継続する**（1件目で即座に確定させると、
    無関係なリクエストに横取りされて本来のリダイレクトを取りこぼす）。
    timeout_seconds の合計時間を使い切っても届かなければ諦める。

    Args:
        redirect_uri: ECA に登録した callback URL（``is_localhost_callback()``
            が True であること）。
        expected_state: ``authorization_url()`` が返した state。これと一致する
            リクエストだけを本物の応答として扱う（CSRF対策・横取り対策）。
        timeout_seconds: リダイレクトを待つ合計の上限秒数。

    Returns:
        受け取った code / state（state は expected_state と一致済み）。

    Raises:
        OSError: ポートを既に他プロセスが使っている等、待ち受けを開始できない場合。
        TimeoutError: timeout_seconds 以内にリダイレクトが来なかった場合。
        SalesforceAuthError: 利用者が承認を拒否した等、Salesforce 側がエラーを返した場合。
    """
    split = urllib.parse.urlsplit(redirect_uri)
    path = split.path or "/"
    address = (split.hostname or "localhost", split.port or 80)
    server = _CallbackServer(address, path, expected_state)
    deadline = time.monotonic() + timeout_seconds
    try:
        logger.debug("OAuthリダイレクトの待ち受けを開始します: path=%s", path)
        while server.oauth_outcome is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            server.timeout = remaining
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
    """認可コードを受け取るためだけの、使い捨てのローカルサーバー。"""

    def __init__(self, address: tuple[str, int], path: str, expected_state: str) -> None:
        super().__init__(address, _CallbackHandler)
        self.oauth_path = path
        self.oauth_expected_state = expected_state
        # (結果, エラーメッセージ) のタプル。 まだ確定していない間は None のまま
        # （タイムアウトしたかどうかを None かどうかで区別する）。
        self.oauth_outcome: tuple[dict[str, str], str | None] | None = None


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """OAuthリダイレクトを受け取り、確定したら結果を server 側へ書き込む。

    パスが違う・state が expected_state と一致しない（favicon.ico の取得や、
    無関係な別プロセスからのリクエスト等）場合は 404 だけ返し、
    server.oauth_outcome は書き込まない（wait_for_callback() 側が待ち受けを続ける）。
    """

    def do_GET(self) -> None:
        """GETリクエストを1件処理する。本物の応答だと確定できたときだけ結果を書き込む。"""
        # http.server の基底クラスでは self.server は BaseServer 型だが、
        # 実際に渡ってくるのは wait_for_callback() が組み立てた _CallbackServer。
        server = cast("_CallbackServer", self.server)
        request_path, _, query = self.path.partition("?")
        result, error = _parse_query(query)
        is_own_path = request_path == server.oauth_path
        # エラー応答（Salesforceが承認を拒否した等）はSalesforce側にstateを
        # 付け返す保証が無いため、path一致だけで確定させる。成功応答（code有り）は
        # 横取り・混線を防ぐためstateの一致も必須にする。
        state_matches = result.get("state") == server.oauth_expected_state
        is_match = is_own_path and (error is not None or state_matches)
        if not is_match:
            self.send_response(404)
            self.end_headers()
            return
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
