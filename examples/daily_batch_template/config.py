from pathlib import Path

from comken.config import Config

# 実プロジェクトでは main.py と config.ini が同じフォルダにあるため Config() だけでよい。
# このサンプルはリポジトリのルートから実行するので、config.ini の場所を明示している
config = Config(Path(__file__).parent / "config.ini")
