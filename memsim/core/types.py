"""코어 내부에서 주고받는 자료형.

ModelInput은 R3(파라미터 생성)의 출력이자 R4(풀이)의 입력이다. 모든 배열은 numpy이고
제품 축 순서는 PRODUCTS, 시장 제품 축 순서는 MARKET_PRODUCTS를 따른다.

단위 (모두 가상의 지수, 설계 v3 3.3절 "W, c, h, δ는 상대값 가정"):
  웨이퍼     기준 분기 자사 웨이퍼 캐파 = 100
  bit       DDR5 웨이퍼 1장에서 나오는 bit = 1
  가격      bit당 가격. 기준 분기 DDR5 가격 = price_base (보통 1.0)
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

PRODUCTS: tuple[str, ...] = ("HBM", "DDR5", "LPDDR")
MARKET_PRODUCTS: tuple[str, ...] = ("DDR5", "LPDDR")  # 시장가로 팔리는 제품 (𝓜)
P = len(PRODUCTS)
M = len(MARKET_PRODUCTS)
HBM = 0
MARKET_IDX = (1, 2)  # PRODUCTS 안에서 MARKET_PRODUCTS의 위치


@dataclass
class ModelInput:
    """R4가 푸는 문제 하나를 완전히 정하는 값들. 모양은 (P, T) 또는 (M, T)."""

    T: int
    W: np.ndarray  # (T,) 웨이퍼 캐파
    g: np.ndarray  # (P, T) 웨이퍼 1장당 판매 가능 bit
    c: np.ndarray  # (P, T) 웨이퍼 1장당 변동비
    h: np.ndarray  # (P,) bit 1개를 한 분기 재고로 들고 있는 비용
    delta: float  # 분기 할인율
    x0: np.ndarray  # (P,) 직전 분기(t=0) 웨이퍼 투입, 전환 속도 제약의 출발점
    I0: np.ndarray  # (P,) 기초 재고
    R: np.ndarray  # (P,) 분기당 웨이퍼 투입 변화 한도 (웨이퍼 장수)
    m: np.ndarray  # (P, T) 장기계약 최소 판매 bit
    pc_hbm: np.ndarray  # (T,) HBM 계약가 (bit당)
    dc_hbm: np.ndarray  # (T,) 고객이 배정한 HBM 물량 상한 (bit)
    k_hbm: np.ndarray  # (T,) HBM 후공정 캐파 (bit)
    a: np.ndarray  # (M, T) 역수요 절편
    b: np.ndarray  # (M,) 역수요 기울기 (> 0)
    s_comp: np.ndarray  # (M, T) 경쟁사 공급 bit (외생)
    active: np.ndarray = field(default_factory=lambda: np.ones(P, dtype=bool))  # 시나리오에 포함된 제품
    # 지수화 기준 (R6)
    price_base: float = 1.0  # 기준 분기 DDR5 bit당 가격
    qty_base: float = 1.0  # 기준 분기 자사 판매 bit 합
    # 정책 (evaluate 모드). None이면 해당 제약 없음
    price_floor: np.ndarray | None = None  # (M, T) 시장가 하한, nan = 없음
    share_floor: np.ndarray | None = None  # (M, T) 점유율 하한 θ, nan = 없음
    fixed_mix: np.ndarray | None = None  # (P,) 웨이퍼 비중 φ (합 1)

    def copy(self, **changes) -> "ModelInput":
        """배열까지 복사한 새 ModelInput. changes로 일부 필드를 바꿀 수 있다."""
        base = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in self.__dict__.items()}
        base.update(changes)
        return replace(self, **base)

    def validate(self) -> None:
        """R3 끝의 assert. 모양, 음수, NaN을 검사한다."""
        T = self.T
        shapes = {
            "W": (T,), "g": (P, T), "c": (P, T), "h": (P,), "x0": (P,), "I0": (P,), "R": (P,),
            "m": (P, T), "pc_hbm": (T,), "dc_hbm": (T,), "k_hbm": (T,), "a": (M, T), "b": (M,),
            "s_comp": (M, T), "active": (P,),
        }
        for name, shape in shapes.items():
            arr = getattr(self, name)
            assert arr.shape == shape, f"{name} 모양 {arr.shape} != {shape}"
            if name != "active":
                assert np.all(np.isfinite(arr)), f"{name}에 NaN/inf"
                assert np.all(arr >= 0), f"{name}에 음수"
        assert np.all(self.b > 0), "b는 양수여야 함"
        assert 0 < self.delta <= 1, "delta는 (0, 1]"
        if self.fixed_mix is not None:
            assert self.fixed_mix.shape == (P,) and abs(self.fixed_mix.sum() - 1) < 1e-9


@dataclass
class Solution:
    """R4의 원시 해 (지수화 전)."""

    status: str  # optimal | infeasible | unbounded | error
    objective: float | None = None  # 할인된 목적값
    x: np.ndarray | None = None  # (P, T)
    s: np.ndarray | None = None  # (P, T)
    I: np.ndarray | None = None  # (P, T)
    wafer_dual: np.ndarray | None = None  # (T,) 할인된 쌍대값
    solver: str = ""
    solve_ms: float = 0.0
