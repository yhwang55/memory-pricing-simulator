"""FastAPI 서버 (설계 v3 8장). 코어를 감싸기만 하고 계산은 memsim.core가 한다.

실행:  uvicorn api.main:app --reload
문서:  http://127.0.0.1:8000/docs  (OpenAPI → 프론트는 openapi-typescript로 타입 생성)
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from memsim import MODEL_VERSION
from memsim.core import assumptions, sensitivity
from memsim.core.params import AssumptionError
from memsim.core.run import compare, run
from memsim.core.scenario import SCHEMA_VERSION, Scenario
from memsim.presets import load_all as load_presets

app = FastAPI(title="memsim API", version=MODEL_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("MEMSIM_CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class CompareRequest(BaseModel):
    scenarios: list[Scenario] = Field(min_length=1, max_length=6)
    baseline: int = Field(default=0, ge=0, description="scenarios 안에서 기준 시나리오의 위치")


class SensitivityRequest(BaseModel):
    scenario: Scenario
    top: int = Field(default=5, ge=1, le=30)
    delta_pct: float | None = Field(default=None, gt=0, le=90, description="null이면 신뢰도별 범위")


@lru_cache(maxsize=256)
def _cached_run(scenario_json: str, assumption_version: str) -> str:
    # 같은 (입력, 모델 버전, 가정 버전)이면 같은 결과 → 다시 계산하지 않는다
    return json.dumps(run(json.loads(scenario_json)), ensure_ascii=False)


def _run(sc: Scenario) -> dict:
    key = json.dumps(sc.model_dump(mode="json"), sort_keys=True)
    try:
        return json.loads(_cached_run(key, assumptions.version()))
    except AssumptionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/v1/meta")
def meta():
    return {"model_version": MODEL_VERSION, "schema_version": SCHEMA_VERSION,
            "assumption_version": assumptions.version()}


@app.post("/v1/runs")
def post_run(scenario: Scenario):
    return _run(scenario)


@app.post("/v1/compare")
def post_compare(req: CompareRequest):
    if req.baseline >= len(req.scenarios):
        raise HTTPException(status_code=422, detail="baseline 위치가 scenarios 길이를 넘습니다")
    try:
        return compare(req.scenarios, baseline=req.baseline)
    except AssumptionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@app.post("/v1/sensitivity")
def post_sensitivity(req: SensitivityRequest):
    try:
        return sensitivity.tornado(req.scenario, top=req.top, delta_pct=req.delta_pct)
    except AssumptionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@app.get("/v1/presets")
def get_presets():
    return load_presets()


@app.get("/v1/assumptions")
def get_assumptions():
    reg = assumptions.load()
    return {
        "assumption_version": assumptions.version(),
        "source": "data/assumptions.yaml" if assumptions.ASSUMPTIONS_YAML.exists() else "toy_defaults",
        "items": [a.to_dict() for a in reg.values()],
    }
