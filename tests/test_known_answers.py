"""L2 정답 시나리오: 답이 뻔한 입력."""
import time

import numpy as np

from memsim.core import optimizer, params
from memsim.core.run import run
from memsim.core.scenario import Scenario
from memsim.core.types import HBM


def test_zero_capacity_zero_sales():
    sc = Scenario(scenario_id="z", assumption_overrides={"wafer_capacity": 0})
    sol = optimizer.solve(params.build(sc).mi)
    assert sol.status == "optimal"
    assert np.allclose(sol.s, 0, atol=1e-6)


def test_hbm_margin_reversal_cuts_hbm(base_input):
    base = optimizer.solve(base_input)
    cheap = optimizer.solve(base_input.copy(pc_hbm=base_input.pc_hbm * 0.25))
    assert cheap.x[HBM].mean() < base.x[HBM].mean() - 1
    # 전환 속도 한도만큼씩 줄어든다
    assert np.all(np.diff(np.concatenate([[base_input.x0[HBM]], cheap.x[HBM]])) >= -base_input.R[HBM] - 1e-6)


def test_lta_above_capacity_is_infeasible_and_diagnosed():
    sc = Scenario(scenario_id="lta", contracts={"lta_min_share": {"DDR5": 1.0, "LPDDR": 1.0}},
                  assumption_overrides={"wafer_capacity": 100},
                  shocks=[{"type": "wafer_capacity", "start_q": 2, "change_pct": -60}])
    r = run(sc)
    assert r["meta"]["status"] == "infeasible"
    assert "lta" in r["diagnostics"]["cause_groups"]


def test_share_floor_04_infeasible_like_prototype():
    """설계 v3 토이 결과: share_floor θ=0.4는 infeasible → R5 진단."""
    r = run({"scenario_id": "sf", "mode": "evaluate",
             "policy": {"type": "share_floor", "product": "DDR5", "theta": 0.4}})
    assert r["meta"]["status"] == "infeasible"
    assert "policy" in r["diagnostics"]["cause_groups"]


def test_nonbinding_policy_equals_optimize(base_input):
    """정책이 사실상 없으면 optimize 결과와 같다."""
    opt = optimizer.solve(base_input)
    mi = base_input.copy(price_floor=np.full((2, base_input.T), 1e-3))
    ev = optimizer.solve(mi)
    assert abs(ev.objective - opt.objective) <= 1e-5 * abs(opt.objective)


def test_wafer_shadow_price_matches_finite_difference(base_input):
    sol = optimizer.solve(base_input)
    t, eps = 4, 1e-2
    mi = base_input.copy()
    mi.W[t] += eps
    fd = (optimizer.solve(mi).objective - sol.objective) / eps
    assert sol.wafer_dual[t] > 0
    assert abs(sol.wafer_dual[t] - fd) <= 0.05 * abs(fd) + 1e-6


def test_resolve_is_fast(base_input):
    optimizer.solve(base_input)  # 컴파일
    t0 = time.perf_counter()
    for _ in range(20):
        optimizer.solve(base_input)
    assert (time.perf_counter() - t0) / 20 < 0.05  # 설계: 재풀이 약 3ms, 넉넉하게 50ms
