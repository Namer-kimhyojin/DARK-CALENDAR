(function () {
  "use strict";

  const fallbackConfig = {
    appVersion: "3.6.7",
    microsoftStoreUrl: "https://apps.microsoft.com/detail/9mxq08rf22k8?hl=ko-KR&gl=KR&ocid=pdpshare",
    sourceCodeUrl: "https://github.com/Namer-kimhyojin/DARK-CALENDAR",
    promotionKitUrl: "promo.html",
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

  const expandedTranslations = {
    ko: {
      navGoogle: "Google 연동",
      metaDescription: "캘린더와 위젯을 바탕화면에 직접 배치하고, 크기·위치·레이아웃·색상을 자유롭게 구성하는 맞춤형 Windows 데스크톱 캘린더 Dark Calendar.",
      heroEyebrow: "사용자 맞춤형 데스크톱 캘린더 & 위젯",
      heroTitle: "바탕화면을<br><em>나만의 시간 공간으로.</em>",
      heroDescription: "캘린더와 업무 패널, 시계·날씨·D-Day 위젯을 바탕화면에 바로 띄우세요. 크기와 위치, 레이아웃과 색상까지 내 방식대로 자유롭게 완성할 수 있습니다.",
      heroSecondary: "맞춤 기능 둘러보기", trustWindows: "바탕화면에 바로 배치",
      desktopTitle: "프로그램 창을 넘어<br><em>바탕화면 자체가 캘린더</em>",
      desktopLead: "Dark Calendar의 가장 큰 장점은 필요한 기능을 바탕화면에 직접 구현하는 것입니다. 정해진 틀에 맞추는 대신, 사용자가 자신의 화면과 업무 방식에 맞춰 공간을 설계합니다.",
      desktopImageAlt: "바탕화면 위에서 캘린더와 위젯의 크기, 위치, 색상, 레이아웃을 조정하는 개념 이미지",
      desktopImageCaption: "이동·크기 조절·정렬·색상 선택을 한 화면에서 이해할 수 있도록 구성한 맞춤형 데스크톱 예시입니다.",
      freedomDirectTitle: "바탕화면에 바로", freedomDirectBody: "앱을 열어 찾아다니지 않아도 캘린더, 업무 목록과 위젯이 데스크톱 위에 계속 보입니다.",
      freedomMoveTitle: "위치와 크기를 자유롭게", freedomMoveBody: "각 요소를 원하는 곳으로 이동하고 화면 크기와 정보량에 맞춰 넓이와 높이를 조절할 수 있습니다.",
      freedomLayoutTitle: "레이아웃은 내 흐름대로", freedomLayoutBody: "캘린더 중심, 업무 패널 중심, 위젯 중심 등 사용 목적에 따라 서로 다른 화면 구성을 만들 수 있습니다.",
      freedomColorTitle: "색상과 표현까지 내 취향으로", freedomColorBody: "테마와 강조 색상, 패널과 위젯의 표현 방식을 조합해 나만의 시각 체계를 완성합니다.",
      atlasImageAlt: "캘린더를 중심으로 업무, 집중, 위젯, 동기화 기능이 연결된 전체 기능 지도",
      atlasImageCaption: "캘린더를 중심으로 계획·실행·집중·위젯·동기화가 연결됩니다.",
      atlasTitle: "보이는 기능부터<br>숨은 도구까지 한눈에", atlasLead: "단순한 월간 달력처럼 보여도, 안에는 하루를 설계하고 실행하는 세부 기능이 촘촘하게 연결되어 있습니다.",
      groupPlanTitle: "일정과 업무", featureMonthTitle: "월간 캘린더", featureMonthBody: "일정과 업무 패널을 한 화면에서 확인",
      featureMultidayTitle: "멀티데이 일정", featureMultidayBody: "드래그로 날짜 범위를 선택하고 이동·복사",
      featureRoutineTitle: "루틴과 디렉티브", featureRoutineBody: "반복 업무와 실행 항목을 분리 관리",
      featureNlpTitle: "자연어 빠른 등록", featureNlpBody: "문장으로 날짜와 시간을 입력해 일정 생성",
      featureChecklistTitle: "체크리스트와 우선순위", featureChecklistBody: "세부 단계와 중요도를 일정 안에서 관리",
      groupDesktopTitle: "바탕화면과 위젯", featureOverlayTitle: "데스크톱 직접 배치", featureOverlayBody: "필요한 정보가 다른 창 위와 바탕화면에 상시 표시",
      featureResizeTitle: "자유 이동·크기 조절", featureResizeBody: "화면과 작업 방식에 맞춘 위치와 크기",
      featureMultiWidgetTitle: "멀티 위젯", featureMultiWidgetBody: "같은 종류도 이름을 달리해 여러 개 배치",
      featureTemplateTitle: "텍스트 템플릿", featureTemplateBody: "시간·D-Day·다음 일정 값을 조합",
      featureThemeTitle: "테마와 색상", featureThemeBody: "강조색과 패널 표현을 취향대로 설정",
      groupFocusTitle: "집중과 유틸리티", featureFocusTitle: "집중 모드·Pomodoro", featureFocusBody: "할 일을 고른 뒤 바로 타이머 시작",
      featureFocusLogTitle: "집중 기록", featureFocusLogBody: "오늘과 이번 달 세션 시간을 확인",
      featureTimeWidgetsTitle: "시간 도구 5종", featureTimeWidgetsBody: "시계·스톱워치·날짜·카운트다운·D-Day",
      featureWeatherTitle: "날씨 위젯", featureWeatherBody: "선택한 도시의 날씨를 데스크톱에서 확인",
      featureScreenTitle: "화면 고정과 자석 배치", featureScreenBody: "창의 위치를 유지하고 가장자리에 맞춰 정렬",
      groupConnectTitle: "연동과 관리", featureGoogleTitle: "Google 양방향 동기화", featureGoogleBody: "가져오기와 변경 사항 전송을 안전하게 처리",
      featureCalendarTypesTitle: "네 가지 캘린더 유형", featureCalendarTypesBody: "로컬·Google·공유·ICS를 한곳에서 관리",
      featureDiagnosticsTitle: "동기화 진단", featureDiagnosticsBody: "연결 상태, 오류, 삭제 재시도를 확인",
      featurePrintTitle: "인쇄와 PDF", featurePrintBody: "달력과 일정 세부 정보를 문서로 출력",
      featureLanguagesTitle: "19개 언어", featureLanguagesBody: "한국어를 포함한 다국어 인터페이스",
      googleTitle: "처음이어도 괜찮은<br><em>Google Calendar 연동</em>",
      googleLead: "연동은 선택 기능입니다. 한 번만 Google Cloud에서 데스크톱용 인증 파일을 준비하면, 이후에는 Dark Calendar 안에서 캘린더를 선택하고 동기화할 수 있습니다.",
      googleOptionalTitle: "연동하지 않아도 사용 가능", googleOptionalBody: "로컬 캘린더와 위젯 기능은 Google 계정 없이도 동작합니다.",
      googleOnceTitle: "인증 준비는 처음 한 번", googleOnceBody: "같은 Google 계정의 여러 캘린더는 인증 후 목록에서 선택합니다.",
      googleControlTitle: "연결과 해제는 사용자가 결정", googleControlBody: "동기화를 끄거나 인증을 초기화하면 언제든 연결을 중단할 수 있습니다.",
      googleImageAlt: "Google Cloud 프로젝트 준비, 인증 파일 다운로드, 브라우저 권한 승인, 양방향 캘린더 동기화의 네 단계",
      googleFlowOne: "Cloud 준비", googleFlowTwo: "JSON 다운로드", googleFlowThree: "브라우저 인증", googleFlowFour: "양방향 동기화",
      googleSetupTitle: "이 순서대로만 진행하세요.", googleSetupLead: "Google의 화면 이름이 바뀌더라도 핵심은 프로젝트 → API → 동의 화면 → 데스크톱 클라이언트 → 앱 인증 순서입니다.",
      googleDocsLink: "Google 공식 빠른 시작", googleConsoleLink: "Google Cloud Console",
      googleStepOneTitle: "Google Cloud 프로젝트 만들기", googleStepOneBody: "Cloud Console에서 새 프로젝트를 만들거나 기존 프로젝트를 선택합니다. 개인용이라면 알아보기 쉬운 이름이면 충분합니다.",
      googleStepTwoTitle: "Google Calendar API 켜기", googleStepTwoBody: "API 라이브러리에서 Google Calendar API를 찾아 ‘사용’으로 설정합니다. 이 단계가 빠지면 인증 후에도 캘린더를 읽을 수 없습니다.",
      googleStepThreeTitle: "OAuth 동의 화면 준비하기", googleStepThreeBody: "Google Auth Platform의 Branding과 Audience를 설정합니다. 외부(External)·테스트 상태라면 로그인할 본인 Google 계정을 테스트 사용자로 추가합니다.",
      googleStepFourTitle: "데스크톱 앱 인증 파일 받기", googleStepFourBody: "Clients에서 OAuth 클라이언트를 만들고 유형은 반드시 ‘Desktop app’을 선택합니다. 생성 후 JSON 파일을 다운로드합니다.",
      googleStepFourWarning: "Web application 유형은 Dark Calendar에서 동작하지 않습니다.",
      googleStepFiveTitle: "Dark Calendar에서 인증하기", googleStepFiveBody: "설정 → Calendar & Sync → 연결에서 ‘Google Calendar 동기화 사용’을 켜고 JSON 파일을 선택한 뒤 ‘인증’을 누릅니다. 브라우저가 열리면 계정을 선택하고 권한을 허용합니다.",
      googleStepSixTitle: "캘린더 선택·테스트·저장", googleStepSixBody: "연결 후 캘린더 목록에서 사용할 항목을 선택하고 ‘캘린더 접근 테스트’를 실행합니다. 성공 메시지를 확인한 뒤 설정을 저장하면 준비가 끝납니다.",
      syncPullTitle: "Google 일정을 가져옵니다.", syncPullBody: "제목, 날짜·시간, 종일 일정, 설명, 장소, 색상과 반복 일정 정보를 Dark Calendar에서 함께 볼 수 있습니다.",
      syncPushTitle: "내 변경 사항을 보냅니다.", syncPushBody: "Dark Calendar에서 만든 일정과 수정한 시간·내용이 선택한 Google 캘린더에 반영됩니다.",
      syncSafetyTitle: "먼저 확인하고 안전하게 반영합니다.", syncSafetyBody: "동기화할 때 Google 변경 사항을 먼저 확인한 뒤 로컬 변경을 전송합니다. 양쪽이 함께 바뀐 충돌은 기록을 보존하고 선택할 수 있게 안내합니다.",
      permissionTitle: "권한 요청이 크게 보이는 이유", permissionBody: "현재 버전은 여러 캘린더의 일정을 가져오고 만들고 수정·삭제하기 위해 Google Calendar 전체 접근 권한을 사용합니다. 인증 파일과 토큰은 사용자 PC에 저장되며 개발자 서버로 전송되지 않습니다.", permissionLink: "개인정보 처리 방식 확인 ↗",
      shareTitle: "바탕화면을 더 잘 쓰고 싶은 사람에게<br><em>Dark Calendar를 알려주세요.</em>",
      shareBody: "일정과 위젯을 자기 방식대로 배치하고 싶은 친구나 동료에게 이 페이지를 공유해 주세요.",
      shareActionsLabel: "Dark Calendar 공유 방법", shareX: "X에 공유", shareFacebook: "Facebook", shareLinkedIn: "LinkedIn", shareEmail: "이메일", shareCopy: "링크 복사", shareCopied: "링크를 복사했습니다.", shareFailed: "주소창의 링크를 복사해 주세요.",
      shareText: "캘린더와 위젯을 바탕화면에 직접 배치하고, 위치·크기·레이아웃·색상까지 내 방식대로 만드는 Windows 앱, Dark Calendar.", shareKit: "공식 홍보자료 내려받기", footerPromotion: "홍보 자료"
    },
    en: {
      navGoogle: "Google sync",
      metaDescription: "Dark Calendar is a customizable Windows desktop calendar that lets you place, move, resize, recolor, and arrange calendars and widgets directly on your desktop.",
      heroEyebrow: "Custom desktop calendar & widgets for Windows",
      heroTitle: "Turn your desktop into<br><em>your personal time space.</em>",
      heroDescription: "Place your calendar, task panels, clock, weather, and D-Day widgets directly on the desktop. Move and resize everything, then shape layouts and colors around the way you work.",
      heroSecondary: "Explore customization", trustWindows: "Place it right on your desktop",
      desktopTitle: "Beyond an app window.<br><em>Your desktop becomes the calendar.</em>",
      desktopLead: "Dark Calendar’s defining advantage is bringing the tools you need directly onto the desktop. Instead of adapting to a fixed frame, you design the space around your screen and workflow.",
      desktopImageAlt: "Concept image showing calendar and widgets being resized, moved, recolored, and arranged on a desktop",
      desktopImageCaption: "A personalized desktop example that brings movement, resizing, alignment, and color selection into one view.",
      freedomDirectTitle: "Directly on the desktop", freedomDirectBody: "Your calendar, task lists, and widgets remain visible on the desktop without hunting through app windows.",
      freedomMoveTitle: "Move and resize freely", freedomMoveBody: "Place every element where it belongs and adjust width and height for your screen and preferred information density.",
      freedomLayoutTitle: "A layout for your flow", freedomLayoutBody: "Build calendar-first, task-first, or widget-first arrangements for different ways of working.",
      freedomColorTitle: "Colors that feel like yours", freedomColorBody: "Combine themes, accents, panels, and widget treatments to create your own visual system.",
      atlasImageAlt: "Feature map connecting calendar planning with tasks, focus, widgets, and sync",
      atlasImageCaption: "Planning, action, focus, widgets, and sync all connect around the calendar.",
      atlasTitle: "Every visible feature—<br>and every hidden tool", atlasLead: "It may look like a simple monthly calendar, but a detailed system for planning and running your day is connected underneath.",
      groupPlanTitle: "Schedule & tasks", featureMonthTitle: "Monthly calendar", featureMonthBody: "See schedules and work panels together",
      featureMultidayTitle: "Multi-day events", featureMultidayBody: "Drag date ranges, then move or copy",
      featureRoutineTitle: "Routines & directives", featureRoutineBody: "Separate recurring work from action items",
      featureNlpTitle: "Natural-language quick add", featureNlpBody: "Create events by typing dates and times in a sentence",
      featureChecklistTitle: "Checklists & priority", featureChecklistBody: "Manage steps and importance inside each task",
      groupDesktopTitle: "Desktop & widgets", featureOverlayTitle: "Desktop-native placement", featureOverlayBody: "Keep essential information visible over windows and on the desktop",
      featureResizeTitle: "Free movement & resizing", featureResizeBody: "Choose the position and size that fit your screen",
      featureMultiWidgetTitle: "Multiple widgets", featureMultiWidgetBody: "Create several named instances of the same type",
      featureTemplateTitle: "Text templates", featureTemplateBody: "Combine time, D-Day, and next-event values",
      featureThemeTitle: "Themes & colors", featureThemeBody: "Tune accents and panel treatments to your taste",
      groupFocusTitle: "Focus & utilities", featureFocusTitle: "Focus Mode & Pomodoro", featureFocusBody: "Choose a task and start the timer immediately",
      featureFocusLogTitle: "Focus history", featureFocusLogBody: "Review today’s and this month’s session time",
      featureTimeWidgetsTitle: "Five time tools", featureTimeWidgetsBody: "Clock, stopwatch, date, countdown, and D-Day",
      featureWeatherTitle: "Weather widget", featureWeatherBody: "See your chosen city’s weather on the desktop",
      featureScreenTitle: "Lock & magnetic placement", featureScreenBody: "Hold windows in place and align them to edges",
      groupConnectTitle: "Connect & manage", featureGoogleTitle: "Google two-way sync", featureGoogleBody: "Safely pull events and send local changes",
      featureCalendarTypesTitle: "Four calendar types", featureCalendarTypesBody: "Manage local, Google, shared, and ICS together",
      featureDiagnosticsTitle: "Sync diagnostics", featureDiagnosticsBody: "Review connection status, errors, and delete retries",
      featurePrintTitle: "Print & PDF", featurePrintBody: "Export calendar pages and event details",
      featureLanguagesTitle: "19 languages", featureLanguagesBody: "A multilingual interface including Korean and English",
      googleTitle: "Google Calendar sync,<br><em>explained for first-timers</em>",
      googleLead: "Sync is optional. Prepare a desktop credential file in Google Cloud once, then choose and sync calendars from inside Dark Calendar.",
      googleOptionalTitle: "Works without Google sync", googleOptionalBody: "Local calendars and desktop widgets work without a Google account.",
      googleOnceTitle: "Set up authorization once", googleOnceBody: "After signing in, choose multiple calendars from the same Google account.",
      googleControlTitle: "You control the connection", googleControlBody: "Turn sync off or reset authorization whenever you want to disconnect.",
      googleImageAlt: "Four stages: prepare a Google Cloud project, download credentials, approve access in a browser, and start two-way calendar sync",
      googleFlowOne: "Prepare Cloud", googleFlowTwo: "Download JSON", googleFlowThree: "Authorize in browser", googleFlowFour: "Two-way sync",
      googleSetupTitle: "Follow these steps in order.", googleSetupLead: "Even if Google renames a screen, the core order remains project → API → consent → desktop client → app authorization.",
      googleDocsLink: "Google official quickstart", googleConsoleLink: "Google Cloud Console",
      googleStepOneTitle: "Create a Google Cloud project", googleStepOneBody: "Create a project in Cloud Console or select an existing one. For personal use, any clear name is fine.",
      googleStepTwoTitle: "Enable the Google Calendar API", googleStepTwoBody: "Find Google Calendar API in the API Library and enable it. Without this step, authorization may succeed but calendars cannot be read.",
      googleStepThreeTitle: "Configure the OAuth consent screen", googleStepThreeBody: "Set up Branding and Audience in Google Auth Platform. If the app is External and in Testing, add the Google account you will use as a test user.",
      googleStepFourTitle: "Download desktop credentials", googleStepFourBody: "Create an OAuth client under Clients and choose ‘Desktop app’ as the application type. Download the JSON file after creation.",
      googleStepFourWarning: "The Web application type does not work with Dark Calendar.",
      googleStepFiveTitle: "Authorize in Dark Calendar", googleStepFiveBody: "Open Settings → Calendar & Sync → Connection, enable Google Calendar sync, choose the JSON file, and select Authenticate. In the browser, choose your account and allow access.",
      googleStepSixTitle: "Choose, test, and save", googleStepSixBody: "Choose calendars from the loaded list and run Calendar Access Test. Once it succeeds, save the settings to finish.",
      syncPullTitle: "Bring Google events in.", syncPullBody: "View titles, dates and times, all-day events, descriptions, locations, colors, and recurring events in Dark Calendar.",
      syncPushTitle: "Send your changes out.", syncPushBody: "Events created in Dark Calendar and edits to their time or content are reflected in the selected Google calendar.",
      syncSafetyTitle: "Check first, then apply safely.", syncSafetyBody: "Sync checks Google changes before sending local edits. If both sides changed, it preserves conflict records and guides you through the choice.",
      permissionTitle: "Why the permission request looks broad", permissionBody: "The current version uses full Google Calendar access to read, create, edit, and delete events across multiple calendars. Credentials and tokens stay on your PC and are not sent to the developer’s server.", permissionLink: "Review data handling ↗",
      shareTitle: "Know someone who wants a better desktop?<br><em>Share Dark Calendar.</em>",
      shareBody: "Send this page to a friend or teammate who wants calendars and widgets arranged around the way they work.",
      shareActionsLabel: "Ways to share Dark Calendar", shareX: "Share on X", shareFacebook: "Facebook", shareLinkedIn: "LinkedIn", shareEmail: "Email", shareCopy: "Copy link", shareCopied: "Link copied.", shareFailed: "Please copy the link from the address bar.",
      shareText: "Dark Calendar is a Windows app that puts calendars and widgets directly on your desktop—with freely adjustable position, size, layout, and color.", shareKit: "Download the official media kit", footerPromotion: "Promotion kit"
    },
    ja: {
      navGoogle: "Google連携",
      metaDescription: "カレンダーとウィジェットをデスクトップに直接配置し、サイズ・位置・レイアウト・色を自由に調整できるWindows用カスタムカレンダー、Dark Calendar。",
      heroEyebrow: "Windows用カスタムデスクトップカレンダー＆ウィジェット",
      heroTitle: "デスクトップを<br><em>自分だけの時間空間に。</em>",
      heroDescription: "カレンダー、タスクパネル、時計、天気、D-Dayをデスクトップに直接配置。位置とサイズ、レイアウト、色まで自分の使い方に合わせられます。",
      heroSecondary: "カスタマイズを見る", trustWindows: "デスクトップに直接配置",
      desktopTitle: "アプリの枠を超えて<br><em>デスクトップ自体がカレンダーに</em>",
      desktopLead: "Dark Calendar最大の魅力は、必要な機能をデスクトップに直接実装できることです。決められた枠ではなく、画面と仕事の流れに合わせて空間を設計できます。",
      desktopImageAlt: "デスクトップ上でカレンダーとウィジェットのサイズ、位置、色、レイアウトを調整するコンセプト画像",
      desktopImageCaption: "移動・サイズ変更・整列・色選択を一画面で理解できるカスタムデスクトップ例です。",
      freedomDirectTitle: "デスクトップに直接", freedomDirectBody: "アプリを探さなくても、カレンダー、タスク、ウィジェットがデスクトップに表示され続けます。",
      freedomMoveTitle: "位置とサイズを自由に", freedomMoveBody: "各要素を好きな場所へ移動し、画面と情報量に合わせて幅と高さを調整できます。",
      freedomLayoutTitle: "自分の流れに合う配置", freedomLayoutBody: "カレンダー中心、タスク中心、ウィジェット中心など目的別の画面を作れます。",
      freedomColorTitle: "色と表現も自分好みに", freedomColorBody: "テーマ、アクセント色、パネル、ウィジェット表現を組み合わせて独自の視覚体系を作れます。",
      atlasImageAlt: "カレンダーを中心にタスク、集中、ウィジェット、同期がつながる機能マップ",
      atlasImageCaption: "計画・実行・集中・ウィジェット・同期がカレンダーを中心につながります。",
      atlasTitle: "見える機能から<br>隠れたツールまで", atlasLead: "シンプルな月間カレンダーに見えても、一日を設計し実行する細かな機能が内部でつながっています。",
      groupPlanTitle: "予定とタスク", featureMonthTitle: "月間カレンダー", featureMonthBody: "予定とタスクパネルを一画面で確認",
      featureMultidayTitle: "複数日予定", featureMultidayBody: "ドラッグで期間を選び、移動・コピー",
      featureRoutineTitle: "ルーティンとディレクティブ", featureRoutineBody: "反復作業と実行項目を分けて管理",
      featureNlpTitle: "自然文ですばやく登録", featureNlpBody: "文章で日付と時刻を入力して予定を作成",
      featureChecklistTitle: "チェックリストと優先度", featureChecklistBody: "細かな手順と重要度を予定内で管理",
      groupDesktopTitle: "デスクトップとウィジェット", featureOverlayTitle: "デスクトップ直接配置", featureOverlayBody: "必要な情報をウィンドウ上やデスクトップに常時表示",
      featureResizeTitle: "自由な移動・サイズ変更", featureResizeBody: "画面と作業方法に合う位置と大きさ",
      featureMultiWidgetTitle: "複数ウィジェット", featureMultiWidgetBody: "同じ種類も名前を変えて複数配置",
      featureTemplateTitle: "テキストテンプレート", featureTemplateBody: "時刻・D-Day・次の予定を組み合わせ",
      featureThemeTitle: "テーマと色", featureThemeBody: "アクセントとパネル表現を好みに設定",
      groupFocusTitle: "集中とユーティリティ", featureFocusTitle: "集中モード・Pomodoro", featureFocusBody: "タスクを選んですぐタイマー開始",
      featureFocusLogTitle: "集中履歴", featureFocusLogBody: "今日と今月のセッション時間を確認",
      featureTimeWidgetsTitle: "5種類の時間ツール", featureTimeWidgetsBody: "時計・ストップウォッチ・日付・カウントダウン・D-Day",
      featureWeatherTitle: "天気ウィジェット", featureWeatherBody: "選んだ都市の天気をデスクトップで確認",
      featureScreenTitle: "画面固定とマグネット配置", featureScreenBody: "位置を保ち、画面端に合わせて整列",
      groupConnectTitle: "連携と管理", featureGoogleTitle: "Google双方向同期", featureGoogleBody: "取得とローカル変更の送信を安全に処理",
      featureCalendarTypesTitle: "4種類のカレンダー", featureCalendarTypesBody: "ローカル・Google・共有・ICSを一元管理",
      featureDiagnosticsTitle: "同期診断", featureDiagnosticsBody: "接続状態、エラー、削除再試行を確認",
      featurePrintTitle: "印刷とPDF", featurePrintBody: "カレンダーと予定詳細を文書出力",
      featureLanguagesTitle: "19言語", featureLanguagesBody: "韓国語・日本語を含む多言語UI",
      googleTitle: "初めてでも分かる<br><em>Google Calendar連携</em>",
      googleLead: "連携は任意です。Google Cloudでデスクトップ用認証ファイルを一度準備すれば、その後はDark Calendar内でカレンダーを選んで同期できます。",
      googleOptionalTitle: "連携なしでも使用可能", googleOptionalBody: "ローカルカレンダーとウィジェットはGoogleアカウントなしでも動作します。",
      googleOnceTitle: "認証準備は最初の一度", googleOnceBody: "同じGoogleアカウントの複数カレンダーは認証後に一覧から選べます。",
      googleControlTitle: "接続と解除は自分で管理", googleControlBody: "同期をオフにするか認証を初期化すれば、いつでも接続を停止できます。",
      googleImageAlt: "Google Cloud準備、認証ファイル取得、ブラウザ承認、双方向同期の4段階",
      googleFlowOne: "Cloud準備", googleFlowTwo: "JSON取得", googleFlowThree: "ブラウザ認証", googleFlowFour: "双方向同期",
      googleSetupTitle: "この順番で進めてください。", googleSetupLead: "Googleの画面名が変わっても、プロジェクト→API→同意画面→デスクトップクライアント→アプリ認証の順は同じです。",
      googleDocsLink: "Google公式クイックスタート", googleConsoleLink: "Google Cloud Console",
      googleStepOneTitle: "Google Cloudプロジェクトを作成", googleStepOneBody: "Cloud Consoleで新しいプロジェクトを作るか既存のものを選びます。個人用なら分かりやすい名前で十分です。",
      googleStepTwoTitle: "Google Calendar APIを有効化", googleStepTwoBody: "APIライブラリでGoogle Calendar APIを探して有効にします。省略すると認証後もカレンダーを読めません。",
      googleStepThreeTitle: "OAuth同意画面を準備", googleStepThreeBody: "Google Auth PlatformのBrandingとAudienceを設定します。External・Testingの場合はログインする自分のGoogleアカウントをテストユーザーに追加します。",
      googleStepFourTitle: "デスクトップ用認証ファイルを取得", googleStepFourBody: "ClientsでOAuthクライアントを作成し、種類は必ず「Desktop app」を選びます。作成後にJSONをダウンロードします。",
      googleStepFourWarning: "Web application種類はDark Calendarでは動作しません。",
      googleStepFiveTitle: "Dark Calendarで認証", googleStepFiveBody: "設定→Calendar & Sync→接続で同期を有効にし、JSONを選んで「認証」を押します。ブラウザでアカウントを選び、アクセスを許可します。",
      googleStepSixTitle: "選択・テスト・保存", googleStepSixBody: "一覧から使うカレンダーを選び、「カレンダーアクセスのテスト」を実行します。成功を確認して設定を保存すれば完了です。",
      syncPullTitle: "Google予定を取り込みます。", syncPullBody: "タイトル、日時、終日予定、説明、場所、色、繰り返し予定をDark Calendarで確認できます。",
      syncPushTitle: "変更内容をGoogleへ送ります。", syncPushBody: "Dark Calendarで作成した予定や変更した時刻・内容が選択中のGoogleカレンダーへ反映されます。",
      syncSafetyTitle: "先に確認して安全に反映。", syncSafetyBody: "Google側の変更を先に確認してからローカル変更を送信します。両方が変わった場合は記録を保存し、選択できるよう案内します。",
      permissionTitle: "権限要求が大きく見える理由", permissionBody: "現行版は複数カレンダーの予定を取得・作成・編集・削除するためGoogle Calendar全体へのアクセスを使用します。認証ファイルとトークンはPCに保存され、開発者サーバーへ送信されません。", permissionLink: "データ処理を確認 ↗",
      shareTitle: "デスクトップをもっと活用したい人へ<br><em>Dark Calendarを紹介してください。</em>",
      shareBody: "カレンダーやウィジェットを自分らしく配置したい友人や同僚に、このページを共有してください。",
      shareActionsLabel: "Dark Calendarの共有方法", shareX: "Xで共有", shareFacebook: "Facebook", shareLinkedIn: "LinkedIn", shareEmail: "メール", shareCopy: "リンクをコピー", shareCopied: "リンクをコピーしました。", shareFailed: "アドレスバーのリンクをコピーしてください。",
      shareText: "カレンダーとウィジェットをデスクトップに直接置き、位置・サイズ・レイアウト・色まで自由に整えられるWindowsアプリ、Dark Calendar。", shareKit: "公式プロモーション素材を入手", footerPromotion: "プロモーション資料"
    },
    zh: {
      navGoogle: "Google 同步",
      metaDescription: "Dark Calendar 是一款可自定义的 Windows 桌面日历，可将日历与小组件直接放在桌面并自由调整大小、位置、布局和颜色。",
      heroEyebrow: "Windows 个性化桌面日历与小组件",
      heroTitle: "把桌面变成<br><em>专属于你的时间空间。</em>",
      heroDescription: "将日历、任务面板、时钟、天气和 D-Day 小组件直接放在桌面。自由移动与缩放，并按你的工作方式定制布局和颜色。",
      heroSecondary: "探索自定义功能", trustWindows: "直接放在桌面",
      desktopTitle: "超越应用窗口，<br><em>让桌面本身成为日历</em>",
      desktopLead: "Dark Calendar最大的优势，是把需要的功能直接实现于桌面。无需适应固定框架，你可以围绕自己的屏幕与工作流程设计空间。",
      desktopImageAlt: "在桌面上调整日历和小组件大小、位置、颜色与布局的概念图",
      desktopImageCaption: "一张呈现移动、缩放、对齐和颜色选择的个性化桌面示例。",
      freedomDirectTitle: "直接显示在桌面", freedomDirectBody: "无需反复寻找应用窗口，日历、任务和小组件会持续显示在桌面上。",
      freedomMoveTitle: "自由移动与缩放", freedomMoveBody: "把每个元素放到合适的位置，并根据屏幕和信息密度调整宽高。",
      freedomLayoutTitle: "布局配合你的流程", freedomLayoutBody: "可创建以日历、任务或小组件为中心的不同工作界面。",
      freedomColorTitle: "颜色与呈现皆可自定义", freedomColorBody: "组合主题、强调色、面板和小组件样式，打造自己的视觉系统。",
      atlasImageAlt: "以日历为中心连接任务、专注、小组件和同步功能的完整功能图",
      atlasImageCaption: "计划、执行、专注、小组件与同步围绕日历连接起来。",
      atlasTitle: "从常用功能到<br>隐藏工具一览无余", atlasLead: "它看似简洁的月历，背后却连接着规划和执行一天所需的细致功能。",
      groupPlanTitle: "日程与任务", featureMonthTitle: "月度日历", featureMonthBody: "在同一界面查看日程与任务面板",
      featureMultidayTitle: "多日事件", featureMultidayBody: "拖动选择日期范围并移动或复制",
      featureRoutineTitle: "例行任务与指令", featureRoutineBody: "将重复工作与执行项分开管理",
      featureNlpTitle: "自然语言快速添加", featureNlpBody: "用句子输入日期与时间来创建日程",
      featureChecklistTitle: "清单与优先级", featureChecklistBody: "在任务中管理步骤和重要程度",
      groupDesktopTitle: "桌面与小组件", featureOverlayTitle: "直接桌面放置", featureOverlayBody: "让重要信息常驻窗口上方和桌面",
      featureResizeTitle: "自由移动与缩放", featureResizeBody: "根据屏幕与工作方式调整位置和大小",
      featureMultiWidgetTitle: "多个小组件", featureMultiWidgetBody: "同一类型也可命名并创建多个实例",
      featureTemplateTitle: "文字模板", featureTemplateBody: "组合时间、D-Day 与下一个日程",
      featureThemeTitle: "主题与颜色", featureThemeBody: "按喜好设置强调色和面板表现",
      groupFocusTitle: "专注与工具", featureFocusTitle: "专注模式与 Pomodoro", featureFocusBody: "选好任务后立即开始计时",
      featureFocusLogTitle: "专注记录", featureFocusLogBody: "查看今天和本月的专注时长",
      featureTimeWidgetsTitle: "五种时间工具", featureTimeWidgetsBody: "时钟、秒表、日期、倒计时与 D-Day",
      featureWeatherTitle: "天气小组件", featureWeatherBody: "在桌面查看所选城市的天气",
      featureScreenTitle: "窗口锁定与磁吸", featureScreenBody: "保持窗口位置并对齐屏幕边缘",
      groupConnectTitle: "连接与管理", featureGoogleTitle: "Google 双向同步", featureGoogleBody: "安全获取事件并发送本地更改",
      featureCalendarTypesTitle: "四种日历类型", featureCalendarTypesBody: "统一管理本地、Google、共享与 ICS",
      featureDiagnosticsTitle: "同步诊断", featureDiagnosticsBody: "查看连接状态、错误和删除重试",
      featurePrintTitle: "打印与 PDF", featurePrintBody: "导出日历页面与事件详情",
      featureLanguagesTitle: "19 种语言", featureLanguagesBody: "包含韩语、中文等多语言界面",
      googleTitle: "第一次也能看懂的<br><em>Google Calendar 同步</em>",
      googleLead: "同步是可选功能。只需在Google Cloud准备一次桌面凭据文件，之后便可在Dark Calendar中选择并同步日历。",
      googleOptionalTitle: "不同步也能使用", googleOptionalBody: "本地日历与桌面小组件无需Google帐号即可运行。",
      googleOnceTitle: "授权准备只做一次", googleOnceBody: "登录后可从同一Google帐号中选择多个日历。",
      googleControlTitle: "连接与断开由你决定", googleControlBody: "关闭同步或重置授权，即可随时停止连接。",
      googleImageAlt: "准备Google Cloud项目、下载凭据、浏览器授权和双向同步四个阶段",
      googleFlowOne: "准备 Cloud", googleFlowTwo: "下载 JSON", googleFlowThree: "浏览器授权", googleFlowFour: "双向同步",
      googleSetupTitle: "请按这个顺序操作。", googleSetupLead: "即使Google更改页面名称，核心顺序仍是项目→API→同意页面→桌面客户端→应用授权。",
      googleDocsLink: "Google 官方快速入门", googleConsoleLink: "Google Cloud Console",
      googleStepOneTitle: "创建 Google Cloud 项目", googleStepOneBody: "在Cloud Console创建新项目或选择现有项目。个人使用时，取一个容易识别的名称即可。",
      googleStepTwoTitle: "启用 Google Calendar API", googleStepTwoBody: "在API库中找到Google Calendar API并启用。省略此步，即使授权成功也无法读取日历。",
      googleStepThreeTitle: "配置 OAuth 同意页面", googleStepThreeBody: "在Google Auth Platform设置Branding和Audience。若为External并处于Testing，请把准备登录的Google帐号添加为测试用户。",
      googleStepFourTitle: "下载桌面应用凭据", googleStepFourBody: "在Clients中创建OAuth客户端，应用类型必须选择“Desktop app”。创建后下载JSON文件。",
      googleStepFourWarning: "Web application 类型无法用于 Dark Calendar。",
      googleStepFiveTitle: "在 Dark Calendar 中授权", googleStepFiveBody: "打开设置→Calendar & Sync→连接，启用同步，选择JSON后点击“授权”。浏览器打开后选择帐号并允许访问。",
      googleStepSixTitle: "选择、测试并保存", googleStepSixBody: "从列表选择要用的日历并运行“日历访问测试”。看到成功消息后保存设置即可。",
      syncPullTitle: "导入 Google 日程。", syncPullBody: "可在Dark Calendar中查看标题、日期与时间、全天事件、说明、地点、颜色和重复事件。",
      syncPushTitle: "发送你的更改。", syncPushBody: "在Dark Calendar中新建的事件，以及对时间与内容的修改，会同步到所选Google日历。",
      syncSafetyTitle: "先检查，再安全更新。", syncSafetyBody: "同步会先检查Google端的更改，再发送本地编辑。若两端都已变化，系统会保留冲突记录并引导你选择。",
      permissionTitle: "为什么权限请求看起来较广", permissionBody: "当前版本使用完整Google Calendar访问权限，以便在多个日历中读取、创建、编辑和删除事件。凭据与令牌只保存在你的电脑，不会发送到开发者服务器。", permissionLink: "查看数据处理方式 ↗",
      shareTitle: "把 Dark Calendar 分享给<br><em>想让桌面更高效的人。</em>",
      shareBody: "将此页面分享给希望按自己的方式排列日历和小组件的朋友或同事。",
      shareActionsLabel: "Dark Calendar 分享方式", shareX: "分享到 X", shareFacebook: "Facebook", shareLinkedIn: "LinkedIn", shareEmail: "电子邮件", shareCopy: "复制链接", shareCopied: "链接已复制。", shareFailed: "请复制地址栏中的链接。",
      shareText: "Dark Calendar 是一款 Windows 应用，可将日历和小组件直接放在桌面，并自由调整位置、大小、布局和颜色。", shareKit: "下载官方推广素材", footerPromotion: "推广资料"
    }
  };

  Object.entries(expandedTranslations).forEach(([locale, copy]) => {
    Object.assign(translations[locale], copy);
  });

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

  const richTextKeys = new Set(["heroTitle", "desktopTitle", "featuresTitle", "atlasTitle", "exploreTitle", "googleTitle", "workflowTitle", "privacyTitle", "faqTitle", "ctaTitle", "shareTitle"]);
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

  function publicShareUrl() {
    const url = new URL("https://namer-kimhyojin.github.io/DARK-CALENDAR/");
    if (currentLanguage !== "ko") url.searchParams.set("lang", currentLanguage);
    return url.toString();
  }

  function updateShareLinks() {
    const copy = translations[currentLanguage];
    const url = publicShareUrl();
    const values = {
      x: `https://twitter.com/intent/tweet?text=${encodeURIComponent(copy.shareText)}&url=${encodeURIComponent(url)}`,
      facebook: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}`,
      linkedin: `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(url)}`,
      email: `mailto:?subject=${encodeURIComponent(copy.metaTitle)}&body=${encodeURIComponent(`${copy.shareText}\n\n${url}`)}`
    };
    document.querySelectorAll("[data-share-channel]").forEach((node) => {
      const value = values[node.dataset.shareChannel];
      if (value) node.setAttribute("href", value);
    });
    const status = document.querySelector("[data-share-status]");
    if (status) status.textContent = "";
  }

  function setLanguage(language, persist) {
    currentLanguage = normalizedLanguage(language);
    const copy = translations[currentLanguage];
    document.documentElement.lang = currentLanguage === "zh" ? "zh-CN" : currentLanguage;
    document.title = copy.metaTitle;
    document.querySelector('meta[name="description"]')?.setAttribute("content", copy.metaDescription);
    document.querySelector('meta[property="og:description"]')?.setAttribute("content", copy.metaDescription);
    document.querySelector('meta[name="twitter:description"]')?.setAttribute("content", copy.metaDescription);
    document.querySelector('meta[name="twitter:title"]')?.setAttribute("content", copy.metaTitle);
    document.querySelector('meta[property="og:locale"]')?.setAttribute("content", ({ ko: "ko_KR", en: "en_US", ja: "ja_JP", zh: "zh_CN" })[currentLanguage]);

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
    updateShareLinks();

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
    const eventActive = currentConfig.event.enabled !== false && Boolean(currentConfig.eventUrl);
    if (eventBand) eventBand.hidden = !eventActive;

    const schemaNode = document.querySelector("#software-schema");
    if (schemaNode) {
      try {
        const schema = JSON.parse(schemaNode.textContent);
        schema.softwareVersion = currentConfig.appVersion;
        schema.downloadUrl = currentConfig.microsoftStoreUrl;
        schema.license = currentConfig.licenseUrl;
        schemaNode.textContent = JSON.stringify(schema);
      } catch (_error) {
        // The visible site remains usable if structured data cannot be refreshed.
      }
    }
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

  function setupSharing() {
    const copyButton = document.querySelector("[data-copy-share]");
    const status = document.querySelector("[data-share-status]");
    if (!copyButton || !status) return;

    copyButton.addEventListener("click", async () => {
      const url = publicShareUrl();
      let copied = false;
      try {
        await window.navigator.clipboard.writeText(url);
        copied = true;
      } catch (_error) {
        const helper = document.createElement("textarea");
        helper.value = url;
        helper.setAttribute("readonly", "");
        helper.style.position = "fixed";
        helper.style.opacity = "0";
        document.body.appendChild(helper);
        helper.select();
        copied = document.execCommand("copy");
        helper.remove();
      }
      status.textContent = copied ? translations[currentLanguage].shareCopied : translations[currentLanguage].shareFailed;
    });
  }

  setupHeader();
  setupLanguagePicker();
  setupScreenExplorer();
  setupLightbox();
  setupFaq();
  setupSharing();
  setLanguage(savedLanguage(), false);

  fetch("site-config.json", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error("Config request failed");
      return response.json();
    })
    .then(applyConfig)
    .catch(() => applyConfig(fallbackConfig));
})();
