# Dark Calendar 개인정보처리방침

**시행일: 2026년 7월 13일**

Dark Calendar(이하 "본 앱")는 김효진(이하 "개발자")이 개발·배포하는 Windows용 데스크톱 캘린더 애플리케이션입니다. 본 방침은 본 앱이 이용자의 정보를 어떻게 처리하는지 설명합니다.

## 1. 핵심 요약

- **개발자는 이용자의 개인정보를 수집하지 않습니다.** 본 앱에는 서버, 계정 시스템, 분석 도구, 광고가 없습니다.
- 이용자가 만든 모든 일정·업무·설정 데이터는 **이용자 PC에만 저장**됩니다.
- 외부 전송은 이용자가 직접 활성화한 기능(Google Calendar 연동, 날씨 위젯, ICS 구독)에 한해, 해당 서비스 제공자에게만 이루어집니다.

## 2. 로컬에 저장되는 데이터

본 앱은 다음 데이터를 이용자 PC의 로컬 폴더(`%LOCALAPPDATA%\kimhyojin\Dark Calendar`)에 저장합니다.

| 데이터 | 용도 |
|---|---|
| 일정·업무·체크리스트 데이터 (SQLite DB) | 캘린더 기능 제공 |
| 앱 설정 (Windows 레지스트리 `HKCU\Software\kimhyojin\Dark Calendar`) | 테마·언어·레이아웃 유지 |
| Google 인증 토큰 (`token.json`) — Google 연동 사용 시에만 | 재로그인 없이 동기화 유지 |
| 진단 로그 파일 | 오류 확인 |

이 데이터는 개발자에게 전송되지 않으며, 개발자는 접근할 수 없습니다.

## 3. 제3자 서비스로의 전송 (이용자가 활성화한 경우에만)

### 3.1 Google Calendar 연동
- 이용자가 Google 계정으로 로그인하면 본 앱은 Google Calendar API를 통해 일정 데이터를 읽고 씁니다.
- 전송 대상: Google LLC ([Google 개인정보처리방침](https://policies.google.com/privacy))
- 인증 토큰은 이용자 PC에만 저장되며, 개발자 서버로 전송되지 않습니다.
- 연동 해제 시 본 앱은 Google에 토큰 취소(revoke)를 요청하고 로컬 토큰을 삭제합니다.
- 본 앱의 Google API로부터 받은 정보의 사용 및 다른 앱으로의 이전은 **제한적 사용(Limited Use) 요구사항을 포함한 [Google API 서비스 사용자 데이터 정책](https://developers.google.com/terms/api-services-user-data-policy)을 준수합니다.**

### 3.2 날씨 위젯
- 이용자가 입력한 **도시 이름**만 Open-Meteo(오픈소스 날씨 서비스, [open-meteo.com](https://open-meteo.com))에 전송되어 좌표와 날씨를 조회합니다.
- GPS 등 기기 위치정보는 수집·사용하지 않습니다.

### 3.3 ICS 캘린더 구독
- 이용자가 직접 입력한 ICS 주소(URL)에 접속하여 일정을 가져옵니다. 해당 URL의 운영자에게 일반적인 웹 요청 정보(IP 주소 등)가 전달될 수 있습니다.

## 4. 데이터 보관 및 삭제

- 모든 데이터는 이용자가 삭제할 때까지 로컬에 보관됩니다.
- **Google 연동 해제**: 앱 내 Google Calendar 설정에서 연동 해제 시 토큰이 취소·삭제됩니다. [Google 계정 보안 설정](https://myaccount.google.com/permissions)에서도 언제든 접근 권한을 철회할 수 있습니다.
- **전체 삭제**: 앱 제거 후 `%LOCALAPPDATA%\kimhyojin\Dark Calendar` 폴더를 삭제하면 모든 데이터가 완전히 제거됩니다.

## 5. 아동의 개인정보

본 앱은 개인정보를 수집하지 않으므로 아동으로부터 별도의 정보를 수집하지 않습니다.

## 6. 방침 변경

본 방침이 변경되는 경우 이 페이지에 갱신된 버전과 시행일을 게시합니다.

## 7. 문의

개인정보 관련 문의: **aplus.mylife@gmail.com**
