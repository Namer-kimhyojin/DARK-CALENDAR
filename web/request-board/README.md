# Air Calendar request board

The promotional homepage in `docs/` uses this anonymous request API. Production posts live in the Sites-managed D1 binding `DB`, independently of desktop calendars. Images live in the Sites-managed R2 binding `BUCKET`. Post passwords use salted PBKDF2-SHA256 (100,000 iterations) with a secret server pepper. Public responses exclude password material; SQL uses bound parameters.

Authors may attach up to three PNG/JPEG/WebP images of 5 MiB each. Create/edit accepts JSON for text-only operations or multipart `payload` JSON plus `images` file parts. Edits may send `removeImages` IDs belonging to that post. The server checks signatures, MIME types, dimensions (8,192 per side and 24 million pixels), counts and bounded request sizes. The homepage normalizes images through canvas, offers file/drop/paste previews, and displays a zoom viewer. Image responses are served through opaque IDs with fixed image MIME, `nosniff`, and no caching; private object keys are never exposed.

Content, image metadata and revision guards commit in one D1 batch. Uploaded objects are staged in a durable cleanup queue before R2 writes; successful commits remove those entries. Rejected/interrupted uploads and post/image deletion retain cleanup entries until R2 deletion succeeds. A subsequent API request retries expired cleanup entries. Metadata removal immediately prevents public image access. Additive table creation preserves existing posts; neither D1 nor R2 is replaced during deployment.

## Development and verification

Requires Node.js 24 or newer; no npm packages are needed.

```sh
npm test
npm run build
npm run dev
```

The local API runs at `http://127.0.0.1:8787`, with persistent SQLite in the ignored `.local/` directory. Its development administrator password is `development-admin-only`. Development CORS permits a frontend at `http://127.0.0.1:8765` only. Production never sets `DEV_MODE`.

## Runtime configuration

Preserve `.openai/hosting.json` and its opaque `project_id`; never create a replacement Site for a redeploy. Set these as secret runtime variables through Sites, never in source or the deployment archive:

- `BOARD_PASSWORD_PEPPER`: stable random secret. Losing or rotating it invalidates existing authors' passwords.
- `ADMIN_PASSWORD_HASH`: SHA256 hex digest of the administrator password. Changing it affects new logins; existing sessions expire after one hour.

The owner credential is kept outside the repository in the current Windows user's local profile. Admin login is available at the bottom of the homepage board. Sessions remain only in browser memory and expire after one hour.

## Publishing

1. Commit the matching frontend and backend source.
2. Split `web/request-board` with `git subtree split` and push that full SHA to this Site's configured source branch using an ephemeral credential. Never persist the Git token.
3. Build from that exact source; archive `.openai/hosting.json` and `dist/server/index.js` plus its generated Wrangler configuration.
4. Save a Sites version with the pushed full SHA and archive, then deploy the saved version. Inspect its terminal status and test live `/api/health`, CRUD and password rejection.
5. Publish `docs/` through the existing GitHub Pages `main:/docs` deployment. `docs/site-config.json` and the HTML fallback contain the API URL.

The API initializes tables additively. Do not delete or replace the D1 database on updates. Creation is idempotent; edits use optimistic revisions. Anonymous create and password attempts, and administrator logins, have durable rate limits. User text is rendered as plain text in the homepage. CORS permits the existing GitHub Pages origin and the API's own origin; it is not treated as authentication.

The tests use real SQLite through a D1-compatible adapter to verify CRUD, authentication, revisions, filters, SQL escaping, idempotency, request validation and rate limits. Production uses the [D1 Worker API](https://developers.cloudflare.com/d1/worker-api/) and [Workers Web Crypto](https://developers.cloudflare.com/workers/runtime-apis/web-crypto/).
