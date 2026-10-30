# 데이터 파이프라인 (설계 v3의 make data)
PY ?= python

.PHONY: data fetch test api

# raw/ → series/ → sources.csv, observations.csv (스키마 검사 포함)
data:
	$(PY) pipeline/clean_data.py
	$(PY) pipeline/build_observations.py

# 원본 다시 수집 (ECOS_KEY, DART_KEY, DATA_GO_KEY, SEC_UA 환경변수 필요)
fetch:
	$(PY) pipeline/fetch_keyed_data.py
	$(PY) pipeline/fetch_sec_capex.py

# 백엔드: 테스트와 API 서버
test:
	$(PY) -m pytest -q

api:
	$(PY) -m uvicorn api.main:app --reload
