"""M4 최적화 (R4 풀이 + R5 진단). 설계 v3 5.1절의 볼록 QP.

    max  Σ_t δ^{t-1} [ P^C_t s_HBM,t + Σ_{p∈𝓜} (a_p,t − b_p (S^comp_p,t + s_p,t)) s_p,t
                       − Σ_p c_p,t x_p,t − Σ_p h_p I_p,t ]
    s.t. (1) Σ_p x_p,t ≤ W_t                          → 쌍대값 λ_t
         (2) I_p,t = I_p,t−1 + g_p,t x_p,t − s_p,t
         (3) s_HBM,t ≤ D^C_t,  s_HBM,t ≤ K_t,  I_HBM,t = 0
         (4) 전환 속도: x_p,t − x_p,t−1 ≤ R_p,  x_p,t−1 − x_p,t ≤ R_p + max(0, W_t−1 − W_t)
             (설계의 |Δx| ≤ R에서 바꾼 점: 캐파가 줄어드는 충격에서는 줄어든 만큼 더 줄일 수 있게 했다.
              그렇지 않으면 웨이퍼 캐파 −20% 충격만으로도 해가 없어진다. 팀 확인 필요)
         (5) s_p,t ≥ m_p,t
         정책(evaluate 모드)은 같은 문제에 선형 제약으로 붙는다 (policies.py에서 범위로 변환).

문제는 T(분기 수)마다 한 번만 만들고(DPP), 이후에는 cp.Parameter 값만 바꿔서 다시 푼다.
목적식의 할인과 a − bS 같은 곱은 파라미터끼리의 곱이 되면 DPP 규칙을 어기므로
numpy에서 미리 계산해 파라미터 하나로 넣는다.
"""
from __future__ import annotations

import threading
import time

import cvxpy as cp
import numpy as np

from memsim.core import policies
from memsim.core.types import HBM, MARKET_IDX, M, P, ModelInput, Solution

SOLVER = "CLARABEL"  # 설계 v3: 지정하지 않으면 OSQP가 골라져 1e-3 수준 오차가 났음
BIG = 1e4  # "제약 없음"을 나타내는 상한 (bit·웨이퍼 단위가 100 안팎이므로 충분히 큼)

# R5에서 하나씩 풀어볼 제약 그룹. 순서가 보고 순서다.
RELAXABLE_GROUPS = ("lta", "policy", "ramp")


class _Compiled:
    """T 하나에 대한 파라미터화된 QP."""

    def __init__(self, T: int):
        self.T = T
        x = cp.Variable((P, T), nonneg=True, name="x")  # 웨이퍼 투입
        s = cp.Variable((P, T), nonneg=True, name="s")  # 판매 bit
        I = cp.Variable((P, T), nonneg=True, name="I")  # 기말 재고 bit
        self.x, self.s, self.I = x, s, I

        par = self.par = {
            "W": cp.Parameter(T, nonneg=True, name="W"),
            "g": cp.Parameter((P, T), nonneg=True, name="g"),
            "cost": cp.Parameter((P, T), nonneg=True, name="cost"),  # δ^{t-1} c
            "hold": cp.Parameter((P, T), nonneg=True, name="hold"),  # δ^{t-1} h
            "hbm_rev": cp.Parameter(T, nonneg=True, name="hbm_rev"),  # δ^{t-1} P^C
            "lin": cp.Parameter((M, T), name="lin"),  # δ^{t-1} (a − b S^comp)
            "quad": cp.Parameter((M, T), nonneg=True, name="quad"),  # δ^{t-1} b
            "x0": cp.Parameter(P, nonneg=True, name="x0"),
            "I0": cp.Parameter(P, nonneg=True, name="I0"),
            "R": cp.Parameter(P, nonneg=True, name="R"),
            "R_down": cp.Parameter((P, T), nonneg=True, name="R_down"),
            "x_ub": cp.Parameter((P, T), nonneg=True, name="x_ub"),  # 비활성 제품은 0
            "dc": cp.Parameter(T, nonneg=True, name="dc"),
            "k": cp.Parameter(T, nonneg=True, name="k"),
            "lta_lb": cp.Parameter((P, T), nonneg=True, name="lta_lb"),
            "pol_s_lb": cp.Parameter((P, T), nonneg=True, name="pol_s_lb"),
            "pol_s_ub": cp.Parameter((P, T), name="pol_s_ub"),  # 음수면 그 자체로 infeasible
            "pol_x_lb": cp.Parameter((P, T), nonneg=True, name="pol_x_lb"),
            "pol_x_ub": cp.Parameter((P, T), nonneg=True, name="pol_x_ub"),
        }

        # 제약 그룹: 이름 → 제약 리스트. postprocess가 병목 판정에 쓴다.
        prev_I = [par["I0"]] + [I[:, t - 1] for t in range(1, T)]
        prev_x = [par["x0"]] + [x[:, t - 1] for t in range(1, T)]
        self.wafer = cp.sum(x, axis=0) <= par["W"]
        self.groups: dict[str, list[cp.Constraint]] = {
            "wafer": [self.wafer],
            "inventory": [I[:, t] == prev_I[t] + cp.multiply(par["g"][:, t], x[:, t]) - s[:, t] for t in range(T)],
            "hbm": [s[HBM, :] <= par["dc"], s[HBM, :] <= par["k"], I[HBM, :] == 0],
            "active": [x <= par["x_ub"]],
            "ramp": [x[:, t] - prev_x[t] <= par["R"] for t in range(T)]
            + [prev_x[t] - x[:, t] <= par["R_down"][:, t] for t in range(T)],
            "lta": [s >= par["lta_lb"]],
            "policy": [s >= par["pol_s_lb"], s <= par["pol_s_ub"], x >= par["pol_x_lb"], x <= par["pol_x_ub"]],
        }

        assert MARKET_IDX == (1, 2)  # 시장 제품이 PRODUCTS 뒤쪽에 연속으로 있어야 슬라이스가 맞다
        s_mkt = s[1:, :]
        revenue = (
            par["hbm_rev"] @ s[HBM, :]
            + cp.sum(cp.multiply(par["lin"], s_mkt))
            - cp.sum(cp.multiply(par["quad"], cp.square(s_mkt)))
        )
        cost = cp.sum(cp.multiply(par["cost"], x)) + cp.sum(cp.multiply(par["hold"], I))
        constraints = [c for group in self.groups.values() for c in group]
        self.prob = cp.Problem(cp.Maximize(revenue - cost), constraints)
        assert self.prob.is_dcp(dpp=True), "QP가 DPP 규칙을 어김"

    def set_params(self, mi: ModelInput, relax: tuple[str, ...] = ()) -> None:
        T = self.T
        disc = mi.delta ** np.arange(T)
        a_mkt_lin = mi.a - mi.b[:, None] * mi.s_comp
        bounds = policies.to_bounds(mi, big=BIG)
        values = {
            "W": mi.W,
            "g": mi.g,
            "cost": mi.c * disc,
            "hold": mi.h[:, None] * disc,
            "hbm_rev": mi.pc_hbm * disc,
            "lin": a_mkt_lin * disc,
            "quad": mi.b[:, None] * disc,
            "x0": mi.x0,
            "I0": mi.I0,
            "R": np.full(P, BIG) if "ramp" in relax else mi.R,
            "R_down": np.full((P, T), BIG) if "ramp" in relax else ramp_down_limit(mi),
            "x_ub": np.where(mi.active[:, None], BIG, 0.0) * np.ones((P, T)),
            "dc": mi.dc_hbm,
            "k": mi.k_hbm,
            "lta_lb": np.zeros((P, T)) if "lta" in relax else mi.m,
        }
        if "policy" in relax:
            bounds = policies.Bounds.none(P, T, BIG)
        values.update(
            pol_s_lb=bounds.s_lb, pol_s_ub=bounds.s_ub, pol_x_lb=bounds.x_lb, pol_x_ub=bounds.x_ub,
        )
        for name, val in values.items():
            self.par[name].value = np.asarray(val, dtype=float)


