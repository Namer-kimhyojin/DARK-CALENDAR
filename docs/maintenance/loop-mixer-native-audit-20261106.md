# 루프 믹서 실제 Windows 점검과 다중 모니터 보완

2026-11-06 KST. 이번 기록은 기존 루프 믹서를 실제 실행 소스에서 점검한 뒤 추가한 **오디오 입력 순서·녹음 대상·다중 화면 배치·진입 메뉴·스타일** 수정의 근거다. 최초 루프 믹서 전체 구현이나 배포·설치 검증 기록을 대신하지 않는다. 제품 버전 이력 등록과 D 실행 소스 반영은 root가 별도로 담당한다.

## 확인한 오류와 수정 범위

사용자 로그의 `CreateDIBSection failed (31849x26173 format6)`와 root가 읽은 저장 논리 크기 `25479 × 20938`, 해당 화면의 DPR `1.25`가 정확히 대응한다. 창 자체의 저장 크기가 커졌으며 그림자 여백만으로 생긴 오류는 아니다.

초기화·강제 복원·크기 맞춤에서 저장 값을 제한 없이 `resize()`로 보낸 경로는 resize spy로 재현했다. 거대 창이나 이미지를 실제로 할당하지 않았다. 첫 안전상한 수정 뒤 root의 실제 Windows 관찰에서도 `1120 × 920 → 1880 × 992`로 상한까지 커져, 상한만으로는 논리 크기의 누적을 막지 못함을 확인했다. 최초로 비정상 값을 만든 정확한 원래 Windows 메시지까지는 확정하지 않는다.

오디오는 서로 다른 두 가지 문제를 분리했다. WinMM 입력 버퍼를 물리 슬롯 번호로 읽으면 재사용된 ring의 캡처 순서가 뒤바뀌는 문제를 제출 순서 기준으로 보완했다. 이미 불러온 WAV의 `file` 트랙이 armed 상태이면 녹음에서 자기 자신을 다시 더해 두 배가 되는 문제는 live 입력 대상에서 `none/file`을 제외해 막았다. 기존 backing PCM과 armed 메타데이터는 보존하며 UI의 불필요한 교체 확인도 같은 기준을 사용한다.

## 새 배치 정책

- Qt의 화면·이벤트·위젯 좌표를 모두 논리 좌표(DIP)로 사용한다. 위치와 크기에 DPR을 수동으로 곱하거나 나누지 않는다. DPR은 네이티브 버퍼 예산 계산에만 사용한다.
- 정상 `fixed_w/h`는 사용자가 정한 논리 크기다. 화면/DPR 변경과 이동 저장은 그때의 Qt current size를 새 사용자 크기로 기록하지 않는다. 작은 화면에 들어갈 때만 실제 표시 크기를 줄인다.
- 드래그는 누적된 current size 대신 누르기 시작한 원본 DIP 크기를 사용한다. 작은 화면에 맞추면 잡은 지점의 상대 비율을 유지하고, 드래그 완료 시 실제 작업영역 안으로 맞춘다. Esc·기존 배치 되돌리기는 유지한다.
- 화면은 실제 포인터가 속한 화면, 창과 교집합이 가장 큰 화면, 가장 가까운 화면 순서로 선택한다. Windows의 논리 화면 사이 빈 공간 때문에 owner/primary 화면으로 갑자기 이동하지 않는다.
- 루프 믹서의 모든 크기 요청은 작업영역과 논리 각 축 4096px, 물리 각 축 8192px, 물리 총 16777216픽셀 예산으로 제한한다. 작은 창의 내용은 내부 스크롤을 사용한다. 같은 breakpoint에서는 컨트롤을 매번 다시 배치하지 않는다.
- KeyDeck은 기존 60–220% 확대 범위를 유지하며 화면에 맞추는 동안 live preview만 조정한다. 저장 배율·패드 데이터는 보존한다. 정수 배율 반올림으로 1px를 넘는 경우도 실제 크기를 재확인한다.
- 메인 창의 일반 제목 영역 이동은 지원되는 경우 `QWindow.startSystemMove()`를 우선하고, 지원하지 않는 경우 기존 수동 이동을 유지한다. 화면 이동 명령도 작업영역 내 이동 비율과 DIP 크기를 기준으로 한다. 최신 메뉴 후보는 manager가 생성하는 기존 위젯 메뉴와 KeyDeck 진입점을 유지한다.

## 실제 Windows에서 확인한 결과

원래 제품의 `Tool | Frameless` 창 형태를 유지한 별도 QA 프로세스로 3개 모니터를 4회 순회했다. 초기 표본을 포함한 **13표본 모두 통과, 정상 종료 코드 0**을 root가 확인했다.

| 화면 | 논리 화면 / 작업영역 | DPR | 실제 믹서 크기 |
|---|---|---:|---:|
| HP 1 | `(0,0) 1920×1080` / `1920×1032` | 1.0 | `1120×920` |
| HP 2 | `(1920,0) 1920×1080` / `1920×1032` | 1.0 | `1120×920` |
| 하단 모니터 | `(1018,1080) 1536×864` / `1536×816` | 1.25 | `1120×776` |

모든 표본에서 저장 의도 크기는 `1120×920`으로 유지됐다. 논리 크기 drift·작업영역 밖 배치·물리 예산 초과·이벤트 폭주가 없었고 guard가 작동한 표본도 없었다. 마지막 누적 이벤트는 resize 15회, layout 7회, DPR 변경 14회다. DB·오디오·네트워크·native QSettings·전역 글꼴 변경 시도는 각각 0회다. [실측 JSON](../../artifacts/loop-mixer-20261106/native-geometry-accepted/geometry-cycle.json).

