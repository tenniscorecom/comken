"""comken/toolbox/credentials/prompt.py — 新しいパスワードをCLIから受け付けて保存する

ブラウザ自動化でサイト側からパスワード変更を強制されたとき、CLIで新しい
パスワードを2回入力させて一致を確かめ、そのまま DPAPI 認証情報ストアへ保存する
（呼び出し側で save() を別途呼ぶ必要はない）。

    from comken.toolbox.credentials import Credentials, prompt_new_password

    cred = Credentials(config.CREDENTIALS.AMS)
    new_password = prompt_new_password(cred)                 # CLI受付→DPAPI保存までここで完結
    change_password_page.submit_new_password(new_password)   # サイト側へは別途反映

無人実行（RPAのスケジュール実行等）では対話入力できないため、
timeout_seconds を過ぎても入力が確定しなければ TimeoutError で失敗する
（入力待ちのままハングし続けない）。
"""

# 対話的にパスワードを受け付けるモジュールのため、プロンプト表示・マスク文字の
# 表示に print を使う（logging はログファイル向けで、対話プロンプトの
# 相手には届かない）
# ruff: noqa: T201

import logging
import msvcrt
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from comken.toolbox.credentials.store import Credentials

logger = logging.getLogger(__name__)

# Credentials に保存する項目名の既定値。パスワード以外を受け付けたいときだけ
# 呼び出し側で field を指定する。
DEFAULT_PASSWORD_FIELD = "password"
# 入力待ちの上限秒数の既定値。無人実行でハングし続けないための上限で、
# 人が使う分には十分長い値にしてある。
DEFAULT_TIMEOUT_SECONDS = 300.0

_ENTER_CHARS = ("\r", "\n")
_BACKSPACE = "\x08"
_INTERRUPT = "\x03"

_EMPTY_MESSAGE = "空のパスワードは登録できません。もう一度入力してください。"
_MISMATCH_MESSAGE = "入力が一致しませんでした。もう一度入力してください。"


def prompt_new_password(
    cred: "Credentials",
    field: str = DEFAULT_PASSWORD_FIELD,
    *,
    label: str = "新しいパスワード",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """新しいパスワードをCLIから2回入力させ、一致したら cred へ保存して返す。

    入力文字は画面に表示しない。1回目と2回目が食い違う間、または未入力の間は
    確定させず何度でも聞き直す。timeout_seconds 以内に入力が確定しなければ
    TimeoutError にする（無人実行でハングし続けるのを防ぐ）。

    確定した値は ``cred.<field> = 値`` の形で代入し、その場で ``cred.save()``
    まで行う。ログイン時に読む側（``cred.password`` 等）と同じインスタンスを
    渡すことで、site 名を書き直す必要がない（typo で別サイトへ保存される
    事故を防ぐ）。

    Args:
        cred: 保存先。``Credentials(config.CREDENTIALS.<サイト>)`` で作ったもの。
        field: 保存する項目名。既定は ``"password"``。
        label: プロンプトに表示する項目名（表示用で、保存先の項目名とは独立）。
        timeout_seconds: 入力待ちの上限秒数。既定 300 秒（5分）。

    Returns:
        2回とも一致した入力値（保存済み）。

    Raises:
        TimeoutError: timeout_seconds 以内に入力が確定しなかった場合。
    """
    new_value = _prompt_confirmed(label, timeout_seconds)
    setattr(cred, field, new_value)
    cred.save()
    logger.debug("新しい値を Credentials へ保存しました: field=%s", field)
    return new_value


def _prompt_confirmed(label: str, timeout_seconds: float) -> str:
    """1回目と2回目が一致するまで、未入力・不一致のたびに聞き直す。"""
    while True:
        first = _read_masked(f"{label}: ", timeout_seconds)
        if not first:
            print(_EMPTY_MESSAGE)
            continue
        second = _read_masked(f"{label}（確認のため再入力）: ", timeout_seconds)
        if first != second:
            print(_MISMATCH_MESSAGE)
            continue
        return first


def _read_masked(prompt: str, timeout_seconds: float) -> str:
    """マスク付きでコンソール入力を受け付ける。timeout_seconds を過ぎたら TimeoutError。

    ``getpass.getpass()`` はタイムアウトできないため、Windows専用の msvcrt で
    1文字ずつ読みながら経過時間を見る形にしている。RPAのスケジュール実行など
    人がいない環境で誤って走らせても、入力待ちのまま延々ハングし続けない
    （対話利用時の見た目・挙動は getpass と変わらない）。
    """
    print(prompt, end="", flush=True)
    buffer: list[str] = []
    deadline = time.monotonic() + timeout_seconds
    while True:
        if msvcrt.kbhit():
            char = msvcrt.getwch()
            if char in _ENTER_CHARS:
                print()
                return "".join(buffer)
            if char == _BACKSPACE:
                if buffer:
                    buffer.pop()
                    print("\b \b", end="", flush=True)
                continue
            if char == _INTERRUPT:
                raise KeyboardInterrupt
            buffer.append(char)
            print("*", end="", flush=True)
        if time.monotonic() >= deadline:
            print()
            raise TimeoutError(
                f"{timeout_seconds:.0f}秒以内に入力がありませんでした"
                "（無人実行では対話入力を待てません）"
            )
        time.sleep(0.05)
