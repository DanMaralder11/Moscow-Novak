import ast
import math
import sqlite3
import sys

import numpy as np
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import (
    QColor, QDoubleValidator, QTextCharFormat, QBrush,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QListWidget, QListWidgetItem, QGroupBox,
    QMessageBox, QSplitter, QCalendarWidget, QCheckBox, QDialog, QTabWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

dpath = "grafer.db"

funcs = {
    "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan,
    "sqrt": np.sqrt, "abs": np.abs, "exp": np.exp,
    "log": np.log, "log10": np.log10, "ln": np.log,
}
const = {"pi": math.pi, "e": math.e}

# ----------ошибки------------
class FormulaError(ValueError):
    pass


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
            check(n.left); check(n.right); return
        
        if isinstance(n, ast.UnaryOp):
            if not isinstance(n.op, (ast.UAdd, ast.USub)):
                raise FormulaError("Недопустимая операция")
            check(n.operand); return
        
        if isinstance(n, ast.Call):
            if not isinstance(n.funcs, ast.Name) or n.funcs.id not in funcs:
                raise FormulaError("Неизвестная функция")
            for a in n.args:
                check(a)
            return
        
        if isinstance(n, ast.Name):
            if n.id != "x" and n.id not in const:
                raise FormulaError(f"Неизвестная переменная: {n.id}")
            return
        if isinstance(n, ast.Constant):
            if not isinstance(n.value, (int, float)):
                raise FormulaError("Недопустимая константа")
            return
        raise FormulaError("Недопустимое выражение")

    check(tree)
    return compile(tree, "<formula>", "eval")
# --------------------------------------------

def eval_formula(code, xs):
    env = {"x": xs, **funcs, **const}
    with np.errstate(all="ignore"):
        try:
            y = eval(code, {"__builtins__": {}}, env)
        except Exception as e:
            raise FormulaError(str(e))
    y = np.asarray(y, dtype=float)
    if y.shape != xs.shape:
        y = np.broadcast_to(y, xs.shape).astype(float)
    y[~np.isfinite(y)] = np.nan
    return y

# ------------------хранение----------------
class DB:
    def __init__(self, path=dpath):
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS formula_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expression TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS favorite_formulas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expression TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        self.conn.commit()

    def add_history(self, expr: str):
        self.conn.execute(
            "INSERT INTO formula_history(expression) VALUES (?)", (expr,))
        self.conn.commit()

    def history(self, limit=100):
        return self.conn.execute(
            "SELECT id, expression, created_at FROM formula_history "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def delete_history(self, hid: int):
        self.conn.execute("DELETE FROM formula_history WHERE id=?", (hid,))
        self.conn.commit()

    def history_dates(self):
        rows = self.conn.execute(
            "SELECT DISTINCT DATE(created_at) FROM formula_history ORDER BY 1 DESC"
        ).fetchall()
        return [r[0] for r in rows if r[0]]

    def history_by_date(self, date_str: str):
        return self.conn.execute(
            "SELECT id, expression, created_at FROM formula_history "
            "WHERE DATE(created_at)=? ORDER BY id DESC", (date_str,)).fetchall()

    def add_favorite(self, expr: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO favorite_formulas(expression) VALUES (?)", (expr,))
        self.conn.commit()

    def remove_favorite(self, fid: int):
        self.conn.execute("DELETE FROM favorite_formulas WHERE id=?", (fid,))
        self.conn.commit()

    def favorites(self):
        return self.conn.execute(
            "SELECT id, expression FROM favorite_formulas ORDER BY id DESC").fetchall()

# ------------календарь----------------
class CalendarDialog(QDialog):
    def __init__(self, db: DB, parent=None):
        super().__init__(parent)
        self.db = db
        self.selected_expression = None
        self.setWindowTitle("Календарь построений")
        self.resize(600, 500)

        layout = QHBoxLayout(self)

        left = QVBoxLayout()
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.clicked.connect(self._on_date)
        left.addWidget(self.calendar)

        fmt = QTextCharFormat()
        fmt.setBackground(QBrush(QColor("#cfe8ff")))
        for d in db.history_dates():
            qd = QDate.fromString(d, "yyyy-MM-dd")
            if qd.isValid():
                self.calendar.setDateTextFormat(qd, fmt)
        layout.addLayout(left)

        right = QVBoxLayout()
        self.lbl_date = QLabel("Выберите дату")
        right.addWidget(self.lbl_date)

        self.list_records = QListWidget()
        self.list_records.itemDoubleClicked.connect(self._on_pick)
        right.addWidget(self.list_records)

        btn_row = QHBoxLayout()
        self.btn_repeat = QPushButton("Повторить построение")
        self.btn_repeat.clicked.connect(self._on_pick)
        self.btn_repeat.setEnabled(False)
        btn_row.addWidget(self.btn_repeat)
        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        right.addLayout(btn_row)
        layout.addLayout(right)

        self._on_date(QDate.currentDate())

    def _on_date(self, qdate: QDate):
        date_str = qdate.toString("yyyy-MM-dd")
        self.lbl_date.setText(f"Записи за {date_str}")
        self.list_records.clear()
        rows = self.db.history_by_date(date_str)
        if not rows:
            self.list_records.addItem("За выбранную дату построений нет")
            self.btn_repeat.setEnabled(False)
            return
        for _hid, expr, ts in rows:
            item = QListWidgetItem(f"{expr}    [{ts}]")
            item.setData(Qt.ItemDataRole.UserRole, expr)
            self.list_records.addItem(item)
        self.btn_repeat.setEnabled(True)

    def _on_pick(self, _item=None):
        item = self.list_records.currentItem()
        if not item:
            return
        expr = item.data(Qt.ItemDataRole.UserRole)
        if expr:
            self.selected_expression = expr
            self.accept()

# ---------основной вид------------------
class MainWindow(QMainWindow):
    PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e",
               "#9467bd", "#8c564b", "#e377c2", "#17becf", "#000000"]

    def __init__(self):
        super().__init__()
        # self.setWindowTitle("Графопостроитель — 7–9 классы")
        self.resize(1200, 760)
        self.db = DB()
        self.active_curves = []
        self.private_mode = False

        self._build_ui()
        self._refresh_history()
        self._refresh_favorites()
        self._validate()

    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        left = QWidget()
        left.setMaximumWidth(360)
        lv = QVBoxLayout(left)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_build(), "Построение")
        self.tabs.addTab(self._tab_history(), "История")
        self.tabs.addTab(self._tab_favorites(), "Избранное")
        lv.addWidget(self.tabs)
        splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        self.fig = Figure(figsize=(7, 6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(right)
        rl.addWidget(self.canvas)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 840])

    def _tab_build(self) -> QWidget:
        w = QWidget()
        lv = QVBoxLayout(w)

        gb_f = QGroupBox("Формула")
        fl = QVBoxLayout(gb_f)
        self.edit_formula = QLineEdit()
        self.edit_formula.textChanged.connect(self._validate)
        self.edit_formula.returnPressed.connect(self.on_build)
        fl.addWidget(self.edit_formula)

        self.btn_build = QPushButton("Построить")
        self.btn_build.clicked.connect(self.on_build)
        fl.addWidget(self.btn_build)

        self.chk_private = QCheckBox("🔒 Приватный режим")
        self.chk_private.toggled.connect(self._toggle_private)
        fl.addWidget(self.chk_private)
        self.lbl_private = QLabel("Приватный режим включён — построения не сохраняются")
        self.lbl_private.setStyleSheet("color: #b00; font-weight: bold;")
        self.lbl_private.setVisible(False)
        fl.addWidget(self.lbl_private)
        lv.addWidget(gb_f)

        hint = QLabel(
            "Примеры:<br>"
            "Прямая: 2*x+3<br>"
            "Парабола: x^2<br>"
            "Гипербола: 1/x<br>"
            "Корень: sqrt(x)<br>"
            "Модуль: abs(x)<br>"
            "Синус: sin(x)<br>"
            "Степень: ^<br>"
        )
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555; font-size: 11px;")
        lv.addWidget(hint)

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

        gb_c = QGroupBox("Кривые на графике")
        cl = QVBoxLayout(gb_c)
        self.list_curves = QListWidget()
        cl.addWidget(self.list_curves)
        btn_rm = QPushButton("🗑 Удалить выбранную")
        btn_rm.clicked.connect(self.on_remove_curve)
        cl.addWidget(btn_rm)
        lv.addWidget(gb_c)

        lv.addStretch()
        return w

    def _tab_history(self) -> QWidget:
        w = QWidget()
        lv = QVBoxLayout(w)
        self.list_history = QListWidget()
        self.list_history.itemDoubleClicked.connect(self._on_history_pick)
        lv.addWidget(self.list_history)

        row = QHBoxLayout()
        btn_cal = QPushButton("📅 Календарь")
        btn_cal.clicked.connect(self.on_open_calendar)
        row.addWidget(btn_cal)
        btn_fav = QPushButton("⭐ В избранное")
        btn_fav.clicked.connect(self.on_add_favorite)
        row.addWidget(btn_fav)
        btn_del = QPushButton("🗑 Удалить")
        btn_del.clicked.connect(self.on_delete_history)
        row.addWidget(btn_del)
        lv.addLayout(row)
        return w

    def _tab_favorites(self) -> QWidget:
        w = QWidget()
        lv = QVBoxLayout(w)
        self.list_favorites = QListWidget()
        self.list_favorites.itemDoubleClicked.connect(self._on_favorite_pick)
        lv.addWidget(self.list_favorites)
        row = QHBoxLayout()
        btn_build = QPushButton("Построить выбранную")
        btn_build.clicked.connect(self._on_favorite_pick)
        row.addWidget(btn_build)
        btn_del = QPushButton("🗑 Убрать из избранного")
        btn_del.clicked.connect(self.on_remove_favorite)
        row.addWidget(btn_del)
        lv.addLayout(row)
        return w

    def _num(self, default):
        e = QLineEdit(default)
        v = QDoubleValidator(-1e9, 1e9, 6)
        v.setNotation(QDoubleValidator.Notation.StandardNotation)
        e.setValidator(v)
        e.textChanged.connect(self._validate)
        return e

    def _bounds(self):
        try:
            xmin = float(self.edit_xmin.text())
            xmax = float(self.edit_xmax.text())
            ymin = float(self.edit_ymin.text())
            ymax = float(self.edit_ymax.text())

# ---------ошибки------------
        except ValueError:
            return None
        if xmin >= xmax or ymin >= ymax:
            return None
        return xmin, xmax, ymin, ymax

    def _validate(self):
        has_formula = bool(self.edit_formula.text().strip())
        bounds_ok = self._bounds() is not None
        self.btn_build.setEnabled(has_formula and bounds_ok)

# ------------построение--------------
    def on_build(self):
        raw = self.edit_formula.text().strip()
        try:
            parse_formula(raw)
        except FormulaError:
            QMessageBox.critical(self, "Ошибка ввода", "Ошибка ввода. Проверьте формулу.")
            return
        if self._bounds() is None:
            QMessageBox.warning(
                self, "Некорректный диапазон",
                "Проверьте границы: минимум должен быть меньше максимума, "
                "а поля должны содержать числа.")
            return
        if any(c[0] == raw for c in self.active_curves):
            QMessageBox.information(self, "Дубликат", "Такая кривая уже есть.")
            return

        color = self.PALETTE[len(self.active_curves) % len(self.PALETTE)]
        self.active_curves.append((raw, color))
        self._sync_curves_list()
        self._save_to_history(raw)
        self.edit_formula.clear()
        self.redraw()

    def on_remove_curve(self):
        row = self.list_curves.currentRow()
        if row < 0:
            return
        self.list_curves.takeItem(row)
        self.active_curves.pop(row)
        self.redraw()

    def _sync_curves_list(self):
        self.list_curves.clear()
        for expr, color in self.active_curves:
            item = QListWidgetItem(expr)
            item.setForeground(QColor(color))
            self.list_curves.addItem(item)

    def _save_to_history(self, expr: str):
        if not self.private_mode:
            self.db.add_history(expr)
            self._refresh_history()

    def redraw(self):
        self.ax.clear()
        self.ax.grid(True)
        xmin, xmax, ymin, ymax = self._bounds() or (-10, 10, -10, 10)
        self.ax.set_xlim(xmin, xmax)
        self.ax.set_ylim(ymin, ymax)
        self.ax.axhline(0, color="black", linewidth=0.6)
        self.ax.axvline(0, color="black", linewidth=0.6)

        # подписи осей у концов
        self.ax.text(xmax, 0, " x", ha="left", va="center", fontsize=12)
        self.ax.text(0, ymax, "y ", ha="center", va="bottom", fontsize=12)

        xs = np.linspace(xmin, xmax, 2000)
        for expr, color in self.active_curves:
            try:
                ys = eval_formula(parse_formula(expr), xs)
                self.ax.plot(xs, ys, color=color, linewidth=1.8, label=expr)
            except Exception:
                continue
        title = "График функций" if self.active_curves else "График"
        if self.private_mode:
            title += " (приватный режим)"
        self.ax.set_title(title)
        if self.active_curves:
            self.ax.legend(loc="best", fontsize=8)
        self.canvas.draw_idle()

    def _refresh_history(self):
        self.list_history.clear()
        self._hist_rows = self.db.history()
        for hid, expr, ts in self._hist_rows:
            item = QListWidgetItem(f"{expr}    [{ts}]")
            item.setData(Qt.ItemDataRole.UserRole, (hid, expr))
            self.list_history.addItem(item)

    def _on_history_pick(self, _item):
        item = self.list_history.currentItem()
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        _hid, expr = data
        self.edit_formula.setText(expr)
        self.on_build()

    def on_delete_history(self):
        item = self.list_history.currentItem()
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        hid, _expr = data
        self.db.delete_history(hid)
        self._refresh_history()

    def on_add_favorite(self):
        item = self.list_history.currentItem()
        if not item:
            QMessageBox.information(self, "Избранное", "Выберите формулу в истории.")
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        _hid, expr = data
        self.db.add_favorite(expr)
        self._refresh_favorites()

    def on_open_calendar(self):
        dlg = CalendarDialog(self.db, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_expression:
            self.edit_formula.setText(dlg.selected_expression)
            self.on_build()

    def _refresh_favorites(self):
        self.list_favorites.clear()
        self._fav_rows = self.db.favorites()
        for fid, expr in self._fav_rows:
            item = QListWidgetItem(f"⭐ {expr}")
            item.setData(Qt.ItemDataRole.UserRole, (fid, expr))
            self.list_favorites.addItem(item)

    def _on_favorite_pick(self, _item=None):
        item = self.list_favorites.currentItem()
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        _fid, expr = data
        self.edit_formula.setText(expr)
        self.on_build()

    def on_remove_favorite(self):
        item = self.list_favorites.currentItem()
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        fid, _expr = data
        self.db.remove_favorite(fid)
        self._refresh_favorites()

    def _toggle_private(self, on: bool):
        self.private_mode = bool(on)
        self.lbl_private.setVisible(self.private_mode)
        self.redraw()

# --------------конец-------------
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Графопостроитель")
    w = MainWindow()
    w.show()
    w.redraw()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()