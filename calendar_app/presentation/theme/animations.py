from PyQt6.QtCore import QEasingCurve, QObject, QPropertyAnimation, QVariantAnimation
from PyQt6.QtGui import QColor


class SmoothHoverAnimation(QObject):
    def __init__(self, target, property_name, duration=200):
        super().__init__(target)
        self.target = target
        self.property_name = property_name
        self.duration = duration
        self.anim = QPropertyAnimation(self.target, self.property_name.encode())
        self.anim.setDuration(self.duration)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)

    def start(self, end_value):
        self.anim.stop()
        self.anim.setEndValue(end_value)
        self.anim.start()


class ColorTransitionAnimation(QVariantAnimation):
    def __init__(self, target, update_fn, duration=300):
        super().__init__(target)
        self.setDuration(duration)
        self.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.valueChanged.connect(update_fn)

    def start_transition(self, start_color, end_color):
        self.stop()
        self.setStartValue(QColor(start_color))
        self.setEndValue(QColor(end_color))
        self.start()


class GeometryAnimation(QPropertyAnimation):
    def __init__(self, target, duration=250):
        super().__init__(target, b"geometry")
        self.setDuration(duration)
        self.setEasingCurve(QEasingCurve.Type.OutBack)  # Slight bounce for premium feel

    def animate_to(self, new_rect):
        self.stop()
        self.setEndValue(new_rect)
        self.start()
