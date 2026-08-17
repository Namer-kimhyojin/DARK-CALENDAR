(function () {
  "use strict";

  const fallbackConfig = {
    appVersion: "3.6.7",
    microsoftStoreUrl: "https://apps.microsoft.com/detail/9mxq08rf22k8?hl=ko-KR&gl=KR&ocid=pdpshare",
    sourceCodeUrl: "https://github.com/Namer-kimhyojin/DARK-CALENDAR",
    releaseSourceUrl: "https://github.com/Namer-kimhyojin/DARK-CALENDAR/releases/tag/v3.6.7",
    licenseUrl: "https://github.com/Namer-kimhyojin/DARK-CALENDAR/blob/v3.6.7/LICENSE",
    thirdPartyNoticesUrl: "https://github.com/Namer-kimhyojin/DARK-CALENDAR/blob/v3.6.7/THIRD_PARTY_NOTICES.md",
    eventUrl: "https://account.microsoft.com/billing/redeem?mstoken=FXJK9-Y7MKP-KX97V-CTHRK-X2MMZ",
    event: { enabled: true }
  };

  const localeNames = {
    ko: "한국어",
    en: "English",
    ja: "日本語",
    zh: "简体中文"
  };

  const translations = {
    ko: {
      metaTitle: "Dark Calendar | 일정과 할 일을 바탕화면 한 곳에",
      metaDescription: "캘린더, 루틴, 집중 타이머와 바탕화면 위젯을 하나의 흐름으로 연결하는 Windows 데스크톱 앱 Dark Calendar를 만나보세요.",
      skip: "본문으로 건너뛰기",
      navFeatures: "기능", navScreens: "제품 화면", navWorkflow: "사용 흐름", navFaq: "FAQ", navStore: "Store에서 보기",
      languageLabel: "언어 선택", menuOpen: "메뉴 열기", close: "닫기",
      heroEyebrow: "Windows 데스크톱 캘린더 & 업무 위젯",
      heroTitle: "일정과 할 일을<br><em>바탕화면 한 곳에.</em>",
      heroDescription: "캘린더, 루틴, 집중 타이머, D-Day 위젯을 원하는 위치에 배치하고 오늘 해야 할 일에 바로 집중하세요.",
      heroPrimary: "가격 및 설치 확인", heroSecondary: "숨은 기능 둘러보기", heroPaid: "Microsoft Store 유료 앱",
      floatToday: "오늘", floatFocus: "집중 세션", heroVisualLabel: "Dark Calendar 제품 화면 미리보기",
      screenMainAlt: "Dark Calendar 월간 캘린더와 업무 패널 화면",
      eventLabel: "기간 한정 이벤트", eventTitle: "이벤트 코드를 Microsoft 계정에 등록하세요.",
      eventDescription: "등록 가능한 코드는 이벤트 종료 시 예고 없이 닫힐 수 있습니다.", eventButton: "코드 등록하기",
      trustLabel: "제품 상세 정보", trustWindows: "데스크톱에 최적화", trustStore: "공식 설치 및 업데이트",
      trustLocalTitle: "로컬 우선", trustLocal: "일정과 설정은 내 PC에", trustGoogle: "선택형 양방향 연동",
      featuresTitle: "달력 너머의<br><em>하루 운영 시스템</em>",
      featuresLead: "기록만 하는 캘린더가 아닙니다. 확인하고, 선택하고, 집중하는 흐름이 한 화면 안에서 이어집니다.",
      cardCalendarLabel: "MONTH VIEW", cardCalendarTitle: "일정과 업무 패널을 나란히",
      cardCalendarBody: "월간 일정, 이번 주 업무, 루틴과 디렉티브를 한눈에 확인하고 바로 처리합니다.",
      cardWidgetLabel: "DESKTOP WIDGETS", cardWidgetTitle: "중요한 정보는 창 밖에서도",
      cardWidgetBody: "시계, 날씨, 스톱워치, 날짜 카드, 카운트다운, D-Day, 텍스트 위젯을 여러 개 띄워두세요.",
      cardFocusLabel: "FOCUS MODE", cardFocusTitle: "할 일을 고르고 곧바로 몰입",
      cardFocusBody: "작업 선택, Pomodoro 타이머, 완료 기록을 끊김 없이 연결해 집중 시간을 쌓습니다.",
      cardCustomLabel: "MAKE IT YOURS", cardCustomTitle: "레이아웃부터 표현 방식까지",
      cardCustomBody: "테마, 패널, 위젯 배치와 텍스트 템플릿을 나의 데스크톱 흐름에 맞게 조정합니다.",
      exploreTitle: "클릭할수록 발견되는<br><em>숨은 기능들</em>",
      exploreLead: "실제 프로그램 화면을 선택해 자세히 살펴보세요. 이미지를 누르면 큰 화면으로 확인할 수 있습니다.",
      screenTabsLabel: "기능 스크린샷", tabMain: "월간 워크스페이스", tabMainSmall: "Calendar + tasks",
      tabWidgets: "위젯 매니저", tabWidgetsSmall: "7 widget types", tabFocus: "집중 기록", tabFocusSmall: "Focus history",
      tabSync: "캘린더 연동", tabSyncSmall: "Google sync", expandScreenshot: "스크린샷 크게 보기", zoomHint: "크게 보기",
      workflowTitle: "하루를 놓치지 않는<br><em>세 번의 움직임</em>",
      workflowLead: "정보를 여러 앱으로 옮기지 않아도 됩니다. 확인에서 몰입까지, 같은 맥락 안에서 이어집니다.",
      flowOneLabel: "SCAN", flowOneTitle: "한눈에 확인합니다.", flowOneBody: "월간 일정과 오늘의 루틴, 이번 주 업무를 같은 화면에서 훑어봅니다.",
      flowTwoLabel: "CHOOSE", flowTwoTitle: "지금 할 일을 선택합니다.", flowTwoBody: "일정, 루틴, 디렉티브를 구분해 우선순위를 정하고 실행 항목을 고릅니다.",
      flowThreeLabel: "FOCUS", flowThreeTitle: "집중하고 기록합니다.", flowThreeBody: "집중 모드와 Pomodoro를 시작하고 완료한 시간은 기록으로 남깁니다.",
      workflowArtCaption: "계획하고, 집중하고, 나만의 흐름을 완성하세요.",
      privacyTitle: "내 일정은<br><em>내 컴퓨터에.</em>",
      privacyBody: "계정 서버와 광고, 사용자 분석 도구 없이 로컬 저장을 기본으로 합니다. Google Calendar, 날씨, ICS 구독은 사용자가 켠 기능에 한해 해당 서비스와 직접 통신합니다.",
      privacyLink: "개인정보 처리 방식 자세히 보기", detailLocalTitle: "로컬 데이터 저장",
      detailLocalBody: "일정, 업무, 설정은 기본적으로 사용자 PC 안에 머뭅니다.", detailSourceTitle: "공개된 전체 소스",
      detailSourceBody: "배포 버전과 같은 태그의 전체 대응 소스와 라이선스를 GitHub에서 제공합니다.", detailSourceLink: "버전별 소스 보기 ↗",
      detailLangTitle: "19개 언어 인터페이스", detailLangBody: "한국어를 기본으로 영어, 일본어, 중국어 등 다양한 언어 전환을 지원합니다.",
      faqTitle: "설치 전에<br><em>궁금한 것들</em>",
      faqOneQ: "어떤 운영체제를 지원하나요?", faqOneA: "Dark Calendar는 Windows 데스크톱 환경에 맞춰 설계되었습니다. 정확한 최신 요구 사항은 Microsoft Store 제품 페이지에서 확인할 수 있습니다.",
      faqTwoQ: "Google Calendar 연동은 필수인가요?", faqTwoA: "아닙니다. 로컬 캘린더만으로 사용할 수 있으며, 필요한 경우에만 Google Calendar 동기화를 직접 설정합니다.",
      faqThreeQ: "무료 프로그램인가요?", faqThreeA: "Microsoft Store에서 판매되는 유료 앱입니다. 현재 가격과 구매 조건은 Store에서 확인하세요. 소스 코드는 GPLv3 조건에 따라 공개됩니다.",
      faqFourQ: "어떤 위젯을 사용할 수 있나요?", faqFourA: "시계, 스톱워치, 날짜 카드, 카운트다운, D-Day, 텍스트, 날씨 위젯을 지원하며 같은 종류를 여러 개 배치할 수도 있습니다.",
      faqFiveQ: "내 데이터가 외부 서버로 전송되나요?", faqFiveA: "기본 데이터는 로컬에 저장됩니다. Google Calendar, 날씨, ICS 등 사용자가 활성화한 외부 기능만 해당 제공자와 직접 통신합니다.",
      ctaTitle: "오늘의 화면을<br><em>나만의 방식으로.</em>", ctaBody: "일정, 할 일, 집중 도구와 위젯을 한곳에 모아보세요.",
      ctaPrimary: "Microsoft Store에서 확인", ctaSecondary: "GitHub 소스 보기", footerTagline: "Windows 데스크톱 캘린더 & 위젯",
      footerPrivacy: "개인정보처리방침", footerRights: "All rights reserved."
    },
    en: {
      metaTitle: "Dark Calendar | Your day, all in one desktop view",
      metaDescription: "Meet Dark Calendar, a Windows desktop app that brings calendars, routines, focus timers, and desktop widgets into one seamless flow.",
      skip: "Skip to content",
      navFeatures: "Features", navScreens: "Product", navWorkflow: "Workflow", navFaq: "FAQ", navStore: "View in Store",
      languageLabel: "Choose language", menuOpen: "Open menu", close: "Close",
      heroEyebrow: "Windows desktop calendar & productivity widgets",
      heroTitle: "Your schedule and tasks,<br><em>together on the desktop.</em>",
      heroDescription: "Place your calendar, routines, focus timer, and D-Day widgets where you want them—and get straight to what matters today.",
      heroPrimary: "Check price & install", heroSecondary: "Explore hidden features", heroPaid: "Paid app on Microsoft Store",
      floatToday: "Today", floatFocus: "Focus session", heroVisualLabel: "Dark Calendar product preview",
      screenMainAlt: "Dark Calendar monthly calendar with task panels",
      eventLabel: "LIMITED-TIME EVENT", eventTitle: "Redeem your event code with your Microsoft account.",
      eventDescription: "Eligible codes may close without notice when the event ends.", eventButton: "Redeem code",
      trustLabel: "Product details", trustWindows: "Built for desktop", trustStore: "Official install & updates",
      trustLocalTitle: "Local-first", trustLocal: "Your schedule stays on your PC", trustGoogle: "Optional two-way sync",
      featuresTitle: "More than a calendar.<br><em>A system for your day.</em>",
      featuresLead: "This is not just a place to record dates. Review, choose, and focus without leaving the same workspace.",
      cardCalendarLabel: "MONTH VIEW", cardCalendarTitle: "Schedule and tasks, side by side",
      cardCalendarBody: "See your month, weekly work, routines, and directives at a glance—and act on them immediately.",
      cardWidgetLabel: "DESKTOP WIDGETS", cardWidgetTitle: "Keep essentials outside the window",
      cardWidgetBody: "Place multiple clocks, weather cards, stopwatches, date cards, countdowns, D-Days, and text widgets on your desktop.",
      cardFocusLabel: "FOCUS MODE", cardFocusTitle: "Choose a task and drop into focus",
      cardFocusBody: "Connect task selection, a Pomodoro timer, and completion history into one uninterrupted focus flow.",
      cardCustomLabel: "MAKE IT YOURS", cardCustomTitle: "From layout to every detail",
      cardCustomBody: "Tune themes, panels, widget placement, and text templates to fit the way your desktop works.",
      exploreTitle: "Hidden tools,<br><em>revealed screen by screen.</em>",
      exploreLead: "Choose a real product screen to uncover more. Select the image to inspect every detail at full size.",
      screenTabsLabel: "Feature screenshots", tabMain: "Monthly workspace", tabMainSmall: "Calendar + tasks",
      tabWidgets: "Widget manager", tabWidgetsSmall: "7 widget types", tabFocus: "Focus history", tabFocusSmall: "Session logs",
      tabSync: "Calendar sync", tabSyncSmall: "Google sync", expandScreenshot: "Expand screenshot", zoomHint: "View larger",
      workflowTitle: "Three moves that keep<br><em>your day on track.</em>",
      workflowLead: "No need to move information between apps. Stay in context from the first scan to deep focus.",
      flowOneLabel: "SCAN", flowOneTitle: "See everything at a glance.", flowOneBody: "Scan your month, today's routines, and this week's work in one view.",
      flowTwoLabel: "CHOOSE", flowTwoTitle: "Choose what matters now.", flowTwoBody: "Separate schedules, routines, and directives to set priorities and pick the next action.",
      flowThreeLabel: "FOCUS", flowThreeTitle: "Focus, then keep the record.", flowThreeBody: "Start Focus Mode or Pomodoro and keep completed time in your history.",
      workflowArtCaption: "Plan, focus, and shape a flow that is yours.",
      privacyTitle: "Your schedule.<br><em>Your computer.</em>",
      privacyBody: "Local storage is the default—without an account server, ads, or user analytics. Google Calendar, weather, and ICS subscriptions connect directly only when you enable them.",
      privacyLink: "See how your data is handled", detailLocalTitle: "Local data storage",
      detailLocalBody: "Schedules, tasks, and settings stay on your PC by default.", detailSourceTitle: "Complete source available",
      detailSourceBody: "GitHub provides the complete corresponding source and license for the same tag as each release.", detailSourceLink: "View source by version ↗",
      detailLangTitle: "Interface in 19 languages", detailLangBody: "Switch between Korean, English, Japanese, Chinese, and many more languages.",
      faqTitle: "Good to know<br><em>before you install.</em>",
      faqOneQ: "Which operating systems are supported?", faqOneA: "Dark Calendar is designed for Windows desktop. Check the Microsoft Store product page for the latest exact system requirements.",
      faqTwoQ: "Is Google Calendar sync required?", faqTwoA: "No. You can use the local calendar on its own and configure Google Calendar sync only when you need it.",
      faqThreeQ: "Is the app free?", faqThreeA: "It is a paid app sold through Microsoft Store. Check the Store for current pricing and purchase terms. The source code is available under GPLv3.",
      faqFourQ: "Which widgets are included?", faqFourA: "Clock, stopwatch, date card, countdown, D-Day, text, and weather widgets are included, with multiple instances of the same type supported.",
      faqFiveQ: "Is my data sent to an external server?", faqFiveA: "Core data is stored locally. Only external features you enable—such as Google Calendar, weather, or ICS—communicate directly with their providers.",
      ctaTitle: "Make today’s screen<br><em>work your way.</em>", ctaBody: "Bring schedules, tasks, focus tools, and widgets together in one place.",
      ctaPrimary: "View on Microsoft Store", ctaSecondary: "View source on GitHub", footerTagline: "Windows desktop calendar & widgets",
      footerPrivacy: "Privacy Policy", footerRights: "All rights reserved."
    },
    ja: {
      metaTitle: "Dark Calendar | 予定とタスクをデスクトップの一か所に",
      metaDescription: "カレンダー、ルーティン、集中タイマー、デスクトップウィジェットを一つの流れにつなぐWindowsアプリ、Dark Calendar。",
      skip: "本文へ移動",
      navFeatures: "機能", navScreens: "製品画面", navWorkflow: "使い方", navFaq: "FAQ", navStore: "Storeで見る",
      languageLabel: "言語を選択", menuOpen: "メニューを開く", close: "閉じる",
      heroEyebrow: "Windowsデスクトップカレンダー＆仕事ウィジェット",
      heroTitle: "予定とタスクを<br><em>デスクトップの一か所に。</em>",
      heroDescription: "カレンダー、ルーティン、集中タイマー、D-Dayウィジェットを好きな位置に置いて、今日やるべきことにすぐ集中できます。",
      heroPrimary: "価格・インストールを確認", heroSecondary: "隠れた機能を見る", heroPaid: "Microsoft Store 有料アプリ",
      floatToday: "今日", floatFocus: "集中セッション", heroVisualLabel: "Dark Calendar 製品画面プレビュー",
      screenMainAlt: "Dark Calendarの月間カレンダーとタスクパネル",
      eventLabel: "期間限定イベント", eventTitle: "イベントコードをMicrosoftアカウントに登録してください。",
      eventDescription: "登録可能なコードはイベント終了時に予告なく閉じる場合があります。", eventButton: "コードを登録",
      trustLabel: "製品情報", trustWindows: "デスクトップに最適化", trustStore: "公式インストールと更新",
      trustLocalTitle: "ローカル優先", trustLocal: "予定と設定は自分のPCに", trustGoogle: "任意の双方向同期",
      featuresTitle: "カレンダーを超えた<br><em>一日の運用システム</em>",
      featuresLead: "記録するだけのカレンダーではありません。確認し、選び、集中する流れが一つの画面で続きます。",
      cardCalendarLabel: "MONTH VIEW", cardCalendarTitle: "予定とタスクパネルを並べて",
      cardCalendarBody: "月間予定、今週の仕事、ルーティン、ディレクティブを一目で確認し、その場で処理できます。",
      cardWidgetLabel: "DESKTOP WIDGETS", cardWidgetTitle: "大切な情報はウィンドウの外にも",
      cardWidgetBody: "時計、天気、ストップウォッチ、日付カード、カウントダウン、D-Day、テキストを複数表示できます。",
      cardFocusLabel: "FOCUS MODE", cardFocusTitle: "タスクを選び、すぐ集中",
      cardFocusBody: "タスク選択、Pomodoroタイマー、完了記録をつなぎ、集中時間を積み上げます。",
      cardCustomLabel: "MAKE IT YOURS", cardCustomTitle: "レイアウトから表現まで",
      cardCustomBody: "テーマ、パネル、ウィジェット配置、テキストテンプレートを自分のデスクトップに合わせて調整できます。",
      exploreTitle: "画面ごとに見つかる<br><em>隠れた機能</em>",
      exploreLead: "実際の製品画面を選んで詳しく見てください。画像を押すと大きく表示できます。",
      screenTabsLabel: "機能スクリーンショット", tabMain: "月間ワークスペース", tabMainSmall: "Calendar + tasks",
      tabWidgets: "ウィジェット管理", tabWidgetsSmall: "7 widget types", tabFocus: "集中記録", tabFocusSmall: "Focus history",
      tabSync: "カレンダー同期", tabSyncSmall: "Google sync", expandScreenshot: "スクリーンショットを拡大", zoomHint: "拡大表示",
      workflowTitle: "一日を逃さない<br><em>3つの動き</em>",
      workflowLead: "情報を複数のアプリへ移す必要はありません。確認から集中まで、同じ文脈で続きます。",
      flowOneLabel: "SCAN", flowOneTitle: "一目で確認。", flowOneBody: "月間予定、今日のルーティン、今週の仕事を同じ画面で見渡します。",
      flowTwoLabel: "CHOOSE", flowTwoTitle: "今やることを選択。", flowTwoBody: "予定、ルーティン、ディレクティブを分けて優先順位を決めます。",
      flowThreeLabel: "FOCUS", flowThreeTitle: "集中して記録。", flowThreeBody: "集中モードやPomodoroを始め、完了した時間を履歴に残します。",
      workflowArtCaption: "計画し、集中し、自分だけの流れをつくりましょう。",
      privacyTitle: "予定データは<br><em>自分のコンピューターに。</em>",
      privacyBody: "アカウントサーバー、広告、ユーザー分析なしのローカル保存が基本です。Google Calendar、天気、ICSは有効にした場合のみ各サービスと直接通信します。",
      privacyLink: "データの取り扱いを詳しく見る", detailLocalTitle: "ローカルデータ保存",
      detailLocalBody: "予定、タスク、設定は基本的にユーザーのPC内に保存されます。", detailSourceTitle: "完全なソースを公開",
      detailSourceBody: "各配布版と同じタグの完全な対応ソースとライセンスをGitHubで提供します。", detailSourceLink: "バージョン別ソースを見る ↗",
      detailLangTitle: "19言語のインターフェース", detailLangBody: "韓国語、英語、日本語、中国語など多様な言語へ切り替えられます。",
      faqTitle: "インストール前に<br><em>知っておきたいこと</em>",
      faqOneQ: "対応OSは？", faqOneA: "Dark CalendarはWindowsデスクトップ向けです。最新の正確な要件はMicrosoft Store製品ページで確認できます。",
      faqTwoQ: "Google Calendar連携は必須ですか？", faqTwoA: "いいえ。ローカルカレンダーだけでも使え、必要な場合にのみGoogle Calendar同期を設定します。",
      faqThreeQ: "無料アプリですか？", faqThreeA: "Microsoft Storeで販売される有料アプリです。現在の価格と購入条件はStoreで確認してください。ソースコードはGPLv3で公開されています。",
      faqFourQ: "どのウィジェットが使えますか？", faqFourA: "時計、ストップウォッチ、日付カード、カウントダウン、D-Day、テキスト、天気に対応し、同じ種類を複数配置できます。",
      faqFiveQ: "データは外部サーバーへ送信されますか？", faqFiveA: "基本データはローカル保存です。Google Calendar、天気、ICSなど有効にした外部機能だけが各提供元と直接通信します。",
      ctaTitle: "今日の画面を<br><em>自分らしい方法で。</em>", ctaBody: "予定、タスク、集中ツール、ウィジェットを一か所にまとめましょう。",
      ctaPrimary: "Microsoft Storeで確認", ctaSecondary: "GitHubでソースを見る", footerTagline: "Windowsデスクトップカレンダー＆ウィジェット",
      footerPrivacy: "プライバシーポリシー", footerRights: "All rights reserved."
    },
    zh: {
      metaTitle: "Dark Calendar | 在桌面一处管理日程与任务",
      metaDescription: "Dark Calendar 是一款 Windows 桌面应用，将日历、例行任务、专注计时器和桌面小组件整合为顺畅的工作流。",
      skip: "跳到正文",
      navFeatures: "功能", navScreens: "产品界面", navWorkflow: "使用流程", navFaq: "常见问题", navStore: "在 Store 查看",
      languageLabel: "选择语言", menuOpen: "打开菜单", close: "关闭",
      heroEyebrow: "Windows 桌面日历与效率小组件",
      heroTitle: "日程和任务<br><em>集中在桌面一处。</em>",
      heroDescription: "将日历、例行任务、专注计时器和 D-Day 小组件放在想要的位置，立即专注于今天的重要事项。",
      heroPrimary: "查看价格与安装", heroSecondary: "探索隐藏功能", heroPaid: "Microsoft Store 付费应用",
      floatToday: "今天", floatFocus: "专注时段", heroVisualLabel: "Dark Calendar 产品界面预览",
      screenMainAlt: "Dark Calendar 月历与任务面板界面",
      eventLabel: "限时活动", eventTitle: "将活动代码兑换到你的 Microsoft 帐户。",
      eventDescription: "活动结束时，可兑换代码可能会不经通知关闭。", eventButton: "兑换代码",
      trustLabel: "产品信息", trustWindows: "为桌面优化", trustStore: "官方安装与更新",
      trustLocalTitle: "本地优先", trustLocal: "日程与设置留在本机", trustGoogle: "可选双向同步",
      featuresTitle: "不只是日历，<br><em>更是每日运作系统</em>",
      featuresLead: "它不只是记录日期。查看、选择并进入专注，整个流程都在同一界面中完成。",
      cardCalendarLabel: "MONTH VIEW", cardCalendarTitle: "日程与任务面板并排呈现",
      cardCalendarBody: "一眼查看月度日程、本周工作、例行任务和指令，并立即处理。",
      cardWidgetLabel: "DESKTOP WIDGETS", cardWidgetTitle: "窗口之外也能掌握重要信息",
      cardWidgetBody: "可在桌面放置多个时钟、天气、秒表、日期卡、倒计时、D-Day 和文字小组件。",
      cardFocusLabel: "FOCUS MODE", cardFocusTitle: "选好任务，立即专注",
      cardFocusBody: "把任务选择、Pomodoro 计时器与完成记录连成不中断的专注流程。",
      cardCustomLabel: "MAKE IT YOURS", cardCustomTitle: "从布局到呈现方式",
      cardCustomBody: "按自己的桌面习惯调整主题、面板、小组件位置和文字模板。",
      exploreTitle: "逐个界面发现<br><em>隐藏功能</em>",
      exploreLead: "选择真实的产品界面深入了解。点击图片即可放大查看细节。",
      screenTabsLabel: "功能截图", tabMain: "月度工作区", tabMainSmall: "Calendar + tasks",
      tabWidgets: "小组件管理器", tabWidgetsSmall: "7 widget types", tabFocus: "专注记录", tabFocusSmall: "Focus history",
      tabSync: "日历同步", tabSyncSmall: "Google sync", expandScreenshot: "放大截图", zoomHint: "放大查看",
      workflowTitle: "三个动作，<br><em>让一天井然有序</em>",
      workflowLead: "无需在多个应用间搬运信息。从浏览到深度专注，始终保持同一上下文。",
      flowOneLabel: "SCAN", flowOneTitle: "一眼浏览。", flowOneBody: "在同一界面查看月度日程、今日例行任务和本周工作。",
      flowTwoLabel: "CHOOSE", flowTwoTitle: "选择当前要做的事。", flowTwoBody: "区分日程、例行任务和指令，确定优先级并选出下一步。",
      flowThreeLabel: "FOCUS", flowThreeTitle: "专注并留下记录。", flowThreeBody: "启动专注模式或 Pomodoro，并把完成时间保存在历史记录中。",
      workflowArtCaption: "计划、专注，打造属于自己的节奏。",
      privacyTitle: "你的日程，<br><em>留在你的电脑。</em>",
      privacyBody: "默认使用本地存储，不设帐户服务器、广告或用户分析。Google Calendar、天气和 ICS 仅在你启用后与相应服务直接通信。",
      privacyLink: "详细了解数据处理方式", detailLocalTitle: "本地数据存储",
      detailLocalBody: "日程、任务和设置默认保留在用户电脑中。", detailSourceTitle: "提供完整源代码",
      detailSourceBody: "GitHub 提供与每个发布版本相同标签的完整对应源代码和许可证。", detailSourceLink: "按版本查看源代码 ↗",
      detailLangTitle: "19 种界面语言", detailLangBody: "支持韩语、英语、日语、中文等多种语言切换。",
      faqTitle: "安装前的<br><em>常见问题</em>",
      faqOneQ: "支持哪些操作系统？", faqOneA: "Dark Calendar 专为 Windows 桌面环境设计。最新准确要求请查看 Microsoft Store 产品页面。",
      faqTwoQ: "必须连接 Google Calendar 吗？", faqTwoA: "不需要。你可以只使用本地日历，仅在需要时自行设置 Google Calendar 同步。",
      faqThreeQ: "这是免费应用吗？", faqThreeA: "这是在 Microsoft Store 销售的付费应用。当前价格和购买条件请以 Store 为准。源代码按 GPLv3 条款公开。",
      faqFourQ: "支持哪些小组件？", faqFourA: "支持时钟、秒表、日期卡、倒计时、D-Day、文字和天气，同一类型也可以放置多个。",
      faqFiveQ: "我的数据会发送到外部服务器吗？", faqFiveA: "核心数据存储在本地。只有你启用的 Google Calendar、天气或 ICS 等外部功能会与各自服务商直接通信。",
      ctaTitle: "让今天的桌面<br><em>按你的方式运作。</em>", ctaBody: "把日程、任务、专注工具和小组件汇集在一处。",
      ctaPrimary: "在 Microsoft Store 查看", ctaSecondary: "在 GitHub 查看源代码", footerTagline: "Windows 桌面日历与小组件",
      footerPrivacy: "隐私政策", footerRights: "All rights reserved."
    }
  };

  const screens = {
    ko: {
      main: { image: "assets/screenshots/main-dashboard.png", alt: "Dark Calendar 월간 캘린더와 업무 패널 화면", kicker: "CALENDAR WORKSPACE", title: "달력과 실행 목록 사이의 거리를 없앴습니다.", description: "월간 캘린더 오른쪽에 이번 주 일정, 루틴, 디렉티브가 이어집니다. 날짜를 확인한 자리에서 해야 할 일을 바로 선택할 수 있습니다.", points: ["멀티데이 일정과 드래그 범위 선택", "오늘·이번 주 패널 전환", "루틴과 실행 항목 분리 관리"] },
      widgets: { image: "assets/screenshots/widget-manager.png", alt: "Dark Calendar 위젯 매니저 화면", kicker: "WIDGET MANAGER", title: "일곱 종류의 위젯을 원하는 만큼 배치하세요.", description: "보이기·숨기기·설정·위치 고정과 삭제를 한곳에서 관리합니다. 같은 종류의 위젯도 이름을 달리해 여러 개 만들 수 있습니다.", points: ["시계·날씨·스톱워치·날짜 카드", "카운트다운·D-Day·텍스트 템플릿", "멀티 인스턴스와 위치 저장"] },
      focus: { image: "assets/screenshots/focus-mode.png", alt: "Dark Calendar 집중 모드 기록 화면", kicker: "FOCUS HISTORY", title: "집중한 시간도 일정처럼 기록됩니다.", description: "최근 집중 세션과 누적 시간을 확인하고, 작업을 선택해 Pomodoro 흐름으로 이어갈 수 있습니다.", points: ["작업 선택형 집중 세션", "오늘·이번 달 누적 시간", "세션 기록 확인과 정리"] },
      sync: { image: "assets/screenshots/calendar-sync.png", alt: "Dark Calendar Google Calendar 동기화 설정 화면", kicker: "GOOGLE CALENDAR", title: "필요할 때만 연결하는 캘린더 동기화.", description: "연결, 캘린더 선택, 구독, 동기화, 진단을 단계별 탭으로 나누어 설정할 수 있습니다. 로컬 캘린더만으로도 사용할 수 있습니다.", points: ["선택형 Google Calendar 인증", "연결 테스트와 동기화 진단", "로컬·Google·ICS 캘린더 관리"] }
    },
    en: {
      main: { image: "assets/screenshots/main-dashboard.png", alt: "Dark Calendar monthly calendar and task panels", kicker: "CALENDAR WORKSPACE", title: "Close the gap between planning and doing.", description: "Weekly schedules, routines, and directives sit beside the monthly calendar, so you can choose what to do from the same place you review the date.", points: ["Multi-day events and drag range selection", "Today and This Week panel views", "Separate routines and action items"] },
      widgets: { image: "assets/screenshots/widget-manager.png", alt: "Dark Calendar Widget Manager", kicker: "WIDGET MANAGER", title: "Place seven types of widgets wherever you need them.", description: "Show, hide, configure, pin, and remove widgets from one manager. Create multiple named instances of the same widget type.", points: ["Clock, weather, stopwatch, and date card", "Countdown, D-Day, and text templates", "Multiple instances with saved positions"] },
      focus: { image: "assets/screenshots/focus-mode.png", alt: "Dark Calendar focus session history", kicker: "FOCUS HISTORY", title: "Your focused time becomes part of the record.", description: "Review recent sessions and totals, then choose a task and continue into a Pomodoro-based focus flow.", points: ["Task-based focus sessions", "Daily and monthly totals", "Review and clean up session history"] },
      sync: { image: "assets/screenshots/calendar-sync.png", alt: "Dark Calendar Google Calendar sync settings", kicker: "GOOGLE CALENDAR", title: "Calendar sync that connects only when you choose.", description: "Connection, calendars, subscriptions, sync, and diagnostics are arranged in guided tabs. The app also works with the local calendar alone.", points: ["Optional Google Calendar authorization", "Connection tests and sync diagnostics", "Local, Google, and ICS calendars"] }
    },
    ja: {
      main: { image: "assets/screenshots/main-dashboard.png", alt: "Dark Calendarの月間カレンダーとタスクパネル", kicker: "CALENDAR WORKSPACE", title: "計画と実行の距離をなくしました。", description: "月間カレンダーの横に今週の予定、ルーティン、ディレクティブを表示。日付を確認した場所で次の行動を選べます。", points: ["複数日予定とドラッグ範囲選択", "今日・今週パネルの切り替え", "ルーティンと実行項目を分けて管理"] },
      widgets: { image: "assets/screenshots/widget-manager.png", alt: "Dark Calendar ウィジェット管理画面", kicker: "WIDGET MANAGER", title: "7種類のウィジェットを好きなだけ配置。", description: "表示、非表示、設定、位置固定、削除を一か所で管理。同じ種類も名前を変えて複数作成できます。", points: ["時計・天気・ストップウォッチ・日付カード", "カウントダウン・D-Day・テキスト", "複数インスタンスと位置保存"] },
      focus: { image: "assets/screenshots/focus-mode.png", alt: "Dark Calendar 集中モード履歴画面", kicker: "FOCUS HISTORY", title: "集中した時間も予定のように記録。", description: "最近の集中セッションと累計時間を確認し、タスクを選んでPomodoroの流れへ続けられます。", points: ["タスク選択型の集中セッション", "今日・今月の累計時間", "セッション履歴の確認と整理"] },
      sync: { image: "assets/screenshots/calendar-sync.png", alt: "Dark Calendar Google Calendar同期設定", kicker: "GOOGLE CALENDAR", title: "必要なときだけつなぐカレンダー同期。", description: "接続、カレンダー選択、購読、同期、診断をタブごとに設定できます。ローカルカレンダーだけでも使用できます。", points: ["任意のGoogle Calendar認証", "接続テストと同期診断", "ローカル・Google・ICS管理"] }
    },
    zh: {
      main: { image: "assets/screenshots/main-dashboard.png", alt: "Dark Calendar 月历与任务面板", kicker: "CALENDAR WORKSPACE", title: "缩短计划与执行之间的距离。", description: "月历旁就是本周日程、例行任务和指令。查看日期后，无需切换界面即可选择下一步。", points: ["多日事件与拖动范围选择", "今日与本周面板切换", "例行任务与执行项分开管理"] },
      widgets: { image: "assets/screenshots/widget-manager.png", alt: "Dark Calendar 小组件管理器", kicker: "WIDGET MANAGER", title: "七类小组件，按需自由放置。", description: "在一处完成显示、隐藏、设置、锁定位置和删除。同一类型也可命名并创建多个实例。", points: ["时钟、天气、秒表和日期卡", "倒计时、D-Day 和文字模板", "多实例与位置保存"] },
      focus: { image: "assets/screenshots/focus-mode.png", alt: "Dark Calendar 专注模式记录", kicker: "FOCUS HISTORY", title: "专注时间也会成为可回顾的记录。", description: "查看近期专注时段与累计时间，选择任务后继续进入 Pomodoro 专注流程。", points: ["基于任务的专注时段", "今日与本月累计时间", "查看并整理时段历史"] },
      sync: { image: "assets/screenshots/calendar-sync.png", alt: "Dark Calendar Google Calendar 同步设置", kicker: "GOOGLE CALENDAR", title: "只在需要时连接日历同步。", description: "连接、日历选择、订阅、同步和诊断按步骤分成标签页。也可以仅使用本地日历。", points: ["可选 Google Calendar 授权", "连接测试与同步诊断", "本地、Google 与 ICS 日历管理"] }
    }
  };

  const richTextKeys = new Set(["heroTitle", "featuresTitle", "exploreTitle", "workflowTitle", "privacyTitle", "faqTitle", "ctaTitle"]);
  let currentLanguage = "ko";
  let currentScreen = "main";
  let currentConfig = fallbackConfig;

  function normalizedLanguage(value) {
    const language = String(value || "").toLowerCase();
    if (language.startsWith("ko")) return "ko";
    if (language.startsWith("ja")) return "ja";
    if (language.startsWith("zh")) return "zh";
    if (language.startsWith("en")) return "en";
    return "ko";
  }

  function savedLanguage() {
    const queryLanguage = new URLSearchParams(window.location.search).get("lang");
    if (queryLanguage && localeNames[normalizedLanguage(queryLanguage)]) return normalizedLanguage(queryLanguage);
    try {
      const stored = window.localStorage.getItem("dark-calendar-language");
      if (stored && localeNames[stored]) return stored;
    } catch (_error) {
      // Language preference remains optional when storage is unavailable.
    }
    return normalizedLanguage(window.navigator.language);
  }

  function updateScreen() {
    const data = screens[currentLanguage][currentScreen];
    const image = document.querySelector("[data-active-screen]");
    if (!image || !data) return;

    image.src = data.image;
    image.alt = data.alt;
    document.querySelector("[data-screen-kicker]").textContent = data.kicker;
    document.querySelector("[data-screen-title]").textContent = data.title;
    document.querySelector("[data-screen-description]").textContent = data.description;

    const pointList = document.querySelector("[data-screen-points]");
    pointList.replaceChildren(...data.points.map((point) => {
      const item = document.createElement("li");
      item.textContent = point;
      return item;
    }));
  }

  function setLanguage(language, persist) {
    currentLanguage = normalizedLanguage(language);
    const copy = translations[currentLanguage];
    document.documentElement.lang = currentLanguage === "zh" ? "zh-CN" : currentLanguage;
    document.title = copy.metaTitle;
    document.querySelector('meta[name="description"]')?.setAttribute("content", copy.metaDescription);
    document.querySelector('meta[property="og:description"]')?.setAttribute("content", copy.metaDescription);

    document.querySelectorAll("[data-i18n]").forEach((node) => {
      const key = node.dataset.i18n;
      if (!Object.prototype.hasOwnProperty.call(copy, key)) return;
      if (richTextKeys.has(key)) node.innerHTML = copy[key];
      else node.textContent = copy[key];
    });

    document.querySelectorAll("[data-i18n-aria]").forEach((node) => {
      const value = copy[node.dataset.i18nAria];
      if (value) node.setAttribute("aria-label", value);
    });

    document.querySelectorAll("[data-i18n-alt]").forEach((node) => {
      const value = copy[node.dataset.i18nAlt];
      if (value) node.setAttribute("alt", value);
    });

    document.querySelectorAll("[data-language-select]").forEach((select) => {
      select.value = currentLanguage;
      select.setAttribute("aria-label", copy.languageLabel);
    });

    updateScreen();

    if (persist) {
      try {
        window.localStorage.setItem("dark-calendar-language", currentLanguage);
      } catch (_error) {
        // The UI still changes even if the preference cannot be persisted.
      }
      const nextUrl = new URL(window.location.href);
      nextUrl.searchParams.set("lang", currentLanguage);
      window.history.replaceState({}, "", nextUrl);
    }
  }

  function applyConfig(config) {
    currentConfig = {
      ...fallbackConfig,
      ...config,
      event: { ...fallbackConfig.event, ...(config.event || {}) }
    };

    document.querySelectorAll("[data-config-link]").forEach((node) => {
      const value = currentConfig[node.dataset.configLink];
      if (value) node.setAttribute("href", value);
    });

    document.querySelectorAll("[data-config-text]").forEach((node) => {
      const value = currentConfig[node.dataset.configText];
      if (value) node.textContent = value;
    });

    const eventBand = document.querySelector("[data-event-band]");
    if (eventBand) eventBand.hidden = currentConfig.event.enabled === false || !currentConfig.eventUrl;
  }

  function setupHeader() {
    const header = document.querySelector("[data-header]");
    const toggle = document.querySelector("[data-menu-toggle]");
    const menu = document.querySelector("[data-mobile-menu]");
    if (!header || !toggle || !menu) return;

    const updateHeader = () => header.classList.toggle("is-scrolled", window.scrollY > 14);
    const closeMenu = () => {
      toggle.setAttribute("aria-expanded", "false");
      menu.hidden = true;
      header.classList.remove("has-open-menu");
    };

    toggle.addEventListener("click", () => {
      const willOpen = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(willOpen));
      menu.hidden = !willOpen;
      header.classList.toggle("has-open-menu", willOpen);
    });
    menu.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));
    window.addEventListener("scroll", updateHeader, { passive: true });
    window.addEventListener("resize", () => {
      if (window.innerWidth > 1100) closeMenu();
    });
    updateHeader();
  }

  function setupLanguagePicker() {
    document.querySelectorAll("[data-language-select]").forEach((select) => {
      select.addEventListener("change", (event) => setLanguage(event.target.value, true));
    });
  }

  function setupScreenExplorer() {
    const tabs = Array.from(document.querySelectorAll("[data-screen]"));
    if (!tabs.length) return;

    function activate(tab, focus) {
      currentScreen = tab.dataset.screen;
      tabs.forEach((item) => {
        const active = item === tab;
        item.setAttribute("aria-selected", String(active));
        item.tabIndex = active ? 0 : -1;
      });
      updateScreen();
      if (focus) tab.focus();
    }

    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => activate(tab, false));
      tab.addEventListener("keydown", (event) => {
        if (!["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        let nextIndex = index;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") nextIndex = (index + 1) % tabs.length;
        if (event.key === "ArrowLeft" || event.key === "ArrowUp") nextIndex = (index - 1 + tabs.length) % tabs.length;
        if (event.key === "Home") nextIndex = 0;
        if (event.key === "End") nextIndex = tabs.length - 1;
        activate(tabs[nextIndex], true);
      });
    });
    activate(tabs.find((tab) => tab.getAttribute("aria-selected") === "true") || tabs[0], false);
  }

  function setupLightbox() {
    const dialog = document.querySelector("[data-lightbox]");
    const openButton = document.querySelector("[data-open-lightbox]");
    const closeButton = document.querySelector("[data-close-lightbox]");
    if (!dialog || !openButton || !closeButton) return;

    function openLightbox() {
      const data = screens[currentLanguage][currentScreen];
      const image = dialog.querySelector("[data-lightbox-image]");
      image.src = data.image;
      image.alt = data.alt;
      dialog.querySelector("[data-lightbox-kicker]").textContent = data.kicker;
      dialog.querySelector("[data-lightbox-title]").textContent = data.title;
      dialog.querySelector("[data-lightbox-description]").textContent = data.description;
      dialog.showModal();
      closeButton.focus();
    }

    openButton.addEventListener("click", openLightbox);
    closeButton.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      const box = dialog.getBoundingClientRect();
      const outside = event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom;
      if (outside) dialog.close();
    });
  }

  function setupFaq() {
    const items = Array.from(document.querySelectorAll(".faq-list details"));
    items.forEach((item) => {
      item.addEventListener("toggle", () => {
        if (!item.open) return;
        items.forEach((other) => {
          if (other !== item) other.open = false;
        });
      });
    });
  }

  setupHeader();
  setupLanguagePicker();
  setupScreenExplorer();
  setupLightbox();
  setupFaq();
  setLanguage(savedLanguage(), false);

  fetch("site-config.json", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error("Config request failed");
      return response.json();
    })
    .then(applyConfig)
    .catch(() => applyConfig(fallbackConfig));
})();
