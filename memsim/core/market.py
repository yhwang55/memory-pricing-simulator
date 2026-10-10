"""M3 시장 (R3의 일부). 담당: 데이터·모델 — 지금은 백엔드가 만든 v0 자리표시.

잔여 수요 모형 (설계 v3: "Cournot"가 아니라 잔여 수요 모형).
  역수요   P_p,t = a_p,t − b_p (S^comp_p,t + s_p,t)
  보정     b = P̄ / (ε Q̄),  a = P̄ + b Q̄          (기준 분기에서 가격 = P̄, 탄력성 = ε)
  수요 충격 a_p,t = P̄ + b Q̄ · 수요배수_p,t      (수요 곡선이 수평으로 이동)
  경쟁사   S^comp_p,t = S0 (1+성장)^(t−1) × 경쟁 충격 배수 (MVP는 외생 경로)
"""
from __future__ import annotations

import numpy as np

from memsim.core.scenario import Scenario, combined_multiplier
from memsim.core.types import MARKET_IDX, MARKET_PRODUCTS


def build(sc: Scenario, v: dict[str, float], T: int, own_base_bits: np.ndarray,
          qbar_mult: np.ndarray) -> dict[str, np.ndarray]:
    t = np.arange(T)
    keys = {"DDR5": "ddr5", "LPDDR": "lpddr"}
    a = np.zeros((len(MARKET_PRODUCTS), T))
    b = np.zeros(len(MARKET_PRODUCTS))
    s_comp = np.zeros_like(a)
    for j, (prod, p) in enumerate(zip(MARKET_PRODUCTS, MARKET_IDX)):
        k = keys[prod]
        pbar, eps, s0 = v[f"price_base_{k}"], v[f"elasticity_{k}"], v[f"comp_supply_{k}"]
        qbar = own_base_bits[p] + s0
        if qbar <= 0:
            raise ValueError(f"{prod} 기준 시장 수요가 0입니다")
        b[j] = pbar / (eps * qbar)
        a[j] = pbar + b[j] * qbar * qbar_mult[j]
        s_comp[j] = s0 * (1 + v["comp_supply_growth"]) ** t * combined_multiplier(
            sc.shocks, T, type="competitor_capacity", product=prod)
    return {"a": a, "b": b, "s_comp": s_comp}


def prices(a: np.ndarray, b: np.ndarray, s_comp: np.ndarray, s_own_mkt: np.ndarray) -> np.ndarray:
    """시장 제품 가격 (M, T). 음수가 될 수 있다 (공급 과잉 표시)."""
    return a - b[:, None] * (s_comp + s_own_mkt)
