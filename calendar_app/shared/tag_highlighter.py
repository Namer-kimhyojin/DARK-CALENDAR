from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat

_TAG_RE = QRegularExpression(r"#[^\s#]+")


class HashTagHighlighter(QSyntaxHighlighter):
    """QTextEdit에서 #태그를 파란색으로 하이라이트."""

    def __init__(self, parent=None, color: str = "#4da6ff"):
        super().__init__(parent)

        fmt = QTextCharFormat()

        fmt.setForeground(QColor(color))

        self._fmt = fmt

    def highlightBlock(self, text: str):
        it = _TAG_RE.globalMatch(text)

        while it.hasNext():
            m = it.next()

            self.setFormat(m.capturedStart(), m.capturedLength(), self._fmt)
