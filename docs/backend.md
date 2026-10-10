# 백엔드 (memsim 코어 + API) — v0

담당: 김동호. 설계 v3의 실행 파이프라인(R1~R6), M2·M4·M5, API를 구현한다.
**지금 숫자는 모두 토이 가정값**이라 실제 시장을 나타내지 않는다. 데이터 담당이 `data/assumptions.yaml`을 만들면 그 값으로 바뀐다.

## 실행

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pytest -q                          # 또는 make test
uvicorn api.main:app --reload      # 또는 make api → http://127.0.0.1:8000/docs
```

Python 3.10 이상 (3.12 권장).

## 구조

```
memsim/core/
  scenario.py     R1  시나리오 스키마 (Pydantic, schema_version 3.0), 충격 펼치기 (step/ramp/pulse)
  assumptions.py  R2  가정 레지스트리: 토이 기본값 → data/assumptions.yaml 덮어쓰기, 신뢰도·출처
  params.py       R2·R3  Scenario → ModelInput (기본값 → yaml → overrides → contracts 순)
  demand.py       M1 v0  세그먼트 충격 → HBM 배정 D^C, DDR5/LPDDR 수요 배수   ← 데이터 담당이 이어받음
  supply.py       M2     W, g, c, R, K, 기준 배분 x0
  market.py       M3 v0  잔여 수요 a, b 보정, 경쟁사 공급 경로              ← 데이터 담당이 이어받음
  optimizer.py    M4 + R4·R5  cvxpy 볼록 QP (DPP, Clarabel), 해가 없을 때 원인 그룹 진단
  policies.py     정책 → 선형 상·하한 (price_floor, share_floor, fixed_mix)
  postprocess.py  R6  지수화, 웨이퍼 쌍대값, 병목 제약, KPI, 경고
  sensitivity.py  M5 v0  하나씩 흔들기 토네이도 (신뢰도별 ±10/25/50%)
  run.py          run(scenario) → dict, compare([...])
memsim/presets/   Q1~Q4 프리셋 초안 (JSON)
api/main.py       FastAPI: /v1/runs, /v1/compare, /v1/sensitivity, /v1/presets, /v1/assumptions, /v1/meta
tests/            L1 불변식, 단조성 3종, L2 정답 시나리오, 스키마, API
```

노트북에서 쓰기:

```python
from memsim.core.run import run, compare
r = run({"scenario_id": "ai_up", "shocks": [{"type": "demand", "segment": "ai_server", "start_q": 3, "change_pct": 20}]})
r["summary"], r["rows"][:3]
```

## 지수 정의 (R6)

| 필드 | 정의 |
|---|---|
| price_idx | bit당 가격 ÷ 기준 분기 DDR5 bit당 가격 × 100 |
| bits_idx, sales_idx, inventory_idx | bit ÷ 기준 분기 자사 bit 합 × 100 |
| profit_idx | 분기 이익 ÷ (기준 DDR5 가격 × 기준 자사 bit 합) × 100, 할인 전 |
| shadow_prices.wafer | 그 분기에 웨이퍼 1장을 더 얻었을 때 profit_idx 증가분 (할인 전) |
| summary.npv_profit_idx | 할인 후 누적 이익 지수 (최적화 목적값) |

q1 = 기준 분기(base_quarter). 해가 없어도 HTTP 200 + `meta.status = "infeasible"` + `diagnostics.cause_groups`로 돌려준다. 스키마 오류와 모르는 가정 키는 422.

## 팀 확인이 필요한 것

1. **전환 속도 제약을 설계에서 조금 바꿨다.** 설계의 |x_t − x_{t−1}| ≤ R 그대로면 웨이퍼 캐파 −20% 같은 충격만으로도 해가 없어진다. 그래서 감소 쪽 한도에 캐파 감소분을 더했다: x_{t−1} − x_t ≤ R + max(0, W_{t−1} − W_t). 증가 쪽은 설계와 같다.
2. **시나리오에서 뺀 제품의 웨이퍼는 다른 제품에 다시 나누지 않는다.** 전환 속도만큼씩 옮겨간다.
3. **충격 type은 5개다.** `demand`(segment: ai_server / general_server / pc / mobile), `competitor_capacity`, `hbm_contract_price`, `wafer_capacity`, `hbm_backend_capacity`. DDR5 수요는 AI 서버 30% / PC 20% / 일반 서버 50%로 나눈다(가정, 신뢰도 low).
4. **market_only 모드 v0**은 기준 분기 웨이퍼 비중을 고정한 결과다. 과거 공급 경로를 넣는 백테스트 입력은 W7에 붙인다.
5. **불변식 테스트는 hypothesis 대신 시드를 고정한 무작위 시나리오 20개**로 돌린다. 의존성을 줄이려는 선택이고, 필요하면 바꾼다.
6. **프리셋 Q1~Q4는 초안이다.** Q3의 "전환" 정의는 W1 결정 사항 ④.

## 데이터 담당과의 연결부

- `data/assumptions.yaml`: 키는 `memsim/core/assumptions.py`의 `TOY_DEFAULTS`와 같아야 한다. 형식은 그 파일 docstring에 있다. 모르는 키가 있으면 로드할 때 오류가 난다.
- `demand.py`, `market.py`: M1·M3 v0 자리표시다. 함수 시그니처(`build(...) -> dict`)만 유지하면 안쪽은 마음대로 바꿔도 된다.
