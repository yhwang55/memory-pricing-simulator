"""시나리오 입력 스키마 (R1 검증) 와 충격 펼치기 (R2 가정 해석).

스키마는 설계 v3 8장 "시나리오 입력"을 따른다. 바꾸면 3인 승인 + SCHEMA_VERSION 증가.
"""
from __future__ import annotations

import re
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from memsim.core.types import MARKET_PRODUCTS, PRODUCTS

SCHEMA_VERSION = "3.0"
MAX_HORIZON = 12

Product = Literal["HBM", "DDR5", "LPDDR"]
MarketProduct = Literal["DDR5", "LPDDR"]
Segment = Literal["ai_server", "general_server", "pc", "mobile"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # 모르는 키는 422


class Shock(_Strict):
    """충격 하나. change_pct는 기준 경로 대비 % (20 = +20%)."""

    type: Literal["demand", "competitor_capacity", "hbm_contract_price", "wafer_capacity", "hbm_backend_capacity"]
    segment: Segment | None = None  # demand 전용
    product: MarketProduct | None = None  # competitor_capacity 전용
    start_q: int = Field(ge=1, le=MAX_HORIZON)
    shape: Literal["step", "ramp", "pulse"] = "step"
    duration_q: int | None = Field(default=None, ge=1, le=MAX_HORIZON)
    change_pct: float = Field(ge=-100, le=500)

    @model_validator(mode="after")
    def _check(self):
        if self.type == "demand" and self.segment is None:
            raise ValueError("demand 충격에는 segment가 필요합니다")
        if self.type != "demand" and self.segment is not None:
            raise ValueError("segment는 demand 충격에만 씁니다")
        if self.type == "competitor_capacity" and self.product is None:
            raise ValueError("competitor_capacity 충격에는 product(DDR5|LPDDR)가 필요합니다")
        if self.type != "competitor_capacity" and self.product is not None:
            raise ValueError("product는 competitor_capacity 충격에만 씁니다")
        if self.shape in ("ramp", "pulse") and self.duration_q is None:
            raise ValueError(f"shape={self.shape}에는 duration_q가 필요합니다")
        return self


class PriceFloor(_Strict):
    type: Literal["price_floor"]
    product: MarketProduct
    price_idx: float = Field(gt=0, description="가격 하한 (기준 분기 DDR5 = 100)")


class ShareFloor(_Strict):
    type: Literal["share_floor"]
    product: MarketProduct
    theta: float = Field(gt=0, lt=1, description="시장 점유율 하한")


class FixedMix(_Strict):
    type: Literal["fixed_mix"]
    mix: dict[Product, float]

    @field_validator("mix")
    @classmethod
    def _sum_one(cls, v):
        if any(x < 0 for x in v.values()):
            raise ValueError("mix 비중은 0 이상")
        if abs(sum(v.values()) - 1) > 1e-6:
            raise ValueError(f"mix 비중 합이 1이 아닙니다 ({sum(v.values()):.4f})")
        return v


Policy = PriceFloor | ShareFloor | FixedMix


class Contracts(_Strict):
    hbm_price_ratio_to_ddr5: float | None = Field(default=None, ge=0, description="null이면 가정 기본값")
    lta_min_share: dict[Product, float] = Field(default_factory=dict, description="기준 분기 판매 대비 최소 물량 비율")

    @field_validator("lta_min_share")
    @classmethod
    def _range(cls, v):
        for k, x in v.items():
            if not 0 <= x <= 1:
                raise ValueError(f"lta_min_share[{k}]는 0~1")
        return v


class Scenario(_Strict):
    schema_version: str = SCHEMA_VERSION
    scenario_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_\-]+$")
    name: str | None = None
    base_quarter: str = "2026Q3"
    horizon_quarters: int = Field(default=MAX_HORIZON, ge=1, le=MAX_HORIZON)
    products: list[Product] = Field(default_factory=lambda: list(PRODUCTS), min_length=1)
    mode: Literal["optimize", "evaluate", "market_only"] = "optimize"
    shocks: list[Shock] = Field(default_factory=list)
    policy: Policy | None = Field(default=None, discriminator="type")
    contracts: Contracts = Field(default_factory=Contracts)
    assumption_overrides: dict[str, float] = Field(default_factory=dict)
    seed: int = 42

    @field_validator("schema_version")
    @classmethod
    def _compatible(cls, v):
        if v.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
            raise ValueError(f"schema_version {v}는 지원하지 않습니다 (현재 {SCHEMA_VERSION})")
        return v

    @field_validator("base_quarter")
    @classmethod
    def _quarter(cls, v):
        if not re.fullmatch(r"20\d\dQ[1-4]", v):
            raise ValueError("base_quarter 형식은 2026Q3")
        return v

    @field_validator("products")
    @classmethod
    def _unique(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("products에 중복이 있습니다")
        return v

    @model_validator(mode="after")
    def _mode_policy(self):
        if self.mode == "evaluate" and self.policy is None:
            raise ValueError("evaluate 모드에는 policy가 필요합니다")
        if self.mode != "evaluate" and self.policy is not None:
            raise ValueError("policy는 evaluate 모드에서만 씁니다")
        for s in self.shocks:
            if s.start_q > self.horizon_quarters:
                raise ValueError(f"충격 start_q={s.start_q}가 horizon({self.horizon_quarters})을 넘습니다")
        if self.policy is not None and self.policy.type in ("price_floor", "share_floor"):
            if self.policy.product not in self.products:
                raise ValueError(f"policy 대상 {self.policy.product}가 products에 없습니다")
        if isinstance(self.policy, FixedMix):
            extra = [p for p, w in self.policy.mix.items() if w > 0 and p not in self.products]
            if extra:
                raise ValueError(f"fixed_mix에 products에 없는 제품이 있습니다: {extra}")
        return self


def quarter_labels(base_quarter: str, n: int) -> list[str]:
    """'2026Q3', 3 → ['2026Q3', '2026Q4', '2027Q1']. q1 = 기준 분기."""
    year, q = int(base_quarter[:4]), int(base_quarter[-1])
    out = []
    for i in range(n):
        k = (q - 1) + i
        out.append(f"{year + k // 4}Q{k % 4 + 1}")
    return out


def shock_multiplier(shock: Shock, T: int) -> np.ndarray:
    """충격 하나를 길이 T의 배수 배열로 펼친다 (1 = 변화 없음).

    step   start_q부터 계속 (duration_q가 있으면 그 기간만)
    ramp   start_q부터 duration_q 분기 동안 선형으로 늘어 끝까지 유지
    pulse  start_q부터 duration_q 분기 동안만
    """
    t = np.arange(1, T + 1)
    full = shock.change_pct / 100.0
    k = t - shock.start_q  # 0 = 시작 분기
    if shock.shape == "ramp":
        frac = np.clip((k + 1) / shock.duration_q, 0, 1)
        eff = np.where(k >= 0, full * frac, 0.0)
    else:
        on = k >= 0
        if shock.duration_q is not None:
            on &= k < shock.duration_q
        eff = np.where(on, full, 0.0)
    return 1.0 + eff


def combined_multiplier(shocks: list[Shock], T: int, **match) -> np.ndarray:
    """조건에 맞는 충격들의 배수를 곱해서 합친다."""
    out = np.ones(T)
    for s in shocks:
        if all(getattr(s, k) == v for k, v in match.items()):
            out *= shock_multiplier(s, T)
    return out


__all__ = [
    "SCHEMA_VERSION", "Scenario", "Shock", "Contracts", "PriceFloor", "ShareFloor", "FixedMix",
    "quarter_labels", "shock_multiplier", "combined_multiplier", "MARKET_PRODUCTS",
]
