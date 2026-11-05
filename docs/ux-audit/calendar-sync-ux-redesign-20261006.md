# 캘린더 동기화·ICS 구독 UI/UX 재설계 — 2026-10-06

사용자 요청: 캘린더 동기화와 ICS 구독 화면을 사용자 중심으로 전면 재설계한다.
이 기록은 현재 개발 폴더의 구현과 로컬 검증을 다룬다. 실행 중인 앱이나 Store 설치본에 업데이트가 적용됐다는 뜻은 아니다.

## 재설계 기준과 구현

기존 화면에서는 서비스·권한·기본 저장·동기화 선택 상태가 캘린더 이름 뒤 한 줄에 모였고,
선택한 캘린더의 여러 작업 버튼이 같은 영역에 노출됐다. 읽기 전용·미선택 상태에서
사용할 수 없는 작업은 버튼 비활성 상태만으로 이유를 파악해야 했다.

새 화면은 사용자가 하려는 작업에 따라 **내 캘린더 → 연결 및 구독 → 문제 해결**로 구분한다.
내 캘린더가 기본 진입 화면이며 기존 서비스/캘린더/문제의 내부 탭 인덱스와 동기화 경로는 유지한다.

| 사용자 작업 | 구현된 동작 |
|---|---|
| 표시할 캘린더 찾기 | 목록에서 캘린더 이름과 출처·읽기 전용·표시·갱신 상태를 두 줄로 확인하고, 검색과 서비스 필터로 범위를 줄인다. |
| 선택한 캘린더 설정 변경 | 상세 영역을 표시와 저장, 이름과 색상, 구독 갱신으로 나눈다. 선택한 캘린더에서 사용할 수 있는 작업을 보여준다. |
| 새 일정의 기본 저장 위치 지정 | 현재 기본 대상을 별도로 표시한다. 읽기 전용 또는 가져오기 대상에서 제외된 캘린더는 버튼과 설명·도움말에 불가 이유를 알린다. |
| 서비스 연결 | Google·ICS를 먼저 보여주고 다른 미연결 서비스는 펼쳐서 찾는다. 이미 연결됐거나 작업·문제가 있는 서비스는 항상 표시한다. |
| 처음 ICS 구독 추가 | 미등록 ICS의 주 버튼은 **주소로 구독**이다. 이 버튼에서 구독 입력창으로 바로 이어지며 Google 로그인을 요구하지 않는다. |
| ICS 주소 입력 | 주소부터 입력·붙여넣고 이름을 정한다. 주소 형식과 필수 입력을 즉시 확인하며 모두 유효할 때만 제출할 수 있다. |
| ICS 연결 결과 확인 | 주소 형식 검사와 실제 일정 가져오기를 구분한다. 아직 수신하지 않은 구독에는 가져온 기록이 없음을 표시한다. |
| ICS 사용 방법 이해 | 구독 주소 찾기 도움말을 펼쳐 Google·Outlook·iCloud의 주소 복사 경로를 읽는다. 입력 본문은 스크롤되고 제출·취소 버튼은 footer에 남는다. |
| 표시와 갱신 독립 조절 | 일정 화면 표시, 이 구독 갱신, 전체 ICS 자동 갱신을 각각 구분한다. 갱신을 중지해도 이미 가져온 일정은 유지된다는 안내를 제공한다. |
| 구독 주소 확인·공유 | 기본 화면에서는 호스트만 보여주고 주소의 나머지를 숨긴다. 주소 보기·복사 작업을 제공하며 다른 구독을 선택하면 주소 노출 상태를 초기화한다. |
| 문제 해결 | 문제 연결만 목록에 표시하고 원인·다음 조치·재시도·설정 경로를 상세 영역에 제공한다. 문제가 없으면 빈 상태 안내를 보여준다. |
| 좁은 창에서 작업 | 캘린더 목록과 상세 영역을 위아래로 배치한다. 캘린더 본문을 스크롤해 구독 주소 수정·갱신·해제 버튼에 접근할 수 있다. |

상태 배지, 마지막 갱신 시각, 현재 안내를 분리해 자동 갱신 켜짐이 최신 일정 수신 완료로 보이지 않게 했다.
ICS 상태 배지는 연결 성공 대신 등록된 구독 수를 표시한다.
공통 시간대와 자동 갱신 전체 설정은 접힌 보조 영역에 둔다.
색상·상태·카드 스타일은 공통 다이얼로그의 테마 토큰을 사용한다.

## 데이터와 작업 상태 계약

