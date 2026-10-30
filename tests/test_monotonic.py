"""단조성 3종 (설계 v3 5.1절 박스)."""
import numpy as np
from conftest import ATOL

from memsim.core import market, optimizer
from memsim.core.types import HBM, MARKET_IDX


def test_more_wafers_never_hurts(base_input):
    prev = -np.inf
    for scale in (0.6, 0.8, 1.0, 1.2, 1.5):
        sol = optimizer.solve(base_input.copy(W=base_input.W * scale))
        assert sol.objective >= prev - ATOL
        prev = sol.objective


def test_competitor_supply_lowers_ddr5_price(base_input):
    prev = None
    for scale in (0.8, 1.0, 1.2, 1.5):
        mi = base_input.copy()
        mi.s_comp = mi.s_comp * scale
        sol = optimizer.solve(mi)
        p = market.prices(mi.a, mi.b, mi.s_comp, sol.s[list(MARKET_IDX)])[0]
        if prev is not None:
            assert np.all(p <= prev + ATOL)
        prev = p


def test_hbm_contract_price_raises_hbm_sales(base_input):
    prev = None
    for ratio in (0.5, 1.0, 2.0, 4.0, 8.0):
        sol = optimizer.solve(base_input.copy(pc_hbm=np.full(base_input.T, ratio)))
        if prev is not None:
            assert np.all(sol.s[HBM] >= prev - ATOL)
        prev = sol.s[HBM]
