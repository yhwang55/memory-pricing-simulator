"""
API 키가 필요한 데이터 3종을 받아 CSV로 저장한다.
  1) 한국은행 ECOS: D램 수출물가지수 (월별)
  2) OpenDART: 삼성전자, SK하이닉스 분기 재무 (매출, 영업이익)
  3) 관세청(공공데이터포털): 메모리 반도체 수출액 (HS 854232, 월별)

사용법
  pip install requests pandas
  export ECOS_KEY=...     # https://ecos.bok.or.kr/api/ 에서 발급
  export DART_KEY=...     # https://opendart.fss.or.kr 에서 발급
  export DATA_GO_KEY=...  # https://www.data.go.kr 에서 '관세청_품목별 국가별 수출입실적(GW)' 활용신청
  python fetch_keyed_data.py

키가 없는 소스는 건너뛴다.
"""
import os
import sys
import time
import xml.etree.ElementTree as ET

import pandas as pd
import requests

OUT = os.path.dirname(os.path.abspath(__file__))
START_YM, END_YM = "201901", "202608"


# ---------------------------------------------------------------- ECOS
def ecos():
    key = os.getenv("ECOS_KEY")
    if not key:
        print("[ECOS] ECOS_KEY 없음, 건너뜀")
        return
    base = f"https://ecos.bok.or.kr/api"

    # 1) '수출물가지수' 통계표 찾기 (표 코드를 하드코딩하지 않고 목록에서 검색)
    r = requests.get(f"{base}/StatisticTableList/{key}/json/kr/1/2000", timeout=30).json()
    tables = r.get("StatisticTableList", {}).get("row", [])
    cands = [t for t in tables if "수출물가지수" in t.get("STAT_NAME", "") and t.get("SRCH_YN") == "Y"]
    if not cands:
        print("[ECOS] 수출물가지수 표를 찾지 못함")
        return
    print("[ECOS] 후보 표:", [(t["STAT_CODE"], t["STAT_NAME"]) for t in cands])

    rows = []
    for t in cands:
        code = t["STAT_CODE"]
        items = requests.get(f"{base}/StatisticItemList/{key}/json/kr/1/5000/{code}", timeout=30).json()
        items = items.get("StatisticItemList", {}).get("row", [])
        hits = [i for i in items if "D램" in i.get("ITEM_NAME", "") or "DRAM" in i.get("ITEM_NAME", "").upper()]
        for it in hits:
            url = f"{base}/StatisticSearch/{key}/json/kr/1/1000/{code}/M/{START_YM}/{END_YM}/{it['ITEM_CODE']}"
            data = requests.get(url, timeout=30).json().get("StatisticSearch", {}).get("row", [])
            for d in data:
                rows.append({
                    "stat_code": code, "stat_name": t["STAT_NAME"],
                    "item_code": it["ITEM_CODE"], "item_name": d.get("ITEM_NAME1"),
                    "month": d.get("TIME"), "value": d.get("DATA_VALUE"), "unit": d.get("UNIT_NAME"),
                })
            time.sleep(0.2)
    if rows:
        pd.DataFrame(rows).to_csv(f"{OUT}/10_ecos_dram_export_price_index.csv", index=False)
        print(f"[ECOS] {len(rows)}행 저장")
    else:
        print("[ECOS] D램 품목을 찾지 못함. 후보 표의 품목 목록을 직접 확인하세요.")


# ---------------------------------------------------------------- OpenDART
CORPS = {"삼성전자": "00126380", "SK하이닉스": "00164779"}
REPORTS = {"11013": "1Q", "11012": "2Q(반기)", "11014": "3Q", "11011": "4Q(사업)"}
ACCOUNTS = {"매출액", "영업이익", "당기순이익"}


def dart():
    key = os.getenv("DART_KEY")
    if not key:
        print("[DART] DART_KEY 없음, 건너뜀")
        return
    rows = []
    for name, corp in CORPS.items():
        for year in range(2019, 2027):
            for rc, label in REPORTS.items():
                p = dict(crtfc_key=key, corp_code=corp, bsns_year=str(year), reprt_code=rc)
                j = requests.get("https://opendart.fss.or.kr/api/fnlttSinglAcnt.json", params=p, timeout=30).json()
                if j.get("status") != "000":
                    continue
                for a in j.get("list", []):
                    if a.get("fs_div") == "CFS" and a.get("account_nm") in ACCOUNTS:
                        rows.append({
                            "company": name, "year": year, "report": label,
                            "account": a["account_nm"],
                            "thstrm_amount_krw": a.get("thstrm_amount"),
                            "note": "반기/3분기/사업보고서 금액은 누적일 수 있음. 분기값은 차감해서 계산",
                        })
                time.sleep(0.15)
    pd.DataFrame(rows).to_csv(f"{OUT}/11_dart_samsung_skhynix_financials.csv", index=False)
    print(f"[DART] {len(rows)}행 저장")


# ---------------------------------------------------------------- 관세청
# 엔드포인트는 공공데이터포털 활용신청 후 '상세기능'에 표시되는 주소로 확인하세요.
CUSTOMS_URL = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"  # 확인 필요
HS = "854232"                        # 메모리 (HS 8542.32)
COUNTRIES = ["CN", "TW", "VN", "US", "HK", "JP", "SG", "MY", "PH"]  # 주요 목적지


def customs():
    key = os.getenv("DATA_GO_KEY")
    if not key:
        print("[관세청] DATA_GO_KEY 없음, 건너뜀")
        return
    rows = []
    # API는 한 번에 1년 이내만 조회 가능
    for y in range(2019, 2027):
        s, e = f"{y}01", (f"{y}12" if y < 2026 else END_YM)
        for c in COUNTRIES:
            p = dict(serviceKey=key, strtYymm=s, endYymm=e, hsSgn=HS, cntyCd=c)
            r = requests.get(CUSTOMS_URL, params=p, timeout=30)
            try:
                root = ET.fromstring(r.content)
            except ET.ParseError:
                print("[관세청] 응답 파싱 실패:", r.text[:200])
                return
            for it in root.iter("item"):
                rec = {ch.tag: ch.text for ch in it}
                rec["country"] = c
                rows.append(rec)
            time.sleep(0.2)
    pd.DataFrame(rows).to_csv(f"{OUT}/12_customs_memory_exports_by_country.csv", index=False)
    print(f"[관세청] {len(rows)}행 저장")


if __name__ == "__main__":
    for fn in (ecos, dart, customs):
        try:
            fn()
        except Exception as ex:  # 한 소스가 실패해도 나머지는 진행
            print(f"[{fn.__name__}] 오류: {ex}", file=sys.stderr)
