# 제품 버전과 변경 이력 관리

2026-10-20 승인한 배포 단위 체계다. 기존 단일 숫자 올림 규칙은 과거 이력 검증에만 사용한다.
이미 공개한 패키지·태그·제출과 기존 이력은 그대로 보존한다.

## 버전 결정 기준

| 구분 | 증가 기준 | 예시 |
|---|---|---|
| PATCH | 오류·성능·안정성 개선을 묶어 배포 | 4.6.9 → 4.6.10 |
| MINOR | 기존 데이터·설정을 유지하는 새 기능 배포 | 4.6.10 → 4.7.0 |
| MAJOR | 기존 데이터·설정·연동 계약과 호환되지 않는 변경 배포 | 4.7.0 → 5.0.0 |
| 변경 기록 | 구현·모듈·테스트·CI·스킬·문서 수정 | 제품 버전 유지 |

수정 횟수나 파일 수는 버전 증가 횟수가 아니다. Store 업로드 자체도 증가 사유가 아니다.
모듈·라이브러리를 교체해도 사용자가 받는 변화의 의미로 배포 버전을 결정한다.
각 숫자는 한 자리로 제한하지 않는다. 앞 세 자리는 MSIX 범위 안의 정수이고 첫 자리는 1 이상,
나머지는 0 이상, 모두 65535 이하이며 선행 0은 금지한다. MSIX/PE는 같은 버전 뒤 `.0`을 붙인다.

## 변경 기록과 읽기 전용 검사

```powershell
.venv/Scripts/python.exe scripts/manage_version.py record --kind change --event-id <고정-작업-ID> --summary "수정 내용" --files <변경 파일들>
.venv/Scripts/python.exe scripts/manage_version.py scan --strict
```

`change`, `module`, `store`는 이력 분류이며 모두 제품 번호를 유지한다. 같은 ID·입력 재시도는
새 이력을 만들지 않는다. 같은 ID로 다른 입력을 덮어쓰려 하면 실패한다. `--files`를 주면 해당
파일만 등록하므로 별개의 미등록 편집을 흡수하지 않는다. 생략하면 현재 전체 실행 입력을 등록하므로
전체 변경을 검토한 경우에만 사용한다. 개인 DB·토큰·사용자 설정은 수집하지 않는다.

`scan`은 추가·수정·삭제된 미등록 실행 입력 목록을 반환하며 파일을 쓰거나 번호를 올리지 않는다.
`scan --strict`는 누락이 있으면 종료 코드 2다. `check`는 기준 버전과 생성된 메타데이터 일치를
확인한다. `run.bat`은 이 읽기 전용 일치 검사 후 앱을 실행하며 자동 변경 등록을 하지 않는다.

## 배포 범위 확정

```powershell
.venv/Scripts/python.exe scripts/manage_version.py prepare --bump patch --event-id release-<고정-ID> --summary "이번 배포의 변경 묶음"
# 명시적인 번호가 필요하면 --bump 대신 --version X.Y.Z 사용
.venv/Scripts/python.exe scripts/manage_version.py check --strict --for-build --expected <확정 버전>
```

`prepare`만 제품 버전을 결정한다. 먼저 미등록 입력을 기록해야 한다. 최종 입력을 예약하며 같은
릴리스 ID 재시도는 번호와 입력을 유지한다. 실제 공개 버전보다 높고 현재 기준 번호보다 낮지 않아야
한다. 이미 같은 번호로 예약한 입력을 바꿔 새 패키지를 만들려면 높은 번호를 선택한다. 공개 파일·
태그·기존 업로드를 교체하거나 이름만 바꾸지 않는다.

테스트·QA 도구만 보완했을 때는 번호를 올리지 않고 별도 Git 커밋·CI 실행 ID로 추적한다. 기존
후보 재검증은 원본 build commit·payload SHA와 새 QA commit·검사 결과를 연결한다. 동일 후보를
재사용하는 경로와 새 패키지를 재빌드하는 경로를 혼합하지 않는다.

## 기준 원본과 생성 파일

`version-history.json`의 `current_version`과 `release.date/channel`이 제품 메타데이터 기준이다.
`sync`/`prepare`가 `calendar_app/app_metadata.py`, `pyproject.toml`, `AppxManifest.xml`,
`version_info.txt`를 원자적으로 맞춘다. 생성된 숫자를 직접 편집하지 않는다.

```powershell
.venv/Scripts/python.exe scripts/manage_version.py sync
```

`sync`는 기준 번호를 바꾸지 않고 생성 파일의 불일치를 복구한다. 공식 빌드는 예약된 전체 입력을
검사한 뒤 `sync --for-build --expected X.Y.Z --channel Stable --date YYYY-MM-DD`를 호출한다.
PackageVersion은 반드시 X.Y.Z.0이다. 빌드용 대응 소스의 공개 안내 준비는 실제 공개·인증·게시
완료 증거가 아니다.

## 공개·Store·설치·DB 상태

- 제품 버전, Git commit, CI run/artifact ID, 패키지 SHA-256을 함께 기록한다.
- GitHub 공개, Store 제출 ID·인증·게시, 이 PC의 설치 버전·실행 확인은 별도로 확인한다.
- `APP_PUBLISHED_VERSION/DATE`와 실제 홈페이지는 확인된 GitHub 공개 버전을 표시한다.
  개발 이력이나 Store 제출만으로 홈페이지의 마지막 공개 버전을 바꾸지 않는다.
- DB 스키마 단계는 기존 DB 마이그레이션 체계가 관리한다. 제품 버전을 DB 스키마 번호로 사용하거나
  제품 버전을 바꾸기 위해 DB를 수정하지 않는다.

## 기존 이력 전환과 중단 복구

```powershell
.venv/Scripts/python.exe scripts/manage_version.py migrate
```

schema 1 이벤트는 원래 증가·override 규칙으로 검증하고 그대로 남긴다. schema 2로 전환하는
policy 이벤트는 현재 번호를 유지한다. 과거 개발 번호 4.6.9와 공개 4.6.4도 보존한다. 이후 `record`는
번호를 올리지 않는다. 이전 `override` 명령은 새 체계의 번호 결정에 사용하지 않는다.

변경 명령은 `.versioning/`의 배타적 잠금·원자 교체·저널을 사용한다. 중단된 쓰기는 다음 변경
명령이 복구하되 새 사용자 편집이 있으면 덮어쓰지 않고 실패한다. 읽기 전용 명령은 복구 쓰기 대신
보류된 저널을 알린다. 사람이 읽는 이력은 `docs/maintenance/version-history.md`에 생성한다.
