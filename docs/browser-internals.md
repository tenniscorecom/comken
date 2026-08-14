# ブラウザ内部設計

利用方法は [browser.md](browser.md) を参照する。本書は、保守するときに
「どのファイルから読み、どこを変更するか」を判断するための地図である。

## 公開API

利用プロジェクトは内部ファイルを直接importせず、次の入口だけを使う。

```python
from comken.toolbox.browser import BrowserOptions, Browsers, Locator, Page
```

`Browsers`、`BrowserSession`などの公開名は互換性のため維持する。内部ファイルは役割が
伝わる短い名詞にし、英語圏の比喩を知らないと意味が取れない名前や、ディレクトリ名と
意味が重複する複合ファイル名は使わない。

## ディレクトリ構成

```text
browser/
├── __init__.py                 公開APIの入口
├── management/                ブラウザーと非同期処理の管理
│   ├── browsers.py            複数ブラウザーをまとめて起動・終了する
│   ├── sessions.py           1サイト分のWebDriverと排他制御
│   ├── startup.py            Edgeの起動・初期化・ドライバー更新
│   ├── tasks.py              裏で動かした処理の結果・例外を受け取る
│   └── tabs.py               1セッション内のタブを開閉する
├── page.py                    Page Objectの共通操作
├── locator.py                 画面要素の指定方法
├── options.py                 Edgeの起動設定
├── download.py                ダウンロード先と完了待ち
└── driver.py                  EdgeDriverの取得・更新
```

## 処理の流れ

```text
利用プロジェクト
  └─ Browsers.launch(name)
       └─ BrowserSessionを作成
            ├─ BrowserOptionsからEdgeを起動
            ├─ DownloadDirをセッションごとに分離
            ├─ PageがBrowserSessionを使って画面を操作
            └─ TabManagerが必要な間だけ別タブを管理

Browsers.start / parallel
  └─ BackgroundTaskが結果・例外を保持
       └─ Browsers終了前に未完了処理を待ってからEdgeを閉じる
```

## 変更先の判断

| 変更したいこと | 主に読むファイル |
|---|---|
| ブラウザーを追加・終了する流れ | `management/browsers.py` |
| Edgeの起動・終了、同時操作の防止 | `management/sessions.py` |
| Edge起動失敗、起動引数、ドライバー更新 | `management/startup.py`、`driver.py` |
| 複数サイトの並列処理 | `management/browsers.py`、`management/tasks.py` |
| ポップアップ、複数タブ読み込み | `management/tabs.py` |
| クリック、入力、待機 | `page.py` |
| Edgeの起動引数 | `options.py` |
| ダウンロード完了の判定 | `download.py` |

`BrowserSession`へ新しい責務を直接足す前に、上表の既存担当へ置けないか確認する。
公開APIを変える場合は、ブラウザー操作文書・サンプル・自動生成APIも同時に更新する。