- 기존 동기화 조정자와 Google·Outlook·CalDAV·ICS 처리 경로를 사용한다. 이번 재설계에서 동기화 엔진이나 DB 스키마를 변경하지 않는다.
- 표시 여부와 원격 가져오기 선택을 구분한다. 읽기 전용 캘린더를 기본 저장 대상으로 지정하는 동작은 화면과 처리 함수 양쪽에서 차단한다.
- 진행 중인 서비스의 중복 갱신을 막고, ICS 작업 중에는 구독 추가·주소 수정·갱신 선택 변경·해제를 차단한다.
- 구독 주소 수정은 기존 ID·일정·색상·표시 설정을 보존하는 기존 전용 함수를 사용한다.
- 문제 화면의 서비스 재시도는 선택한 서비스만 대상으로 한다. ICS 재시도는 활성 실패 구독만 대상으로 하며, 개별 상세의 갱신은 선택한 구독 한 개만 대상으로 한다.
- 과거 오류가 남은 일시정지 구독을 현재 활성 오류보다 먼저 선택하지 않는다.
- ICS 문제 상세에는 활성 실패 구독의 이름과 실제 오류 원인을 표시한다. 일반적인 갱신 실패 설명만 표시하지 않는다.
- 작업 시작 안내는 실제 작업이 종료되면 제거한다. 완료·실패 뒤에도 진행 중이라는 안내를 남기지 않는다.
- UTC 등 시간대 정보가 포함된 구독 수신 시각은 현지 시간으로 변환해 허브와 상세 화면의 시각이 일치하게 표시한다.
- 구독 해제의 확인 문구는 구독 목록 제거·갱신 중지와 원본 및 이미 가져온 일정 보존을 구분한다.

## 완료한 로컬 검증

검증은 독립 임시 SQLite DB와 별도 QSettings, 합성 계정·일정으로 수행했다.
외부 구독 주소와 사용자 계정은 사용하지 않았으며 네트워크 워커 실행을 대체해 UI·경로·상태 전이를 확인했다.

| 검증 | 결과 |
|---|---|
| 신규 사용자 흐름 최초 7개 검사 | **7 passed**, 26.93초 |
| 주소 숨김·선택 변경 초기화, 펼친 주소 도움말의 footer 접근성 보강 후 해당 검사 | **2 passed**, 13.67초 |
| 진행 안내 종료와 일시정지 실패 구독을 제외한 오류 선택 경로 보강 후 해당 검사 | **2 passed**, 19.36초 |
| 진행 안내 종료를 포함한 신규 8개 검사 전체 | **8 passed**, 52.28초 |
| 수신 시각의 현지 시간 변환과 긴 문제 설명의 작업 버튼 접근 | **2 passed**, 16.38초 |
| 이름·실제 ICS 오류 표시를 포함한 최종 신규 사용자 흐름 전체 | **9 passed**, 64.46초 |
| 최종 렌더 보완 후 상태 배지의 실제 표시·작업 중 상태와 좁은 창 버튼 접근 | **2 passed**, 16.37초 |
| 신규 검사 파일 Ruff | 통과 |

위 숫자는 회차별 검사 결과이며 서로 겹치는 검사를 포함한다. 합산 검사 수가 아니다.
신규 파일 `tests/test_calendar_sync_redesign.py`는 현재 9개 검사로 다음 흐름을 다룬다.

1. 내 캘린더 기본 진입과 미연결 ICS의 직접 추가 행동.
2. Google·ICS 작업 중 중복 실행 방지와 구독 수정 잠금, 실제로 보이는 상태 배지 및 작업 중 상태.
3. 읽기 전용·비활성 캘린더의 기본 저장 금지 및 이유 안내.
4. 활성 ICS 실패 구독으로 이동, 주소 표시 초기화, 선택한 구독만 재시도.
5. 완료 후 허브·구독 상세의 진행 안내 제거.
6. UTC와 다른 시간대의 수신 시각을 현지 시간으로 표시.
7. 선택한 서비스만 재시도.
8. 640×500 창과 긴 안내에서 구독 작업·문제 해결 버튼 스크롤 접근.
9. 붙여넣기 주소 형식·필수 입력·정규화, 실제 가져오기 전 성공 시각 미기록, 펼친 도움말의 footer 접근.

