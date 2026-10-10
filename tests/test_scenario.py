"""R1 검증·R2 충격 펼치기. cvxpy 없이 돈다."""
import numpy as np
import pytest
from pydantic import ValidationError

from memsim.core import params
from memsim.core.scenario import Scenario, Shock, quarter_labels, shock_multiplier
from memsim.presets import load_all


def test_defaults():
    sc = Scenario(scenario_id="a")
    assert sc.horizon_quarters == 12 and sc.products == ["HBM", "DDR5", "LPDDR"] and sc.mode == "optimize"


@pytest.mark.parametrize("bad", [
    {"scenario_id": "a", "unknown": 1},                                   # 모르는 키
    {"scenario_id": "A B"},                                               # id 형식
    {"scenario_id": "a", "schema_version": "2.0"},                        # 호환 안 되는 버전
    {"scenario_id": "a", "mode": "evaluate"},                             # evaluate인데 policy 없음
    {"scenario_id": "a", "policy": {"type": "share_floor", "product": "DDR5", "theta": 0.3}},  # optimize + policy
    {"scenario_id": "a", "shocks": [{"type": "demand", "start_q": 1, "change_pct": 10}]},     # segment 없음
    {"scenario_id": "a", "shocks": [{"type": "demand", "segment": "pc", "start_q": 13, "change_pct": 10}]},
    {"scenario_id": "a", "shocks": [{"type": "wafer_capacity", "start_q": 1, "shape": "pulse", "change_pct": 10}]},
    {"scenario_id": "a", "mode": "evaluate", "policy": {"type": "fixed_mix", "mix": {"HBM": 0.5, "DDR5": 0.4}}},
    {"scenario_id": "a", "products": ["HBM", "HBM"]},
    {"scenario_id": "a", "base_quarter": "2026-3"},
    {"scenario_id": "a", "contracts": {"lta_min_share": {"DDR5": 1.5}}},
])
def test_rejects(bad):
    with pytest.raises(ValidationError):
        Scenario.model_validate(bad)


def test_shock_shapes():
    step = Shock(type="demand", segment="ai_server", start_q=3, change_pct=20)
    np.testing.assert_allclose(shock_multiplier(step, 5), [1, 1, 1.2, 1.2, 1.2])
    ramp = Shock(type="wafer_capacity", start_q=2, shape="ramp", duration_q=4, change_pct=40)
    np.testing.assert_allclose(shock_multiplier(ramp, 7), [1, 1.1, 1.2, 1.3, 1.4, 1.4, 1.4])
    pulse = Shock(type="wafer_capacity", start_q=2, shape="pulse", duration_q=2, change_pct=-50)
    np.testing.assert_allclose(shock_multiplier(pulse, 5), [1, 0.5, 0.5, 1, 1])


def test_quarter_labels():
    assert quarter_labels("2026Q3", 4) == ["2026Q3", "2026Q4", "2027Q1", "2027Q2"]


def test_unknown_override_rejected():
    with pytest.raises(params.AssumptionError):
        params.build(Scenario(scenario_id="a", assumption_overrides={"nope": 1}))
    with pytest.raises(params.AssumptionError):
        params.build(Scenario(scenario_id="a", assumption_overrides={"hbm_g_ratio": 5}))


def test_base_quarter_reproduces_base_price():
    """기준 분기에 기준 배분을 팔면 시장 가격 = P̄ (M3 보정 확인)."""
    mi = params.build(Scenario(scenario_id="a")).mi
    own = mi.x0 * mi.g[:, 0]
    price = mi.a[:, 0] - mi.b * (mi.s_comp[:, 0] + own[1:])
    np.testing.assert_allclose(price, [1.0, 0.9])


def test_ai_shock_moves_hbm_and_ddr5():
    base = params.build(Scenario(scenario_id="a")).mi
    up = params.build(Scenario(scenario_id="b", shocks=[
        {"type": "demand", "segment": "ai_server", "start_q": 3, "change_pct": 20}])).mi
    np.testing.assert_allclose(up.dc_hbm[:2], base.dc_hbm[:2])
    np.testing.assert_allclose(up.dc_hbm[2:], base.dc_hbm[2:] * 1.2)
    assert np.all(up.a[0, 2:] > base.a[0, 2:]) and np.allclose(up.a[1], base.a[1])


def test_presets_valid():
    for p in load_all():
        params.build(Scenario.model_validate(p["scenario"]))
