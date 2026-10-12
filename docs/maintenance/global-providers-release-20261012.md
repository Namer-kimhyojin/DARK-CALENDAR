# 해외 CalDAV 서비스 1차 및 3.8.1 배포 기록

2026-10-12 KST.

Yahoo Calendar, Zoho Calendar, Fastmail의 계정 연결, 캘린더 필터, 서비스별 상태, 수동·자동 동기화와 일정 저장 후 동기화를 추가했다. Zoho는 데이터센터 서버를 선택하고 같은 연결에서 다른 데이터센터로 인증 정보를 보내는 리디렉션을 차단한다. 암호는 기존 Windows 사용자 보호 저장을 사용한다. 한국어·영어·일본어·중국어 간체 안내를 추가했고 다른 번들 언어의 신규 키는 영어를 사용한다.

CalDAV는 서비스당 현재 연결 계정 하나를 사용한다. 반복·초대 일정은 읽기 전용이며 Yahoo! JAPAN 계정은 이번 Yahoo 연결에 포함하지 않는다. 실제 Yahoo/Zoho/Fastmail 계정 인증·원격 CRUD는 수행하지 않았다.

배포에 필요한 현재 run.bat 입력을 포함하고 기존 미커밋 실행 소스를 보존했다. 계정·DB·일반 사용자 문서·임시 아티팩트는 커밋 대상에서 제외했다. 기존 위젯 열기 실패가 OPENING 상태를 남기는 문제는 복구 처리를 추가해 기존 실패/재진입 검사와 일반 전환 검사를 통과했다.

## 검증

- 219개 파일, 3,957개 회귀 사례 통과. 첫 실패/시간 제한 결과와 재검사 결과를 별도 보존했다.
- 신규 서비스 25개 사례, 기존 워커 48개, 계정 동기화 UI 46개 및 서비스 설정 UX 47개 검사 통과.
- 로컬 패키지에서 추출한 코드의 103개 사례 통과, 소스 fallback 없이 실행, Native QSettings 보존 확인.
- 커밋 훅 및 GitHub Quality Gate·Encoding Policy·Build Release·Pages 성공.
- 공개 MSIX의 286개 코드 모듈 일치, 203개 리소스 중 4개 SVG/Markdown은 Git 줄바꿈 차이만 확인.
- 기본 DB에는 로컬 캘린더 한 행만 있고 나머지 테이블은 비어 있다. 라이선스 및 공개 소스 묶음 검사 통과.
- 공개 업로드 컨테이너 안 MSIX가 별도 공개 MSIX와 동일하다. 앱 identity·publisher·PublisherDisplayName·PE/MSIX 3.8.1.0 x64 확인.
- 공개 소스 ZIP의 305개 application Python 파일이 현재 입력과 일치한다.

## 배포

런타임 입력 커밋: d2903bf3583436a7842cbc5707286891dedec970.

공개 릴리스: https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/tag/v3.8.1

Store 제출 파일: artifacts/deployment/3.8.1/20261012-2052/DarkCalendar-3.8.1.0-x64.msixupload

SHA256: 9c95b5ddc164dffa66068a46c0033808054851df8e62c576ce2221a7b3e555f4.

로컬 Python 3.13.14는 고정 빌드 요구 3.13.15와 달라 공식 Python 3.13.15와 별도 가상환경을 마련했다. 로컬 Windows SDK 부재로 MSIX는 기존 GitHub Windows CI에서 공식 build-release.bat으로 생성했다. SDK 소스 약관 자동 수락 옵션은 자동 승인 검토에서 거부되었으며 약관을 수락하지 않았다. GitHub CI가 성공한 패키지를 다시 내려받아 검증했다.

기존 Submission 25는 초기 Partner Center 조회에서 게시 상태였고 제품 identity도 대조했다. 이후 인증된 Edge 연결이 끊겼고 Chrome 연결도 없어졌으며 API 자격증명은 현재 경로에 없다. 3.8.1의 Store 초안 생성·업로드·심사 제출은 수행하지 않았다. 설치 버전은 3.8.0.0 x64다.

다음 단계는 로그인된 Partner Center 브라우저를 연결하고 기존 제품 9MXQ08RF22K8의 새 업데이트에 검증된 업로드 파일을 등록하는 것이다. 업로드 Validated·3.8.1.0 x64를 확인한 뒤 변경 안내 및 제출 옵션을 검토해 심사 제출한다. 게시와 설치 업데이트는 별도로 확인한다.

증거: artifacts/deployment/3.8.1/20261012-2052/ 및 artifacts/global-providers/validation-summary.json.
