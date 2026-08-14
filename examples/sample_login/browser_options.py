from comken.browser.options import BrowserOptions


class SampleBrowserOptions(BrowserOptions):
    """sample_login 用のブラウザオプション。

    デフォルト（BrowserOptions）から変更したいものだけ上書きする。
    全オプションのデフォルト値は comken/browser/options.py を参照。
    """

    DRIVER_PATH = r"C:\Users\Public\Documents\msedgedriver.exe"

    # このサンプルではシークレットモードを使わない
    INCOGNITO = False

    # ウィンドウサイズを固定（--start-maximized と併用不可なので無効化）
    START_MAXIMIZED = False
    WINDOW_SIZE = "1600,1024"
