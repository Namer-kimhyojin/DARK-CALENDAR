# -*- coding: utf-8 -*-
"""Build complete, directly linkable setup guides from one shared template."""

import argparse
from collections import Counter
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import struct
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
BASE = "https://namer-kimhyojin.github.io/DARK-CALENDAR/"
LOCALES = {
    "ko": ("ko", "ko_KR", "sync-guide.html"),
    "en": ("en", "en_US", "sync-guide-en.html"),
    "ja": ("ja", "ja_JP", "sync-guide-ja.html"),
    "zh": ("zh-CN", "zh_CN", "sync-guide-zh.html"),
}
TOKEN = re.compile(r"\{\{([A-Za-z0-9_.]+)\}\}")


class Fragment(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.tags = Counter()
        self.urls = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags[tag] += 1
        self.urls.extend((key, value) for key, value in attrs if key in {"href", "src"})


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8", errors="strict"))


def validate(messages, original, language):
    if messages.keys() != original.keys():
        raise ValueError(f"{language}: translation keys differ from Korean source")
    for key, value in messages.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{language}: empty or invalid translation: {key}")
        if Counter(TOKEN.findall(value)) != Counter(TOKEN.findall(original[key])):
            raise ValueError(f"{language}: changed placeholders: {key}")
        if key.startswith("html."):
            before, after = Fragment(original[key]), Fragment(value)
            if before.tags != after.tags or sorted(before.urls) != sorted(after.urls):
                raise ValueError(f"{language}: changed markup or URLs: {key}")
        if language != "ko" and re.search(r"[가-힣]", value):
            raise ValueError(f"{language}: untranslated Korean in {key}")


def expand(template, values):
    for _ in range(4):
        result = TOKEN.sub(lambda match: values[match[1]], template)
        if result == template:
            break
        template = result
    if TOKEN.search(template):
        raise ValueError("Unexpanded template token")
    return template


def localized_home(match, language):
    parts = urlsplit(match[1])
    query = dict(parse_qsl(parts.query))
    query["lang"] = language
    return 'href="' + urlunsplit(("", "", parts.path, urlencode(query), parts.fragment)) + '"'


def size_image(match):
    source = re.search(r'\bsrc="([^"]+)"', match[0])
    if not source:
        return match[0]
    path = DOCS / source[1]
    if not path.is_file():
        raise ValueError(f"Missing image: {path}")
    if path.suffix != ".png" or not source[1].startswith("assets/sync-guide/"):
        return match[0]
    with path.open("rb") as stream:
        header = stream.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Invalid PNG: {path}")
    width, height = struct.unpack("!II", header[16:24])
    result = re.sub(r'\bwidth="\d+"', f'width="{width}"', match[0])
    return re.sub(r'\bheight="\d+"', f'height="{height}"', result)


def build(language, original, template):
    messages = read_json(SOURCE / "locales" / f"{language}.json")
    validate(messages, original, language)
    html_lang, og_locale, filename = LOCALES[language]
    values = {
        key: escape(value, quote=True) if key.startswith("attr.") else value
        for key, value in messages.items()
    }
    values.update(
        pageLang=html_lang,
        pageUrl=BASE + filename,
        ogLocale=og_locale,
        heroPath="assets/sync-guide/"
        + ("" if language == "ko" else language + "/")
        + "sync-workflow.webp",
        alternates="\n  ".join(
            f'<link rel="alternate" hreflang="{code}" href="{BASE}{name}">'
            for code, _, name in LOCALES.values()
        )
        + f'\n  <link rel="alternate" hreflang="x-default" href="{BASE}sync-guide.html">',
    )
    page = expand(template, values)
    page = page.replace(
        '<html lang="' + html_lang + '">',
        '<html lang="' + html_lang + '" data-guide-locale="' + language + '">',
    )
    page = page.replace(
        'data-guide-language="' + language + '"',
        'data-guide-language="' + language + '" aria-current="page"',
    )
    if language != "ko":
        page = re.sub(
            r"assets/sync-guide/([^/\"\s]+\.png)", rf"assets/sync-guide/{language}/\1", page
        )
    page = re.sub(
        r'href="(index\.html(?:[?#][^"]*)?)"', lambda match: localized_home(match, language), page
    )
    page = re.sub(r"<img\b[^>]*>", size_image, page)
    return DOCS / filename, page


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if generated pages are stale")
    parser.add_argument("--locale", choices=LOCALES, action="append")
    args = parser.parse_args()
    original = read_json(SOURCE / "locales/ko.json")
    template = (SOURCE / "template.html").read_text(encoding="utf-8", errors="strict")
    for language in args.locale or LOCALES:
        path, page = build(language, original, template)
        if args.check:
            if path.read_text(encoding="utf-8", errors="strict") != page:
                raise ValueError(f"Generated page is stale: {path}")
        else:
            path.write_text(page, encoding="utf-8", errors="strict")
        print(f"{language}: {len(original)} messages, {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
