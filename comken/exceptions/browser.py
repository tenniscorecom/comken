"""ブラウザ操作に関する例外。

BrowserError
├── 起動・終了に関するもの
│   ├── DriverStartError            ドライバーの起動に失敗した
│   ├── SessionNotStartedError      with に入らずに操作した
│   └── SessionClosedError          with を抜けた後に操作した
├── 並列実行に関するもの
│   └── ConcurrentSessionUseError   1つのセッションを複数スレッドから同時に操作した
├── 複数サイト管理に関するもの
│   ├── SessionNameConflictError    同じ名前で2回起動した
│   └── SessionNotFoundError        起動していない名前を取り出そうとした
└── 画面操作に関するもの
    ├── ElementNotFoundError        要素が時間内に見つからなかった
    ├── PopupTabNotOpenedError      新しいタブが時間内に開かなかった
    └── DownloadTimeoutError        ダウンロードが時間内に完了しなかった

例外メッセージには「何が起きたか」だけでなく「次に何を確認すればよいか」まで書く。
ブラウザ操作の失敗は画面側の変更が原因であることが多く、
ログだけを見る人が原因にたどり着けるようにするため。
"""

from .base import ComkenError


class BrowserError(ComkenError):
    """ブラウザ操作の例外をまとめて捕捉するための基底クラス。直接送出しない。"""


# ------------------------------------------------------------ 起動・終了


class DriverStartError(BrowserError):
    """Edge WebDriver の起動に失敗した場合。

    発生箇所: Browsers.launch()
    """

    def __init__(self, driver_path: str, detail: Exception) -> None:
        super().__init__(
            f"Edge WebDriver を起動できませんでした: {driver_path}\n"
            f"（{detail}）\n"
            "次を確認してください:\n"
            "  1. そのパスに msedgedriver.exe があるか\n"
            "  2. msedgedriver.exe のバージョンが、今インストールされている Edge と一致しているか\n"
            "     （Edge のバージョンは edge://version で確認できます）"
        )


class SessionNotStartedError(BrowserError):
    """with に入る前のセッションを操作した場合。

    BrowserSession は with 文の中でだけ使える。with を使わないと、
    処理の途中で例外が出たときにブラウザのプロセスが残り続けるため。

        # 誤り
        session = BrowserSession(...)
        session.open("https://example.com")     # ← ここで送出される

        # 正しい
        with Browsers() as browsers:
            session = browsers.launch("kintai")
            session.open("https://example.com")
    """

    def __init__(self, operation: str) -> None:
        super().__init__(
            f"with に入る前のセッションを操作しました: {operation}\n"
            "BrowserSession は with 文の中でだけ使えます。\n"
            "  with Browsers() as browsers:\n"
            '      session = browsers.launch("サイト名")\n'
            "      session.open(...)\n"
            "サイトを増やすときは launch を1行足してください。"
        )


class SessionClosedError(BrowserError):
    """with を抜けて閉じ終わったセッションを操作した場合。

    with の外へセッションを持ち出すと起きる。取得したデータを with の外で使いたい場合は、
    セッションではなく取り出した値（文字列やファイルパス）を返すようにする。
    """

    def __init__(self, name: str, operation: str) -> None:
        super().__init__(
            f"閉じ終わったセッション「{name}」を操作しました: {operation}\n"
            "with を抜けた後のセッションは使えません。\n"
            "with の外へ持ち出すのはセッションではなく、取り出した値にしてください。"
        )


# ------------------------------------------------------------ 並列実行


class ConcurrentSessionUseError(BrowserError):
    """1つのセッションを複数スレッドから同時に操作した場合。

    WebDriver は1つの接続でコマンドを順番に処理するため、
    同じセッションを2スレッドから同時に操作すると応答が入れ替わり、
    「別の画面を操作していた」という追跡困難な不具合になる。
    サイトごとにセッションを分けること（Browsers.launch で1サイト1セッション）。
    """

    def __init__(self, name: str, operation: str, holder_thread: str) -> None:
        super().__init__(
            f"セッション「{name}」を複数スレッドから同時に操作しました: {operation}\n"
            f"（先に操作中のスレッド: {holder_thread}）\n"
            "1つのセッションを同時に操作できるのは1スレッドだけです。\n"
            "並列にしたい場合は Browsers.launch でサイトごとにセッションを分け、\n"
            "Browsers.parallel で実行してください。"
        )


# ------------------------------------------------------------ 複数サイト管理


class SessionNameConflictError(BrowserError):
    """同じ名前のセッションを2回起動しようとした場合。

    発生箇所: Browsers.launch()
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"セッション名が重複しています: {name}\n"
            "1つの Browsers の中で同じ名前は使えません。\n"
            "同じサイトに2つのアカウントでログインする場合は、"
            '「kintai_a」「kintai_b」のように名前を分けてください。'
        )


class SessionNotFoundError(BrowserError):
    """起動していないセッションを取り出そうとした場合。

    発生箇所: Browsers.__getitem__()
    """

    def __init__(self, name: str, launched: list[str]) -> None:
        launched_text = "、".join(launched) if launched else "（まだ1つも起動していません）"
        super().__init__(
            f"起動していないセッションです: {name}\n"
            f"起動済み: {launched_text}\n"
            "Browsers.launch(name) で起動してから使ってください。"
        )


# ------------------------------------------------------------ 画面操作


class ElementNotFoundError(BrowserError):
    """要素が待機時間内に見つからなかった場合。

    selenium の TimeoutException を、どのセレクターで失敗したかが分かる形に包み直したもの。
    素の TimeoutException はメッセージにセレクターが入らず、ログから原因を追えないため。
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


class PopupTabNotOpenedError(BrowserError):
    """popup_tab() で新しいタブが待機時間内に開かなかった場合。

    発生箇所: BrowserSession.popup_tab()
    """

    def __init__(self, seconds: int) -> None:
        super().__init__(
            f"新しいタブが {seconds} 秒以内に開きませんでした。\n"
            "次を確認してください:\n"
            "  1. popup_tab() に入る前に、タブを開く操作（リンクのクリック等）を済ませているか\n"
            "  2. ポップアップがブラウザにブロックされていないか"
            "（BrowserOptions.DISABLE_POPUP_BLOCKING を True にする）\n"
            "  3. 実際は同じタブで開いていないか（その場合 popup_tab は不要）"
        )


class DownloadTimeoutError(BrowserError):
    """ダウンロードが待機時間内に完了しなかった場合。

    発生箇所: DownloadDir.wait()
    """

    def __init__(self, directory: object, seconds: int) -> None:
        super().__init__(
            f"ダウンロードが {seconds} 秒以内に完了しませんでした: {directory}\n"
            "次を確認してください:\n"
            "  1. ダウンロード操作が実際に始まっているか（画面にエラーが出ていないか）\n"
            "  2. ファイルが大きく時間がかかるだけではないか（wait(timeout=...) を長くする）\n"
            "  3. ブラウザの保存先がこのフォルダになっているか"
            "（セッションごとに download_dir を分けている場合は取り違えに注意）"
        )