def ramp_down_limit(mi: ModelInput) -> np.ndarray:
    """(P, T) 분기별 웨이퍼 감소 한도 = R + 캐파 감소분."""
    W_prev = np.concatenate([[mi.x0.sum()], mi.W[:-1]])
    return mi.R[:, None] + np.maximum(0.0, W_prev - mi.W)[None, :]


_cache: dict[int, _Compiled] = {}
_lock = threading.Lock()  # 컴파일된 문제는 파라미터를 공유하므로 동시에 하나만 푼다


def _compiled(T: int) -> _Compiled:
    if T not in _cache:
        _cache[T] = _Compiled(T)
    return _cache[T]


def solve(mi: ModelInput, relax: tuple[str, ...] = ()) -> Solution:
    """ModelInput 하나를 푼다. relax에 든 제약 그룹은 끈다 (R5 진단용)."""
    mi.validate()
    with _lock:
        comp = _compiled(mi.T)
        comp.set_params(mi, relax)
        t0 = time.perf_counter()
        try:
            comp.prob.solve(solver=SOLVER)
            raw_status = comp.prob.status
        except cp.SolverError:
            raw_status = "error"
        ms = (time.perf_counter() - t0) * 1000

        if raw_status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
            return Solution(
                status="optimal" if raw_status == cp.OPTIMAL else "optimal_inaccurate",
                objective=float(comp.prob.value),
                x=np.maximum(comp.x.value, 0.0),
                s=np.maximum(comp.s.value, 0.0),
                I=np.maximum(comp.I.value, 0.0),
                # cvxpy는 Maximize 문제에서도 ≤ 제약의 쌍대값을 0 이상으로 돌려준다.
                # 부호는 tests/test_known_answers.py의 유한차분 테스트로 확인한다.
                wafer_dual=np.asarray(comp.wafer.dual_value, dtype=float).reshape(-1),
                solver=SOLVER,
                solve_ms=ms,
            )
        status = {
            cp.INFEASIBLE: "infeasible", cp.INFEASIBLE_INACCURATE: "infeasible",
            cp.UNBOUNDED: "unbounded", cp.UNBOUNDED_INACCURATE: "unbounded",
        }.get(raw_status, "error")
        return Solution(status=status, solver=SOLVER, solve_ms=ms)


def diagnose(mi: ModelInput) -> dict:
    """R5: 해가 없을 때 제약 그룹을 하나씩 풀어서 다시 풀고, 해가 생기게 만드는 그룹을 보고한다."""
    culprits = [g for g in RELAXABLE_GROUPS if solve(mi, relax=(g,)).status.startswith("optimal")]
    if culprits:
        return {"cause_groups": culprits, "note": "이 그룹 중 하나만 풀어도 해가 생긴다"}
    if solve(mi, relax=RELAXABLE_GROUPS).status.startswith("optimal"):
        return {"cause_groups": list(RELAXABLE_GROUPS), "note": "여러 그룹이 함께 충돌한다 (하나만 풀어서는 해가 없음)"}
    return {"cause_groups": [], "note": "장기계약·정책·전환 속도를 모두 풀어도 해가 없다 (HBM 재고 0 또는 기초 재고 등 입력 확인)"}
