# Calendar setup guide assets

Updated 2026-10-19 for `docs/sync-guide.html` using the current checkout's Korean UI.

## Product screenshots

The PNG files are real renders of the current PyQt6 dialog classes at Windows scale 1 with Malgun Gothic. They use synthetic example accounts, calendars and a nonfunctional example.com feed URL. They are illustrations of setup states, not evidence of live account authorization or remote synchronization.

The capture isolated QSettings, local and shared SQLite paths, and application paths, disabled legacy file migration, and blocked network and browser launches. No personal settings, databases, credentials, or remote accounts were used.

The reproducible local helper and capture manifest are in `artifacts/sync-guide-20261019/` (excluded from the published website).

| Asset | Screen |
|---|---|
| services.png | Connections and subscriptions, additional services collapsed |
| services-expanded.png | Additional services expanded |
| services-all.png | Full scroll content of all eight service cards, without window chrome |
| google-connect.png | Google account connection and credential file controls |
| google-calendars.png | Google import selection and settings save |
| google-sync-options.png | Default Google automatic sync intervals |
| outlook-connect.png | Microsoft app preparation and login |
| outlook-calendar-selection.png | Outlook calendar selection and sync controls |
| icloud-connect.png | iCloud account and app-specific password inputs |
| icloud-calendar-selection.png | CalDAV calendar selection and sync controls |
| ics-add.png | ICS feed address and name inputs |
| ics-management.png | Subscription visibility and refresh controls |
| calendars.png | Calendar visibility and default save target |
| issues.png | Unified troubleshooting |

## Workflow illustration

`sync-workflow.webp` is a new conceptual infographic generated with the built-in image generation tool and converted to WebP (1672 × 941, quality 90). It is not a product screenshot. The original asset remains in the task's generated image directory; this website uses its project-local WebP copy.

Final prompt specification: landscape 16:9 Korean educational infographic on midnight navy, restrained blue/teal/amber. Heading: “캘린더 연결, 한눈에 따라가기”. Show Google, Outlook and iCloud communicating bidirectionally with Air Calendar for writable calendars, and Naver/ICS flowing only into Air Calendar. No links between services. Central conceptual calendar and a result check. Four bottom steps: “01 계정 연결 / 로그인 또는 구독 주소”, “02 캘린더 선택 / 가져올 대상 저장”, “03 동기화 실행 / 지금 동기화 · 자동 갱신”, “04 결과 확인 / 내 캘린더 · 문제 해결”. Footer: “다른 서비스로 일정을 자동 복사하지 않습니다”. Large readable Korean labels, no extra claims or watermark.
