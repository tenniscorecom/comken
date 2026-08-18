"""
src/browser_options.py — このプロジェクトのブラウザ設定

comken の BrowserOptions のデフォルトから、変えたい項目だけ上書きする。
ブラウザ設定は「環境で変わる非機密の値」ではなく「コードの一部」なので、
config.ini ではなくこのファイル（src/ 内の Python）で持つ。

ブラウザ操作を使わないプロジェクトでは、このファイルは削除してよい。

サイトが複数あるときは、サイトごとに SiteBase サブクラスを src/site.py に作って、
それぞれ OPTIONS をこの BrowserOptions のサブクラスに向ける。
起動オプション・ダウンロード先・ログイン状態はサイトごとに独立するので、
片方の設定がもう片方へ影響しない。

使い方（呼ぶ側）:
    from comken.toolbox.browser import Browsers

    from src.site import ExampleSite

    with Browsers() as browsers:
        site = browsers.launch(ExampleSite)
        site.go_login()                    # 行ける画面は go_〇〇() で書く
"""

from comken.toolbox.browser import BrowserOptions


class ExampleSiteOptions(BrowserOptions):
    """サイトごとに1クラス作り、変えたい項目だけ上書きする。

    設定できる項目とその値は print(ExampleSiteOptions()) で一覧できる。
    """

    # HEADLESS = True                       # 画面を出さずに動かす
    # DOWNLOAD_DIR = r"C:\作業\downloads"    # サイト名のサブフォルダへ自動で分かれる
    #
    # 標準のフォルダへ入れるなら Paths を使う（OneDrive で場所が移されていても
    # 実際の場所に付いていける）。from comken.toolbox.windows import Paths
    # DOWNLOAD_DIR = Paths.downloads()       # ほかに desktop() / temp_dir()
    # WAIT_SECONDS = 20                      # 要素待機のタイムアウト秒

    # 指定するとログイン状態が次回も残る（サイトごとに別フォルダへ自動で分かれる）
    # PROFILE_ROOT = r"C:\作業\browser_profiles"
