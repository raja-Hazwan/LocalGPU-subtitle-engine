"""Draw the app icon (assets/app.ico): white subtitle lines on the app's blue, rounded square.

Usage:  python tools/make_icon.py
"""
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

out = Path(__file__).resolve().parent.parent / "assets" / "app.ico"
app = QGuiApplication([])
size = 256
img = QImage(size, size, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
p.setPen(Qt.NoPen)
p.setBrush(QColor("#1f6feb"))
p.drawRoundedRect(QRectF(8, 8, 240, 240), 48, 48)
p.setBrush(QColor("white"))
p.drawRoundedRect(QRectF(48, 132, 160, 28), 14, 14)   # subtitle line 1
p.drawRoundedRect(QRectF(72, 176, 112, 28), 14, 14)   # subtitle line 2
p.setBrush(QColor("#9dbcf4"))
p.drawEllipse(QRectF(100, 52, 56, 56))                # "speaker" dot
p.end()
out.parent.mkdir(exist_ok=True)
assert img.save(str(out), "ICO"), "Qt could not write .ico"
print("Icon written to", out)
