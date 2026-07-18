import re

# Regex for matching common emojis and symbols used in titles
# This covers most of the pictographs, symbols, and dingbats ranges.
_EMOJI_RE = re.compile(
    r"[\U00010000-\U0010ffff]|\u2705|\u274c|\u2b50|\u2700-\u27bf|\u2300-\u23ff|\u2b00-\u2bff|\u2600-\u26ff",
    re.UNICODE,
)


def apply_dialog_title(dialog, title: str):
    """
    Sets the window title after removing any decorative emojis.
    Used for bulk cleaning of window titles where a separate icon is present.
    """
    if hasattr(dialog, "setWindowTitle"):
        # Remove emojis and then strip leading/trailing whitespace
        clean_title = _EMOJI_RE.sub("", title).strip()
        dialog.setWindowTitle(clean_title)
