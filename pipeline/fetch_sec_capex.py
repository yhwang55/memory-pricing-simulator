"""
하이퍼스케일러 4사(마이크로소프트, 알파벳, 아마존, 메타)의 분기 설비투자(capex)와
마이크론 분기 매출총이익률을
SEC XBRL API에서 받아 CSV로 저장한다. API 키는 필요 없다.

사용법
  export SEC_UA="Yoon Hwang your_email@example.com"   # SEC가 요구하는 User-Agent (이름 + 이메일)
  python fetch_sec_capex.py

결과: 16_hyperscaler_capex_quarterly.csv, 18_micron_gross_margin_quarterly.csv
  현금흐름표 값은 회계연도 초부터의 누적값이라, 같은 회계연도 안에서 앞 분기를 빼서 분기값을 만든다.
"""
import os
import sys
import time

import pandas as pd
import requests
from pathlib import Path

os.chdir(Path(__file__).resolve().parents[1] / "data" / "raw")  # 결과는 data/raw에 저장

UA = os.getenv("SEC_UA")
if not UA:
    sys.exit("SEC_UA 환경변수에 '이름 이메일'을 넣어주세요.")

COMPANIES = {
    "Microsoft": "0000789019",
    "Alphabet": "0001652044",
    "Amazon": "0001018724",
    "Meta": "0001326801",
}
# 회사마다 capex를 다른 태그로 신고할 수 있어 순서대로 시도한다
TAGS = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]


def fetch(cik, tag):
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    if r.status_code != 200:
        return None
    return r.json()["units"].get("USD")


rows = []
for name, cik in COMPANIES.items():
    # 회사마다 연도별로 쓰는 항목 이름이 다를 수 있어 모든 후보를 받아 합친다
    frames = []
    for priority, tag in enumerate(TAGS):
        facts = fetch(cik, tag)
        time.sleep(0.2)  # SEC 요청 제한(초당 10건) 준수
        if facts:
            f = pd.DataFrame(facts)
            f["tag"], f["priority"] = tag, priority
            frames.append(f)
    if not frames:
        print(f"[{name}] capex 태그를 찾지 못함")
        continue
    df = pd.concat(frames, ignore_index=True)
    df = df[df.form.isin(["10-Q", "10-K"]) & df.start.notna()]
    df["start"] = pd.to_datetime(df.start)
    df["end"] = pd.to_datetime(df.end)
    # 같은 기간이 여러 번 신고되면: 같은 항목끼리는 가장 최근 신고값(정정 반영),
    # 항목이 다르면 TAGS 앞쪽 항목을 우선
    df = df.sort_values(["priority", "filed"], ascending=[False, True])
    df = df.drop_duplicates(["start", "end"], keep="last")
    df = df[df.end >= "2019-01-01"]

    n_before = len(rows)
    for start, g in df.groupby("start"):
        g = g.sort_values("end")
        prev = 0.0
        for _, r in g.iterrows():
            days = (r.end - start).days
            months = round(days / 30.4)
            if months not in (3, 6, 9, 12):
                continue
            q_val = r.val - prev if months > 3 else r.val
            prev = r.val
            rows.append({"company": name, "quarter_end": r.end.date(), "capex_usd_bn": round(q_val / 1e9, 2),
                         "ytd_months": months, "form": r.form, "tag": r.tag})
    got = len({x["quarter_end"] for x in rows[n_before:]})
    print(f"[{name}] 완료: {got}개 분기" + ("  <- 분기 수가 적음, 확인 필요" if got < 28 else ""))

out = pd.DataFrame(rows).drop_duplicates(["company", "quarter_end"], keep="last").sort_values(["company", "quarter_end"])
out["calendar_quarter"] = pd.to_datetime(out.quarter_end).dt.to_period("Q").astype(str)
out.to_csv("16_hyperscaler_capex_quarterly.csv", index=False)
print(f"{len(out)}행 저장. 값은 현금 설비투자(금융리스 제외)라 회사 발표 capex보다 작을 수 있음. 마이크로소프트는 2026년 리스 회계 변경에 주의.")


# ---------------------------------------------------------------- 마이크론 분기 매출총이익률
# 손익계산서 값은 10-Q에 3개월 값이 따로 있어서 약 90일짜리 기간만 쓰고,
# 4분기(10-K)는 연간에서 1~3분기를 빼서 만든다.
def quarterly_flow(cik, tags):
    for tag in tags:
        facts = fetch(cik, tag)
        time.sleep(0.2)
        if facts:
            break
    if not facts:
        return None
    df = pd.DataFrame(facts)
    df = df[df.form.isin(["10-Q", "10-K"]) & df.start.notna()]
    df["start"] = pd.to_datetime(df.start)
    df["end"] = pd.to_datetime(df.end)
    df = df.sort_values("filed").drop_duplicates(["start", "end"], keep="last")
    df["days"] = (df.end - df.start).dt.days
    q = df[df.days.between(80, 100)].set_index("end").val
    annual = df[df.days.between(350, 380)]
    for _, a in annual.iterrows():
        inside = q[(q.index > a.start) & (q.index < a.end)]
        if len(inside) == 3 and a.end not in q.index:
            q.loc[a.end] = a.val - inside.sum()
    return q.sort_index()


MICRON = "0000723125"
rev = quarterly_flow(MICRON, ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"])
gp = quarterly_flow(MICRON, ["GrossProfit"])
if rev is not None and gp is not None:
    gm = pd.DataFrame({"revenue_usd_bn": (rev / 1e9).round(2), "gross_profit_usd_bn": (gp / 1e9).round(2)}).dropna()
    gm["gross_margin_pct"] = (gm.gross_profit_usd_bn / gm.revenue_usd_bn * 100).round(1)
    gm = gm[gm.index >= "2019-01-01"]
    gm.index.name = "fiscal_quarter_end"
    gm.to_csv("18_micron_gross_margin_quarterly.csv")
    print(f"[Micron] 매출총이익률 {len(gm)}개 분기 저장 (GAAP 기준)")
else:
    print("[Micron] 매출 또는 매출총이익 태그를 찾지 못함")
