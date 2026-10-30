"""코어의 공개 진입점. 노트북, API, (대안) Streamlit이 모두 run(scenario) → dict 를 호출한다."""
from __future__ import annotations

import hashlib
import json
import time

from memsim import MODEL_VERSION
from memsim.core import assumptions, optimizer, params, postprocess
from memsim.core.scenario import SCHEMA_VERSION, Scenario


def _as_scenario(scenario: Scenario | dict) -> Scenario:
    return scenario if isinstance(scenario, Scenario) else Scenario.model_validate(scenario)


def input_hash(sc: Scenario) -> str:
    return hashlib.sha1(json.dumps(sc.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()[:12]


def run(scenario: Scenario | dict, registry=None) -> dict:
    """R1~R6. 해가 없으면 status=infeasible과 diagnostics를 담아 돌려준다 (예외를 던지지 않음).

    R1 검증 실패는 pydantic.ValidationError, 가정 오류는 params.AssumptionError를 던진다.
    """
    t0 = time.perf_counter()
    sc = _as_scenario(scenario)
    res = params.build(sc, registry)
    sol = optimizer.solve(res.mi)
    diagnostics = None
    if sol.status == "infeasible":
        diagnostics = optimizer.diagnose(res.mi)
    body = postprocess.build(sc, res, sol)
    return {
        "scenario_id": sc.scenario_id,
        "meta": {
            "model_version": MODEL_VERSION,
            "schema_version": SCHEMA_VERSION,
            "assumption_version": assumptions.version(),
            "input_hash": input_hash(sc),
            "mode": sc.mode,
            "solver": sol.solver,
            "status": sol.status,
            "runtime_ms": round((time.perf_counter() - t0) * 1000, 2),
        },
        **body,
        "diagnostics": diagnostics,
    }


def compare(scenarios: list[Scenario | dict], baseline: int = 0) -> dict:
    """여러 시나리오를 실행하고 baseline 대비 누적 이익·분기 이익 차이를 붙인다."""
    results = [run(s) for s in scenarios]
    base = results[baseline]
    base_ok = base["meta"]["status"].startswith("optimal")
    for r in results:
        ok = base_ok and r["meta"]["status"].startswith("optimal")
        r["vs_baseline"] = None if not ok else {
            "baseline_id": base["scenario_id"],
            "cum_profit_idx_diff": round(r["summary"]["cum_profit_idx"] - base["summary"]["cum_profit_idx"], 4),
            "profit_by_quarter_idx_diff": [
                round(a - b, 4) for a, b in zip(r["summary"]["profit_by_quarter_idx"],
                                                base["summary"]["profit_by_quarter_idx"])
            ],
        }
    return {"baseline_id": base["scenario_id"], "results": results}
