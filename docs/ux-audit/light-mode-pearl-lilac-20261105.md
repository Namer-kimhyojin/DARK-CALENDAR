# 라이트 모드 Pearl Lilac 시안과 구현

2026-11-05 · 개발 소스 4.9.2. 먼저 [창·모달·서브 탭 오류 수정](ui-usability-followup-20261105.md)을 완료한 뒤, 이번 실행에서 라이트 모드 시안을 생성하고 공통 테마 코드에 적용했다. 기존 화면의 기능·입력 항목·자유 배치를 유지하며 색상과 읽기 계층을 정리했다.

## 시안과 색상 구성

![생성한 라이트 모드 디자인 시안](../../artifacts/light-mode-design-20261105/pearl-lilac-proposal.png)

이미지는 디자인 제안이다. 실제 실행 화면이나 새 기능의 구현 증거로 사용하지 않는다. 달력·흰 읽기 카드·단일 모달 제목·제목 아래 탭·라일락 주요 동작이라는 구성 원칙을 기존 Qt 컴포넌트에 적용했다. 기존 깃털 심벌과 모든 입력 항목을 유지했다.

| 역할 | 기준 색상 | 적용 방식 |
|---|---|---|
| 캔버스 | `#F6F7FB` | 밝은 회백색으로 흰 카드와 구분 |
| 카드·입력·모달 | `#FFFFFF` | 읽기 영역을 선명하게 유지 |
| 본문 | `#20283A` | 짙은 슬레이트 |
| 설명 | `#5E687C` | 불투명 보조 글자 |
| 주요 동작 | `#7653C4` | 선택·저장·활성 표시 |
| 선택 배경 | 연한 라일락 | 사용자 강조색에 맞춰 동적으로 혼합 |
| 구분선 | `#DDE2ED` 계열 | 헤더·표·탭의 경계 구분 |
| 토요일·일요일 | `#386EC4` · `#BA4961` | 밝은 배경에서 대비 확보 |

새로 고르는 네이비·라일락 계열의 밝은 쌍인 `Lilac Day` 프리셋을 갱신했다. 기존에 저장된 다른 계열·색상 쌍은 강제로 바꾸지 않는다. 다크 팔레트의 기존 값과 장식 표면의 투명도 조절도 유지한다. 모달 읽기 표면만 앞 단계에서 정한 불투명 계약을 따른다.

## 사용자 흐름과 구현

1. **모드를 선택한다.** 라이트·다크·시스템 모드가 같은 유효 테마 해석 경로를 사용한다. 메뉴와 명령 팔레트 모두 저장 배경색을 덮어쓰지 않는다. 색상 쌍이 없는 기존 설정은 저장값을 유지한 채 표시할 때 밝기를 조정한다.
2. **스타일을 고른다.** 모양 설정의 네이비·라일락 계열은 밝은 모드에서 Pearl Lilac 구성을 제공한다. 다른 계열과 직접 지정한 강조색도 계속 사용할 수 있다. 이미 저장된 옛 색상 쌍은 보존되므로 새 프리셋 색상은 해당 스타일을 다시 선택해 적용한다.

직접 배경색과 강조색의 출처는 독립적이다. 배경만 바꿔도 계열 강조색 연결은 유지되고, 모양 설정 재열기·취소·변경 없는 수락·강조색만 적용으로 원래 배경을 바꾸지 않는다. 카탈로그와 다른 저장 색상 쌍도 새 스타일을 명시 선택하기 전까지 유지한다.

3. **메인 캘린더를 읽는다.** 월간·주간·상단 도구·선택일 일정 카드가 공통 색상 역할을 사용한다. 하단 탭 오른쪽 빈 영역의 투명 계약은 유지한다. 좁은 날짜 칸의 제목은 기존 말줄임을 사용하며, 선택일 목록에서 전체 제목을 읽는다.
4. **관리창과 서브 탭을 연다.** 업무 관리 3탭, 위젯 관리자 3탭과 갤러리, 브리핑, 도움말, 체크리스트, 캘린더 관리 5탭, Google 설정 5탭에 같은 읽기 색상과 버튼 계층을 적용한다. 개별 위젯 스킨의 어두운 미리보기는 사용자의 별도 선택이므로 유지한다.
5. **캘린더 표시를 설정한다.** 표시 설정창이 저장된 원시 다크 색상 대신 현재 유효 라이트 테마를 사용하도록 수정했다. 창을 열어도 저장된 배경·강조색을 덮어쓰지 않는 픽셀 회귀를 추가했다.
6. **상태와 세부 설정을 읽는다.** 실제 화면에서 추가로 드러난 흰색 다중 선택 안내, 연한 초록·경고·오류 글자, Google의 잘린 인증 이동 버튼을 수정했다. 선택 안내는 유효 테마의 본문색을 쓰고, 두 토큰 builder가 같은 모드별 의미색을 제공한다. 인증 이동은 고정 폭 대신 글자와 스타일 padding에 맞게 늘어난다. 브리핑의 `매일 다시 알림` 제목은 시간·토글 위에 한 줄로 배치한다. 본문을 스크롤해도 저장·취소는 고정된다.

