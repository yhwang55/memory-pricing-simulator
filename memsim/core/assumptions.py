"""가정 레지스트리 (R2의 입력).

지금 값은 모두 **토이 값**이다. 설계 v3 5.1절 토이 프로토타입처럼 가상의 지수로 만든
값이고 실제 시장을 나타내지 않는다. 데이터 담당이 D3 보정으로 data/assumptions.yaml을
만들면 load()가 그 파일의 값으로 덮어쓴다 (파일에 없는 키는 토이 값 유지).

data/assumptions.yaml 형식 (키는 아래 TOY_DEFAULTS와 같아야 한다):

    hbm_g_ratio:
      value: 0.35
      confidence: medium          # high | medium | low → 민감도 범위 ±10/25/50%
      sources: [TF-20260602, MU-HOTCHIPS-2026]
      note: Micron 약 3배 웨이퍼 면적, TrendForce 웨이퍼/bit 비중 역산 0.35~0.40
"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ASSUMPTIONS_YAML = REPO / "data" / "assumptions.yaml"

CONFIDENCE_RANGE = {"high": 0.10, "medium": 0.25, "low": 0.50}  # 설계 L4


@dataclass
class Assumption:
    key: str
    value: float
    unit: str
    confidence: str  # high | medium | low
    description: str
    sources: list[str] = field(default_factory=list)
    lo: float | None = None  # 허용 범위 (assumption_overrides 검사용)
    hi: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _a(key, value, unit, confidence, description, lo=None, hi=None, sources=()):
    return Assumption(key, value, unit, confidence, description, list(sources), lo, hi)


# 토이 기본값. 출처가 없는 값은 모두 "가정"이며 신뢰도 low.
TOY_DEFAULTS: dict[str, Assumption] = {a.key: a for a in [
    # M2 공급
    _a("wafer_capacity", 100.0, "index", "high", "자사 분기 웨이퍼 캐파 (기준 = 100)", 0, 1000),
    _a("hbm_g_ratio", 0.35, "x", "medium", "HBM 웨이퍼당 bit ÷ DDR5 웨이퍼당 bit", 0.05, 1.0,
       ["TF-20260602"]),
    _a("lpddr_g_ratio", 0.9, "x", "low", "LPDDR 웨이퍼당 bit ÷ DDR5 웨이퍼당 bit", 0.3, 1.5),
    _a("cost_wafer_hbm", 0.70, "price_idx/wafer", "low", "HBM 웨이퍼당 변동비 (TSV·적층 포함)", 0, 10),
    _a("cost_wafer_ddr5", 0.45, "price_idx/wafer", "low", "DDR5 웨이퍼당 변동비", 0, 10),
    _a("cost_wafer_lpddr", 0.45, "price_idx/wafer", "low", "LPDDR 웨이퍼당 변동비", 0, 10),
    _a("holding_cost", 0.02, "price_idx/bit/q", "low", "bit 1개 분기 재고비", 0, 1),
    _a("discount_factor", 0.98, "x", "low", "분기 할인 계수 δ", 0.5, 1.0),
    _a("ramp_wafers", 5.0, "wafer/q", "medium", "제품별 분기 웨이퍼 투입 변화 한도 R (업계 HBM 비중 연 +4~8%p보다 넓게)",
       0, 100, ["TF-20260602"]),
    _a("init_share_hbm", 0.22, "share", "medium", "기준 분기 HBM 웨이퍼 비중 (업계 2026년 말 추정 22%)", 0, 1,
       ["TF-20260602"]),
    _a("init_share_ddr5", 0.50, "share", "low", "기준 분기 DDR5 웨이퍼 비중 (나머지는 LPDDR)", 0, 1),
    _a("hbm_backend_bits", 9.0, "bit", "low", "기준 분기 HBM 후공정 캐파 K (공개 수치 없음)", 0, 1000),
    _a("hbm_backend_growth", 0.04, "pct/q", "low", "HBM 후공정 캐파 분기 증가율", -0.5, 1),
    # M1 수요
    _a("hbm_demand_bits", 8.0, "bit", "low", "기준 분기 고객이 배정한 HBM 물량 D^C", 0, 1000),
    _a("hbm_demand_growth", 0.05, "pct/q", "low", "HBM 배정 물량 분기 증가율", -0.5, 1),
    _a("market_demand_growth", 0.02, "pct/q", "low", "범용 DRAM 시장 수요(Q̄) 분기 증가율", -0.5, 1),
    _a("ai_share_of_ddr5", 0.30, "share", "low", "DDR5 수요 중 AI 서버 몫", 0, 1),
    _a("pc_share_of_ddr5", 0.20, "share", "low", "DDR5 수요 중 PC 몫 (나머지는 일반 서버)", 0, 1),
    # M3 시장
    _a("price_base_ddr5", 1.0, "price_idx", "high", "기준 분기 DDR5 bit당 가격 (지수 기준)", 0.01, 100),
    _a("price_base_lpddr", 0.9, "price_idx", "low", "기준 분기 LPDDR bit당 가격 (DDR5 대비)", 0.01, 100),
    _a("elasticity_ddr5", 1.0, "x", "low", "DDR5 수요 가격탄력성 ε (공개 추정치 없음)", 0.05, 10),
    _a("elasticity_lpddr", 1.0, "x", "low", "LPDDR 수요 가격탄력성 ε (공개 추정치 없음)", 0.05, 10),
    _a("comp_supply_ddr5", 100.0, "bit", "low", "기준 분기 경쟁사 DDR5 공급 S^comp", 0, 10000),
    _a("comp_supply_lpddr", 50.0, "bit", "low", "기준 분기 경쟁사 LPDDR 공급 S^comp", 0, 10000),
    _a("comp_supply_growth", 0.02, "pct/q", "low", "경쟁사 공급 분기 증가율", -0.5, 1),
    # 계약
    _a("hbm_price_ratio", 4.0, "x", "low", "HBM 계약가 ÷ 기준 DDR5 bit당 가격 (절대 가격 비공개)", 0, 50),
]}


def load(path: Path = ASSUMPTIONS_YAML) -> dict[str, Assumption]:
    """토이 기본값 위에 data/assumptions.yaml을 덮어쓴 레지스트리."""
    reg = {k: Assumption(**v.to_dict()) for k, v in TOY_DEFAULTS.items()}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for key, spec in data.items():
            if key not in reg:
                raise KeyError(f"{path.name}: 모르는 가정 키 '{key}'")
            if isinstance(spec, dict):
                for f in ("value", "confidence", "sources", "note", "unit", "lo", "hi"):
                    if f in spec:
                        setattr(reg[key], "description" if f == "note" else f, spec[f])
            else:
                reg[key].value = float(spec)
    return reg


def version() -> str:
    """assumption_version: git 커밋 해시. git이 없으면 yaml 내용 해시."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%h", "--", "data/assumptions.yaml", "memsim/core/assumptions.py"],
            cwd=REPO, capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    text = ASSUMPTIONS_YAML.read_text(encoding="utf-8") if ASSUMPTIONS_YAML.exists() else "toy"
    return "sha:" + hashlib.sha1(text.encode()).hexdigest()[:8]