최종 신규 검사와 Ruff 실행 명령:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& '.venv/Scripts/python.exe' -m pytest tests/test_calendar_sync_redesign.py --basetemp artifacts/sync-redesign-final-nine-qa -p no:cacheprovider
& '.venv/Scripts/python.exe' -m pytest tests/test_calendar_sync_redesign.py -k 'busy_sync or controls_are' --basetemp artifacts/sync-redesign-badge-final-qa -p no:cacheprovider
& '.venv/Scripts/python.exe' -m ruff check tests/test_calendar_sync_redesign.py
```

## 최종 확인란

아래 결과는 현재 개발 소스에서 확인했다.

| 항목 | 상태·증거 |
|---|---|
| 신규 9개 검사 전체 최종 재실행 | **9 passed**, 64.46초. 위 실행 명령의 CLI 결과 확인 |
| 기존 동기화·ICS·다이얼로그 회귀 검사 | **124 passed**, 종료 코드 0. 기존 동기화·ICS 103개, Google 표시 1개, 인코딩 12개, 수집 당시 신규 UX 8개. 이후 추가된 시각 검사와 최종 UX 9개는 별도 실행에서 통과. `artifacts/sync-redesign/regression-result.json` |
| 인코딩 정책·유틸, 변경 범위 Ruff·diff 검사 | **12 passed**, `scripts/run_encoding_guard.py` 성공. 변경 Python Ruff·scoped `git diff --check` 통과. 기존 접근 제한 캐시 2개에 대한 compileall 경고는 남았으나 종료 코드 0. |
| 번역 구조·런타임 | **33 passed**. 새 키 106개를 19개 번들에 동기화. 한국어·영어 번역 완료, 나머지 17개는 이번 신규 키에 영어 fallback. JSON·중복 키·placeholder·런타임 조회 검증 통과. |
| 다이얼로그 라우터 | **6 passed**. `artifacts/sync-redesign/router-regression.xml` |
| 한국어·영어, 어두운·밝은 테마 Qt 렌더 | 실제 다이얼로그 합성 데이터 캡처 **23개**. 한국어 dark/light, 영어 dark의 캘린더·구독·연결·문제·입력·가이드 화면 판독. |
| 넓은 창·좁은 창, 미연결·진행·오류 상태 렌더 | 1040×900 목록·상세 2열, 640×500 세로 전환 및 스크롤 확인. 미연결·Google 작업 중·ICS 접근 거부 상태를 확인했다. 긴 오류는 별도 스크롤로 해결 버튼에 접근한다. |

관련 구현: `calendar_sync_hub.py`, `calendar_manager_page.py`, `ics_subscription_dialog.py`, `calendar_sync_style.py`.
신규 사용자 흐름 검사: `tests/test_calendar_sync_redesign.py`.

회귀 실행 명령:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTHONUTF8='1'
& '.venv/Scripts/python.exe' -m pytest tests/test_calendar_sync_coordinator.py tests/test_sync_unification.py tests/test_calendar_sync_redesign.py tests/test_ics_snapshot_safety.py tests/test_ics_timezones.py tests/test_gcal_calendar_visibility_ui.py tests/test_encoding_policy.py tests/test_encoding_utils.py -q --basetemp artifacts/sync-redesign/final-regression -p no:cacheprovider
```

화면 증거:

- [내 캘린더 — 어두운 테마](../../artifacts/sync-redesign/ko-dark-calendars.png)
- [연결 및 구독 — 밝은 테마](../../artifacts/sync-redesign/ko-light-connections.png)
- [ICS 입력](../../artifacts/sync-redesign/ko-dark-ics-form.png)
- [ICS 접근 거부 복구](../../artifacts/sync-redesign/ko-dark-issues.png)
- [작은 창의 구독 작업](../../artifacts/sync-redesign/ko-dark-narrow-bottom.png)
- [영어 주소 찾기 가이드](../../artifacts/sync-redesign/en-dark-ics-guide.png)

캡처 생성기는 `artifacts/sync-redesign/render_previews.py`이며 사용자 DB·계정·구독 주소를 읽지 않는다.
offscreen의 기본 800px 모니터 제한은 캡처에서만 큰 화면으로 조정했고,
Malgun Gothic 폰트를 명시적으로 로드해 한글 렌더를 확인했다.
번역 검증 증거는 `artifacts/calendar-sync-redesign/i18n-validation.json`에 기록했다.
번들 파일 전체 canonical 형식 검사 1개는 변경 전부터 한국어·영어의 기존 배열 줄바꿈 형식으로 실패했다.
이번 키 추가 전 원문으로 같은 실패를 확인했으며, 관련 없는 기존 형식을 일괄 변경하지 않았다.

실제 외부 서비스의 구독 주소로 가져오기가 성공하는지, 사용자 Google OAuth 연결이 복구되는지는 검증하지 않았다.
이 문서의 로컬 UI 검증은 외부 인증 문제 해결을 뜻하지 않는다.
Store 설치본의 변경·설치·동작과 커밋·푸시·배포 상태도 이 문서의 검증 범위에 포함하지 않는다.
