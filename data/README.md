# 데이터 (2026-09-28 기준)

데이터 담당: 황윤. 아키텍처 설계 v3의 데이터 파이프라인(D0~D2)에 맞춘 구조다. 검증 결과는 `VERIFICATION.md`에 있다.

## 구조

```
data/
  sources.csv        출처 목록 (source_id, 발행처, 제목, URL, 발행일, 열람일, tier)
  observations.csv   값 하나당 한 줄. 모델 보정(D3)은 이 파일에서 시작한다
  range_rules.csv    "low 60s" 같은 문장형 범위를 구간으로 바꾸는 팀 규칙
  raw/               수집한 원본 (파일별 넓은 형식)
  series/            원본을 정리한 시계열 (월별·분기별 패널)
pipeline/
  fetch_keyed_data.py   ECOS, OpenDART, 관세청 수집 (API 키 필요) → raw/
  fetch_sec_capex.py    하이퍼스케일러 capex, 마이크론 매출총이익률 (키 불필요) → raw/
  clean_data.py         raw/ → series/
  build_observations.py raw/ + series/ → sources.csv, observations.csv, range_rules.csv (스키마 검사 포함)
```

다시 만들기: 레포 맨 위에서 `make data` (또는 `python pipeline/clean_data.py && python pipeline/build_observations.py`).

## observations.csv 열

| 열 | 뜻 |
|---|---|
| period | 월별 `2026-08`, 분기 `2026Q2`(달력 분기로 통일), 연간 `2026` |
| freq | M / Q / A |
| metric | 예: `bit_qoq`, `asp_qoq`, `contract_price_qoq`, `dram_revenue`, `revenue_share`, `export_price_index_contract_ccy`, `wafer_share`, `capex_cash` |
| product | `dram`, `conventional_dram`, `hbm`, `ddr5`(서버 DRAM), `lpddr`(모바일 DRAM), `company_total` 등 |
| player | `industry`, `samsung`, `skhynix`, `micron`, `cxmt`, `korea_exports`, `nvidia` 등 |
| value_lo / value_hi | 구간. 점값이면 둘이 같다 |
| unit | `pct`, `usd_bn`, `krw_tn`, `index_2020=100`, `x`(배수) 등 |
| kind | `actual`(실적) / `forecast`(전망) / `estimate`(추정·역산). 전망은 백테스트 정답으로 쓰지 않는다 |
| source_id | sources.csv 키 |
| quote | 원문 표현 (범위로 발표된 값은 원문 그대로) |
| fiscal_period | 회계분기가 달력과 다른 회사의 원래 분기 (마이크론, 엔비디아) |
| raw_file | 이 값이 나온 raw/ 파일 |

회계분기 → 달력 분기: 분기 종료일에서 45일을 뺀 날짜가 속한 분기. 마이크론 FQ3-26(5월 28일 종료) → 2026Q2.

## 백엔드가 바로 쓸 파일

| 파일 | 내용 | 기간 |
|---|---|---|
| series/21_quarterly_panel.csv | 분기별 D램 가격지수, 수출액, 물량 근사지수, 삼성·하이닉스 매출과 이익률, 업계 DRAM 매출 | 1Q19 ~ 3Q26(2개월) |
| series/20_monthly_panel.csv | 월별 D램 가격지수, 수출액, 물량 근사지수, 미국 PPI, 산업생산 | 2019-01 ~ 2026-08 |
| series/13_ecos_dram_export_price_monthly.csv | D램 수출물가지수 (계약통화, 원화 기준) | 2019-01 ~ 2026-08 |
| series/14_dart_quarterly_financials.csv | 삼성전자·SK하이닉스 분기 매출, 영업이익 (조 원) | 1Q19 ~ 2Q26 |
| series/15_customs_memory_exports_monthly_by_country.csv | 국가별·품목 그룹별 메모리 수출액 (백만 달러) | 2019-01 ~ 2026-08 |

**백테스트 정답 제안:** 설계 L3는 "범용 DRAM 계약가 분기 증감"을 쓰는데, 이 과거 시계열은 공개 자료로 연속해서 얻을 수 없다(`raw/19`에 있는 건 대부분 전망치). 대신 한국은행 D램 수출물가지수(계약통화 기준, `series/13`)를 정답으로 쓰고 TrendForce 실적 값은 교차 확인에 쓰는 것을 제안한다.

## 원본 파일 (raw/)

