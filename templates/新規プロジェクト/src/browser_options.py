"""
src/browser_options.py — このプロジェクトのブラウザ設定

comken の BrowserOptions のデフォルトから、変えたい項目だけ上書きする。
ブラウザ設定は「環境で変わる非機密の値」ではなく「コードの一部」なので、
config.ini ではなくこのファイル（src/ 内の Python）で持つ。

ブラウザ操作を使わないプロジェクトでは、このファイルは削除してよい。

サイトが複数あるときは、サイトごとにクラスを分ける。
起動オプション・ダウンロード先・ログイン状態はサイトごとに独立するので、
片方の設定がもう片方へ影響しない。

使い方（呼ぶ側）:
    from comken.toolbox.browser import Browsers

    from .browser_options import KintaiOptions

    with Browsers() as browsers:
        kintai = browsers.launch("kintai", KintaiOptions)
        kintai.open("https://kintai.example.co.jp")
"""

from comken.toolbox.browser import BrowserOptions


class KintaiOptions(BrowserOptions):
    """サイトごとに1クラス作り、変えたい項目だけ上書きする。

    設定できる項目とその値は print(KintaiOptions()) で一覧できる。
    """

    # HEADLESS = True                       # 画面を出さずに動かす
    # DOWNLOAD_DIR = r"C:\作業\downloads"    # サイト名のサブフォルダへ自動で分かれる
    # WAIT_SECONDS = 20                      # 要素待機のタイムアウト秒

    # Edge の自動更新でドライバーと食い違ったとき、ここから自動でコピーして直す
    # DRIVER_SOURCE_DIR = r"\\共有サーバー\ツール\msedgedriver"

    # 指定するとログイン状態が次回も残る（サイトごとに別フォルダへ自動で分かれる）
    # PROFILE_ROOT = r"C:\作業\browser_profiles"
