"""M1 수요 (R3의 일부). 담당: 데이터·모델 — 지금은 백엔드가 만든 v0 자리표시.

세그먼트(AI 서버·일반 서버·PC·모바일) 충격을 제품별 수요 배수로 바꾼다.
  HBM 배정 D^C   = 기준 배정 × (1+성장)^(t−1) × AI 서버 배수
  DDR5 수요 배수  = AI 비중 × AI 배수 + PC 비중 × PC 배수 + 나머지 × 일반 서버 배수
  LPDDR 수요 배수 = 모바일 배수
수요 배수는 M3(market.py)에서 역수요 절편 a를 옮기는 데 쓴다.
"""
from __future__ import annotations

import numpy as np

from memsim.core.scenario import Scenario, combined_multiplier


def build(sc: Scenario, v: dict[str, float], T: int) -> dict[str, np.ndarray]:
    t = np.arange(T)
    seg = {s: combined_multiplier(sc.shocks, T, type="demand", segment=s)
           for s in ("ai_server", "general_server", "pc", "mobile")}
    ai, pc = v["ai_share_of_ddr5"], v["pc_share_of_ddr5"]
    if ai + pc > 1:
        raise ValueError("ai_share_of_ddr5 + pc_share_of_ddr5 > 1")
    ddr5 = ai * seg["ai_server"] + pc * seg["pc"] + (1 - ai - pc) * seg["general_server"]
    growth = (1 + v["market_demand_growth"]) ** t
    return {
        "dc_hbm": v["hbm_demand_bits"] * (1 + v["hbm_demand_growth"]) ** t * seg["ai_server"],
        "qbar_mult": np.vstack([ddr5 * growth, seg["mobile"] * growth]),  # (M, T)
    }
