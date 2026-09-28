# 메모리 시뮬레이터 데이터 (2026-09-27 기준)

데이터 담당: 황윤. 백엔드는 `clean/` 폴더의 파일과 가정 파일(08, 09, 17)을 쓰면 된다. 원본 파일은 출처 확인과 재생성용이다. 검증 결과는 `VERIFICATION.md`에 있다.

## 백엔드가 쓸 파일 (clean/)

`python clean_data.py`를 실행하면 원본에서 다시 만든다.

| 파일 | 내용 | 기간 |
|---|---|---|
| 21_quarterly_panel.csv | **메인 입력.** 분기별 D램 가격지수, 수출액, 물량 근사지수, 삼성·하이닉스 매출과 이익률, 업계 DRAM 매출 | 1Q19 ~ 3Q26(2개월) |
| 20_monthly_panel.csv | 월별 D램 가격지수, 수출액, 물량 근사지수, 미국 PPI, 산업생산 | 2019-01 ~ 2026-08 |
| 13_ecos_dram_export_price_monthly.csv | D램 수출물가지수 (계약통화, 원화 기준) | 2019-01 ~ 2026-08 |
| 14_dart_quarterly_financials.csv | 삼성전자·SK하이닉스 분기 매출, 영업이익 (조 원) | 1Q19 ~ 2Q26 |
| 15_customs_memory_exports_monthly_by_country.csv | 국가별·품목 그룹별 메모리 수출액 (백만 달러) | 2019-01 ~ 2026-08 |

## 원본 파일

| 파일 | 내용 | 기간 | 출처 |
|---|---|---|---|
| 01_fred_semis_ppi_monthly.csv | 미국 반도체·전자부품 생산자물가지수 | 2019-01 ~ 2026-08 | FRED PCU33443344 |
| 02_fred_semis_industrial_production_monthly.csv | 미국 반도체·전자부품 산업생산지수 | 2019-01 ~ 2026-08 | FRED IPG3344S |
| 03_dram_supplier_revenue_share_quarterly.csv | DRAM 공급사별 매출, 증감, 점유율 | 2Q22 ~ 2Q26 | TrendForce 분기 보도자료 |
| 05_demand_proxies_quarterly.csv | 엔비디아 데이터센터 매출, 스마트폰·PC 출하량 | FQ1 FY24 ~ FQ2 FY27 (엔비디아) | 엔비디아 실적, IDC |
| 06_micron_dram_bits_asp_history.csv | 마이크론 DRAM 매출, 비트·ASP 전분기 대비 증감 | FQ1-22 ~ FQ3-26 (19개 분기) | 마이크론 실적 콜 |
| 07_skhynix_dram_bits_asp_history.csv | SK하이닉스 DRAM 비트·ASP 전분기 대비 증감 | 2Q23 ~ 3Q26 가이던스 | SK하이닉스 실적 콜 |
| 08_hbm_assumptions.csv | HBM 웨이퍼 소모 계수, 웨이퍼·비트 비중, HBM 가격 프리미엄 | 2025 ~ 2027 | 마이크론, TrendForce |
| 09_market_structure_assumptions.csv | 응용처별 비트 비중, 기기당 탑재량, 비트 수요·공급 증가율, 캐파 | 2023 ~ 2026 | TrendForce, Counterpoint, Yole, Omdia, 마이크론 |
| 17_cost_and_contract_assumptions.csv | 마이크론 매출총이익률, 원가 방향, 장기계약(SCA·LTA) 조건, 업계 capex | 2025 ~ 2030 | 마이크론, SK하이닉스, TrendForce |
| 16_hyperscaler_capex_quarterly.csv | 마이크로소프트·알파벳·아마존·메타 분기 현금 capex | 1Q19 ~ 2Q26 | SEC XBRL (`fetch_sec_capex.py`) |
| 18_micron_gross_margin_quarterly.csv | 마이크론 분기 매출, 매출총이익, 이익률 (GAAP) | FQ2-19 ~ FQ3-26 | SEC XBRL (`fetch_sec_capex.py`) |
| 10_ecos_dram_export_price_index.csv | 한국은행 D램 수출물가지수 원본 (API가 같은 값을 여러 번 돌려줘 중복 행이 있음. 정리본은 clean/13) | 2019-01 ~ 2026-08 | ECOS (`fetch_keyed_data.py`) |
| 11_dart_samsung_skhynix_financials.csv | 삼성전자·SK하이닉스 보고서별 매출, 영업이익 원본 (정리본은 clean/14) | 2019 ~ 2Q26 | OpenDART (`fetch_keyed_data.py`) |
| 12_customs_memory_exports_by_country.csv | 메모리 수출액 원본, HS 10자리·국가·월 단위 (정리본은 clean/15) | 2019-01 ~ 2026-08 | 관세청 (`fetch_keyed_data.py`) |

