import numpy as np
import pytest

from memsim.core import params
from memsim.core.scenario import Scenario

ATOL = 1e-5  # Clarabel 기준 허용오차 (값의 크기가 100 안팎)


@pytest.fixture
def base_scenario() -> Scenario:
    return Scenario(scenario_id="base")


@pytest.fixture
def base_input(base_scenario):
    return params.build(base_scenario).mi


def check_invariants(mi, sol, atol=ATOL):
    """L1 불변식. 위반하면 AssertionError."""
    x, s, I = sol.x, sol.s, sol.I
    assert x.min() >= -atol and s.min() >= -atol and I.min() >= -atol, "음수"
    assert np.all(x.sum(axis=0) <= mi.W + atol), "웨이퍼 합 > W"
    prev = np.column_stack([mi.I0, I[:, :-1]])
    np.testing.assert_allclose(I, prev + mi.g * x - s, atol=atol, err_msg="재고 보존")
    assert np.all(np.abs(I[0]) <= atol), "HBM 재고 ≠ 0"
    assert np.all(s[0] <= np.minimum(mi.dc_hbm, mi.k_hbm) + atol), "HBM 배정·후공정 초과"
    px = np.column_stack([mi.x0, x[:, :-1]])
    W_prev = np.concatenate([[mi.x0.sum()], mi.W[:-1]])
    assert np.all(x - px <= mi.R[:, None] + atol), "전환 속도(증가) 초과"
    assert np.all(px - x <= mi.R[:, None] + np.maximum(0, W_prev - mi.W) + atol), "전환 속도(감소) 초과"
    assert np.all(s >= mi.m - atol), "장기계약 최소 물량 미달"
    assert np.all(x[~mi.active] <= atol), "비활성 제품에 웨이퍼 투입"
    assert np.all(sol.wafer_dual >= -atol), "λ < 0"
