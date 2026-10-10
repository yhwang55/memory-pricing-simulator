"""R2 가정 해석 + R3 파라미터 생성: Scenario → ModelInput.

덮어쓰기 순서: 토이 기본값 → data/assumptions.yaml → (프리셋) → assumption_overrides → contracts.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from memsim.core import assumptions, demand, market, supply
from memsim.core.scenario import FixedMix, PriceFloor, Scenario, ShareFloor, combined_multiplier
from memsim.core.types import MARKET_PRODUCTS, PRODUCTS, ModelInput


class AssumptionError(ValueError):
    """모르는 가정 키나 범위를 벗어난 값. API에서 422로 바뀐다."""


@dataclass
class Resolved:
    mi: ModelInput
    values: dict[str, float]  # 실제로 쓴 가정값
    registry: dict[str, assumptions.Assumption]
    warnings: list[str] = field(default_factory=list)


def resolve_values(sc: Scenario, registry: dict[str, assumptions.Assumption]) -> dict[str, float]:
    values = {k: a.value for k, a in registry.items()}
    for key, val in sc.assumption_overrides.items():
        if key not in registry:
            raise AssumptionError(f"assumption_overrides: 모르는 키 '{key}'")
        a = registry[key]
        if (a.lo is not None and val < a.lo) or (a.hi is not None and val > a.hi):
            raise AssumptionError(f"assumption_overrides.{key}={val}는 허용 범위 [{a.lo}, {a.hi}] 밖입니다")
        values[key] = float(val)
    if sc.contracts.hbm_price_ratio_to_ddr5 is not None:
        values["hbm_price_ratio"] = sc.contracts.hbm_price_ratio_to_ddr5
    return values


def build(sc: Scenario, registry: dict[str, assumptions.Assumption] | None = None,
          values: dict[str, float] | None = None) -> Resolved:
    """values를 주면 레지스트리 대신 그 값을 쓴다 (M5 민감도에서 하나씩 흔들 때)."""
    registry = registry or assumptions.load()
    v = values if values is not None else resolve_values(sc, registry)
    T = sc.horizon_quarters
    active = np.array([p in sc.products for p in PRODUCTS])
    warnings: list[str] = []

    try:
        sup = supply.build(sc, v, T, active)
        dem = demand.build(sc, v, T)
        mkt = market.build(sc, v, T, sup["own_base_bits"], dem["qbar_mult"])
    except ValueError as e:
        raise AssumptionError(str(e)) from e

    pbar = v["price_base_ddr5"]
    pc = v["hbm_price_ratio"] * pbar * combined_multiplier(sc.shocks, T, type="hbm_contract_price")

    lta = np.array([sc.contracts.lta_min_share.get(p, 0.0) for p in PRODUCTS])
    m = np.repeat((lta * sup["own_base_bits"] * active)[:, None], T, axis=1)

    price_floor = share_floor = fixed_mix = None
    pol = sc.policy
    if isinstance(pol, PriceFloor):
        price_floor = np.full((len(MARKET_PRODUCTS), T), np.nan)
        price_floor[MARKET_PRODUCTS.index(pol.product)] = pol.price_idx / 100 * pbar
    elif isinstance(pol, ShareFloor):
        share_floor = np.full((len(MARKET_PRODUCTS), T), np.nan)
        share_floor[MARKET_PRODUCTS.index(pol.product)] = pol.theta
    elif isinstance(pol, FixedMix):
        fixed_mix = np.array([pol.mix.get(p, 0.0) for p in PRODUCTS])
    if sc.mode == "market_only":
        # v0: 기준 분기 배분을 그대로 유지했을 때의 시장 결과 (백테스트에서는 과거 공급 경로로 바꾼다)
        fixed_mix = sup["share0"]
        warnings.append("market_only v0: 기준 분기 웨이퍼 비중을 고정한 결과입니다 (과거 공급 경로 입력은 W7)")

    mi = ModelInput(
        T=T, W=sup["W"], g=sup["g"], c=sup["c"], h=sup["h"], delta=v["discount_factor"],
        x0=sup["x0"], I0=np.zeros(len(PRODUCTS)), R=sup["R"], m=m,
        pc_hbm=pc, dc_hbm=dem["dc_hbm"], k_hbm=sup["k_hbm"],
        a=mkt["a"], b=mkt["b"], s_comp=mkt["s_comp"], active=active,
        price_base=pbar, qty_base=float(sup["own_base_bits"].sum()),
        price_floor=price_floor, share_floor=share_floor, fixed_mix=fixed_mix,
    )
    try:
        mi.validate()
    except AssertionError as e:
        raise AssumptionError(f"파라미터 검사 실패: {e}") from e
    return Resolved(mi=mi, values=v, registry=registry, warnings=warnings)
