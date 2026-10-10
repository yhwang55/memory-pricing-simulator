"""API 계약 테스트 (FastAPI TestClient)."""
import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_meta():
    r = client.get("/v1/meta")
    assert r.status_code == 200 and r.json()["schema_version"] == "3.0"


def test_run_shape():
    r = client.post("/v1/runs", json={"scenario_id": "base"})
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["status"] == "optimal"
    assert len(body["rows"]) == 12 * 3
    assert {"q", "quarter", "product", "wafer_share", "bits_idx", "sales_idx", "inventory_idx",
            "price_idx", "profit_idx"} <= set(body["rows"][0])
    assert len(body["shadow_prices"]["wafer"]) == 12
    assert {"cum_profit_idx", "recommended_mix", "avg_hbm_wafer_share"} <= set(body["summary"])


def test_run_cached_same_answer():
    a = client.post("/v1/runs", json={"scenario_id": "base"}).json()
    b = client.post("/v1/runs", json={"scenario_id": "base"}).json()
    assert a["summary"] == b["summary"]


@pytest.mark.parametrize("payload", [
    {"scenario_id": "x", "bogus": 1},
    {"scenario_id": "x", "assumption_overrides": {"no_such_key": 1}},
    {"scenario_id": "x", "mode": "evaluate"},
])
def test_run_422(payload):
    assert client.post("/v1/runs", json=payload).status_code == 422


def test_infeasible_returns_200_with_diagnostics():
    r = client.post("/v1/runs", json={"scenario_id": "sf", "mode": "evaluate",
                                      "policy": {"type": "share_floor", "product": "DDR5", "theta": 0.4}})
    assert r.status_code == 200
    assert r.json()["meta"]["status"] == "infeasible" and r.json()["diagnostics"]["cause_groups"]


def test_compare():
    r = client.post("/v1/compare", json={"scenarios": [
        {"scenario_id": "base"},
        {"scenario_id": "ai", "shocks": [{"type": "demand", "segment": "ai_server", "start_q": 3, "change_pct": 20}]},
    ]})
    assert r.status_code == 200
    res = r.json()["results"]
    assert res[0]["vs_baseline"]["cum_profit_idx_diff"] == 0
    assert len(res[1]["vs_baseline"]["profit_by_quarter_idx_diff"]) == 12


def test_sensitivity():
    r = client.post("/v1/sensitivity", json={"scenario": {"scenario_id": "base"}, "top": 5})
    assert r.status_code == 200 and len(r.json()["items"]) == 5


def test_presets_and_assumptions():
    presets = client.get("/v1/presets").json()
    assert {p["preset_id"] for p in presets} >= {"q1_ai_server_up_20", "q4_demand_down_lta"}
    for p in presets:
        assert client.post("/v1/runs", json=p["scenario"]).json()["meta"]["status"] == "optimal"
    items = client.get("/v1/assumptions").json()["items"]
    assert all(i["confidence"] in ("high", "medium", "low") for i in items)
