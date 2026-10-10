"""Q1~Q4 프리셋 (초안). 값 확정은 W6 데이터 담당 일정. 파일 하나 = 프리셋 하나."""
from __future__ import annotations

import json
from pathlib import Path

DIR = Path(__file__).resolve().parent


def load_all() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(DIR.glob("*.json"))]