## 실화면 증거

Qt windows 플랫폼에서 강제 배율 없이 실제 96/120 DPI를 사용했다. QA는 임시 DB·INI와 샘플 일정을 사용하며 실제 계정에 연결하지 않는다. 메인 캘린더는 실제 bootstrap을 통과한 disposable OverlayApp이다. 라이트→다크→라이트로 실제 메뉴 핸들러를 호출한 뒤 월간·주간·좁은 화면을 캡처했다.

![실제 Windows 라이트 모드 월간 화면](../../artifacts/light-mode-design-20261105/native-main-125-final/01-monthly-full.png)

![실제 Windows 라이트 모드 주간 화면](../../artifacts/light-mode-design-20261105/native-main-125-final/02-weekly-full.png)

![라이트 관리창 제목과 탭 순서](../../artifacts/light-mode-design-20261105/native-subtabs-125-accepted/01-work-management-tab-0.png)

![브리핑 아래 설정과 고정 버튼](../../artifacts/light-mode-design-20261105/native-subtabs-125-accepted/10-daily-summary-settings-bottom.png)

![글자 잘림을 수정한 Google 인증 이동 버튼](../../artifacts/light-mode-design-20261105/native-subtabs-125-accepted/22-google-settings-tab-1.png)

최종 채택 캡처는 100% 서브 탭 24상태, 125% 서브 탭 25상태(브리핑 하단 스크롤 1상태 추가), 메인 월간·주간/좁은 화면은 100%·125% 각 4상태다. 모두 정상 종료, 작업 영역 내 배치, 캡처 오류 0, native 설정 변화 없음이다. [100% 서브 탭](../../artifacts/light-mode-design-20261105/native-subtabs-100-final/subtab-audit.json), [125% 서브 탭](../../artifacts/light-mode-design-20261105/native-subtabs-125-accepted/subtab-audit.json), [100% 메인](../../artifacts/light-mode-design-20261105/native-main-100-final/main-captures.json), [125% 메인](../../artifacts/light-mode-design-20261105/native-main-125-final/main-captures.json).

메인 화면의 투명 영역은 QA 전용 회색 배경 창 위에서 실제 desktop 픽셀을 캡처했다. 이는 사용자 바탕화면을 변경한 것이 아니다. 모달은 불투명 QA 소유 창과 OS HWND 캡처를 사용했다. 이전 단계의 실패 캡처는 삭제하지 않고 채택 결과와 구분한다.

## 검증 범위

라이트 팔레트·스타일 계열·모드 전환·모달 표면·달력·스플래시·설정 취소를 관련 회귀로 확인했다. 본문·설명은 대표 밝은 표면에서 4.5:1 이상, 보조·미세 글자는 3:1 이상을 검사한다. 이 수치는 전체 접근성 인증이나 모든 사용자 색상 조합의 보장은 아니다.

- 팔레트와 상태색 통합: **127 passed + 144 subtests**, 임시 INI 쓰기 174건·거부 0건. [결과](../../artifacts/light-mode-design-20261105/light-palette-and-state-final.xml).
- 모드·직접 배경색·모양 설정 재진입: **90 passed + 5 subtests**, 실제 Qt 다이얼로그의 취소·강조색만 적용·명시 계열 선택·저장된 옛 색상 쌍을 검사했다. [결과](../../artifacts/light-mode-design-20261105/custom-background-origin-final.xml).
- 선택 안내: **59 passed + 3 subtests**, 실제 QLabel 20조건의 최소 대비 **7.62:1**. [결과](../../artifacts/light-mode-design-20261105/selection-hint-regressions.xml).
- 브리핑 설정 배치·취소·공통 모달: **44 passed + 9 subtests**. [결과](../../artifacts/light-mode-design-20261105/daily-reminder-modal-regression.xml).
- Google 인증 버튼과 계정 UI: **56 passed**, 수정 전 140px 폭이 최소 글자 폭 154px보다 작아 실패하던 회귀를 보존했다. [수정 전](../../artifacts/light-mode-design-20261105/google-button-before.xml), [수정 후](../../artifacts/light-mode-design-20261105/google-button-after.xml).

테스트 수는 서로 중복되는 묶음별 실행 결과이며 합산하지 않는다. 실패 재현 XML과 중간 native 캡처는 덮어쓰지 않았다. `light-before`는 새 팔레트 전 이번 실행의 실제 밝은 화면이며, `native-subtabs-125`와 `native-subtabs-125-final`은 뒤에 수정한 상태색·버튼 폭까지 모두 반영한 최종 증거로 사용하지 않는다.

사용자 실제 DB·일정·계정·사용자 설정을 변경하거나 실행 중인 앱을 종료하지 않았다. 소스 변경이며 빌드·배포·Store 설치는 수행하지 않았다. Google/ICS 화면 검토는 실제 원격 동기화 성공 검증과 구분한다.