## 스크립트

- `fetch_keyed_data.py`: ECOS, OpenDART, 관세청 데이터 수집 (API 키 필요)
- `fetch_sec_capex.py`: 하이퍼스케일러 4사 분기 capex와 마이크론 분기 매출총이익률 수집 (키 불필요, `SEC_UA`에 이름과 이메일)
- `clean_data.py`: 원본을 정리해 `clean/` 생성

## 주의

**가격·물량**
- 모델에는 D램 가격지수 중 계약통화 기준을 쓴다. 원화 기준은 환율 효과가 섞여 있다.
- dram_volume_proxy는 D램 수출액을 가격지수로 나눈 값(2020년 평균 = 100)이다. 실제 비트 출하가 아니라 근사치다.
- 수출액은 주요 9개국 합계이고 전 세계 합계가 아니다.
- 관세청 품목 그룹: dram(8542.32.1010), flash(8542.32.1030), multichip_mcp(8542.32.3000), mco(8542.32.40xx), other. HBM의 신고 코드는 공개 자료로 확인되지 않았다.

**비트·ASP (06, 07)**
- 회사는 범위로만 공개한다("low-60s %" 등). 원문 표현(`*_text`)을 그대로 두고, 모델용 중간값(`*_mid_pct`)을 따로 붙였다.
- 06의 check_implied_rev_qoq_pct는 (1+비트)(1+ASP)-1로 다시 계산한 매출 증감이다. 실제 매출 증감과 대부분 3%p 안에서 맞는다.
- 마이크론 회계분기는 달력보다 약 1개월 빠르다. calendar_quarter_approx 열로 맞춘다.
- 하이닉스 2022년~1Q23은 공개 녹취를 찾지 못해 비어 있다. 이 구간은 마이크론 값으로 대신한다.
- 하이닉스 1Q24 비트 증감은 녹취가 깨져 있어 TrendForce 매출 증감과 ASP로 역산했다(−15%).
- 07의 check_gap_pp는 비트·ASP로 계산한 매출 증감과 TrendForce 매출 증감의 차이다. 모든 분기가 ±3.2%p 이내다.
- 삼성전자는 분기별 비트·ASP를 숫자로 공개하지 않는다.

**점유율 (03)**
- 보도자료에 점유율이 없는 분기는 매출/업계 합계로 계산했고 note에 "share computed"로 표시했다.
- 2Q22와 1Q23 업계 합계는 다음 분기 값과 증감률로 역산했다.
- CXMT 점유율은 2차 인용이다.

**수요 (05)**
- 엔비디아 FQ1 FY24 ~ FQ1 FY26은 2차 자료(소수점 첫째 자리 반올림)이고, 그 이후는 엔비디아 발표 원문이다.
- 스마트폰 출하량은 일부 분기만 있다. IDC 상세 데이터는 유료다.

**capex·매출총이익률 (16, 18)**
- 16의 capex는 현금 설비투자(금융리스 제외)라 회사가 발표하는 capex보다 작을 수 있다. 예: 메타 2Q26 301억 달러 vs 발표 311억 달러.
- 마이크로소프트는 2026년 리스 회계 변경으로 기준이 바뀌었다.
- 18은 GAAP 기준이다. 콜에서 말하는 non-GAAP 값과 0.3~0.7%p 차이가 날 수 있다.

**가정 파일 (08, 09, 17)**
- 모든 행에 출처, 기준 시점, 신뢰도(high/medium/low)가 있다. 범위로 발표된 값은 중간값을 넣고 원문 범위를 cross_check나 note에 적었다.
- 신뢰도 low 값은 민감도 분석 대상으로 쓴다.

**기타**
- 영업이익률은 회사 전체 기준이다. 삼성전자는 메모리 외 사업이 섞여 있다.
- 01, 02는 웹 조회 도구로 받은 값이다. 레포에 올리기 전에 FRED에서 CSV를 직접 내려받아 대조한다.
- 다음 업데이트: 마이크론 FQ4-26 실적 (2026-09-30).
