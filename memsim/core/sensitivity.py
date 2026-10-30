"""M5 민감도 v0: 가정을 하나씩 흔들어 누적 이익 변화로 토네이도를 만든다 (설계 L4).

흔드는 폭은 신뢰도별 high ±10%, medium ±25%, low ±50% (assumptions.CONFIDENCE_RANGE).
허용 범위 [lo, hi]를 넘으면 경계에서 자른다. 해가 없어지는 쪽은 infeasible로 표시한다.
"""
from __future__ import annotations

from memsim.core import assumptions, optimizer, params, postprocess
from memsim.core.run import _as_scenario


def _cum_profit(sc, res) -> float | None:
    sol = optimizer.solve(res.mi)
    if not sol.status.startswith("optimal"):
        return None
    return postprocess.build(sc, res, sol)["summary"]["cum_profit_idx"]


def tornado(scenario, top: int = 5, keys: list[str] | None = None, delta_pct: float | None = None) -> dict:
    """delta_pct를 주면 신뢰도와 상관없이 모든 가정을 ±delta_pct%로 흔든다."""
    sc = _as_scenario(scenario)
    registry = assumptions.load()
    base_res = params.build(sc, registry)
    base_values = base_res.values
    base = _cum_profit(sc, base_res)
    if base is None:
        return {"status": "infeasible", "base_cum_profit_idx": None, "items": []}

    items = []
    for key in keys or list(registry):
        a = registry[key]
        d = (delta_pct / 100) if delta_pct is not None else assumptions.CONFIDENCE_RANGE[a.confidence]
        row = {"assumption": key, "confidence": a.confidence, "base_value": base_values[key], "delta_pct": d * 100}
        for side, sign in (("low", -1), ("high", 1)):
            val = base_values[key] * (1 + sign * d)
            if a.lo is not None:
                val = max(val, a.lo)
            if a.hi is not None:
                val = min(val, a.hi)
            try:
                res = params.build(sc, registry, values={**base_values, key: val})
                cp = _cum_profit(sc, res)
            except params.AssumptionError:
                cp = None
            row[f"{side}_value"] = round(val, 6)
            row[f"{side}_cum_profit_change_pct"] = None if cp is None else round((cp - base) / abs(base) * 100, 3)
        swing = [abs(row[f"{s}_cum_profit_change_pct"]) for s in ("low", "high")
                 if row[f"{s}_cum_profit_change_pct"] is not None]
        row["swing"] = max(swing) if swing else float("inf")  # 해가 없어지는 가정은 맨 위로
        items.append(row)
    items.sort(key=lambda r: r["swing"], reverse=True)
    for r in items:
        if r["swing"] == float("inf"):
            r["swing"] = None
    return {"status": "optimal", "base_cum_profit_idx": base, "items": items[:top], "n_evaluated": len(items)}
