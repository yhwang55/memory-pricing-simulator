"""L1 불변식: 무작위 시나리오 여러 개에서 해가 모든 제약을 지키는지."""
import numpy as np
import pytest
from conftest import check_invariants

from memsim.core import optimizer, params
from memsim.core.scenario import Scenario
from memsim.presets import load_all


def _random_scenario(seed: int) -> Scenario:
    rng = np.random.default_rng(seed)
    shocks = [
        {"type": "demand", "segment": str(rng.choice(["ai_server", "general_server", "pc", "mobile"])),
         "start_q": int(rng.integers(1, 13)), "shape": "step", "change_pct": float(rng.uniform(-40, 60))},
        {"type": "competitor_capacity", "product": str(rng.choice(["DDR5", "LPDDR"])),
         "start_q": int(rng.integers(1, 13)), "shape": "ramp", "duration_q": int(rng.integers(1, 6)),
         "change_pct": float(rng.uniform(-30, 50))},
    ]
    return Scenario(
        scenario_id=f"rand{seed}",
        shocks=shocks,
        contracts={"hbm_price_ratio_to_ddr5": float(rng.uniform(1, 8)),
                   "lta_min_share": {"DDR5": float(rng.uniform(0, 0.3))}},
        assumption_overrides={"ramp_wafers": float(rng.uniform(2, 15)),
                              "elasticity_ddr5": float(rng.uniform(0.3, 3))},
    )


@pytest.mark.parametrize("seed", list(range(20)))
def test_random_scenarios(seed):
    mi = params.build(_random_scenario(seed)).mi
    sol = optimizer.solve(mi)
    if sol.status == "infeasible":  # 무작위 조합이 실제로 불가능할 수 있다 → 진단이 원인을 내야 함
        assert optimizer.diagnose(mi)["cause_groups"]
        return
    assert sol.status == "optimal"
    check_invariants(mi, sol)


@pytest.mark.parametrize("preset", load_all(), ids=lambda p: p["preset_id"])
def test_presets(preset):
    mi = params.build(Scenario.model_validate(preset["scenario"])).mi
    sol = optimizer.solve(mi)
    assert sol.status == "optimal"
    check_invariants(mi, sol)


@pytest.mark.parametrize("policy", [
    {"type": "price_floor", "product": "DDR5", "price_idx": 100},
    {"type": "share_floor", "product": "LPDDR", "theta": 0.3},
    {"type": "fixed_mix", "mix": {"HBM": 0.22, "DDR5": 0.5, "LPDDR": 0.28}},
])
def test_policies(policy):
    mi = params.build(Scenario(scenario_id="p", mode="evaluate", policy=policy)).mi
    sol = optimizer.solve(mi)
    assert sol.status == "optimal"
    check_invariants(mi, sol)
