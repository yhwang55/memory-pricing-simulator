"""M2 공급 (R3의 일부). 담당: 백엔드.

웨이퍼 캐파 W, 웨이퍼당 bit g, 변동비 c, 전환 한도 R, HBM 후공정 캐파 K, 기준 분기 배분 x0.
제품 순서는 types.PRODUCTS = (HBM, DDR5, LPDDR).
"""
from __future__ import annotations

import numpy as np

from memsim.core.scenario import Scenario, combined_multiplier
from memsim.core.types import P


def build(sc: Scenario, v: dict[str, float], T: int, active: np.ndarray) -> dict[str, np.ndarray]:
    t = np.arange(T)
    W0 = v["wafer_capacity"]
    W = W0 * combined_multiplier(sc.shocks, T, type="wafer_capacity")
    g_col = np.array([v["hbm_g_ratio"], 1.0, v["lpddr_g_ratio"]])
    g = np.repeat(g_col[:, None], T, axis=1)
    c = np.repeat(np.array([v["cost_wafer_hbm"], v["cost_wafer_ddr5"], v["cost_wafer_lpddr"]])[:, None], T, axis=1)

    share = np.array([v["init_share_hbm"], v["init_share_ddr5"], 1 - v["init_share_hbm"] - v["init_share_ddr5"]])
    if share[2] < -1e-9:
        raise ValueError("init_share_hbm + init_share_ddr5 > 1")
    # 시나리오에서 뺀 제품의 웨이퍼는 다른 제품에 다시 나누지 않는다 (남는 캐파는 전환 속도에 따라 옮겨감).
    share = np.where(active, np.maximum(share, 0), 0.0)
    if share.sum() <= 0:  # 활성 제품의 기준 비중이 모두 0이면 균등 배분
        share = active / active.sum()
    x0 = share * W0

    k = v["hbm_backend_bits"] * (1 + v["hbm_backend_growth"]) ** t
    k = k * combined_multiplier(sc.shocks, T, type="hbm_backend_capacity")
    return {
        "W": W, "g": g, "c": c, "x0": x0, "share0": share,
        "R": np.full(P, v["ramp_wafers"]), "k_hbm": k,
        "h": np.full(P, v["holding_cost"]),
        "own_base_bits": x0 * g_col,  # (P,) 기준 분기 자사 bit
    }
