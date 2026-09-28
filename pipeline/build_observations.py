"""
설계 D1 단계: data/raw, data/series의 파일을 긴 형식 두 개로 변환한다.

  data/sources.csv       출처 목록 (source_id, publisher, title, url, published, accessed, tier)
  data/observations.csv  값 하나당 한 줄 (period, metric, product, player, value_lo/hi, unit, kind, source_id, quote ...)
  data/range_rules.csv   문장형 범위("low 60s" 등)를 구간으로 바꾸는 팀 규칙

사용법:  python pipeline/build_observations.py
마지막에 스키마 검사를 하고, 실패하면 오류로 끝난다.
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"
RAW, SERIES = DATA / "raw", DATA / "series"
ACC1, ACC2 = "2026-09-26", "2026-09-27"  # 열람일

# ======================================================================
# 1. 출처 목록
# ======================================================================
TF = "https://www.trendforce.com/presscenter/news/"
TF_RELEASES = {  # source_id: (published, url 뒷부분, 제목)
    "TF-20221116": ("2022-11-16", "20221116-11459.html", "Global DRAM Revenue for 3Q22 Showed QoQ Drop of Almost 30%"),
    "TF-20230109": ("2023-01-09", "20230109-11533.html", "QoQ Decline in DRAM ASP Will Moderate to Around 13~18% for 1Q23"),
    "TF-20230220": ("2023-02-20", "20230220-11572.html", "Server DRAM Will Overtake Mobile DRAM in Supply in 2023"),
    "TF-20230302": ("2023-03-02", "20230302-11588.html", "Global DRAM Revenue Fell by More Than 30% for 4Q22"),
    "TF-20230328": ("2023-03-28", "20230328-11626.html", "Decline in DRAM ASP Narrows to 10~15% in 2Q23"),
    "TF-20230705": ("2023-07-05", "20230705-11743.html", "DRAM ASP Decline Narrows to 0~5% for 3Q23"),
    "TF-20230824": ("2023-08-24", "20230824-11805.html", "Q2 DRAM Industry Revenue Rebounds with a 20.4% Quarterly Increase"),
    "TF-20231204": ("2023-12-04", "20231204-11942.html", "Contract Prices Bottom Out in Q3, Boosting DRAM Revenue by Nearly 20%"),
    "TF-20240205": ("2024-02-05", "20240205-12021.html", "Server DRAM 2024 Content per Box +17.3%"),
    "TF-20240305": ("2024-03-05", "20240305-12060.html", "DRAM Industry Sees Nearly 30% Revenue Growth in 4Q23"),
    "TF-20240613": ("2024-06-13", "20240613-12188.html", "Contract Price Increases Offset Seasonal Slump, Boosting DRAM Q1 Revenue by 5.1%"),
    "TF-20240815": ("2024-08-15", "20240815-12254.html", "DRAM Industry Revenue Surges 24.8% in 2Q24"),
    "TF-20241126": ("2024-11-26", "20241126-12380.html", "Server DRAM and HBM Boost 3Q24 DRAM Industry Revenue by 13.6% QoQ"),
    "TF-20250227": ("2025-02-27", "20250227-12492.html", "4Q24 DRAM Industry Revenue Increases by 9.9% QoQ"),
    "TF-20250603": ("2025-06-03", "20250603-12603.html", "DRAM Revenue Drops 5.5% in the First Quarter of 2025"),
    "TF-20250902": ("2025-09-02", "20250902-12694.html", "2Q25 DRAM Revenue Jumps 17.1%"),
    "TF-20250924": ("2025-09-24", "20250924-12733.html", "DRAM Prices to Continue Rising in 4Q25"),
    "TF-20251113": ("2025-11-13", "20251113-12780.html", "Memory Industry to Maintain Cautious CapEx in 2026"),
    "TF-20251117": ("2025-11-17", "20251117-12784.html", "Rising Memory Prices Weigh on Consumer Markets; 2026 Outlook Revised Downward"),
    "TF-20251126": ("2025-11-26", "20251126-12802.html", "Global DRAM Revenue Jumps 30.9% in 3Q25"),
    "TF-20251218": ("2025-12-18", "20251218-12843.html", "Higher DDR5 Profitability Strengthening HBM3e Pricing Momentum in 2026"),
    "TF-20260105": ("2026-01-05", "20260105-12860.html", "Memory Makers Prioritize Server Applications in 1Q26"),
    "TF-20260202": ("2026-02-02", "20260202-12911.html", "Memory Price Outlook for 1Q26 Sharply Upgraded"),
    "TF-20260226": ("2026-02-26", "20260226-12937.html", "Price Rally Drives 4Q25 DRAM Revenue Up 29.4%"),
    "TF-20260331": ("2026-03-31", "20260331-12995.html", "AI Server Demand to Drive Memory Contract Price Increases in 2Q26"),
    "TF-20260601": ("2026-06-01", "20260601-13070.html", "Rapid Contract Price Surge Drives 1Q26 DRAM Industry Up 81% QoQ"),
    "TF-20260602": ("2026-06-02", "20260602-13074.html", "Tight DRAM Supply Gives Suppliers Greater Pricing Power in HBM"),
    "TF-20260703": ("2026-07-03", "20260703-13134.html", "AI Server Demand Continues to Support Memory Prices in 3Q26"),
    "TF-20260709": ("2026-07-09", "20260709-13140.html", "Server DRAM Contract Prices Expected to Rise 13-18% QoQ in 3Q26"),
    "TF-20260730": ("2026-07-30", "20260730-13158.html", "Diverging Memory Market Outlook in 2027"),
    "TF-20260907": ("2026-09-07", "20260907-13219.html", "DRAM Industry Revenue Rises 59.5% QoQ in 2Q26"),
}
MU = "https://investors.micron.com/static-files/"
MU_SOURCES = {  # fiscal_quarter: (source_id, publisher, url, published, tier)
    "FQ1-22": ("MU-FQ1-22", "MarketBeat (transcript)", "https://www.marketbeat.com/earnings/reports/2021-12-20-micron-technology-inc-stock", "2021-12-20", "secondary"),
    "FQ2-22": ("MU-FQ2-22", "MarketBeat (transcript)", "https://www.marketbeat.com/earnings/reports/2022-3-29-micron-technology-inc-stock", "2022-03-29", "secondary"),
    "FQ3-22": ("MU-FQ3-22", "MarketBeat (transcript)", "https://www.marketbeat.com/earnings/transcripts/76332", "2022-06-30", "secondary"),
    "FQ4-22": ("MU-FQ4-22", "MarketBeat (transcript)", "https://www.marketbeat.com/earnings/transcripts/80054", "2022-09-29", "secondary"),
    "FQ1-23": ("MU-FQ1-23", "MarketBeat (transcript)", "https://www.marketbeat.com/earnings/transcripts/84325", "2022-12-21", "secondary"),
    "FQ2-23": ("MU-FQ2-23", "Yahoo Finance (transcript)", "https://finance.yahoo.com/news/micron-technology-inc-nasdaq-mu-100813695.html", "2023-03-28", "secondary"),
    "FQ3-23": ("MU-FQ3-23", "Micron (prepared remarks)", MU + "5d57ee3a-72f3-40f2-99e5-51322403192b", "2023-06-28", "primary"),
    "FQ4-23": ("MU-FQ4-23", "MarketBeat (transcript)", "https://www.marketbeat.com/earnings/reports/2023-9-27-micron-technology-inc-stock", "2023-09-27", "secondary"),
    "FQ1-24": ("MU-FQ1-24", "Yahoo Finance (transcript)", "https://finance.yahoo.com/news/micron-technology-inc-nasdaq-mu-140047727.html", "2023-12-20", "secondary"),
    "FQ2-24": ("MU-FQ2-24", "Yahoo Finance (transcript)", "https://finance.yahoo.com/news/micron-technology-inc-nasdaq-mu-151930165.html", "2024-03-20", "secondary"),
    "FQ3-24": ("MU-FQ3-24", "Micron (prepared remarks)", MU + "4550f98c-1054-4847-a929-c17d520a0564", "2024-06-26", "primary"),
    "FQ4-24": ("MU-FQ4-24", "Motley Fool (transcript)", "https://www.fool.com/earnings/call-transcripts/2024/10/10/micron-technology-mu-q4-2024-earnings-call-transcr/", "2024-09-25", "secondary"),
    "FQ1-25": ("MU-FQ1-25", "Motley Fool (transcript)", "https://www.fool.com/earnings/call-transcripts/2024/12/18/micron-technology-mu-q1-2025-earnings-call-transcr/", "2024-12-18", "secondary"),
    "FQ2-25": ("MU-FQ2-25", "Motley Fool (transcript)", "https://www.fool.com/earnings/call-transcripts/2025/03/20/micron-technology-mu-q2-2025-earnings-call-transcr/", "2025-03-20", "secondary"),
    "FQ3-25": ("MU-FQ3-25", "Micron (prepared remarks)", MU + "39bb28c4-dd18-4097-a1fe-e5eb4956bcfc", "2025-06-25", "primary"),
    "FQ4-25": ("MU-FQ4-25", "Micron (prepared remarks)", "https://s25.q4cdn.com/621799436/files/doc_financials/2025/q4/Q4-2025-Prepared-Remarks-1.pdf", "2025-09-23", "primary"),
    "FQ1-26": ("MU-FQ1-26", "Micron (prepared remarks)", "https://s25.q4cdn.com/621799436/files/doc_financials/2026/q1/Micron_Q1-2026-Prepared-Remarks.pdf", "2025-12-17", "primary"),
    "FQ2-26": ("MU-FQ2-26", "Micron (prepared remarks)", "https://s25.q4cdn.com/621799436/files/doc_financials/2026/q2/Q2-2026-Prepared-Remarks.pdf", "2026-03-18", "primary"),
    "FQ3-26": ("MU-FQ3-26", "Micron (prepared remarks)", "https://s25.q4cdn.com/621799436/files/doc_events/2026/06/Q3-FY26-Prepared-Remarks.pdf", "2026-06-24", "primary"),
}
AS = "https://www.alphaspread.com/security/krx/000660/investor-relations/earnings-call/"
HX_SOURCES = {q: (f"SKH-{q}", "Alpha Spread (transcript)", AS + f"q{q[0]}-20{q[2:]}", "", "secondary")
              for q in ["2Q23", "3Q23", "4Q23", "1Q24", "2Q24", "3Q24", "4Q24", "1Q25", "2Q25", "3Q25", "4Q25"]}
HX_SOURCES.update({
    "1Q26": ("SKH-1Q26", "Silicon Analysts (call review)", "https://siliconanalysts.com/analysis/sk-hynix-1q26-the-mix-cycle", "2026-04-23", "secondary"),
    "2Q26": ("SKH-2Q26", "Yahoo Finance (transcript)", "https://finance.yahoo.com/quote/SKHY/earnings/SKHY-Q2-2026-earnings_call-653208.html", "2026-07-28", "secondary"),
    "3Q26 guidance": ("SKH-2Q26-SUMMARY", "BigGo Finance (call summary)", "https://finance.biggo.com/quote/000660.KS/earnings-call/KR_000660.KS_2026-07-28", "2026-07-28", "secondary"),
})
OTHER = [  # source_id, publisher, title, url, published, tier
    ("FRED-PCU33443344", "U.S. BLS via FRED", "PPI: Semiconductor and Other Electronic Component Mfg", "https://fred.stlouisfed.org/series/PCU33443344", "", "primary"),
    ("FRED-IPG3344S", "Federal Reserve via FRED", "Industrial Production: Semiconductor and Other Electronic Component", "https://fred.stlouisfed.org/series/IPG3344S", "", "primary"),
    ("BOK-ECOS-402Y016", "Bank of Korea ECOS", "Export price index by item: DRAM (30911201AA)", "https://ecos.bok.or.kr/", "", "primary"),
    ("DART-OPENAPI", "FSS OpenDART", "fnlttSinglAcnt (Samsung Electronics, SK hynix)", "https://opendart.fss.or.kr/", "", "primary"),
    ("KCS-DATAGO-15100475", "Korea Customs Service via data.go.kr", "Exports by item and country, HS 854232", "https://www.data.go.kr/data/15100475/openapi.do", "", "primary"),
    ("SEC-XBRL", "U.S. SEC EDGAR XBRL API", "companyconcept (capex, revenue, gross profit)", "https://data.sec.gov/api/xbrl/companyconcept/", "", "primary"),
    ("MU-10Q-FQ2-26", "Micron (Form 10-Q)", "Form 10-Q for quarter ended 2026-02-26", "https://www.sec.gov/Archives/edgar/data/723125/000072312526000006/mu-20260226.htm", "2026-03", "primary"),
    ("TOMS-20260825", "Tom's Hardware", "Micron says the silicon gap between HBM and DDR5 is widening (Hot Chips 2026)", "https://www.tomshardware.com/tech-industry/semiconductors/micron-says-the-silicon-gap-between-hbm-and-ddr5-is-widening-with-every-generation", "2026-08-25", "secondary"),
    ("TFN-20251226", "TrendForce News (reporting)", "AI to consume 20% of global DRAM wafer capacity in 2026", "https://www.trendforce.com/news/2025/12/26/news-ai-reportedly-to-consume-20-of-global-dram-wafer-capacity-in-2026-hbm-gddr7-lead-demand/", "2025-12-26", "secondary"),
    ("TFN-20260409", "TrendForce News (reporting)", "Samsung and SK hynix reset Big Tech memory contracts to 3-5 year LTAs", "https://www.trendforce.com/news/2026/04/09/news-from-annual-deals-to-3-5-year-ltas-samsung-and-sk-hynix-reportedly-reset-big-tech-memory-contracts/", "2026-04-09", "secondary"),
    ("SAMMY-20260918", "Sammy Fans (citing TrendForce)", "Samsung, SK Hynix memory lead faces growing pressure from CXMT, Micron", "https://www.sammyfans.com/2026/09/18/samsung-sk-hynixs-memory-lead-faces-growing-pressure-from-cxmt-micron/", "2026-09-18", "secondary"),
    ("SEDAILY-20260903", "Seoul Economic Daily (citing Counterpoint)", "China's CXMT breaks 10 percent in global DRAM market", "https://en.sedaily.com/finance/2026/09/03/chinas-cxmt-breaks-10-percent-in-global-dram-market", "2026-09-03", "secondary"),
    ("ZDNET-20260629", "ZDNet Korea (citing Counterpoint)", "올해 D램 절반 이상 데이터센터로 향한다", "https://zdnet.co.kr/view/?no=20260629103036", "2026-06-29", "secondary"),
    ("CP-SMARTPHONE-DRAM-2025", "Counterpoint Research", "Global Smartphone Average DRAM Hits Record 8.4GB in 2025", "https://counterpointresearch.com/en/insights/Global-Smartphone-Average-DRAM-Hits-Record-8.4GB-in-2025", "2026", "primary"),
    ("TECHNOBABOY-20260714", "Technobaboy (citing Omdia)", "Global average smartphone DRAM and NAND capacity climbs in 2026", "https://www.technobaboy.com/2026/07/14/global-average-smartphone-dram-and-nand-capacity-climbs-in-2026/", "2026-07-14", "secondary"),
    ("ETNEWS-20260127", "Electronic Times (citing Yole)", "D램 부족 2027년까지 지속 전망, 올해 수요 23% 증가", "https://www.etnews.com/20260127000216", "2026-01-27", "secondary"),
    ("THELEC-LTA-2026", "The Elec", "SK hynix locks in five years of chip demand with long-term deals", "https://www.thelec.net/news/articleView.html?idxno=12631", "2026-07", "secondary"),
    ("NVDA-RUBIN-BLOG", "NVIDIA Technical Blog", "Inside the NVIDIA Vera Rubin Platform", "https://developer.nvidia.com/blog/inside-the-nvidia-rubin-platform-six-new-chips-one-ai-supercomputer/", "2026", "primary"),
    ("NVDA-FQ2FY26", "NVIDIA", "Financial Results for Second Quarter Fiscal 2026", "https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-second-quarter-fiscal-2026", "2025-08-27", "primary"),
    ("NVDA-FQ3FY26", "NVIDIA", "Financial Results for Third Quarter Fiscal 2026", "https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-third-quarter-fiscal-2026", "2025-11-19", "primary"),
    ("NVDA-FQ4FY26", "NVIDIA", "Financial Results for Fourth Quarter and Fiscal 2026", "https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-fourth-quarter-and-fiscal-2026", "2026-02-25", "primary"),
    ("NVDA-FQ1FY27", "NVIDIA (8-K)", "Financial Results for First Quarter Fiscal 2027", "https://www.sec.gov/Archives/edgar/data/0001045810/000104581026000051/q1fy27pr.htm", "2026-05-20", "primary"),
    ("NVDA-FQ2FY27", "NVIDIA (8-K)", "Financial Results for Second Quarter Fiscal 2027", "https://www.sec.gov/Archives/edgar/data/0001045810/000104581026000073/q2fy27pr.htm", "2026-08-26", "primary"),
    ("VALUEADD-NVDA", "Value Add VC (compiled from NVIDIA releases)", "NVIDIA revenue by segment and quarter", "https://valueaddvc.com/blog/nvidia-revenue-2026-data-center-gaming-and-auto-breakdown-by-quarter", "2026", "secondary"),
    ("IDC-20260708", "IDC", "Worldwide PC shipments Q2 2026", "https://www.idc.com/resource-center/press-releases/", "2026-07-08", "primary"),
    ("IDC-20260828", "IDC", "Smartphone market share Q2 2026 (final)", "https://www.idc.com/promo/smartphone-market-share/", "2026-08-28", "primary"),
    ("IDC-BLOG-2026FCST", "IDC", "Smartphone shipments set for record 16.7% drop in 2026", "https://www.idc.com/resource-center/blog/smartphone-shipments-set-for-record-16-7-drop-in-2026-as-the-memory-crisis-hits-full-force/", "2026-08", "primary"),
    ("IDC-PR-2Q25", "IDC", "Worldwide Smartphone Market Grows 1.0% in Q2 2025", "https://my.idc.com/getdoc.jsp?containerId=prUS53684525", "2025-07", "primary"),
    ("IDC-PR-3Q25", "IDC", "Worldwide Smartphone Market Grows 2.6% in Q3 2025", "https://my.idc.com/getdoc.jsp?containerId=prUS53868725", "2025-10", "primary"),
    ("SEMITODAY-20230126", "Semiconductor Today (citing IDC)", "Quarterly smartphone shipments fall 18.3% in Q4/2022", "https://www.semiconductor-today.com/news_items/2023/jan/idc-260123.shtml", "2023-01-26", "secondary"),
]


def build_sources():
    rows = [(k, "TrendForce", t, TF + u, p, ACC2, "primary") for k, (p, u, t) in TF_RELEASES.items()]
    for fq, (sid, pub, url, p, tier) in MU_SOURCES.items():
        rows.append((sid, pub, f"Micron {fq} earnings call", url, p, ACC2, tier))
    for q, (sid, pub, url, p, tier) in HX_SOURCES.items():
        rows.append((sid, pub, f"SK hynix {q} earnings call", url, p, ACC2, tier))
    rows += [(a, b, c, d, e, ACC2, f) for a, b, c, d, e, f in OTHER]
    return pd.DataFrame(rows, columns=["source_id", "publisher", "title", "url", "published", "accessed", "tier"])


# 원본 파일의 source 문장 → source_id
def tf_id(text):
    m = re.search(r"TrendForce (\d{4})-(\d{2})-(\d{2})", text)
    return f"TF-{m.group(1)}{m.group(2)}{m.group(3)}" if m else None


SOURCE_TEXT = {
    "Sammy Fans citing TrendForce 2026-09-18": "SAMMY-20260918",
    "computed from TrendForce 3Q22 (18.19, -28.9% QoQ)": "TF-20221116",
    "computed from TrendForce 2Q23 (11.43, +20.4% QoQ)": "TF-20230824",
    "IDC 2026-07-08": "IDC-20260708", "IDC 2Q25 release": "IDC-PR-2Q25", "IDC 2Q25 release (prior-year comparison)": "IDC-PR-2Q25",
    "IDC 3Q25 release": "IDC-PR-3Q25", "IDC 3Q25 release (prior-year comparison)": "IDC-PR-3Q25",
    "IDC final data 2026-08-28": "IDC-20260828", "IDC forecast 2026": "IDC-BLOG-2026FCST",
    "IDC via Semiconductor Today 2023-01-26": "SEMITODAY-20230126",
    "NVIDIA 8-K 2026-05-20": "NVDA-FQ1FY27", "NVIDIA 8-K 2026-08-26": "NVDA-FQ2FY27",
    "NVIDIA press release 2025-08-27": "NVDA-FQ2FY26", "NVIDIA press release 2025-11-19": "NVDA-FQ3FY26",
    "NVIDIA press release 2026-02": "NVDA-FQ4FY26", "Value Add VC segment breakdown (from NVIDIA releases)": "VALUEADD-NVDA",
    "Micron at Hot Chips 2026 (Tom's Hardware)": "TOMS-20260825",
    "Counterpoint (record high)": "CP-SMARTPHONE-DRAM-2025", "Counterpoint via ZDNet Korea 2026-06-29": "ZDNET-20260629",
    "Micron FQ1-26 remarks ('around 20%')": "MU-FQ1-26", "Micron FQ1-26 remarks ('low 20% range')": "MU-FQ1-26",
    "Omdia via Technobaboy 2026-07-14": "TECHNOBABOY-20260714", "TrendForce news 2025-12-26": "TFN-20251226",
    "Yole via Electronic Times 2026-01-27": "ETNEWS-20260127", "Micron 10-Q FQ2-26": "MU-10Q-FQ2-26",
    "Micron FQ1-26 remarks": "MU-FQ1-26", "Micron FQ3-26 remarks": "MU-FQ3-26", "Micron FQ4-25 remarks": "MU-FQ4-25",
    "The Elec": "THELEC-LTA-2026", "The Elec / SK hynix 2Q26 call": "THELEC-LTA-2026",
    "TrendForce news 2026-04-09": "TFN-20260409", "NVIDIA Technical Blog (Rubin platform)": "NVDA-RUBIN-BLOG",
    "Counterpoint via Seoul Economic Daily 2026-09-03": "SEDAILY-20260903",
}


def sid(text):
    if text in SOURCE_TEXT:
        return SOURCE_TEXT[text]
    t = tf_id(text) if isinstance(text, str) else None
    if t in TF_RELEASES:
        return t
    raise KeyError(f"출처 매핑 없음: {text!r}")


# ======================================================================
# 2. 문장형 범위 → 구간 (팀 규칙)
# ======================================================================
RANGE_RULES = [  # 표현, 구간, 근거
    ("low single-digit", "1~3", "설계 v3 팀 규칙"), ("mid single-digit", "4~6", "설계 v3 팀 규칙"),
    ("high single-digit", "7~9", "설계 v3 팀 규칙"), ("low 60s", "60~63", "설계 v3 팀 규칙 (다른 십의 자리도 같은 방식)"),
    ("mid 60s", "64~66", "low 60s 규칙의 확장"), ("high 60s", "67~69", "low 60s 규칙의 확장"),
    ("approximately / around / about / roughly X", "X-2~X+2", "설계 v3 팀 규칙"),
    ("low teens / low double-digit", "10~13", "low 60s 규칙의 확장"), ("mid teens", "14~16", "low 60s 규칙의 확장"),
    ("high teens", "17~19", "low 60s 규칙의 확장"), ("over / more than / slightly over X", "X~X+3", "데이터 담당 제안"),
    ("in the X% range", "X-2~X+2", "데이터 담당 제안 (approximately와 같게)"),
    ("flat / flattish", "-1~1", "데이터 담당 제안"), ("slightly up / up slightly", "0~2", "데이터 담당 제안"),
    ("slight decrease / declined slightly", "-2~0", "데이터 담당 제안"), ("exact X% (rose 20%)", "X~X", "숫자 그대로"),
    ("declined / decreased / down / lower", "부호를 음수로", "방향 표현"),
]
LVL = {"low": (0, 3), "lower": (0, 3), "mid": (4, 6), "high": (7, 9)}


def parse_range(text):
    if not isinstance(text, str) or not text.strip() or "transcript reads" in text:
        return None
    t = text.lower().replace("–", "-")
    neg = bool(re.search(r"declin|decreas|\bdown\b|slight decrease", t))
    if "flat" in t:
        return (-1.0, 1.0)
    if "slight decrease" in t or "declined slightly" in t:
        return (-2.0, 0.0)
    if re.search(r"up slightly|slightly up", t):
        return (0.0, 2.0)
    m = re.search(r"\b(low|lower|mid|high)[- ]?single[- ]digit", t)
    if m:
        lo, hi = {"low": (1, 3), "lower": (1, 3), "mid": (4, 6), "high": (7, 9)}[m.group(1)]
    else:
        m = re.search(r"\b(low|mid|high)[- ]?(teens?|double[- ]digit)", t)
        if m:
            lo, hi = {"low": (10, 13), "mid": (14, 16), "high": (17, 19)}[m.group(1)]
        else:
            m = re.search(r"\b(low|mid|high)[- ]?(\d)0(s|%|\b)", t)
            if m:
                b = int(m.group(2)) * 10
                a, c = LVL[m.group(1)]
                lo, hi = b + a, b + c
            else:
                m = re.search(r"(slightly over|over|more than)\s+(\d+(?:\.\d+)?)", t)
                if m:
                    x = float(m.group(2)); lo, hi = x, x + 3
                else:
                    m = re.search(r"(approximately|around|about|roughly)\s+(\d+(?:\.\d+)?)", t) or \
                        re.search(r"in the (\d+(?:\.\d+)?)[- ]?(?:%|percent|percentage)?[- ]?(?:percentage )?range", t)
                    if m:
                        x = float(m.groups()[-1]); lo, hi = x - 2, x + 2
                    else:
                        m = re.search(r"(\d+(?:\.\d+)?)\s*%", t)
                        if not m:
                            return None
                        x = float(m.group(1)); lo, hi = x, x
    lo, hi = float(lo), float(hi)
    return (-hi, -lo) if neg else (lo, hi)


# ======================================================================
# 3. 관측값
# ======================================================================
def qlabel(label):  # "2Q26" -> "2026Q2"
    m = re.match(r"([1-4])Q(\d{2})", label)
    return f"20{m.group(2)}Q{m.group(1)}"


def cal_q(date):  # 회계분기 종료일 -> 대부분이 속한 달력 분기 (종료일 45일 전 기준)
    return str((pd.Timestamp(date) - pd.Timedelta(days=45)).to_period("Q"))


OBS = []


def add(period, freq, metric, product, player, lo, hi, unit, kind, source_id, raw_file,
        quote="", fiscal_period="", note=""):
    OBS.append(dict(period=period, freq=freq, metric=metric, product=product, player=player,
                    value_lo=lo, value_hi=hi, unit=unit, kind=kind, source_id=source_id,
                    quote=quote, fiscal_period=fiscal_period, raw_file=raw_file, note=note))


PLAYER = {"Industry total": "industry", "Samsung": "samsung", "SK hynix": "skhynix", "Micron": "micron",
          "Nanya": "nanya", "Winbond": "winbond", "CXMT": "cxmt"}


def build():
    # 01, 02 FRED
    for f, metric, unit, s in [("01_fred_semis_ppi_monthly.csv", "ppi_semis_us", "index_1984dec=100", "FRED-PCU33443344"),
                               ("02_fred_semis_industrial_production_monthly.csv", "industrial_production_semis_us", "index_2017=100", "FRED-IPG3344S")]:
        d = pd.read_csv(RAW / f)
        for _, r in d.iterrows():
            v = float(r.iloc[1])
            add(r.iloc[0][:7], "M", metric, "semis", "us_industry", v, v, unit, "actual", s, f)

    # 13 ECOS (정리본)
    e = pd.read_csv(SERIES / "13_ecos_dram_export_price_monthly.csv")
    for _, r in e.iterrows():
        for col, metric in [("dram_px_contract_ccy", "export_price_index_contract_ccy"), ("dram_px_krw", "export_price_index_krw")]:
            add(r.month[:7], "M", metric, "dram", "korea_exports", r[col], r[col], "index_2020=100", "actual",
                "BOK-ECOS-402Y016", "10_ecos_dram_export_price_index.csv")

    # 15 관세청 (월별 품목 그룹 합계, 국가별 상세는 series/15)
    c = pd.read_csv(SERIES / "15_customs_memory_exports_monthly_by_country.csv")
    groups = [g for g in ["dram", "flash", "multichip_mcp", "mco", "other", "total_memory"] if g in c.columns]
    t = c.groupby("month")[groups].sum().reset_index()
    for _, r in t.iterrows():
        for g in groups:
            add(r.month[:7], "M", "export_value", g, "korea_exports_9c", round(r[g], 1), round(r[g], 1), "usd_mn", "actual",
                "KCS-DATAGO-15100475", "12_customs_memory_exports_by_country.csv", note="9개국 합계 (CN TW VN US HK JP SG MY PH)")

    # 14 DART (정리본)
    dq = pd.read_csv(SERIES / "14_dart_quarterly_financials.csv")
    for _, r in dq.iterrows():
        pl = "samsung" if r.company == "삼성전자" else "skhynix"
        note = "4분기 = 사업보고서 연간 - 1~3분기" if r.period.endswith("Q4") else ""
        for col, metric in [("revenue_krw_tn", "revenue"), ("op_income_krw_tn", "operating_income")]:
            add(r.period, "Q", metric, "company_total", pl, r[col], r[col], "krw_tn", "actual", "DART-OPENAPI",
                "11_dart_samsung_skhynix_financials.csv", note=note)

    # 03 공급사 매출·점유율
    d = pd.read_csv(RAW / "03_dram_supplier_revenue_share_quarterly.csv")
    for _, r in d.iterrows():
        p, pl, s = qlabel(r.quarter), PLAYER[r.supplier], sid(r.source)
        note = r.note if isinstance(r.note, str) else ""
        derived_total = r.source.startswith("computed") or "computed as" in note
        if pd.notna(r.dram_revenue_usd_bn):
            kind = "estimate" if (derived_total or "revenue computed" in note or pl == "cxmt") else "actual"
            add(p, "Q", "dram_revenue", "dram", pl, r.dram_revenue_usd_bn, r.dram_revenue_usd_bn, "usd_bn", kind, s,
                "03_dram_supplier_revenue_share_quarterly.csv", note=note)
        if pd.notna(r.qoq_pct):
            add(p, "Q", "dram_revenue_qoq", "dram", pl, r.qoq_pct, r.qoq_pct, "pct", "actual", s,
                "03_dram_supplier_revenue_share_quarterly.csv", note=note)
        if pd.notna(r.market_share_pct):
            kind = "estimate" if "share computed" in note else "actual"
            add(p, "Q", "revenue_share", "dram", pl, r.market_share_pct, r.market_share_pct, "pct", kind, s,
                "03_dram_supplier_revenue_share_quarterly.csv", note=note)

    # 05 수요 지표
    d = pd.read_csv(RAW / "05_demand_proxies_quarterly.csv")
    for _, r in d.iterrows():
        s = sid(r.source)
        note = r.note if isinstance(r.note, str) else ""
        if r.series == "NVIDIA data center revenue":
            add(cal_q(r.period_end), "Q", "datacenter_revenue", "ai_accelerator", "nvidia", r.value, r.value, "usd_bn",
                "actual", s, "05_demand_proxies_quarterly.csv", fiscal_period=r.period, note=note)
        elif r.series == "Worldwide smartphone shipments forecast":
            add(r.period[2:], "A", "shipments_yoy", "smartphone", "world", r.yoy_pct, r.yoy_pct, "pct", "forecast", s,
                "05_demand_proxies_quarterly.csv", note=note)
        else:
            prod = "smartphone" if "smartphone" in r.series else "pc"
            if r.period.startswith("CY"):
                period, freq = r.period[2:], "A"
            else:
                period, freq = qlabel(r.period), "Q"
            add(period, freq, "shipments", prod, "world", r.value, r.value, "mn_units", "actual", s,
                "05_demand_proxies_quarterly.csv", note=note)
            if pd.notna(r.yoy_pct):
                add(period, freq, "shipments_yoy", prod, "world", r.yoy_pct, r.yoy_pct, "pct", "actual", s,
                    "05_demand_proxies_quarterly.csv")

    # 06 마이크론
    d = pd.read_csv(RAW / "06_micron_dram_bits_asp_history.csv")
    for _, r in d.iterrows():
        s = MU_SOURCES[r.fiscal_quarter][0]
        p = cal_q(r.period_end)
        f = "06_micron_dram_bits_asp_history.csv"
        add(p, "Q", "dram_revenue", "dram", "micron", r.dram_revenue_usd_bn, r.dram_revenue_usd_bn, "usd_bn", "actual", s, f, fiscal_period=r.fiscal_quarter)
        add(p, "Q", "dram_revenue_qoq", "dram", "micron", r.dram_rev_qoq_pct, r.dram_rev_qoq_pct, "pct", "actual", s, f, fiscal_period=r.fiscal_quarter)
        for col, metric in [("bit_qoq_text", "bit_qoq"), ("asp_qoq_text", "asp_qoq")]:
            rng = parse_range(r[col])
            if rng is None:
                raise ValueError(f"범위 해석 실패: {r[col]!r}")
            add(p, "Q", metric, "dram", "micron", rng[0], rng[1], "pct", "actual", s, f, quote=r[col], fiscal_period=r.fiscal_quarter)

    # 07 SK하이닉스
    d = pd.read_csv(RAW / "07_skhynix_dram_bits_asp_history.csv")
    for _, r in d.iterrows():
        s = HX_SOURCES[r.quarter][0]
        guide = "guidance" in r.quarter
        p = qlabel(r.quarter.split()[0])
        f = "07_skhynix_dram_bits_asp_history.csv"
        for col, metric, mid in [("bit_qoq_text", "bit_qoq", "bit_qoq_mid_pct"), ("asp_qoq_text", "asp_qoq", "asp_qoq_mid_pct")]:
            rng = parse_range(r[col])
            if rng is not None:
                add(p, "Q", metric, "dram", "skhynix", rng[0], rng[1], "pct", "forecast" if guide else "actual", s, f, quote=r[col])
            elif pd.notna(r[mid]):  # 1Q24 비트: 녹취가 깨져 매출 증감과 ASP로 역산
                add(p, "Q", metric, "dram", "skhynix", r[mid] - 2, r[mid] + 2, "pct", "estimate", s, f, quote=str(r[col]),
                    note="TrendForce 매출 증감 +2.7%와 ASP +21%로 역산")

    # 16 capex, 18 마이크론 매출총이익률
    d = pd.read_csv(RAW / "16_hyperscaler_capex_quarterly.csv")
    for _, r in d.iterrows():
        add(r.calendar_quarter, "Q", "capex_cash", "company_total", r.company.lower(), r.capex_usd_bn, r.capex_usd_bn, "usd_bn",
            "actual", "SEC-XBRL", "16_hyperscaler_capex_quarterly.csv", note=f"tag={r.tag}; 금융리스 제외")
    d = pd.read_csv(RAW / "18_micron_gross_margin_quarterly.csv")
    for _, r in d.iterrows():
        p, fq = cal_q(r.fiscal_quarter_end), f"FQ ending {r.fiscal_quarter_end}"
        add(p, "Q", "revenue", "company_total", "micron", r.revenue_usd_bn, r.revenue_usd_bn, "usd_bn", "actual", "SEC-XBRL",
            "18_micron_gross_margin_quarterly.csv", fiscal_period=fq)
        add(p, "Q", "gross_margin", "company_total", "micron", r.gross_margin_pct, r.gross_margin_pct, "pct", "actual", "SEC-XBRL",
            "18_micron_gross_margin_quarterly.csv", fiscal_period=fq, note="GAAP")

    # 19 계약가 증감
    d = pd.read_csv(RAW / "19_trendforce_contract_price_qoq.csv")
    for _, r in d.iterrows():
        lo = r.qoq_lo_pct
        hi = r.qoq_hi_pct if pd.notna(r.qoq_hi_pct) else lo + 3
        note = "" if pd.notna(r.qoq_hi_pct) else "'over X' 규칙으로 상한 = X+3"
        if r["product"] == "ddr5":
            note = (note + "; " if note else "") + "server DRAM, DDR5가 출하의 90% 이상 (TrendForce 2Q26)"
        if r["product"] == "lpddr":
            note = (note + "; " if note else "") + "mobile DRAM (LPDDR4X/5X)"
        add(qlabel(r.quarter), "Q", "contract_price_qoq", r["product"], "industry", lo, hi, "pct", r.kind, tf_id(r.source),
            "19_trendforce_contract_price_qoq.csv", quote=r.quote, note=note)

    # 08, 09, 17 가정 파일
    for f in ["08_hbm_assumptions.csv", "09_market_structure_assumptions.csv", "17_cost_and_contract_assumptions.csv"]:
        d = pd.read_csv(RAW / f)
        for _, r in d.iterrows():
            spec = ASSUMPTION_MAP.get(r.key)
            if spec is None:
                raise KeyError(f"{f}: 매핑 없는 key {r.key}")
            if spec == "skip":
                continue
            period, freq, metric, product, player, lo, hi, unit, kind = spec
            note_parts = [x for x in [r.get("note"), r.get("cross_check")] if isinstance(x, str) and x]
            add(period, freq, metric, product, player, lo, hi, unit, kind, sid(r.source), f,
                quote=str(r.value), note="; ".join(note_parts))


# key: (period, freq, metric, product, player, lo, hi, unit, kind)   "skip" = 수치가 아닌 항목
ASSUMPTION_MAP = {
    # 08
    "hbm_wafer_penalty_vs_ddr5": ("2026", "A", "wafer_area_ratio_vs_ddr5", "hbm", "industry", 2.5, 4.0, "x", "estimate"),
    "hbm_share_of_dram_wafers_2025": ("2025", "A", "wafer_share", "hbm", "top3", 18, 18, "pct", "estimate"),
    "hbm_share_of_dram_bits_2025": ("2025", "A", "bit_share", "hbm", "top3", 8, 8, "pct", "estimate"),
    "hbm_share_of_dram_wafers_2026": ("2026", "A", "wafer_share", "hbm", "top3", 22, 22, "pct", "estimate"),
    "hbm_share_of_dram_bits_2026": ("2026", "A", "bit_share", "hbm", "top3", 9, 9, "pct", "estimate"),
    "hbm_share_of_dram_wafers_2027": ("2027", "A", "wafer_share", "hbm", "top3", 30, 30, "pct", "forecast"),
    "hbm_share_of_dram_bits_2027": ("2027", "A", "bit_share", "hbm", "top3", 13, 13, "pct", "forecast"),
    "hbm3e_price_premium_vs_server_ddr5_2025": ("2025", "A", "price_per_bit_ratio_vs_ddr5", "hbm", "industry", 4, 5, "x", "estimate"),
    "hbm3e_price_premium_vs_server_ddr5_end2026": ("2026Q4", "Q", "price_per_bit_ratio_vs_ddr5", "hbm", "industry", 1, 2, "x", "forecast"),
    "hbm_pricing_mechanism": "skip",
    # 09
    "share_bits_server_2023": ("2023", "A", "bit_share_by_application", "server", "industry", 37.6, 37.6, "pct", "forecast"),
    "share_bits_mobile_2023": ("2023", "A", "bit_share_by_application", "mobile", "industry", 36.8, 36.8, "pct", "forecast"),
    "share_bits_server_2026": ("2026", "A", "bit_share_by_application", "server", "industry", 48, 48, "pct", "forecast"),
    "share_bits_hbm_2026": ("2026", "A", "bit_share_by_application", "hbm", "industry", 9, 9, "pct", "forecast"),
    "share_bits_mobile_2026": ("2026", "A", "bit_share_by_application", "mobile", "industry", 22, 22, "pct", "forecast"),
    "share_bits_pc_2026": ("2026", "A", "bit_share_by_application", "pc", "industry", 10, 10, "pct", "forecast"),
    "share_bits_other_2026": ("2026", "A", "bit_share_by_application", "other", "industry", 12, 12, "pct", "forecast"),
    "share_revenue_datacenter_2026": ("2026", "A", "revenue_share_by_application", "datacenter", "industry", 65, 65, "pct", "forecast"),
    "content_smartphone_avg_gb_2025": ("2025", "A", "content_per_unit", "smartphone", "world", 8.4, 8.4, "gb", "actual"),
    "content_smartphone_avg_gb_1q26": ("2026Q1", "Q", "content_per_unit", "smartphone", "world", 8.3, 8.3, "gb", "actual"),
    "content_growth_server_2024": ("2024", "A", "content_per_unit_yoy", "server", "world", 17.3, 17.3, "pct", "forecast"),
    "content_growth_smartphone_2024": ("2024", "A", "content_per_unit_yoy", "smartphone", "world", 14.1, 14.1, "pct", "forecast"),
    "content_growth_notebook_2024": ("2024", "A", "content_per_unit_yoy", "pc", "world", 12.4, 12.4, "pct", "forecast"),
    "content_growth_server_2026": ("2026", "A", "content_per_unit_yoy", "server", "world", 25, 25, "pct", "forecast"),
    "content_growth_smartphone_2026": ("2026", "A", "content_per_unit_yoy", "smartphone", "world", 16, 16, "pct", "forecast"),
    "content_growth_pc_2026": ("2026", "A", "content_per_unit_yoy", "pc", "world", 15, 15, "pct", "forecast"),
    "content_growth_auto_2026": ("2026", "A", "content_per_unit_yoy", "auto", "world", 36, 36, "pct", "forecast"),
    "bit_demand_growth_2025": ("2025", "A", "bit_demand_yoy", "dram", "industry", 20, 23, "pct", "estimate"),
    "bit_demand_growth_2026": ("2026", "A", "bit_demand_yoy", "dram", "industry", 20, 26, "pct", "forecast"),
    "bit_supply_growth_2026": ("2026", "A", "bit_supply_yoy", "dram", "industry", 18, 22, "pct", "forecast"),
    "sufficiency_ratio_2026": ("2026", "A", "sufficiency_ratio", "dram", "industry", -2, -1, "pct", "forecast"),
    "dram_capacity_total_2026": ("2026", "A", "capacity", "dram", "industry", 40, 40, "eb", "forecast"),
    "dram_capacity_growth_annual": ("2026", "A", "capacity_yoy", "dram", "industry", 10, 15, "pct", "forecast"),
    "ai_share_of_dram_wafers_2026": ("2026", "A", "wafer_share", "ai_memory", "industry", 20, 20, "pct", "forecast"),
    "wafer_multiplier_hbm_per_gb": ("2026", "A", "wafer_area_ratio_vs_std_dram", "hbm", "industry", 4, 4, "x", "estimate"),
    "wafer_multiplier_gddr7_per_gb": ("2026", "A", "wafer_area_ratio_vs_std_dram", "gddr7", "industry", 1.7, 1.7, "x", "estimate"),
    "new_capacity_timing": "skip",
    "smartphone_production_2026": ("2026", "A", "production_yoy", "smartphone", "world", -2, -2, "pct", "forecast"),
    "notebook_production_2026": ("2026", "A", "production_yoy", "pc", "world", -2.4, -2.4, "pct", "forecast"),
    "dram_share_of_smartphone_bom": ("2025", "A", "bom_share", "smartphone", "world", 10, 15, "pct", "estimate"),
    "hbm_capacity_per_gpu_rubin": ("2026", "A", "hbm_per_gpu_max", "rubin", "nvidia", 288, 288, "gb", "actual"),
    "share_revenue_cxmt_2q26": ("2026Q2", "Q", "revenue_share", "dram", "cxmt", 10, 10, "pct", "actual"),
    "share_revenue_skhynix_2q26_counterpoint": ("2026Q2", "Q", "revenue_share_counterpoint", "dram", "skhynix", 25, 25, "pct", "actual"),
    # 17
    "micron_gross_margin_fq1_26": "skip",  # 18번(SEC)과 중복
    "micron_gross_margin_fq2_26": "skip",
    "micron_gross_margin_fq3_26": ("2026Q2", "Q", "gross_margin_non_gaap", "company_total", "micron", 84.9, 84.9, "pct", "actual"),
    "micron_gross_margin_fq4_26_guide": ("2026Q3", "Q", "gross_margin_non_gaap", "company_total", "micron", 85, 87, "pct", "forecast"),
    "micron_dram_cost_per_bit_fy25": ("2025", "A", "cost_per_bit_yoy", "dram", "micron", -3, -1, "pct", "actual"),
    "micron_dram_cost_per_bit_outlook": "skip",
    "micron_sca_count": ("2026", "A", "lta_count", "dram", "micron", 16, 16, "count", "actual"),
    "micron_sca_share_dram_volume": ("2026", "A", "lta_volume_share", "dram", "micron", 18, 22, "pct", "actual"),
    "micron_sca_term": ("2026", "A", "lta_term", "dram", "micron", 5, 5, "years", "actual"),
    "micron_sca_structure": "skip",
    "micron_sca_min_revenue": ("2026", "A", "lta_min_revenue", "company_total", "micron", 100, 100, "usd_bn", "actual"),
    "skhynix_lta_count": ("2026", "A", "lta_count", "dram", "skhynix", 10, 10, "count", "actual"),
    "skhynix_lta_term": ("2026", "A", "lta_term", "dram", "skhynix", 5, 5, "years", "actual"),
    "skhynix_lta_share_volume": "skip",
    "samsung_lta_term": ("2026", "A", "lta_term", "dram", "samsung", 3, 3, "years", "actual"),
    "lta_upfront_payment": ("2026", "A", "lta_upfront_share", "dram", "industry", 10, 30, "pct", "estimate"),
    "dram_capex_industry_2025": ("2025", "A", "capex", "dram", "industry", 53.7, 53.7, "usd_bn", "estimate"),
    "dram_capex_industry_2026": ("2026", "A", "capex", "dram", "industry", 61.3, 61.3, "usd_bn", "forecast"),
    "dram_capex_samsung_2026": ("2026", "A", "capex", "dram", "samsung", 20.0, 20.0, "usd_bn", "forecast"),
    "dram_capex_skhynix_2026": ("2026", "A", "capex", "dram", "skhynix", 20.5, 20.5, "usd_bn", "forecast"),
    "dram_capex_micron_2026": ("2026", "A", "capex", "dram", "micron", 13.5, 13.5, "usd_bn", "forecast"),
}


# ======================================================================
# 4. 스키마 검사
# ======================================================================
def validate(obs, src):
    errs = []
    kinds = {"actual", "forecast", "estimate"}
    if not set(obs.kind) <= kinds:
        errs.append(f"kind 값 오류: {set(obs.kind) - kinds}")
    if (obs.value_lo > obs.value_hi).any():
        errs.append(f"lo > hi: {obs[obs.value_lo > obs.value_hi][['period','metric','player']].values.tolist()}")
    if obs[["value_lo", "value_hi"]].isna().any().any():
        errs.append("값이 빈 행 있음")
    missing = set(obs.source_id) - set(src.source_id)
    if missing:
        errs.append(f"sources.csv에 없는 source_id: {missing}")
    pat = {"M": r"^\d{4}-\d{2}$", "Q": r"^\d{4}Q[1-4]$", "A": r"^\d{4}$"}
    for fq, p in pat.items():
        bad = obs[(obs.freq == fq) & ~obs.period.str.match(p)]
        if len(bad):
            errs.append(f"period 형식 오류 ({fq}): {bad.period.unique()[:5]}")
    key = ["period", "metric", "product", "player", "kind", "source_id"]
    dup = obs[obs.duplicated(key, keep=False)]
    if len(dup):
        errs.append(f"중복 키 {len(dup)}행: {dup[key].head(3).values.tolist()}")
    if src.source_id.duplicated().any():
        errs.append("source_id 중복")
    if not set(src.tier) <= {"primary", "secondary"}:
        errs.append("tier 값 오류")
    return errs


def main():
    # 범위 규칙 자체 테스트
    tests = {"increased low-60s %": (60, 63), "declined lower single-digit %": (-3, -1), "flattish": (-1, 1),
             "increased approximately 20%": (18, 22), "decreased mid-20% range": (-26, -24), "rose high-teen %": (17, 19),
             "increased over 20%": (20, 23), "increased in the 10% range": (8, 12), "ASPs declined slightly": (-2, 0),
             "rose 20%": (20, 20), "grew mid-30%": (34, 36), "increased low double-digit %": (10, 13)}
    for text, want in tests.items():
        got = parse_range(text)
        assert got == tuple(float(x) for x in want), f"범위 규칙 오류: {text} -> {got}, 기대 {want}"

    build()
    src = build_sources()
    obs = pd.DataFrame(OBS)
    used = set(obs.source_id)
    src = src[src.source_id.isin(used)].reset_index(drop=True)  # 실제로 쓴 출처만
    obs.insert(0, "obs_id", [f"OBS-{i:05d}" for i in range(1, len(obs) + 1)])

    errs = validate(obs, src)
    if errs:
        print("스키마 검사 실패:\n- " + "\n- ".join(errs))
        sys.exit(1)

    src.to_csv(DATA / "sources.csv", index=False)
    obs.to_csv(DATA / "observations.csv", index=False)
    pd.DataFrame(RANGE_RULES, columns=["expression", "interval_pct", "basis"]).to_csv(DATA / "range_rules.csv", index=False)

    # 요약과 설계 게이트 G1 점검 (observations 50행 이상, 출처 100%)
    print(f"sources.csv: {len(src)}개 (primary {sum(src.tier=='primary')}, secondary {sum(src.tier=='secondary')})")
    print(f"observations.csv: {len(obs)}행")
    print(obs.groupby(["freq", "kind"]).size().unstack(fill_value=0).to_string())
    tier = obs.merge(src[["source_id", "tier"]], on="source_id")
    print("\n값 기준 출처 등급:", tier.tier.value_counts().to_dict())
    print(f"G1 점검: 행 {len(obs)} ≥ 50 → {'통과' if len(obs) >= 50 else '미달'}, 출처 연결 100% → 통과")


if __name__ == "__main__":
    main()
