# 2026-11-02 배포 후보 종료 오류 진단

4.9.1 후보는 공개하지 않았다. 현재 실행 입력 704개로 만든 CI 패키지의 첫 검증에서 새 프로필 1·2회는 정상 종료했지만 3회째 정상 종료 확인 뒤 `0xc0000005`로 끝났다. 당시 모든 Python 회귀와 빌드는 통과했으므로, 소스 검사와 실제 EXE 종료 검증을 구분해 공개를 차단했다.

## 재현과 증거

- Build Release `41366550223`, build commit `c0d4b01d903ab4cb89427d312ad1491d69c852fd`.
- 원본 native 실패 artifact `13107572590`, ZIP SHA-256 `da6479ed3f7211623216b95fceb07749a07dfcea7e809bac7cdb38cb287bced3`.
- 진단 도구에 예외 주소·매개변수 및 second-chance의 읽기 전용 덤프 수집만 추가했다. 예외는 원래 처리기로 전달하고 실패 판정은 유지한다. 진단 도구 회귀 173건 통과.
- QA commit `24402d7fa0689cfb2b0b291a1afaa12c6e80b62c`에서 후보 commit·원시 payload artifact ID·SHA와 제품/의존성/패키지 입력 불변을 대조했다. 새 QA 도구만으로 버전을 올리거나 패키지를 다시 만들지 않았다.
- 첫 진단 run `41367788359`는 후보 6회가 통과했다. 최초 오류가 설명되지 않아 이 성공만으로 공개하지 않았다.
- 추가 진단 run `41368156104`는 후보 새 프로필 3회가 정상 종료했지만, 업그레이드 fixture를 만드는 이전 공개 4.3.3 EXE의 종료에서 같은 `0xc0000005`가 재현됐다.
- 추가 실패 artifact `13107888514`, ZIP SHA-256 `fc389a1bd08148f1a33ff28f137fde49c9eb1059052401be3bb61ae53aef1ff5`. 덤프의 실패 PID 2948 / TID 4420, fault address `0x00007fffb7310496`은 이전 패키지의 `PyQt6/sip.cp313-win_amd64.pyd + 0x10496`이다. 주변 스택에는 QtCore와 Python 종료 경로가 있다. 이 덤프는 이전 버전의 추가 재현이며, 덤프가 없는 최초 4.9.1 오류의 정확한 명령 주소까지 같은 것으로 단정하지 않는다.

## 적용할 수정과 검증 범위

현재 runtime lock은 `PyQt6-sip==13.11.1`이었다. [SIP upstream 종료 충돌 보고](https://github.com/Python-SIP/sip/issues/115)는 다른 Python/Qt 조합에서 13.11.1 → 13.12.0 뒤 종료 오류가 사라진 사례와 유지보수자의 수정 설명을 담고 있다. [공식 SIP 릴리스 기록](https://python-sip.readthedocs.io/en/latest/releases.html#v6-16-0)도 ABI v13.12.0의 오류 수정을 설명한다. 이 자료와 실제 SIP 내부 덤프를 근거로 최소 범위의 13.12.0 업데이트를 선택한다. Python·PyQt6·Qt·SQLite의 제품 버전은 그대로 유지한다. 실제 기존/새 패키지의 6회 기동·정상 종료/재시작 검증이 필요하며, 해당 보고의 Python 3.14 재현을 이 프로젝트 Python 3.13의 완전한 원인 입증으로 쓰지 않는다.

별도로 공통 버튼 번역기가 매핑하지 않은 Qt 문구까지 빈 문자열로 바꾸는 오류를 격리 재현했다. null QString을 반환해 원래 Qt 문구로 대체하도록 수정했고 관련 44건이 통과했다. 이 오류와 native 종료 오류를 같은 원인으로 단정하지 않는다.

원본·실패·성공 증거는 `artifacts/deployment/4.9.1/20261102-0908/`에 보존한다. 새 dependency와 번역 수정은 다른 입력이므로 4.9.2 새 후보로 빌드한다. 기존 후보 태그·파일·이력은 바꾸지 않는다. 개인 DB와 설치 앱은 진단 대상에 포함하지 않았다.

## 로컬 도구 제한

Windows 앱 제어 정책이 일부 pre-commit 보조 실행 파일을 차단했다. 정책을 변경하지 않았으며, 통과한 진단 테스트·인코딩·Ruff·YAML·compile 및 staged whitespace/conflict/debug-statement 검사를 근거로 GitHub API에 정확한 QA bytes를 기록하고 원격 CI를 확인했다. 이 제한을 회피하기 위해 차단 실행 파일을 이동하거나 보안 정책을 끄지 않았다.


## 4.9.2 최종 결과

SIP 13.12.0과 Qt 문구 수정 후 최종 격리 회귀는 3,168건 통과, Windows 심볼릭 링크 권한 제약 4건 건너뜀이다. 단일 build commit `4818a7b8957c9f59af8e37fb6632256946bff5f3`의 동일 payload를 QA commit `fba7fb1a231f496c5c79d53ff06cd84a841ab37e`의 별도 VM run `41371580195`에서 검증했다. 새 프로필 3회와 기존 데이터 업그레이드 프로필 3회가 모두 정상 기동·정상 종료·재시작했고, 6개 화면과 DB 보존·무결성·원본 payload 해시를 확인했다. 최종 run에서는 이전 4.3.3 fixture도 정상 종료했으므로 제한적 legacy 예외 분류를 사용하지 않았다.

원본 build run의 앞선 OS 화면 가림 실패와 이전 4.3.3 SIP 종료 실패 증거는 각각 별도로 보존한다. 최종 성공이 앞선 실패를 삭제하거나 최초 4.9.1의 정확한 원인을 소급 입증하지 않는다. 6회 성공은 간헐적 오류가 전혀 없다는 보장이 아니다.

GitHub release `430981895`로 같은 4.9.2 파일을 공개하고 자산 6개를 새로 다운로드해 검토한 draft와 완전히 일치함을 확인했다. 증거는 `artifacts/deployment/4.9.2/20261102-0943/`의 `private-candidate-verification.json`, `candidate-verification.json`, `native-visual-review.json`, `public-download-verification.json`에 있다. Store 제출과 실제 설치판 인수는 아직 별도 대기 단계다.
