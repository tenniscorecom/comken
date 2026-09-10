"""comken/toolbox/salesforce/auth/oauth_redirect.py — OAuthリダイレクトURLの解析

承認後にリダイレクトされたURLから、認可コード（``code``）とCSRF検証用の
``state`` を取り出す。ブラウザのアドレスバーからURL全体をそのままコピペ
させる前提（``code=`` の後ろだけを切り出させると、認可コードに含まれる
ことが多い ``=`` 等の記号で貼り間違いが起きやすいため）。
"""

import urllib.parse
from dataclasses import dataclass

from comken.exceptions import SalesforceAuthError


@dataclass(frozen=True)
class CallbackResult:
    """リダイレクトURLから取り出した認可コードと state。"""

    code: str
    state: str


def parse_redirect_url(url: str) -> CallbackResult:
    """リダイレクトされた URL 全体から code / state を取り出す。

    Raises:
        SalesforceAuthError: URL に code が含まれない（承認を拒否した・
            違う URL を貼り付けた等）場合。
    """
    result, error = _parse_query(urllib.parse.urlsplit(url).query)
    if error is not None:
        raise SalesforceAuthError(200, f"URL に認可コードが含まれていません: {error}")
    return CallbackResult(code=result["code"], state=result.get("state", ""))


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


__all__ = ["CallbackResult", "parse_redirect_url"]
