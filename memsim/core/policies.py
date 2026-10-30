"""정책 = 선형 제약 (설계 v3 5.2절, evaluate 모드).

정책을 판매 bit s와 웨이퍼 x의 상·하한으로 바꿔서 optimizer의 파라미터에 넣는다.
제약 구조가 바뀌지 않으므로 정책이 있든 없든 같은 컴파일된 문제를 쓴다.

  price_floor  시장가 ≥ P^hold     ⇔  s_p,t ≤ (a_p,t − P^hold)/b_p − S^comp_p,t
  share_floor  점유율 ≥ θ          ⇔  s_p,t ≥ θ/(1−θ) · S^comp_p,t
  fixed_mix    웨이퍼 비중 = φ      ⇔  x_p,t = φ_p · W_t
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from memsim.core.types import MARKET_IDX, ModelInput


@dataclass
class Bounds:
    s_lb: np.ndarray
    s_ub: np.ndarray
    x_lb: np.ndarray
    x_ub: np.ndarray

    @classmethod
    def none(cls, P: int, T: int, big: float) -> "Bounds":
        return cls(np.zeros((P, T)), np.full((P, T), big), np.zeros((P, T)), np.full((P, T), big))


def to_bounds(mi: ModelInput, big: float) -> Bounds:
    P = mi.g.shape[0]
    b = Bounds.none(P, mi.T, big)
    for j, p in enumerate(MARKET_IDX):
        if mi.price_floor is not None:
            pf = mi.price_floor[j]
            ok = np.isfinite(pf)
            ub = (mi.a[j] - pf) / mi.b[j] - mi.s_comp[j]
            b.s_ub[p] = np.where(ok, np.minimum(ub, big), big)
        if mi.share_floor is not None:
            th = mi.share_floor[j]
            ok = np.isfinite(th)
            lb = np.where(ok, np.nan_to_num(th) / (1 - np.nan_to_num(th)) * mi.s_comp[j], 0.0)
            b.s_lb[p] = lb
    if mi.fixed_mix is not None:
        fixed = mi.fixed_mix[:, None] * mi.W[None, :]
        b.x_lb, b.x_ub = fixed.copy(), fixed.copy()
    return b
