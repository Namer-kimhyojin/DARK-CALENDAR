# Four-language calendar setup guide

All four guides have complete static HTML, including navigation, instructions, image captions, accessibility labels, and metadata. They remain readable when JavaScript or browser storage is disabled.

| Language | Published page | Catalog | Screenshots and hero |
|---|---|---|---|
| Korean | `docs/sync-guide.html` | `locales/ko.json` | `docs/assets/sync-guide/` |
| English | `docs/sync-guide-en.html` | `locales/en.json` | `docs/assets/sync-guide/en/` |
| Japanese | `docs/sync-guide-ja.html` | `locales/ja.json` | `docs/assets/sync-guide/ja/` |
| Simplified Chinese | `docs/sync-guide-zh.html` | `locales/zh.json` | `docs/assets/sync-guide/zh/` |

Edit `template.html` for shared structure and the catalogs for wording. Every catalog must have the same keys. `html.*` values are HTML fragments; `attr.*` values are plain text escaped by the builder. Preserve links, code, and template placeholders. Use the labels shown in the current app locale; newer Japanese/Chinese controls may still use English. The guide explains these labels in the reader's language.

Rebuild with the project virtual environment:

```powershell
.venv/Scripts/python.exe web/sync-guide/build.py
.venv/Scripts/python.exe web/sync-guide/build.py --check
```

The builder checks catalog completeness, markup/link preservation, remaining Korean in other-language catalogs, unresolved placeholders and image presence. It sets localized image paths, PNG dimensions, canonical/alternate links, Open Graph locale and the active language link.

`docs/sync-guide.js` shares the homepage's `dark-calendar-language` preference. An explicit `?lang=ko|en|ja|zh` wins. Direct translated pages select their own language. The default entry page uses the saved preference, then browser language, then Korean. Language links preserve the current section. Homepage links include an explicit language so the preference also works without storage.

The app's locale files and application behavior are separate from this website. This guide does not change those files.
