# Air Calendar — Claude 작업 안내

이 프로젝트의 공통 기준은 [AGENTS.md](AGENTS.md)입니다. Claude도 같은 기준을 적용합니다.

- 작업 시작: [AGENTS.md](AGENTS.md)
- 현재 진행 상태: [TASKS.md](TASKS.md)
- 주제별 문서 탐색: [문서 색인](docs/README.md)
- 다이얼로그·아이콘 상세 구현: [rules/dialog_ui.md](rules/dialog_ui.md)

관련 규칙과 실제 호출부를 확인한 뒤 작업하며, 기존 미커밋 변경을 보존합니다. 이 파일에 공통 규칙을 다시 복제하지 않습니다.

## UI/UX skills

Taste, a11y, bans, voice, and icon library for this project live in `.ux-profile.md`.
Run `setup-ui-ux-skills` again only to change those defaults.
Before UI or microcopy work, read `.ux-profile.md`, then the matching domain skill (page-patterns, viewports, forms, surfaces, loaders, empty-states, copy, motion).
Before creating a new page, read `page-patterns` and name the pattern. Do not write page markup until the pattern is named.
Layouts must pass `viewports` at the compact calendar-toolbar width and at a 1280px window width (desktop app: there is no 375px phone layout).
Before finishing UI, run `ux-audit`.
