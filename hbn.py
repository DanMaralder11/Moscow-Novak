import ast
import math
import sqlite3
import sys

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QDoubleValidator
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QListWidget, QListWidgetItem,
    QGroupBox, QMessageBox, QSplitter,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

DB_PATH = "grafer.db"
ALLOWED_FUNCS = {
    "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan,
    "sqrt": np.sqrt, "abs": np.abs, "exp": np.exp,
    "log": np.log, "log10": np.log10, "ln": np.log,
}
ALLOWED_CONSTS = {"pi": math.pi, "e": math.e}


class DB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS formulas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expression TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        self.conn.commit()

    def add_formula(self, expr: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO formulas(expression) VALUES (?)", (expr,))
        self.conn.commit()


class FormulaError(ValueError):
    pass


def _is_zero_constant(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value == 0
    return False


def parse_formula(raw: str):
    s = (raw or "").strip()
    if not s:
        raise FormulaError("Пустая формула")
    if "=" in s:
        s = s.split("=", 1)[1].strip()
    s = s.replace("^", "**")
    try:
        tree = ast.parse(s, mode="eval")
    except SyntaxError:
        raise FormulaError("Некорректный синтаксис")

    def check(n):
        if isinstance(n, ast.Expression):
            return check(n.body)
        if isinstance(n, ast.BinOp):
            if not isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div,
                                        ast.Pow, ast.Mod, ast.FloorDiv)):
                raise FormulaError("Недопустимая операция")
            if isinstance(n.op, (ast.Div, ast.Mod, ast.FloorDiv)):
                if _is_zero_constant(n.right):
                    raise FormulaError("Деление на ноль")
            check(n.left); check(n.right); return
        if isinstance(n, ast.UnaryOp):
            if not isinstance(n.op, (ast.UAdd, ast.USub)):
                raise FormulaError("Недопустимая операция")
            check(n.operand); return
        if isinstance(n, ast.Call):
            if not isinstance(n.func, ast.Name) or n.func.id not in ALLOWED_FUNCS:
                raise FormulaError("Неизвестная функция")
            for a in n.args:
                check(a)
            return
        if isinstance(n, ast.Name):
            if n.id != "x" and n.id not in ALLOWED_CONSTS:
                raise FormulaError(f"Неизвестная переменная: {n.id}")
            return
        if isinstance(n, ast.Constant):
            if not isinstance(n.value, (int, float)):
                raise FormulaError("Недопустимая константа")
            return
        raise FormulaError("Недопустимое выражение")

    check(tree)
    return compile(tree, "<formula>", "eval")


def eval_formula(code, xs):
    env = {"x": xs, **ALLOWED_FUNCS, **ALLOWED_CONSTS}
    with np.errstate(divide="raise", invalid="raise", over="raise"):
        try:
            y = eval(code, {"__builtins__": {}}, env)
        except ZeroDivisionError:
            raise FormulaError("Деление на ноль")
        except FloatingPointError:
            raise FormulaError(
                "Недопустимая математическая операция "
                "(деление на ноль или выход из области определения)")
        except Exception as e:
            raise FormulaError(str(e))
    y = np.asarray(y, dtype=float)
    if y.shape != xs.shape:
        y = np.broadcast_to(y, xs.shape).astype(float)
    if not np.all(np.isfinite(y)):
        raise FormulaError(
            "Формула даёт неопределённые значения "
            "(деление на ноль или выход из области определения)")
    return y


