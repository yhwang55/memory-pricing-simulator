"""R6 후처리: 원시 해 → 결과 JSON (설계 v3 8장 "결과 출력").

지수 기준 (모두 기준 분기 = q1 기준):
  price_idx   bit당 가격 ÷ 기준 DDR5 가격 × 100
  bits/sales/inventory_idx   bit ÷ 기준 분기 자사 판매 bit 합 × 100
  profit_idx  분기 이익 ÷ (기준 DDR5 가격 × 기준 자사 bit 합) × 100   — 할인 전
  wafer shadow price   웨이퍼 1장을 더 얻었을 때 그 분기 이익 지수 증가분 (할인 전)
"""
from __future__ import annotations

from collections import Counter

import numpy as np

from memsim.core import market
from memsim.core.params import Resolved
from memsim.core.scenario import Scenario, quarter_labels
from memsim.core.types import HBM, MARKET_IDX, PRODUCTS, Solution

TOL = 1e-4  # 병목 판정 허용오차 (bit·웨이퍼 단위가 100 안팎)


def _r(x: float, n: int = 4) -> float:
    return float(round(float(x), n))


def build(sc: Scenario, res: Resolved, sol: Solution) -> dict:
    mi = res.mi
    T = mi.T
    labels = quarter_labels(sc.base_quarter, T)
    out: dict = {"rows": [], "shadow_prices": {"wafer": []}, "binding": [], "summary": {}, "warnings": list(res.warnings)}
    if not sol.status.startswith("optimal"):
        return out

    x, s, I = sol.x, sol.s, sol.I
    price = np.zeros((len(PRODUCTS), T))
    price[HBM] = mi.pc_hbm
    price[list(MARKET_IDX)] = market.prices(mi.a, mi.b, mi.s_comp, s[list(MARKET_IDX)])
    revenue = price * s
    profit = revenue - mi.c * x - mi.h[:, None] * I
    money_base = mi.price_base * mi.qty_base
    disc = mi.delta ** np.arange(T)
    W_safe = np.where(mi.W > 0, mi.W, 1.0)

    for t in range(T):
        for p, name in enumerate(PRODUCTS):
            if not mi.active[p]:
                continue
            out["rows"].append({
                "q": t + 1, "quarter": labels[t], "product": name,
                "wafer_share": _r(x[p, t] / W_safe[t]),
                "wafers": _r(x[p, t]),
                "bits_idx": _r(mi.g[p, t] * x[p, t] / mi.qty_base * 100),
                "sales_idx": _r(s[p, t] / mi.qty_base * 100),
                "inventory_idx": _r(I[p, t] / mi.qty_base * 100),
                "price_idx": _r(price[p, t] / mi.price_base * 100),
                "profit_idx": _r(profit[p, t] / money_base * 100),
            })

    lam = sol.wafer_dual / disc / money_base * 100
    out["shadow_prices"]["wafer"] = [{"q": t + 1, "value": _r(lam[t])} for t in range(T)]
    out["binding"] = _binding(mi, x, s, price)

    total_profit = profit[mi.active].sum(axis=0)
    shares = x / W_safe
    hits = Counter()
    for b in out["binding"]:
        hits[b["constraint"]] += len(b["quarters"])
    out["summary"] = {
        "cum_profit_idx": _r(total_profit.sum()),
        "npv_profit_idx": _r(sol.objective / money_base * 100),
        "profit_by_quarter_idx": [_r(v) for v in total_profit],
        "avg_hbm_wafer_share": _r(shares[HBM].mean()) if mi.active[HBM] else 0.0,
        "avg_wafer_shadow_price": _r(lam.mean()),
        "recommended_mix": {n: _r(shares[p].mean(), 3) for p, n in enumerate(PRODUCTS) if mi.active[p]},
        "main_bottleneck": hits.most_common(1)[0][0] if hits else None,
    }

    if np.any(price[list(MARKET_IDX)][:, :] < 0):
        out["warnings"].append("시장 가격이 음수가 된 분기가 있습니다 (공급 과잉, 가정 확인 필요)")
    low = [k for k, a in res.registry.items() if a.confidence == "low"]
    out["warnings"].append(f"신뢰도 low 가정 {len(low)}개가 쓰였습니다. 민감도(토네이도)로 결론이 바뀌는지 확인하세요")
    return out


def _quarters(mask: np.ndarray) -> list[int]:
    return [int(t) + 1 for t in np.flatnonzero(mask)]


def _binding(mi, x, s, price) -> list[dict]:
    """등호로 붙어 있는(여유가 없는) 제약 목록."""
    out: list[dict] = []

    def add(name, mask, product=None):
        qs = _quarters(mask)
        if qs:
            out.append({"constraint": name, "product": product, "quarters": qs})

    add("wafer_capacity", (mi.W > TOL) & (x.sum(axis=0) >= mi.W - TOL))
    if mi.active[HBM]:
        add("hbm_demand", s[HBM] >= mi.dc_hbm - TOL, "HBM")
        add("hbm_backend_capacity", s[HBM] >= mi.k_hbm - TOL, "HBM")
    prev = np.column_stack([mi.x0, x[:, :-1]])
    dx = x - prev
    W_prev = np.concatenate([[mi.x0.sum()], mi.W[:-1]])
    r_down = mi.R[:, None] + np.maximum(0.0, W_prev - mi.W)[None, :]
    for p, name in enumerate(PRODUCTS):
        if not mi.active[p]:
            continue
        add("ramp_up", dx[p] >= mi.R[p] - TOL, name)
        add("ramp_down", -dx[p] >= r_down[p] - TOL, name)
        add("lta_min_volume", (mi.m[p] > TOL) & (s[p] <= mi.m[p] + TOL), name)
    for j, p in enumerate(MARKET_IDX):
        if mi.price_floor is not None:
            pf = mi.price_floor[j]
            add("price_floor", np.isfinite(pf) & (price[p] <= np.nan_to_num(pf) + TOL), PRODUCTS[p])
        if mi.share_floor is not None:
            th = np.nan_to_num(mi.share_floor[j])
            lb = th / np.where(th < 1, 1 - th, 1) * mi.s_comp[j]
            add("share_floor", np.isfinite(mi.share_floor[j]) & (s[p] <= lb + TOL), PRODUCTS[p])
    return out
