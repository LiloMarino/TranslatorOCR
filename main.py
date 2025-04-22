import sys

import keyboard
import pytesseract
from deep_translator import GoogleTranslator
from PIL import Image, ImageEnhance, ImageFilter, ImageGrab
from PyQt5 import QtCore, QtGui, QtWidgets

# Defina o caminho do Tesseract se necessário
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def preprocess_image(img):
    img = img.convert("L")  # grayscale
    img = img.filter(ImageFilter.SHARPEN)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)  # aumentar contraste
    return img


class SnippingWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowState(QtCore.Qt.WindowFullScreen)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CrossCursor))

        self.begin = QtCore.QPoint()
        self.end = QtCore.QPoint()

    def paintEvent(self, event):
        brush_color = QtGui.QColor(0, 0, 0, 100)
        selection_color = QtGui.QColor(255, 0, 0, 120)
        painter = QtGui.QPainter(self)
        painter.setBrush(brush_color)
        painter.setPen(QtGui.QPen(selection_color, 2))
        painter.drawRect(self.rect())

        if not self.begin.isNull() and not self.end.isNull():
            rect = QtCore.QRect(self.begin, self.end)
            painter.setBrush(QtGui.QColor(0, 0, 0, 0))
            painter.drawRect(rect)

    def mousePressEvent(self, event):
        self.begin = event.pos()
        self.end = self.begin
        self.update()

    def mouseMoveEvent(self, event):
        self.end = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        self.close()
        QtWidgets.QApplication.processEvents()
        x1 = min(self.begin.x(), self.end.x())
        y1 = min(self.begin.y(), self.end.y())
        x2 = max(self.begin.x(), self.end.x())
        y2 = max(self.begin.y(), self.end.y())
        self.capture(x1, y1, x2, y2)

    def capture(self, x1, y1, x2, y2):
        img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        processed = preprocess_image(img)
        text = pytesseract.image_to_string(processed, lang="eng")

        print("\n🔍 Texto capturado: ")
        print(text.strip())

        if text.strip():
            try:
                translated = GoogleTranslator(source="auto", target="pt").translate(
                    text
                )
                print("\n🌐 Tradução:")
                print(translated.strip())
            except Exception as e:
                print("\n[ERRO AO TRADUZIR]:", e)


def start_snip():
    app = QtWidgets.QApplication(sys.argv)
    window = SnippingWidget()
    window.show()
    app.exec_()


def main():
    print("🚀 OCR Snipping Tool iniciado. Pressione F8 para capturar uma área da tela.")
    while True:
        keyboard.wait("F8")
        print("\n[INFO] Selecione a área com o mouse...")
        start_snip()


if __name__ == "__main__":
    main()
