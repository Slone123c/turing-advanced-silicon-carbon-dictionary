"""测试共用：把仓库根加入 sys.path，供 `python3 -m unittest discover -s tests` 导入 scan / install / adapters。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