class MainWindow(QMainWindow):
    PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e",
               "#9467bd", "#8c564b", "#e377c2", "#17becf", "#000000"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Графопостроитель")
        self.resize(1000, 650)
        self.db = DB()
        self.active_curves = []
        self._build_ui()
        self._validate()

    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # -----лево-----
        left = QWidget()
        left.setMaximumWidth(320)
        lv = QVBoxLayout(left)

        gb_f = QGroupBox("Формула")
        fl = QVBoxLayout(gb_f)
        self.edit_formula = QLineEdit()
        self.edit_formula.textChanged.connect(self._validate)
        self.edit_formula.returnPressed.connect(self.on_add)
        fl.addWidget(self.edit_formula)

        self.btn_add = QPushButton("Построить")
        self.btn_add.clicked.connect(self.on_add)
        fl.addWidget(self.btn_add)

        hint = QLabel(
            "Примеры:<br>"
            "Корень: sqrt(x)<br>"
            "Модуль: abs(x)<br>"
            "Синус: sin(x)<br>"
            "---------------<br>"
            "Степень — ^</b>"
        )
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555; font-size: 11px;")
        fl.addWidget(hint)
        lv.addWidget(gb_f)

        gb_r = QGroupBox("Область определения")
        form = QFormLayout(gb_r)
        self.edit_xmin = self._num("-10")
        self.edit_xmax = self._num("10")
        self.edit_ymin = self._num("-10")
        self.edit_ymax = self._num("10")
        form.addRow("X min", self.edit_xmin)
        form.addRow("X max", self.edit_xmax)
        form.addRow("Y min", self.edit_ymin)
        form.addRow("Y max", self.edit_ymax)
        lv.addWidget(gb_r)

        gb_c = QGroupBox("Кривые")
        cl = QVBoxLayout(gb_c)
        self.list_curves = QListWidget()
        cl.addWidget(self.list_curves)
        btn_rm = QPushButton("Удалить выбранную")
        btn_rm.clicked.connect(self.on_remove)
        cl.addWidget(btn_rm)
        lv.addWidget(gb_c)

        lv.addStretch()
        splitter.addWidget(left)

        # -----право-----
        right = QWidget()
        rl = QVBoxLayout(right)
        self.fig = Figure(figsize=(7, 6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(right)
        rl.addWidget(self.canvas)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 700])

    def _num(self, default):
        e = QLineEdit(default)
        v = QDoubleValidator(-1e9, 1e9, 6)
        v.setNotation(QDoubleValidator.Notation.StandardNotation)
        e.setValidator(v)
        e.textChanged.connect(self._validate)
        return e

    def _bounds(self):
        try:
            xmin, xmax = float(self.edit_xmin.text()), float(self.edit_xmax.text())
            ymin, ymax = float(self.edit_ymin.text()), float(self.edit_ymax.text())
        except ValueError:
            return None
        if xmin >= xmax or ymin >= ymax:
            return None
        return xmin, xmax, ymin, ymax

    def _validate(self):
        ok = bool(self.edit_formula.text().strip()) and self._bounds() is not None
        self.btn_add.setEnabled(ok)

    def on_add(self):
        raw = self.edit_formula.text().strip()
        try:
            code = parse_formula(raw)
            # Пробный прогон, чтобы поймать деление на ноль в точках (x/(x-x))
            xmin, xmax, _, _ = self._bounds()
            xs = np.linspace(xmin, xmax, 2000)
            eval_formula(code, xs)
        except FormulaError as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка ввода:\n{e}")
            return
        if any(c[0] == raw for c in self.active_curves):
            QMessageBox.information(self, "Дубликат", "Такая кривая уже есть.")
            return
        color = self.PALETTE[len(self.active_curves) % len(self.PALETTE)]
        self.active_curves.append((raw, color))
        item = QListWidgetItem(raw)
        item.setForeground(QColor(color))
        self.list_curves.addItem(item)
        self.db.add_formula(raw)
        self.edit_formula.clear()
        self.redraw()

    def on_remove(self):
        row = self.list_curves.currentRow()
        if row < 0:
            return
        self.list_curves.takeItem(row)
        self.active_curves.pop(row)
        self.redraw()

    def redraw(self):
        self.ax.clear()
        self.ax.grid(True)
        xmin, xmax, ymin, ymax = self._bounds() or (-10, 10, -10, 10)
        self.ax.set_xlim(xmin, xmax)
        self.ax.set_ylim(ymin, ymax)
        self.ax.axhline(0, color="black", linewidth=0.6)
        self.ax.axvline(0, color="black", linewidth=0.6)

        xs = np.linspace(xmin, xmax, 2000)
        try:
            for expr, color in self.active_curves:
                ys = eval_formula(parse_formula(expr), xs)
                self.ax.plot(xs, ys, color=color, linewidth=1.8, label=expr)
        except FormulaError as e:
            self.ax.clear()
            self.canvas.draw_idle()
            QMessageBox.critical(
                self, "Ошибка", f"Не удалось построить график:\n{e}")
            return
        if self.active_curves:
            self.ax.legend(loc="best", fontsize=8)
        self.canvas.draw_idle()


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    w.redraw()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()