"""comken/toolbox/browser/sites/box/pages/app_page.py — Box 共通の SitePage。

``BASE_URL`` はここでは書かない。``SitePage.BASE_URL`` が未設定のときは、
起動したサイトクラス（``Box``）の ``BASE_URL`` へ自動でフォールバックする
（解決順は ``comken/toolbox/browser/page/site.py`` を参照）。同じ値を
``site.py`` とここの2箇所に書くと、書き換え忘れで食い違う事故につながる。
"""

from comken.toolbox.browser import Locator, SitePage


class AppPage(SitePage):
    """Box 共通の基底クラス。

    全画面クラスはこのクラスを継承する。
    サイト固有の共通処理（ログイン済みの判定に使う目印など）をここに置く。
    """

    # ログイン後の画面（右上に出てくるアカウントアイコン）にある目印。
    # 「ログイン済み」の判定に使う（URL がログイン画面でなく、かつこれが
    # 出ていればログイン済みとみなす）。
    # 根拠: https://github.com/bhandigare/UIAutomation の
    # src/main/java/.../pageObjects/HomePage.java に
    # ``@FindBy(css = "span.avatar-initials")`` があり、
    # ``isSuccessfulLogin()`` がこの要素の ``isDisplayed()`` で判定している。
    # 表示文字列（日本語／英語）ではなく要素そのもので判定するため、
    # UI の言語に依存しない。
    APP_SHELL = Locator.css("span.avatar-initials")