| 파일 | 내용 | 기간 | 출처 |
|---|---|---|---|
| 01_fred_semis_ppi_monthly.csv | 미국 반도체·전자부품 생산자물가지수 | 2019-01 ~ 2026-08 | FRED PCU33443344 |
| 02_fred_semis_industrial_production_monthly.csv | 미국 반도체·전자부품 산업생산지수 | 2019-01 ~ 2026-08 | FRED IPG3344S |
| 03_dram_supplier_revenue_share_quarterly.csv | DRAM 공급사별 매출, 증감, 점유율 | 2Q22 ~ 2Q26 | TrendForce 분기 보도자료 |
| 05_demand_proxies_quarterly.csv | 엔비디아 데이터센터 매출, 스마트폰·PC 출하량 | FQ1 FY24 ~ FQ2 FY27 (엔비디아) | 엔비디아 실적, IDC |
| 06_micron_dram_bits_asp_history.csv | 마이크론 DRAM 매출, 비트·ASP 전분기 대비 증감 | FQ1-22 ~ FQ3-26 (19개 분기) | 마이크론 실적 콜 |
| 07_skhynix_dram_bits_asp_history.csv | SK하이닉스 DRAM 비트·ASP 전분기 대비 증감 | 2Q23 ~ 3Q26 가이던스 | SK하이닉스 실적 콜 |
| 08_hbm_assumptions.csv | HBM 웨이퍼 소모 계수, 웨이퍼·비트 비중(2025~2027), HBM 가격 프리미엄 | 2025 ~ 2027 | 마이크론, TrendForce |
| 09_market_structure_assumptions.csv | 응용처별 비트 비중, 기기당 탑재량, 비트 수요·공급 증가율, 캐파, GPU당 HBM 용량 | 2023 ~ 2026 | TrendForce, Counterpoint, Yole, Omdia, 마이크론, 엔비디아 |
| 10_ecos_dram_export_price_index.csv | 한국은행 D램 수출물가지수 원본 (API가 같은 값을 여러 번 돌려줘 중복 행이 있음) | 2019-01 ~ 2026-08 | ECOS |
| 11_dart_samsung_skhynix_financials.csv | 삼성전자·SK하이닉스 보고서별 매출, 영업이익 원본 | 2019 ~ 2Q26 | OpenDART |
| 12_customs_memory_exports_by_country.csv | 메모리 수출액 원본, HS 10자리·국가·월 단위 | 2019-01 ~ 2026-08 | 관세청 |
| 16_hyperscaler_capex_quarterly.csv | 마이크로소프트·알파벳·아마존·메타 분기 현금 capex | 1Q19 ~ 2Q26 | SEC XBRL |
| 17_cost_and_contract_assumptions.csv | 마이크론 매출총이익률, 원가 방향, 장기계약(SCA·LTA) 조건, 업계 capex | 2025 ~ 2030 | 마이크론, SK하이닉스, TrendForce |
| 18_micron_gross_margin_quarterly.csv | 마이크론 분기 매출, 매출총이익, 이익률 (GAAP) | FQ2-19 ~ FQ3-26 | SEC XBRL |
| 19_trendforce_contract_price_qoq.csv | 범용 DRAM·서버·모바일 계약가 분기 증감 (실적과 전망 구분) | 1Q23 ~ 3Q26 | TrendForce 보도자료 |

## 주의

**출처 등급 (tier)**
- 값 기준 약 93%가 1차 자료(발표 기관 원문)다.
- 2차 자료: 마이크론 12개 분기(녹취록), SK하이닉스 전체(녹취록·요약), CXMT 점유율, 엔비디아 FQ1 FY24~FQ1 FY26. 설계 규칙대로 IR 원문으로 확인되면 tier를 primary로 바꾼다.
- 2차 자료인 비트·ASP 값도 매출 증감과 교차 확인은 통과했다(`VERIFICATION.md` 3절).

**kind**
- `estimate`: 역산하거나 계산한 값(2Q22·1Q23·4Q24 업계 합계, 매출로 계산한 점유율, 하이닉스 1Q24 비트), 연중 추정치(HBM 웨이퍼·비트 비중).
- `forecast`: 전망(2026~2027 수요·공급, 계약가 전망, capex 계획, 하이닉스 3Q26 가이던스). 같은 분기에 전망과 실적이 모두 있으면 둘 다 남겨 두었다.

**범위 (range_rules.csv)**
- 설계에 있는 규칙(low single-digit = 1~3% 등)을 그대로 쓰고, 설계에 없던 표현(over X, flat, in the X% range)은 데이터 담당이 제안한 규칙으로 처리했다. 팀이 바꾸면 `build_observations.py`의 `parse_range`와 이 파일을 같이 고친다.

**가격·물량**
- D램 가격지수는 계약통화 기준을 쓴다. 원화 기준은 환율 효과가 섞여 있다.
- dram_volume_proxy는 D램 수출액을 가격지수로 나눈 값(2020년 평균 = 100)이다. 실제 비트 출하가 아니라 근사치다.
- 수출액은 주요 9개국 합계이고 전 세계 합계가 아니다.
- 관세청 품목 그룹: dram(8542.32.1010), flash(8542.32.1030), multichip_mcp(8542.32.3000), mco(8542.32.40xx), other. HBM의 신고 코드는 공개 자료로 확인되지 않았다.
- 제품별(DDR5, LPDDR) 가격 시계열은 공개 자료에 없다. 계약가 증감의 서버·모바일 구분은 19번의 일부 분기뿐이다.

**비트·ASP (06, 07)**
- 하이닉스 2022년~1Q23은 공개 녹취를 찾지 못해 비어 있다. 이 구간은 마이크론 값으로 대신한다.
- 삼성전자는 분기별 비트·ASP를 숫자로 공개하지 않는다.

**capex·매출총이익률 (16, 18)**
- 16은 현금 설비투자(금융리스 제외)라 회사 발표 capex보다 작을 수 있다. 마이크로소프트는 2026년 리스 회계 변경에 주의.
- 18은 GAAP 기준이다. 콜의 non-GAAP 값과 0.3~0.7%p 차이가 날 수 있다.

**기타**
- 영업이익률은 회사 전체 기준이다. 삼성전자는 메모리 외 사업이 섞여 있다.
- 다음 업데이트: 마이크론 FQ4-26 실적 (2026-09-30), 삼성·하이닉스 3Q26 실적 (10월 말).
