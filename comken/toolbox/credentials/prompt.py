"""comken/toolbox/credentials/prompt.py — 新しいパスワードをCLIから受け付ける

ブラウザ自動化でサイト側からパスワード変更を強制されたとき、CLIで新しい
パスワードを2回入力させて一致を確かめる。ここで得た値は呼び出し側が
サイトへ送信し、save_credential() でDPAPI認証情報ストアへも反映する
（サイト側とDPAPI側のパスワードがずれないよう、同じ値を両方に使う）。

    from comken.toolbox.credentials import prompt_new_password, save_credential

    new_password = prompt_new_password()
    change_password_page.submit_new_password(new_password)   # サイト側へ反映
    save_credential("ams", "password", new_password)          # DPAPI側へ反映
"""

# 対話的にパスワードを受け付けるモジュールのため、再入力を促すメッセージの
# 表示に print を使う（logging はログファイル向けで、対話プロンプトの
# 相手には届かない）
# ruff: noqa: T201

import getpass
import logging

logger = logging.getLogger(__name__)

_EMPTY_MESSAGE = "空のパスワードは登録できません。もう一度入力してください。"
_MISMATCH_MESSAGE = "入力が一致しませんでした。もう一度入力してください。"


def prompt_new_password(label: str = "新しいパスワード") -> str:
    """新しいパスワードをCLIから2回入力させ、一致するまで再入力を求める。

    入力文字は画面に表示しない（getpass）。1回目と2回目が食い違う間、
    または未入力のままの間は確定させず、何度でも聞き直す。タイプミスした
    まま確定して、サイト側とDPAPI側の値がずれる事故を防ぐため。

    Args:
        label: プロンプトに表示する項目名。複数サイトを扱うスクリプトで
               「どの値を聞かれているか」を区別したいときに使う。

    Returns:
        2回とも一致した入力値。
    """
    while True:
        first = getpass.getpass(f"{label}: ")
        if not first:
            print(_EMPTY_MESSAGE)
            continue
        second = getpass.getpass(f"{label}（確認のため再入力）: ")
        if first != second:
            print(_MISMATCH_MESSAGE)
            continue
        logger.debug("パスワード入力を受け付けました: label=%s length=%d", label, len(first))
        return first
