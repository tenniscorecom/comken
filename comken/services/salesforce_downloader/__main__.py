"""comken/services/salesforce_downloader/__main__.py — CLI の入口。

`python -m comken.services.salesforce_downloader` で `cli.main(argv)` を呼ぶ
薄い入口。テストや埋め込み利用からも `cli.main(argv)` を直接呼べる形を保つ。
"""

import sys

from comken.services.salesforce_downloader.cli import main

if __name__ == "__main__":
    sys.exit(main())
