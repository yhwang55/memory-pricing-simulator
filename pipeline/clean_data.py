"""data/raw의 원본 CSV를 정리해 data/series에 모델용 데이터셋을 만든다."""
import pandas as pd, numpy as np, os
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
os.chdir(DATA / "raw")  # 원본은 data/raw에서 읽는다
os.makedirs("../series", exist_ok=True)  # 정리본은 data/series에 쓴다

# ---------- ECOS: 월마다 값 2개(계약통화 기준, 원화 기준). 순서는 계약통화가 먼저.
e = pd.read_csv("10_ecos_dram_export_price_index.csv")
e = e.drop_duplicates(["month", "value"])
rows = []
for m, g in e.groupby("month", sort=True):
    v = g["value"].tolist()
    rows.append({"month": pd.to_datetime(str(m), format="%Y%m"), "dram_px_contract_ccy": v[0], "dram_px_krw": v[1]})
ecos = pd.DataFrame(rows)
# 검증용: 원화지수/계약통화지수 x 2020년 평균환율(약 1,180원)은 그 달 환율과 비슷해야 한다
ecos["implied_krw_per_usd"] = (ecos.dram_px_krw / ecos.dram_px_contract_ccy * 1180).round(0)
ecos.to_csv("../series/13_ecos_dram_export_price_monthly.csv", index=False)

# ---------- DART: 1Q·2Q·3Q는 분기값, 사업보고서는 연간값 -> 4Q = 연간 - (1Q+2Q+3Q)
d = pd.read_csv("11_dart_samsung_skhynix_financials.csv")
d["amt"] = d.thstrm_amount_krw.str.replace(",", "").astype(float) / 1e12
d["q"] = d.report.str[:2]
w = d.pivot_table(index=["company", "year", "account"], columns="q", values="amt").reset_index()
w["4Q"] = w["4Q"] - w[["1Q", "2Q", "3Q"]].sum(axis=1, min_count=3)
long = w.melt(id_vars=["company", "year", "account"], value_vars=["1Q", "2Q", "3Q", "4Q"], var_name="q", value_name="krw_tn").dropna()
dq = long.pivot_table(index=["company", "year", "q"], columns="account", values="krw_tn").reset_index()
dq = dq.rename(columns={"매출액": "revenue_krw_tn", "영업이익": "op_income_krw_tn"})
dq["quarter"] = dq.q.str[0] + "Q" + dq.year.astype(str).str[2:]
dq["period"] = pd.PeriodIndex(dq.year.astype(str) + "Q" + dq.q.str[0], freq="Q")
dq["op_margin_pct"] = (dq.op_income_krw_tn / dq.revenue_krw_tn * 100).round(1)
dq = dq.sort_values(["company", "period"])[["company", "period", "quarter", "revenue_krw_tn", "op_income_krw_tn", "op_margin_pct"]]
dq[["revenue_krw_tn", "op_income_krw_tn"]] = dq[["revenue_krw_tn", "op_income_krw_tn"]].round(2)
dq.to_csv("../series/14_dart_quarterly_financials.csv", index=False)

# ---------- 관세청: '총계' 행 제거, 품목을 그룹으로 묶어 월x국가 합산 (단위: 백만 달러)
c = pd.read_csv("12_customs_memory_exports_by_country.csv", dtype={"hsCd": str})
c = c[c.hsCd != "-"].copy()
c["month"] = pd.to_datetime(c.year.str.replace(".", "-", regex=False) + "-01")
grp = {"8542321010": "dram", "8542321030": "flash", "8542323000": "multichip_mcp"}
fallback = pd.Series(np.where(c.hsCd.str.startswith("85423240"), "mco", "other"), index=c.index)
c["group"] = c.hsCd.map(grp).fillna(fallback)
cx = c.pivot_table(index=["month", "country"], columns="group", values="expDlr", aggfunc="sum", fill_value=0) / 1e6
cx["total_memory"] = cx.sum(axis=1)
cx = cx.round(1).reset_index()
cx.to_csv("../series/15_customs_memory_exports_monthly_by_country.csv", index=False)
tot = cx.drop(columns="country").groupby("month").sum().reset_index()

# ---------- 월별 패널
ppi = pd.read_csv("01_fred_semis_ppi_monthly.csv", parse_dates=["date"]).rename(columns={"date": "month"})
ip = pd.read_csv("02_fred_semis_industrial_production_monthly.csv", parse_dates=["date"]).rename(columns={"date": "month"})
mp = ecos[["month", "dram_px_contract_ccy", "dram_px_krw"]].merge(
    tot.rename(columns=lambda x: x if x == "month" else f"exp_{x}_usd_mn"), on="month", how="outer"
).merge(ppi, on="month", how="left").merge(ip, on="month", how="left").sort_values("month")
# 수출액 / 가격지수 = 물량 근사 지수 (2020년 평균 = 100)
vol = mp.exp_dram_usd_mn / mp.dram_px_contract_ccy
mp["dram_volume_proxy"] = (vol / vol[mp.month.dt.year == 2020].mean() * 100).round(1)
mp.to_csv("../series/20_monthly_panel.csv", index=False)

# ---------- 분기 패널
mp["period"] = mp.month.dt.to_period("Q")
qp = mp.groupby("period").agg(
    dram_px_contract_ccy=("dram_px_contract_ccy", "mean"),
    exp_dram_usd_mn=("exp_dram_usd_mn", "sum"),
    exp_total_memory_usd_mn=("exp_total_memory_usd_mn", "sum"),
    dram_volume_proxy=("dram_volume_proxy", "mean"),
    n_months=("month", "count"),
).round(2)
for name, tag in [("삼성전자", "sec"), ("SK하이닉스", "hynix")]:
    s = dq[dq.company == name].set_index("period")[["revenue_krw_tn", "op_margin_pct"]]
    qp = qp.join(s.add_prefix(f"{tag}_"))
tf = pd.read_csv("03_dram_supplier_revenue_share_quarterly.csv")
tf = tf[tf.supplier == "Industry total"].copy()
tf["period"] = pd.PeriodIndex("20" + tf.quarter.str[2:] + "Q" + tf.quarter.str[0], freq="Q")
qp = qp.join(tf.set_index("period")["dram_revenue_usd_bn"].rename("industry_dram_rev_usd_bn"))
qp = qp.reset_index()
qp["quarter"] = qp.period.dt.quarter.astype(str) + "Q" + qp.period.dt.year.astype(str).str[2:]
qp.to_csv("../series/21_quarterly_panel.csv", index=False)
print("done")
