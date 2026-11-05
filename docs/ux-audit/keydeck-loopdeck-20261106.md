# KeyDeck 루프덱 · 4트랙

## 사용 순서

1. 비트메이커 Studio의 **루프덱 · 4트랙**을 누릅니다. 기존 **연주·녹음** 화면과 바탕화면 위젯의 음악 메뉴에서도 열 수 있습니다.
2. BPM, 길이(1·2·4·8마디), 박자 맞춤을 정합니다. 트랙 1을 선택하고 **선택 트랙 녹음**을 누릅니다. 첫 패드부터 한 바퀴를 녹음한 뒤 자동으로 반복합니다.
3. 트랙 2를 선택하고 다시 녹음합니다. 트랙 1이 반복되는 동안 새로운 소리를 겹칠 수 있습니다. 같은 트랙에 더하려면 **겹쳐 녹음**을 켭니다.
4. 각 트랙의 **음소거**, **음량**으로 다음 타격의 재생을 조절합니다. **정지** 후 BPM이나 길이를 바꿀 수 있습니다. 길이를 줄이며 소리가 잘리는 경우와 기존 트랙을 다시 녹음하거나 지우는 경우에는 확인합니다.

숫자 키와 QWER/ASDF/ZXCV 입력은 패드에 초점이 있을 때만 연주합니다. BPM이나 선택 상자를 편집하는 입력은 연주하지 않습니다. 기존 단일 녹음은 별도로 남습니다. 마이크 입력이나 오디오 파일 믹스다운 기능은 추가하지 않았습니다.

Studio에서 연 루프는 초안입니다. 연주창을 닫고 Studio에서 **적용**해야 위젯에 반영되며, 실행 취소·다시 실행도 기존 방식으로 동작합니다. 바탕화면 위젯에서 연 경우 닫으면 저장됩니다. 다시 열었을 때 자동 재생하지 않습니다.

## 저장·재생 계약

- 기존 `beatmaker_recording` version 1과 `BeatmakerTimeline`은 그대로 유지합니다. 새 `beatmaker_looper`는 별도 선택 필드이며 손상되거나 알 수 없는 버전이면 그 필드만 제외합니다.
- 저장 위치는 beat 기준 tick입니다. BPM만 바꾸면 연주 위치를 유지하며, 박자 맞춤은 16분음표 또는 끄기입니다. 네 트랙은 하나의 절대 monotonic clock을 공유합니다.
- 최초 패드를 기다리는 동안 녹음 시간은 흐르지 않습니다. 기존 루프가 있으면 다른 트랙이 계속 반복되고, 새 트랙은 첫 패드를 누른 시점부터 한 바퀴를 녹음합니다. 빈 녹음은 기존 내용을 보존합니다.
- 재생 중 생긴 UI 지연을 다음 루프의 시작점에 누적하지 않습니다. 100ms보다 오래 지난 타격은 절전 복귀 시 몰아서 재생하지 않습니다. 한도는 트랙당 2,048타, 전체 8,192타입니다.
- 이벤트는 패드의 음원·WAV 경로·음량을 스냅샷으로 보관합니다. 이후 패드 설정을 바꿔도 기존 루프가 다른 음원으로 바뀌지 않습니다. 키 동작·단축키·프로그램 실행 명령은 루프에 저장하거나 재생하지 않습니다.
- 전체 덱 공유는 단일 녹음과 네 트랙의 사용자 WAV를 함께 내장·복원합니다. 페이지 가져오기는 받는 덱의 기존 단일 녹음과 루프를 보존합니다.

## 검증 범위

순수 도메인은 fake clock으로 첫 패드, 같은 위상의 레이어, 오버더빙, 정확한 경계, jitter·절전·시계 역행, 한도와 손상 입력을 확인합니다. Qt 테스트는 소리를 stub으로 바꾸고 실제 패드 입력, 녹음 완료 후 버튼 상태, 트랙 믹서, 초안·실행 취소·위젯 저장·재열기와 종료 정리를 검증합니다. WAV 공유 테스트는 임시 파일을 사용합니다.

근거는 `artifacts/beatmaker-loopdeck-20261106/`에 보존합니다. Native probe의 실제 백엔드 호출·상태, 물리 배율의 화면 캡처, 사람이 들은 음성 확인은 서로 다른 검증 결과로 기록합니다. 자동 테스트 통과를 사람의 청취 확인으로 표현하지 않습니다.

## 실제 화면 후속 확인