첫 native helper 실행은 기능 표본이 통과했어도 QA 로그 파일이 열린 채 임시 폴더를 정리하여 종료 코드 1이었다. 그 실행은 정상 종료 근거에서 제외했다. root가 helper의 logging 정리를 보완한 뒤 재실행한 위 accepted 결과를 채택한다.

일반 UI의 요소 식별을 위한 별도 Windows QA에서는 **QA 프로세스 안에서만 `Tool → Window` metadata adapter**를 사용했다. 이 조건의 UI 클릭·표시 결과를 원래 Tool 창 배치 결과와 혼합하지 않는다. 원래 flags에 대한 배치 근거는 위 독립 13표본이다. QA 데이터와 자체 INI·캡처만 보관하며 사용자 앱 창이나 개인 프로필로 재현하지 않는다.

## 마이크와 실제 녹음의 확인 한계

현재 장치 프로브는 `input_devices=[]`, `input_opened=false`, `output_opened=false`, `microphone_device_missing`을 기록했다. 장치가 없는 경우와 장치는 있으나 PCM 형식을 지원하지 않는 경우를 구별하도록 수정한 뒤 root가 다시 확인한 결과다. PCM은 저장하지 않았다. **물리 마이크 캡처 품질·권한·실제 지연·청취 성공은 확인하지 못했다.** [장치 경계 기록](../../artifacts/loop-mixer-native-audit-20261106/microphone-signal.json).

root의 실제 두 KeyDeck을 이용한 16초 녹음과 오버더빙은 컴퓨터 사용이 사용자 physical Escape로 중단되어 **미확인**이다. synthetic 입력으로 통과한 테스트를 실제 장치 녹음·청취 성공으로 표현하지 않는다. 후속 확인 결과는 root가 이 절에 추가한다.

## 격리 회귀와 자료 보존

| 검증 | 결과 | 근거 |
|---|---:|---|
| 두 KeyDeck bus·가짜 마이크 PCM·backing WAV·오버더빙·믹싱·프로젝트/WAV 왕복 | 89 통과 / 정상 0 | [audio accepted](../../artifacts/loop-mixer-20261106/audio-followup/audio-and-entrypoints-accepted.xml) |
| 입력 ring 순서·재사용·정리와 기존 오디오 회귀 | 99 통과 / 정상 0 | [FIFO final](../../artifacts/loop-mixer-20261106/audio-followup/input-ring-final.xml) |
| 믹서/공통 배치·DPR·Esc·기존 resize·화면 선택 | 128 통과 / 정상 0 | [다중 화면 accepted](../../artifacts/loop-mixer-20261106/multimonitor-accepted.xml) |
| manager·기존 위치 복원 관련 감사 | 72 통과 / 정상 0 | [복원 final](../../artifacts/loop-mixer-20261106/common-restore-final.xml) |
| 메인 창 화면 이동·native drag 경계·메뉴 | 63 통과 / 정상 0 | [main/menu accepted](../../artifacts/startup-optimization-20261106/main-monitor-native-menu-accepted.xml) |
| 공통 화면 선택 helper와 기존 geometry·encoding | 95 통과 / 정상 0 | [screen helper](../../artifacts/loop-mixer-persistence-20261106/screen-helper.xml) |
| 테마/패널/위젯 전용 화면 스타일 | 89 통과 / 정상 0 | [style final](../../artifacts/widget-mode-surface-20261106/focused-final.xml) |

이 수치는 중복되는 관련 회귀를 포함하므로 서로 더해 전체 고유 테스트 수로 제시하지 않는다. 소스 UTF-8 compile·Ruff 0.15.9·관련 encoding 검사와 diff-check도 확인했다. 최초 실패 XML은 삭제하지 않았다. geometry 통합 중 live clock의 시각에 따라 최소폭이 달라졌던 snap fixture는 의도한 240/200px 상자 크기를 명시하고 기존 우측 경계 assert를 유지했다. 예전 10월 감사의 기본 10pt 기대 5개는 현재 11pt 정책과 다른 별개 실패로 보존했으며 이번 패치에 맞추어 임의 수정하지 않았다.

B의 테스트는 임시 APPDATA/LOCALAPPDATA·INI와 장치 없는 backend를 사용했고 실제 DB 접근과 native QSettings 생성을 차단했다. 실제 QSettings는 root가 해당 루프 인스턴스의 기존 6개 키를 **읽기 확인만** 했고 이번 점검에서 값을 바꾸지 않았다. 개인 DB·기존 프로필·사용자 프로젝트를 테스트 입력으로 쓰지 않았다. QA 자체 INI 보관은 사용자 설정 복원이나 대체가 아니다.

최종 수정 파일과 테스트의 raw/LF SHA, 각 동결 근거, D에만 있던 persistence 테스트를 C로 동일 바이트 복사한 기록은 [final-fix-files.json](../../artifacts/loop-mixer-native-audit-20261106/final-fix-files.json)에 있다. 최초 루프 믹서 전체 파일 목록은 포함하지 않는다. 스타일은 C의 4개 제품 파일 동결을 취합했으며 기존 4개 관련 테스트 모듈과 offscreen dark/light 2개 렌더를 통과했다. 이를 실제 Windows 스타일 화면 검증으로 표현하지 않는다. 최종 실제 녹음 결과는 별도 후속 확인 항목으로 남긴다.
