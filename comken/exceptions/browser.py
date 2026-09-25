"""comken/exceptions/browser.py — ブラウザ操作に関する例外。

BrowserError は、画面側でしか起きない失敗をまとめて分類するための
カテゴリ基底。直接送出しない。
"""

from comken.exceptions.base import ComkenError


class BrowserError(ComkenError):
    """ブラウザ操作に関するエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


# 利用者プロジェクトのサイト・ページが送出する前提のエラー。
# 呼び出し側が型で分岐するので、カテゴリにはまとめない
class ElementNotFoundError(BrowserError):
    """画面の部品が時間内に見つからない

    selenium の TimeoutException を、どのセレクターで失敗したかが分かる形に包み直したもの。
    素の TimeoutException はメッセージにセレクターが入らず、ログから原因を追えないため。

    対処:
        もう一度実行する。サイトが重いだけのことが多い。毎回出るなら画面が変わった可能性があるので管理者へ（エラーに、どの部品を探していたかが出ます）
    """

    def __init__(self, locator: object, seconds: int, condition: str) -> None:
        super().__init__(
            f"要素が {seconds} 秒以内に{condition}ませんでした: {locator}\n"
            "次を確認してください:\n"
            "  1. 画面の HTML が変わってセレクターが古くなっていないか\n"
            "  2. 前の画面から遷移しきる前に操作していないか\n"
            "  3. iframe の中の要素ではないか（その場合は frame() で切り替えが必要）\n"
            "待つだけで解決する場合は wait_seconds を長くしてください。"
        )


class LoginFailedError(BrowserError):
    """ログインに失敗した（ユーザー名・パスワードが違う等）

    サイト固有の画面クラス（例: ``LoginPage.login()``）が、送信後もログイン
    画面のエラー表示を検知した場合に送出する。パスワード期限切れによる
    強制的な変更画面への遷移とは別の、単純な「認証情報が間違っている」
    失敗を表す。

    発生箇所: 利用プロジェクト側のログイン画面クラス（サイト固有の実装）

    対処:
        表示されたエラー内容（サイト側のエラーメッセージ）を確認する。
        DPAPI に保存した認証情報が古くなっていないか
        `python -m comken cred list` で確認し、必要なら
        `python -m comken cred gui` で登録し直す
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"ログインに失敗しました: {reason}")
