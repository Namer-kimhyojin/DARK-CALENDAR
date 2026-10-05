# Air Calendar Global Promotion Log

This log records completed promotion actions and their observable verification points. Estimated outcomes are not recorded as measured results.

## 2026-09-17 — Search discovery

- **Action:** Added an IndexNow ownership key and submitted the newly published English use-case pages after production deployment.
- **Audience intents:** Windows desktop calendar, Google Calendar desktop overlay, D-Day/countdown widget, and Pomodoro calendar workflow.
- **Verification:** The key file and all submitted URLs must return HTTP 200 before submission; retain the IndexNow HTTP response as execution evidence.
- **Measure next:** Bing Webmaster Tools IndexNow receipt, crawl status, indexed URLs, impressions, and Store visits attributed to each page's existing `cid`.
- **Boundary:** IndexNow notifies participating search engines of changes; it does not guarantee crawling, ranking, or indexing.

## 2026-10-02 — Local calendar purchase intent

- Baseline: four English intent guides; campaign metrics have no observed acquisition values. Store listing identifies Air Calendar; live guide checked before change. No measured keyword volume or conversion lift available.
- Candidates: local-calendar SEO (qualified intent, low effort, reversible, feedback in days/weeks); Store copy (high intent, account access required); community post (potential reach, moderation/login dependency). Chose the owned local-calendar guide.
- Action: publish /offline-desktop-calendar-windows/, link from homepage and desktop guide, and add to sitemap. Reuse approved dashboard screenshot. Explain local planning, paid Store installation, and optional user-managed Google OAuth without claiming all features work offline.
- Attribution: aircal-20261002-seo-local-calendar. Preserve all existing campaign IDs.
- Validation: verify metadata, screenshot and internal links, desktop/mobile rendering, Store CTA campaign ID, and production response after deployment.
- Measure: review Store campaign page views and acquisitions on October 9 and October 16; record unavailable data as blank. Check search impressions and indexing only if webmaster access is available. No automated reminder created.
- Next candidate: refresh version metadata in existing English guides against the current release; then evaluate Store screenshot clarity when account access is available.

## 2026-10-05 — Conversion path and measurement repairs

- Baseline: read-only promotion audit found four malformed metric rows, two guides carrying softwareVersion 3.7.3 while the published site reported 3.7.10, and no homepage Store campaign ID. Homepage document width was 1546px at a 1440px viewport and 510px at 390px. Acquisition values remain unavailable.
- Candidates: repair the owned conversion path (qualified existing visitors, low effort, reversible, immediate technical feedback); create another SEO guide (possible additional reach, slower feedback); revise Store screenshots (account and current-asset verification required). Selected the existing conversion path and measurement foundation.
- Action: contain hero decoration and desktop mockup overflow, fit the mobile/tablet mockup within its visual column, remove outdated optional guide version fields, repair the four CSV rows, and register the four pre-existing SEO campaign IDs for measurement.
- New attribution: aircal-20261005-owned-home on the homepage's five Store links and SoftwareApplication download URL. Works with static HTML and after config loading; an existing configured campaign ID takes precedence. Existing SEO IDs and locale/query parameters are preserved.
- Local validation: metadata/link/metric audit passed 202 checks with zero failures. Browser verification passed 90 checks covering 11 homepage widths (320–1440px), mobile ko/en/ja/zh, five guides and the media kit, images/runtime, configuration-fetch failure, an existing campaign ID, and JavaScript-disabled homepage links. Unobserved acquisition data remains a warning, not a fabricated zero.
- Deployment verification: confirm the production CSS/JS/HTML match the scoped commit, campaign links carry the expected IDs, Pages publishes that commit, and rerun the live audit and browser checks. A push alone is not completion.
- Measure next: obtain Store campaign page views and acquisitions for the existing guide IDs and the new homepage ID on October 12 and October 19 if account access is available. Keep unavailable numeric fields blank. No reminder or recurring automation was created by this repair.
- Next strongest candidate: review current Store screenshots and descriptions against verified product behavior and compare attributed results when acquisition data is available. This repair proves technical correctness, not a conversion lift.