최초 Windows 100% silent probe는 입력·clock·저장·정지 check를 통과했지만, 직접 화면을 보며 검정 scroll 배경과 가려진 진행 상태를 발견했습니다. 이를 별도 UI 결함으로 기록하고 공통 reading surface, pad/mixer 2열·좁은 폭 세로 전환, 한 줄 트랙 mixer, 스크롤 밖 고정 transport/progress/status로 정리했습니다.

[재배치 후 100% 실행](../../artifacts/beatmaker-loopdeck-20261106/native-light-100-layout-final/probe.json)은 23개 check와 client/shadow 5쌍이 정상입니다. 이 화면에서 기본 OS 색상으로 남은 progress를 추가 발견해 공통 accent와 중립 groove로 수정했습니다. [해당 UI 회귀](../../artifacts/beatmaker-loopdeck-20261106/ui-progress-final.xml)는 19개가 정상 종료했습니다.

이후 [125% 실제 오디오 실행](../../artifacts/beatmaker-loopdeck-20261106/native-navy-125-placed-audio-final/probe.json)은 header/footer 배치와 백엔드 준비 등 47개 check를 통과했지만, 직접 본 가운데 영역이 약 192px로 줄어 16패드와 트랙 4가 함께 보이지 않았습니다. 이 실행을 최종 사용성 통과로 채택하지 않습니다. `nativeinside`, backend ready, header/footer 검사만으로 연주 영역 전체의 가시성을 판단할 수 없다는 재현 사례입니다.

고정 영역을 더 줄여 녹음/재생/정지와 겹쳐 녹음을 한 줄로 묶고 master volume과 닫기를 같은 footer에 두었습니다. 반복 안내는 녹음 tooltip으로, 마이크·저장 안내는 닫기 tooltip과 접근성 설명으로 보존했습니다. [최신 Qt geometry 회귀](../../artifacts/beatmaker-loopdeck-20261106/ui-compact-target-first.xml)는 11pt·880×736 client에서 16개 pad rect와 네 track row가 viewport 안에 있고 세로 스크롤이 없음을 확인합니다. 24pt에서는 고정 동작·닫기에 접근하고 가운데만 스크롤할 수 있습니다.

최종 실제 Windows 실행은 다음 두 경로를 채택합니다. 각 실행은 첫 패드 녹음, 자동 반복, 두 번째 레이어, 음소거·음량, 정지·닫기와 헤더·고정 동작·물리 화면 범위를 검증했습니다. 모두 오류 0·정상 종료이며, 임시 INI 격리와 실사용 설정 보존을 확인했습니다.

| 실행 | 확인 | 실제 화면 |
|---|---|---|
| 밝은 테마 · 100% | 46개 check, silent stub, 5상태의 client/shadow 10파일 | [두 레이어](../../artifacts/beatmaker-loopdeck-20261106/native-light-100-app-style-final/03-two-layers-playing.png), [보고서](../../artifacts/beatmaker-loopdeck-20261106/native-light-100-app-style-final/probe.json) |
| 네이비 · 125% | 47개 check, 실제 QSoundEffect 백엔드, 5상태의 client/shadow 10파일 | [16패드·4트랙 전체](../../artifacts/beatmaker-loopdeck-20261106/native-navy-125-app-style-final/03-two-layers-playing.png), [보고서](../../artifacts/beatmaker-loopdeck-20261106/native-navy-125-app-style-final/probe.json) |

두 최종 실행에는 메인 창의 실제 global/tooltip stylesheet builder도 적용했습니다. 125% 실행에서 음원 effect 32개가 모두 Ready였고 실제 play 전달은 7회, 요청 gain은 최대 0.2였습니다. 레이어 재생 중 effect 2개가 동시에 `isPlaying=true`였고, 정지 후에는 0개였습니다. 오디오 오류와 Qt 경고는 없었습니다. 이는 소프트웨어의 재생 경로·상태 증거이며, 사람이 스피커 출력을 청취하거나 장시간 리듬 정확도를 측정한 결과는 아닙니다.

최종 공통 UI·루프덱 통합은 [322 passed·69 subtests](../../artifacts/unified-ui-final-20261106/integrated-accepted-v2.xml), 정상 종료·임시 INI 격리·실사용 설정 보존으로 확인했습니다. 단독 fixture와 실제 공통 제목·전역 QSS의 차이를 최소 순서로 재현한 뒤, 제목을 포함한 geometry와 진행 막대의 로컬 선택색 역할을 보완했습니다.
