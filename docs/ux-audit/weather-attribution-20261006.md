# 날씨 위젯 출처 표시 정리 — 2026-10-06

날씨 위젯 하단에 고정 표시하던 `MET Norway · GeoNames` 링크 줄을 제거했다. 날씨·온도·도시 템플릿과 로딩·오류·이전 날씨 상태 안내는 보존했다. 소스 변경이며 Store 설치본은 업데이트하지 않았다.

출처는 우클릭 → **날씨 데이터 출처**와 일반 날씨 설정창의 같은 버튼으로 확인한다. 두 경로는 같은 읽기 전용 다이얼로그를 사용하며 설정·위치·크기·타이머·네트워크 요청을 변경하지 않는다.

공식 [MET Norway 안내](https://api.met.no/doc/License)와 [GeoNames 데이터 안내](https://download.geonames.org/export/dump/readme.txt)는 출처 명시를 요구한다. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)의 합리적인 방식의 표시 조건에 따라 사용 화면에 계속 붙이는 대신 쉽게 찾을 수 있는 출처 화면으로 옮겼다. 제공처·원본 데이터·이용 조건·라이선스 링크와 앱의 데이터 추출/단위/표시 형식 변환 및 비보증 안내를 포함했다.

기존 번역은 유지하고 19개 로케일에 7개 안내 문자열을 추가했다. 한국어와 영어를 제공하며 나머지 언어에는 영어 대체값을 사용한다.

## 검증

- 출처 화면/위젯 회귀 4개와 기존 날씨 로딩/제공자 22개, 총 26개 통과 — [JUnit](../../artifacts/weather-attribution-20261006/tests.xml).
- 날씨 에셋과 번역 구조/런타임 검사 19개 통과 — [JUnit](../../artifacts/weather-attribution-20261006/locale-assets-tests.xml). 새 번역 키 순서를 한국어/영어의 정규 형식에 맞춰 확인했다.
- 데이터 변경, 프리셋, 크기 조절, 그림자 변경 이후에도 하단 출처가 재생성되지 않는다. 성공·로딩·오류 상태 안내는 유지된다.
- 실제 메뉴 클릭과 설정 버튼으로 같은 화면을 열고, 제공처/라이선스 링크와 사용자 설정·네트워크·배치·타이머 불변을 검증했다.
- 임시 INI 설정과 고정 날씨 데이터로 Windows 네이티브 투명 창을 렌더링했다. 사용자 설정은 실행 전후 보존하고 외부 날씨 요청은 보내지 않았다 — [결과](../../artifacts/weather-attribution-20261006/results-native.json).
- 관련 Ruff·diff 공백 검사·인코딩 가드 통과(인코딩 검사 12개). compileall의 기존 접근 불가 pytest 캐시 두 곳 경고는 남아 있다.

## 미리보기

- [출처 문구를 제거한 날씨 위젯](../../artifacts/weather-attribution-20261006/weather-clean.png)
- [별도 출처 화면](../../artifacts/weather-attribution-20261006/sources-native.png)
