import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QDoubleValidator
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QListWidget, QListWidgetItem,
    QGroupBox, QMessageBox, QSplitter,
)
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Графопостроитель")
        self.resize(1000, 650)
        self.active_curves = []
        self._build_ui()

    # def _build_ui(self):
    #     splitter = QSplitter(Qt.Orientation.Horizontal)
    #     self.setCentralWidget(splitter)

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()