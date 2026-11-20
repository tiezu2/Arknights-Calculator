# -*- coding: utf-8 -*-
"""明日方舟 · 干员培养终端 —— 原生桌面版（PySide6，无浏览器、无网络服务）

复用 calc.py（移植自 cn.ark-nights.com 的算法）与 arknights.db。
启动: python app_desktop.py
"""
import os
import sys

from PySide6.QtCore import Qt, QRectF, QSize, Signal
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPolygonF, QPixmap)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
                               QCheckBox, QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QTabWidget, QTableWidget,
                               QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calc import Calc, ATTR_CN  # noqa: E402
from import_dialog import ImportDialog  # noqa: E402

PROF_CHAR = {"CASTER": "术", "SNIPER": "狙", "WARRIOR": "近", "TANK": "重",
             "MEDIC": "医", "SUPPORT": "辅", "SPECIALIST": "特", "SPECIAL": "特", "PIONEER": "先"}
_ICONS = {}
_PROFB = {}
ICON_DIR = None          # 在 BASE/RES 确定后再赋值


def mat_pix(mid, size=30):
    """材料图标（缓存 + 缩放）"""
    key = (str(mid), size)
    if key in _ICONS:
        return _ICONS[key]
    pm = QPixmap()
    if ICON_DIR:
        p = os.path.join(ICON_DIR, str(mid) + ".png")
        if os.path.exists(p):
            pm = QPixmap(p)
            if not pm.isNull():
                pm = pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    _ICONS[key] = pm
    return pm


OP_DIR = None
_OPICONS = {}


def op_pix(uid, size=28):
    """干员头像（PRTS 抓的），没有则返回 None"""
    key = (str(uid), size)
    if key in _OPICONS:
        return _OPICONS[key]
    pm = QPixmap()
    if OP_DIR:
        p = os.path.join(OP_DIR, str(uid) + ".png")
        if os.path.exists(p):
            pm = QPixmap(p)
            if not pm.isNull():
                pm = pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    _OPICONS[key] = pm
    return pm


def prof_badge(prof, rarity, size=22):
    """职业徽章：菱形描边 + 职业汉字，颜色取星级色"""
    key = (prof, rarity, size)
    if key in _PROFB:
        return _PROFB[key]
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    col = QColor(RARITY.get(rarity, "#5b6b78"))
    c = size * 0.24
    path = QPainterPath()
    path.moveTo(c, 0)
    path.lineTo(size - c, 0)
    path.lineTo(size, size * 0.5)
    path.lineTo(size - c, size)
    path.lineTo(c, size)
    path.lineTo(0, size * 0.5)
    path.closeSubpath()
    p.fillPath(path, QColor(8, 14, 19, 235))
    p.setPen(QPen(col, 1.5))
    p.drawPath(path)
    f = QFont("Microsoft YaHei UI", int(size * 0.44))
    f.setBold(True)
    p.setFont(f)
    p.setPen(col)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, PROF_CHAR.get(prof, "?"))
    p.end()
    _PROFB[key] = pm
    return pm

if getattr(sys, "frozen", False):
    # 打包成 exe：数据库放在 exe 同目录（可写、可持久），首启用内置副本初始化
    BASE = os.path.dirname(sys.executable)
    RES = getattr(sys, "_MEIPASS", BASE)
    DB = os.path.join(BASE, "arknights.db")
    if not os.path.exists(DB):
        import shutil
        src = os.path.join(RES, "arknights.db")
        if os.path.exists(src):
            shutil.copyfile(src, DB)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
    RES = BASE
    DB = os.path.join(BASE, "arknights.db")

ICON_DIR = os.path.join(RES, "icons", "materials")
OP_DIR = os.path.join(RES, "icons", "operators")

# ---------------- 主题 ----------------
BG = "#070a0d"
PANEL = "#0d151b"
PANEL2 = "#101a22"
LINE = "#223140"
LINE2 = "#2f4356"
CYAN = "#0cc3e7"
GOLD = "#f2c14e"
RED = "#e5484d"
TEXT = "#d7e3ec"
MUTED = "#7c8f9e"
TIER = {"T1": "#8a939c", "T2": "#7fb069", "T3": "#4aa8e0", "T4": "#b07fe0",
        "T5": "#f2c14e", "T6": "#f0863f", None: "#5b6b78"}
RARITY = {1: "#8a939c", 2: "#7fb069", 3: "#4aa8e0", 4: "#b07fe0", 5: "#f2c14e", 6: "#f0863f"}
PROF_CN = {"CASTER": "术师", "SNIPER": "狙击", "WARRIOR": "近卫", "TANK": "重装",
           "MEDIC": "医疗", "SUPPORT": "辅助", "SPECIALIST": "特种", "PIONEER": "先锋",
           "SPECIAL": "特种"}
PROF_ORDER = [("PIONEER", "先锋"), ("WARRIOR", "近卫"), ("TANK", "重装"), ("SNIPER", "狙击"),
              ("CASTER", "术师"), ("MEDIC", "医疗"), ("SUPPORT", "辅助"), ("SPECIAL", "特种")]
PROF_SHORT = {"": "全", "PIONEER": "先", "WARRIOR": "近", "TANK": "重", "SNIPER": "狙",
              "CASTER": "术", "MEDIC": "医", "SUPPORT": "辅", "SPECIAL": "特"}

QSS = f"""
QWidget {{ background: transparent; color: {TEXT};
  font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"; font-size: 13px; }}
QMainWindow, #root {{ background: {BG}; }}
QLabel#head {{ color: #cfe6f2; font-weight: 700; letter-spacing: 2px; font-size: 12.5px; }}
QLabel#brand {{ color: #eaf6fb; font-weight: 700; letter-spacing: 6px; font-size: 17px; }}
QLabel#brandSub {{ color: #0a8ba3; font-size: 10.5px; letter-spacing: 3px; }}
QLabel#muted {{ color: {MUTED}; font-size: 11.5px; }}
QLabel#picked {{ background: #0a1218; border-left: 3px solid {CYAN}; padding: 8px 10px;
  color: #cfe6f2; font-weight: 600; }}
QLabel#pickedEmpty {{ background: #0a1218; border-left: 3px solid {LINE2}; padding: 8px 10px;
  color: {MUTED}; }}
QLineEdit, QSpinBox, QComboBox {{
  background: #0a1218; border: 1px solid {LINE2}; padding: 6px 8px; color: {TEXT};
  selection-background-color: {CYAN}; selection-color: #04131a; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {CYAN}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{ background: #0b1218; border: 1px solid {LINE2};
  selection-background-color: #12303c; color: {TEXT}; outline: none; }}
QPushButton {{ background: #0d151c; border: 1px solid {LINE2}; padding: 8px 14px;
  color: {TEXT}; font-weight: 600; letter-spacing: 1px; }}
QPushButton:hover {{ border-color: {CYAN}; background: #102029; }}
QPushButton:disabled {{ color: #4b5a66; border-color: {LINE}; }}
QPushButton:checked {{ background: {CYAN}; border: 1px solid {CYAN}; color: #04131a; }}
QPushButton#primary {{ background: {CYAN}; border: 1px solid {CYAN}; color: #04131a; }}
QPushButton#primary:hover {{ background: #23d6f5; border-color: #23d6f5; }}
QPushButton#primary:disabled {{ background: #0c3b46; border-color: #0c3b46; color: #4d7a86; }}
QPushButton#danger {{ color: #f2a2a4; border-color: #5a2a2c; }}
QPushButton#danger:hover {{ background: rgba(229,72,77,0.14); border-color: {RED}; color: #ffd7d8; }}
QPushButton#ghost {{ background: transparent; }}
QListWidget {{ background: #0a1116; border: 1px solid {LINE}; outline: none; }}
QListWidget::item {{ padding: 6px 8px; border-bottom: 1px solid #101b24; }}
QListWidget::item:hover {{ background: #0d1a22; }}
QListWidget::item:selected {{ background: #0e2130; border-left: 3px solid {CYAN}; color: #eaf6fb; }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: #080d11; width: 9px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #1d2f3d; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #2b4657; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QTableWidget {{ background: #0a1116; border: 1px solid {LINE}; gridline-color: #16232e;
  outline: none; }}
QHeaderView::section {{ background: #0e1922; color: #9fb4c3; border: none;
  border-bottom: 1px solid {LINE2}; padding: 6px; font-weight: 600; letter-spacing: 1px; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 8px 18px; margin-right: 2px;
  border: 1px solid transparent; letter-spacing: 1px; }}
QTabBar::tab:selected {{ color: #04131a; background: {CYAN}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
"""


# ---------------- 自绘小部件 ----------------
class HexLogo(QWidget):
    def __init__(self, size=38, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        cx, cy, r = w / 2, w / 2, w * 0.46
        poly = QPolygonF()
        import math
        for i in range(6):
            a = math.radians(60 * i - 30)
            poly.append(QPointF_(cx + r * math.cos(a), cy + r * math.sin(a)))
        p.setPen(QPen(QColor(CYAN), 1.6))
        p.drawPolygon(poly)
        inner = QPolygonF()
        for i in range(6):
            a = math.radians(60 * i - 30)
            inner.append(QPointF_(cx + r * 0.66 * math.cos(a), cy + r * 0.66 * math.sin(a)))
        p.setBrush(QColor(12, 195, 231, 32))
        p.setPen(QPen(QColor(GOLD), 1))
        p.drawPolygon(inner)
        p.setPen(QPen(QColor(CYAN), 2))
        p.drawPolyline(QPolygonF([QPointF_(cx - 6, cy + 7), QPointF_(cx, cy - 8), QPointF_(cx + 6, cy + 7)]))
        p.end()


def QPointF_(x, y):
    from PySide6.QtCore import QPointF
    return QPointF(x, y)


class Panel(QFrame):
    """切角面板：自绘背景 + 左上青色高亮条"""
    def __init__(self, parent=None, cut=14, accent=True):
        super().__init__(parent)
        self.cut = cut
        self.accent = accent
        self.setAttribute(Qt.WA_StyledBackground, False)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h, c = self.width(), self.height(), self.cut
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(w, 0)
        path.lineTo(w, h - c)
        path.lineTo(w - c, h)
        path.lineTo(0, h)
        path.closeSubpath()
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor(18, 27, 34, 246))
        g.setColorAt(1, QColor(10, 15, 20, 246))
        p.fillPath(path, g)
        p.setPen(QPen(QColor(LINE), 1))
        p.drawPath(path)
        if self.accent:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(CYAN))
            p.drawRect(QRectF(0, 0, 3, 46))
        p.end()


class Card(QFrame):
    """材料合计卡片"""
    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.item = item
        self.setFixedHeight(64)
        self.setMinimumWidth(168)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        tier = TIER.get(self.item.get("tier"))
        path = QPainterPath()
        c = 8
        path.moveTo(0, 0)
        path.lineTo(w, 0)
        path.lineTo(w, h - c)
        path.lineTo(w - c, h)
        path.lineTo(0, h)
        path.closeSubpath()
        p.fillPath(path, QColor(11, 19, 25))
        p.setPen(QPen(QColor(LINE), 1))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(tier))
        p.drawRect(QRectF(0, 0, 3, h))

        pm = mat_pix(self.item.get("id"), 30)
        if not pm.isNull():
            p.drawPixmap(9, int((h - 30) / 2), pm)

        p.setPen(QColor(TEXT))
        f = QFont("Microsoft YaHei UI", 9)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(46, 6, w - 56, 20), Qt.AlignLeft | Qt.AlignVCenter, self.item["name"])

        mono = QFont("Consolas", 9)
        p.setFont(mono)
        it = self.item
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(46, 26, w - 56, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   f"需 {it['need']}   存 {it['stock']}")
        miss = it["miss"]
        p.setPen(QColor("#7fb069") if miss == 0 else QColor("#f2a2a4"))
        txt = "已够" if miss == 0 else f"缺 {miss}"
        p.drawText(QRectF(46, 42, w - 56, 16), Qt.AlignLeft | Qt.AlignVCenter, txt)
        if it.get("craftable"):
            p.setPen(QColor(GOLD))
            p.drawText(QRectF(46, 42, w - 56, 16), Qt.AlignRight | Qt.AlignVCenter,
                       f"可合成 {it['craftable']}")
        p.end()


class PlanRow(QFrame):
    remove = Signal(int)

    def __init__(self, row, parent=None):
        super().__init__(parent)
        self.row = row
        self.setMinimumHeight(58)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        path = QPainterPath()
        c = 8
        path.moveTo(0, 0)
        path.lineTo(w, 0)
        path.lineTo(w, h - c)
        path.lineTo(w - c, h)
        path.lineTo(0, h)
        path.closeSubpath()
        p.fillPath(path, QColor(11, 19, 25))
        p.setPen(QPen(QColor("#1b2836"), 1))
        p.drawPath(path)

        av = op_pix(self.row.get("uid"), 26)
        if not av.isNull():
            p.drawPixmap(11, 7, av)
        else:
            p.drawPixmap(12, 8, prof_badge(self.row.get("profession"), self.row.get("rarity") or 1, 24))

        f = QFont("Microsoft YaHei UI", 10)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(TEXT))
        p.drawText(QRectF(44, 8, 140, 20), Qt.AlignLeft | Qt.AlignVCenter, self.row["operator_name"])
        p.setFont(QFont("Microsoft YaHei UI", 8))
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(44, 30, 140, 18), Qt.AlignLeft | Qt.AlignVCenter, self.row["attr_name"])

        # 材料 chip
        x = 184
        p.setFont(QFont("Microsoft YaHei UI", 8))
        for m in self.row["reqs"][:9]:
            tier = TIER.get(m.get("tier"))
            txt = f"{m['name']} ×{m['qty']}"
            fm = p.fontMetrics()
            cw = fm.horizontalAdvance(txt) + 16
            icon = mat_pix(m.get("id"), 16)
            if not icon.isNull():
                cw += 20
            if x + cw > w - 120:
                break
            r = QRectF(x, 18, cw, 22)
            p.setPen(QPen(QColor(tier if tier else "#1d2c3a"), 1))
            p.setBrush(QColor(10, 20, 26))
            p.drawRect(r)
            tx = r
            if not icon.isNull():
                p.drawPixmap(int(x + 4), int(18 + 3), icon)
                tx = QRectF(x + 22, 18, cw - 22, 22)
            p.setPen(QColor(tier if tier else "#b8cbd8"))
            p.drawText(tx, Qt.AlignCenter, txt)
            x += cw + 6

        p.setFont(QFont("Consolas", 9))
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(w - 105, 18, 70, 22), Qt.AlignRight | Qt.AlignVCenter,
                   f"{self.row['cur']} → {self.row['target']}")
        p.setFont(QFont("Consolas", 12))
        p.setPen(QColor("#6a7d8b"))
        p.drawText(QRectF(w - 26, 0, 26, h), Qt.AlignCenter, "\u00d7")
        p.end()

    def mousePressEvent(self, e):
        if e.position().x() > self.width() - 30:
            self.remove.emit(self.row["id"])


# ---------------- 主窗口 ----------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.calc = Calc(DB)
        self.setWindowTitle("RHODES ISLAND · 干员培养终端")
        self.resize(1500, 900)
        self.setMinimumSize(1180, 720)
        self.setStyleSheet(QSS)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(14, 12, 14, 14)
        body.setSpacing(12)
        self.stack = QStackedWidget()
        self.page_plan = self._build_plan_page()
        self.page_inv = self._build_inventory_page()
        self.stack.addWidget(self.page_plan)
        self.stack.addWidget(self.page_inv)
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)

        self._style_tabs(0)
        self.refresh_all()
        self.do_search("")

    # ---------- 顶栏 ----------
    def _build_header(self):
        h = QWidget()
        h.setFixedHeight(62)
        h.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #0e151b, stop:1 #0a0f14);"
                        f"border-bottom: 1px solid {LINE};")
        lay = QHBoxLayout(h)
        lay.setContentsMargins(20, 8, 20, 8)
        lay.setSpacing(12)

        lay.addWidget(HexLogo(38))
        box = QVBoxLayout()
        box.setSpacing(1)
        b1 = QLabel("RHODES ISLAND"); b1.setObjectName("brand")
        b2 = QLabel("干员培养终端 · TRAINING TERMINAL"); b2.setObjectName("brandSub")
        box.addWidget(b1); box.addWidget(b2)
        lay.addLayout(box)
        lay.addSpacing(24)

        self.btn_tab_plan = QPushButton("培养计划"); self.btn_tab_plan.setCheckable(True); self.btn_tab_plan.setChecked(True)
        self.btn_tab_inv = QPushButton("库存"); self.btn_tab_inv.setCheckable(True)
        self.btn_tab_plan.clicked.connect(lambda: self.switch_tab(0))
        self.btn_tab_inv.clicked.connect(lambda: self.switch_tab(1))
        lay.addWidget(self.btn_tab_plan)
        lay.addWidget(self.btn_tab_inv)
        self.btn_import = QPushButton("导入")
        self.btn_import.clicked.connect(self.open_import)
        self.btn_import.setToolTip("导入 MAA 导出的库存 / 干员列表（JSON·CSV·TXT 或粘贴）")
        lay.addWidget(self.btn_import)

        lay.addStretch(1)
        self.lbl_status = QLabel("数据已载入"); self.lbl_status.setObjectName("muted")
        lay.addWidget(self.lbl_status)
        dot = QLabel("◆"); dot.setStyleSheet(f"color:{CYAN}; font-size: 12px;")
        lay.addWidget(dot)
        return h

    def _style_tabs(self, i):
        on = ("background:%s; border:1px solid %s; color:#04131a; font-weight:700;"
              " letter-spacing:1px; padding:8px 20px;" % (CYAN, CYAN))
        off = ("background:transparent; border:1px solid %s; color:%s;"
               " letter-spacing:1px; padding:8px 20px;" % (LINE, MUTED))
        self.btn_tab_plan.setStyleSheet(on if i == 0 else off)
        self.btn_tab_inv.setStyleSheet(on if i == 1 else off)

    def switch_tab(self, i):
        self.stack.setCurrentIndex(i)
        self._style_tabs(i)
        if i == 1:
            self.refresh_inventory()
        else:
            # 回到培养页：恢复完整干员列表（清掉「我的」筛选）
            if getattr(self, "only_owned", False):
                self.only_owned = False
                self.btn_owned.setChecked(False)
                self._chip_style(self.btn_owned, False)
            self.do_search(self.search.text())

    # ---------- 培养页 ----------
    def _build_plan_page(self):
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        # 左
        left = Panel()
        left.setFixedWidth(348)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 12)
        lv.setSpacing(0)
        lv.addWidget(self._head("干员检索"))

        self.search = QLineEdit()
        self.search.setPlaceholderText("输入干员名 / 拼音（如 阿米娅 / amiya）")
        self.search.textChanged.connect(lambda t: self.do_search(t))
        sw = QWidget(); sl = QVBoxLayout(sw); sl.setContentsMargins(12, 10, 12, 8); sl.addWidget(self.search)
        lv.addWidget(sw)

        # 职业筛选
        fw = QWidget(); fl = QVBoxLayout(fw); fl.setContentsMargins(10, 0, 10, 4); fl.setSpacing(4)
        row1 = QHBoxLayout(); row1.setSpacing(3)
        self.prof_btns = {}
        for code, cn in [("", "全部")] + list(PROF_ORDER):
            b = QPushButton(PROF_SHORT.get(code, cn))
            b.setCheckable(True); b.setChecked(code == "")
            b.setFixedSize(QSize(30, 24)); b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(cn)
            b.clicked.connect(lambda _=False, c=code: self.set_prof_filter(c))
            row1.addWidget(b)
            self.prof_btns[code] = b
        self.btn_owned = QPushButton("我的")
        self.btn_owned.setCheckable(True)
        self.btn_owned.setFixedSize(QSize(38, 24))
        self.btn_owned.setCursor(Qt.PointingHandCursor)
        self.btn_owned.setToolTip("只显示「我的干员」")
        self.btn_owned.clicked.connect(self.toggle_owned_filter)
        row1.addWidget(self.btn_owned)
        row1.addStretch(1)
        fl.addLayout(row1)

        # 星级筛选
        row2 = QHBoxLayout(); row2.setSpacing(3)
        self.rar_btns = {}
        for r in [0, 6, 5, 4, 3, 2, 1]:
            b = QPushButton("全" if r == 0 else str(r))
            b.setCheckable(True); b.setChecked(r == 0); b.setFixedSize(QSize(30, 24))
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip("全部星级" if r == 0 else f"{r} 星")
            b.clicked.connect(lambda _=False, rr=r: self.set_rarity_filter(rr))
            row2.addWidget(b)
            self.rar_btns[r] = b
        row2.addStretch(1)
        fl.addLayout(row2)

        for k, b in self.prof_btns.items():
            self._chip_style(b, k == "")
        self._chip_style(self.btn_owned, False)
        for k, b in self.rar_btns.items():
            self._chip_style(b, k == 0)

        self.lbl_count = QLabel("统计中…"); self.lbl_count.setObjectName("muted")
        self.lbl_count.setWordWrap(True)
        fl.addWidget(self.lbl_count)
        lv.addWidget(fw)

        self.oplist = QTreeWidget()
        self.oplist.setHeaderHidden(True)
        self.oplist.setRootIsDecorated(False)
        self.oplist.setIndentation(10)
        self.oplist.setUniformRowHeights(True)
        self.oplist.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.oplist.itemClicked.connect(self.on_pick)
        self.oplist.setStyleSheet(
            "QTreeWidget{background:#0a1116;border:1px solid #223140;outline:none;}"
            "QTreeWidget::item{padding:4px 6px;border-bottom:1px solid #101b24;}"
            "QTreeWidget::item:hover{background:#0d1a22;}"
            "QTreeWidget::item:selected{background:#0e2130;color:#eaf6fb;}")
        lw = QWidget(); ll = QVBoxLayout(lw); ll.setContentsMargins(10, 0, 10, 8); ll.addWidget(self.oplist)
        lv.addWidget(lw, 1)

        lv.addWidget(self._head("培养目标"))
        tw = QWidget(); tl = QVBoxLayout(tw); tl.setContentsMargins(12, 10, 12, 12); tl.setSpacing(8)
        self.lbl_picked = QLabel("未选择干员"); self.lbl_picked.setObjectName("pickedEmpty")
        tl.addWidget(self.lbl_picked)

        tl.addWidget(self._small("目标项（可勾选多项，各自填 现 → 目标）"))

        self.tgt_tabs = QTabWidget()
        self.tgt_tabs.setMinimumHeight(226)
        self.tgt_tabs.setMaximumHeight(252)
        self.tgt_tabs.setStyleSheet(
            "QTabWidget::pane{border:1px solid #1b2836;background:transparent;top:-1px;}"
            "QTabBar::tab{background:#0a1218;color:#7c8f9e;padding:5px 14px;margin-right:2px;"
            "border:1px solid #1b2836;border-bottom:none;font-size:11px;letter-spacing:1px;}"
            "QTabBar::tab:selected{background:rgba(12,195,231,0.14);color:#cfe6f2;"
            "border-color:#0cc3e7;border-bottom:none;}"
            "QTabBar::tab:hover{color:#d7e3ec;}")
        tl.addWidget(self.tgt_tabs)

        row = QHBoxLayout(); row.setSpacing(6)
        b_all = QPushButton("全选"); b_all.setObjectName("ghost")
        b_all.clicked.connect(lambda: self.check_all(True))
        b_none = QPushButton("全不选"); b_none.setObjectName("ghost")
        b_none.clicked.connect(lambda: self.check_all(False))
        self.btn_add = QPushButton("加入计算表"); self.btn_add.setObjectName("primary")
        self.btn_add.setEnabled(False); self.btn_add.clicked.connect(self.add_plans)
        row.addWidget(b_all); row.addWidget(b_none); row.addWidget(self.btn_add, 1)
        tl.addLayout(row)

        self.lbl_hint = QLabel("选择干员后可勾选目标项"); self.lbl_hint.setObjectName("muted")
        self.lbl_hint.setWordWrap(True)
        tl.addWidget(self.lbl_hint)
        lv.addWidget(tw)
        lay.addWidget(left)

        # 右
        right = Panel()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 10)
        rv.setSpacing(0)

        head = QWidget(); hl = QHBoxLayout(head); hl.setContentsMargins(0, 0, 12, 0)
        hl.addWidget(self._head("培养表"), 1)
        b_ref = QPushButton("刷新"); b_ref.setObjectName("ghost"); b_ref.clicked.connect(self.refresh_all)
        b_clr = QPushButton("清空"); b_clr.setObjectName("danger"); b_clr.clicked.connect(self.clear_plans)
        hl.addWidget(b_ref); hl.addWidget(b_clr)
        rv.addWidget(head)

        self.plan_tabs = QTabWidget()
        self.plan_tabs.setStyleSheet(
            "QTabWidget::pane{border:1px solid #1b2836;background:transparent;top:-1px;}"
            "QTabBar::tab{background:#0a1218;color:#7c8f9e;padding:5px 12px;margin-right:2px;"
            "border:1px solid #1b2836;border-bottom:none;font-size:11px;}"
            "QTabBar::tab:selected{background:rgba(12,195,231,0.14);color:#cfe6f2;"
            "border-color:#0cc3e7;border-bottom:none;}"
            "QTabBar::tab:hover{color:#d7e3ec;}")
        self.plan_tabs.currentChanged.connect(lambda _i: self._render_totals())
        self._tab_rows = {}
        rv.addWidget(self.plan_tabs, 1)

        rv.addWidget(self._head("材料合计 / 缺少"))
        self.tot_area = QScrollArea(); self.tot_area.setWidgetResizable(True)
        self.tot_host = QWidget(); self.tot_layout = QGridLayout(self.tot_host)
        self.tot_layout.setContentsMargins(12, 10, 12, 10); self.tot_layout.setSpacing(7)
        self.tot_area.setWidget(self.tot_host)
        rv.addWidget(self.tot_area, 1)
        lay.addWidget(right, 1)
        return page

    # ---------- 库存页 ----------
    def _build_inventory_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        panel = Panel()
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(0, 0, 0, 12)
        pv.setSpacing(0)
        pv.addWidget(self._head("库存"))

        top = QWidget(); tl = QHBoxLayout(top); tl.setContentsMargins(12, 10, 12, 8)
        self.inv_search = QLineEdit(); self.inv_search.setPlaceholderText("筛选材料…")
        self.inv_search.textChanged.connect(self.refresh_inventory)
        tl.addWidget(self.inv_search, 1)
        b_save = QPushButton("保存库存"); b_save.setObjectName("primary"); b_save.clicked.connect(self.save_inventory)
        b_clear = QPushButton("清空库存"); b_clear.setObjectName("danger"); b_clear.clicked.connect(self.clear_inventory)
        tl.addWidget(b_save); tl.addWidget(b_clear)
        pv.addWidget(top)

        self.inv_table = QTableWidget(0, 3)
        self.inv_table.setHorizontalHeaderLabels(["材料", "等级", "库存数量"])
        self.inv_table.verticalHeader().setVisible(False)
        self.inv_table.horizontalHeader().setStretchLastSection(False)
        self.inv_table.setColumnWidth(0, 560)
        self.inv_table.setColumnWidth(1, 90)
        self.inv_table.setColumnWidth(2, 200)
        self.inv_table.verticalHeader().setDefaultSectionSize(32)
        self.inv_table.horizontalHeader().setStretchLastSection(True)
        pv.addWidget(self.inv_table, 1)

        tip = QLabel("「缺少」= 合计 − 库存；改完点「保存库存」写回数据库")
        tip.setObjectName("muted"); tip.setContentsMargins(12, 6, 12, 0)
        pv.addWidget(tip)
        lay.addWidget(panel)
        return page

    # ---------- 小工具 ----------
    def _head(self, text):
        w = QWidget(); w.setFixedHeight(38)
        w.setStyleSheet(f"border-bottom: 1px solid {LINE}; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                        f" stop:0 rgba(12,195,231,26), stop:0.55 transparent);")
        l = QHBoxLayout(w); l.setContentsMargins(14, 0, 12, 0); l.setSpacing(9)
        dot = QLabel("◆"); dot.setStyleSheet(f"color:{CYAN}; font-size:10px;")
        lab = QLabel(text); lab.setObjectName("head")
        l.addWidget(dot); l.addWidget(lab); l.addStretch(1)
        return w

    def _small(self, text):
        lab = QLabel(text); lab.setObjectName("muted")
        return lab

    # ---------- 数据 ----------
    def _chip_style(self, b, on):
        if on:
            b.setStyleSheet("QPushButton{background:#0cc3e7;border:1px solid #0cc3e7;color:#04131a;"
                            "font-weight:700;font-size:11px;padding:0;}")
        else:
            b.setStyleSheet("QPushButton{background:#0a1218;border:1px solid #2f4356;color:#9fb4c3;"
                            "font-size:11px;padding:0;}"
                            "QPushButton:hover{border-color:#0cc3e7;color:#d7e3ec;}")

    def set_prof_filter(self, code):
        self.prof_filter = code
        for k, b in self.prof_btns.items():
            b.setChecked(k == code)
            self._chip_style(b, k == code)
        self.do_search(self.search.text())

    def set_rarity_filter(self, r):
        self.rarity_filter = r
        for k, b in self.rar_btns.items():
            b.setChecked(k == r)
            self._chip_style(b, k == r)
        self.do_search(self.search.text())

    def do_search(self, kw):
        kw = (kw or "").strip()
        rows = self._search_db(kw)
        prof_f = getattr(self, "prof_filter", "")
        rar_f = getattr(self, "rarity_filter", 0)

        total_all = self._count_ops()
        total_excluded = self._count_excluded()
        # 过滤
        rows = [r for r in rows
                if (not prof_f or r[3] == prof_f or (prof_f == "SPECIAL" and r[3] == "SPECIALIST"))
                and (not rar_f or r[2] + 1 == rar_f)]

        owned_set = set(self._owned_uids())
        self.oplist.clear()
        groups = {}
        for uid, name, rarity, prof, pinyin in rows:
            key = prof if prof in dict(PROF_ORDER) else ("SPECIAL" if prof == "SPECIALIST" else prof)
            groups.setdefault(key, []).append((uid, name, rarity, prof))

        shown = 0
        for code, cn in PROF_ORDER:
            items = groups.get(code) or []
            if not items:
                continue
            items.sort(key=lambda x: (-x[2], x[1]))
            top = QTreeWidgetItem([f"◆ {cn}   {len(items)}"])
            top.setFlags(Qt.ItemIsEnabled)
            top.setForeground(0, QColor(CYAN))
            f = QFont("Microsoft YaHei UI", 9); f.setBold(True); top.setFont(0, f)
            top.setBackground(0, QColor(12, 195, 231, 26))
            self.oplist.addTopLevelItem(top)
            for uid, name, rarity, prof in items:
                stars = "★" * (rarity + 1)
                mark = " ●" if uid in owned_set else ""
                it = QTreeWidgetItem([f"   {name}{mark}    {stars}"])
                it.setData(0, Qt.UserRole, {"uid": uid, "name": name, "rarity": rarity + 1, "prof": prof})
                it.setForeground(0, QColor(RARITY.get(rarity + 1, TEXT)))
                av = op_pix(uid, 28)
                it.setIcon(0, QIcon(av if not av.isNull() else prof_badge(prof, rarity + 1, 24)))
                self.oplist.addTopLevelItem(it)
                shown += 1

        self.oplist.expandAll()
        # 统计
        rar_cnt = {}
        for _, _, r, _p, _x in rows:
            rar_cnt[r + 1] = rar_cnt.get(r + 1, 0) + 1
        parts = [f"{k}★ {v}" for k, v in sorted(rar_cnt.items(), reverse=True)]
        owned_n = len(self._owned_uids()) if getattr(self, "only_owned", False) else 0
        tip = f"可培养 {total_all} 名（已排除预备/特殊 {total_excluded}）"
        if getattr(self, "only_owned", False):
            tip = "仅我的 · " + tip
        if kw or prof_f or rar_f:
            tip += f" · 筛选后 {shown} 名"
        tip += "   |   " + " / ".join(parts) if parts else ""
        self.lbl_count.setText(tip)

    def _search_db(self, kw):
        import sqlite3
        con = sqlite3.connect(DB)
        try:
            owned = getattr(self, "only_owned", False)
            if owned:
                con.execute("CREATE TABLE IF NOT EXISTS owned (uid TEXT PRIMARY KEY)")
                own_sql = " AND uid IN (SELECT uid FROM owned)"
            else:
                own_sql = ""
            if not kw:
                return con.execute("SELECT uid,name,rarity,profession,pinyin FROM operators "
                                   "WHERE available=1" + own_sql +
                                   " ORDER BY rarity DESC, name LIMIT 1000").fetchall()
            like = "%" + kw + "%"
            return con.execute("SELECT uid,name,rarity,profession,pinyin FROM operators "
                               "WHERE available=1 AND (name LIKE ? OR pinyin LIKE ?)" + own_sql +
                               " ORDER BY rarity DESC, name LIMIT 1000",
                               (like, like)).fetchall()
        finally:
            con.close()

    def _count_ops(self):
        import sqlite3
        con = sqlite3.connect(DB)
        try:
            return con.execute("SELECT COUNT(*) FROM operators WHERE available=1").fetchone()[0]
        finally:
            con.close()

    def open_import(self):
        dlg = ImportDialog(DB, self)
        dlg.exec()
        self.refresh_all()
        self.refresh_inventory()
        self.do_search(self.search.text())

    def toggle_owned_filter(self):
        self.only_owned = not getattr(self, "only_owned", False)
        if self.only_owned and not self._owned_uids():
            self.only_owned = False
            self.btn_owned.setChecked(False)
            self._chip_style(self.btn_owned, False)
            self.lbl_hint.setText("还没有「我的干员」：先在 导入 → 干员列表 里导入练度")
            self.do_search(self.search.text())
            return
        self.btn_owned.setChecked(self.only_owned)
        self._chip_style(self.btn_owned, self.only_owned)
        self.do_search(self.search.text())

    def _owned_levels(self):
        """uid -> {elite, level}（来自导入的练度）"""
        import sqlite3
        con = sqlite3.connect(DB)
        try:
            con.execute("CREATE TABLE IF NOT EXISTS owned "
                        "(uid TEXT PRIMARY KEY, elite INTEGER DEFAULT 0, level INTEGER DEFAULT 0)")
            import json as _json
            cols = [c[1] for c in con.execute("PRAGMA table_info(owned)")]
            sel = "uid, elite, level"
            if "potential" in cols:
                sel += ", potential"
            if "skills" in cols:
                sel += ", skills"
            if "modules" in cols:
                sel += ", modules"
            out = {}
            for r in con.execute("SELECT " + sel + " FROM owned"):
                d = {"elite": r[1] or 0, "level": r[2] or 0, "potential": 0,
                     "skills": [], "modules": []}
                idx = 3
                if "potential" in cols:
                    d["potential"] = r[idx] or 0
                    idx += 1
                if "skills" in cols:
                    try:
                        d["skills"] = _json.loads(r[idx] or "[]")
                    except Exception:
                        d["skills"] = []
                    idx += 1
                if "modules" in cols:
                    try:
                        d["modules"] = _json.loads(r[idx] or "[]")
                    except Exception:
                        d["modules"] = []
                out[r[0]] = d
            return out
        finally:
            con.close()

    def _owned_uids(self):
        import sqlite3
        con = sqlite3.connect(DB)
        try:
            con.execute("CREATE TABLE IF NOT EXISTS owned (uid TEXT PRIMARY KEY)")
            return [r[0] for r in con.execute("SELECT uid FROM owned")]
        finally:
            con.close()

    def _count_excluded(self):
        import sqlite3
        con = sqlite3.connect(DB)
        try:
            return con.execute("SELECT COUNT(*) FROM operators WHERE available=0").fetchone()[0]
        finally:
            con.close()

    def on_pick(self, item, _col=0):
        d = item.data(0, Qt.UserRole) if hasattr(item, "data") else None
        if not d:
            return
        op = self.calc.operator(d["uid"])
        if not op:
            return
        self.op = op
        self.attrs = self.calc.attributes(op)
        self.lbl_picked.setObjectName("picked")
        self.lbl_picked.style().unpolish(self.lbl_picked); self.lbl_picked.style().polish(self.lbl_picked)
        self.lbl_picked.setText(f"{op['name']}   {'★' * (op['rarity'] + 1)}   {PROF_CN.get(op['profession'], '')}")
        self._rebuild_targets()
        self.btn_add.setEnabled(True)
        self.lbl_hint.setText("勾选目标项后点「加入计算表」")

    def _clear_layout(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

    def _make_target_row(self, a, parent_lay):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(6, 3, 6, 3)
        h.setSpacing(6)
        chk = QCheckBox(a["name"])
        chk.setMinimumWidth(150)
        sp1 = QSpinBox(); sp1.setRange(a["min"], a["max"]); sp1.setValue(a["cur"]); sp1.setFixedWidth(58)
        lab = QLabel("→"); lab.setObjectName("muted")
        sp2 = QSpinBox(); sp2.setRange(a["min"], a["max"]); sp2.setValue(a["target"]); sp2.setFixedWidth(58)
        for sp in (sp1, sp2):
            sp.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            sp.setStyleSheet(
                "QSpinBox{background:#0a1218;border:1px solid #2f4356;color:#d7e3ec;"
                "font-family:Consolas;font-size:11px;padding:1px 4px;}"
                "QSpinBox:focus{border-color:#0cc3e7;}"
                "QSpinBox::up-button,QSpinBox::down-button{width:0;height:0;}")
        h.addWidget(chk); h.addWidget(sp1); h.addWidget(lab); h.addWidget(sp2)
        h.addStretch(1)
        parent_lay.addWidget(w)
        rec = {"a": a, "chk": chk, "from": sp1, "to": sp2}
        chk.toggled.connect(lambda _=False: self._update_tab_labels())
        return rec

    def _rebuild_targets(self):
        """把目标项按 等级·阶段 / 技能 / 模组 三页排布"""
        attrs = getattr(self, "attrs", [])
        while self.tgt_tabs.count():
            page = self.tgt_tabs.widget(0)
            self.tgt_tabs.removeTab(0)
            page.deleteLater()
        self.tgt_rows = []
        if not attrs:
            return

        level_attrs = [a for a in attrs if a["t"] == "level"]
        top_level = level_attrs[-1] if level_attrs else None
        groups = {"等级·阶段": [], "技能": [], "模组": []}
        for a in attrs:
            if a["t"] in ("level", "rank"):
                groups["等级·阶段"].append(a)
            elif a["t"] in ("skill", "master"):
                groups["技能"].append(a)
            else:
                groups["模组"].append(a)

        lv = self._owned_levels().get(getattr(self, "op", {}).get("uid", ""), None)
        for title, items in groups.items():
            if not items:
                continue
            page = QWidget()
            page.setProperty("baseTitle", title)
            lay = QVBoxLayout(page)
            lay.setContentsMargins(0, 2, 0, 2)
            lay.setSpacing(1)
            for a in items:
                rec = self._make_target_row(a, lay)
                on = (a["code"] == "ELITE_RANK") or (top_level is not None and a is top_level)
                rec["chk"].setChecked(on)
                rec["tab"] = title
                # 按导入练度预填现等级 / 精英阶段
                if lv:
                    code = a["code"]
                    if code == "ELITE_RANK":
                        rec["from"].setValue(max(a["min"], min(a["max"], lv["elite"])))
                    elif code.startswith("LEVEL_ELITE_"):
                        phase = int(code[-1])
                        if phase == lv["elite"]:
                            rec["from"].setValue(max(a["min"], min(a["max"], lv["level"] or a["min"])))
                    elif code == "SKILL_LEVEL":
                        lvs = [int(sk.get("level") or 0) for sk in (lv.get("skills") or [])]
                        if lvs:
                            rec["from"].setValue(max(a["min"], min(a["max"], min(7, max(lvs)))))
                    elif code in ("MASTER_SKILL_1", "MASTER_SKILL_2", "MASTER_SKILL_3"):
                        slot = int(code[-1]) - 1
                        sks = lv.get("skills") or []
                        if slot < len(sks):
                            rec["from"].setValue(max(a["min"], min(a["max"], int(sks[slot].get("spec") or 0))))
                    elif code.startswith("ADVANCED_EQUIPMENT_"):
                        slot = int(code[-1]) - 1
                        mds = lv.get("modules") or []
                        if slot < len(mds):
                            rec["from"].setValue(max(a["min"], min(a["max"], int(mds[slot] or 0))))
                try:
                    if rec["from"].value() >= rec["to"].value():
                        rec["chk"].setChecked(False)
                except Exception:
                    pass
                self.tgt_rows.append(rec)
            lay.addStretch(1)
            self.tgt_tabs.addTab(page, title)
        self._update_tab_labels()

    def _update_tab_labels(self):
        cnt = {}
        for r in getattr(self, "tgt_rows", []):
            t = r.get("tab")
            if not t:
                continue
            cnt[t] = cnt.get(t, 0) + (1 if r["chk"].isChecked() else 0)
        for i in range(self.tgt_tabs.count()):
            page = self.tgt_tabs.widget(i)
            base = page.property("baseTitle")
            if not base:
                continue
            got = cnt.get(base, 0)
            self.tgt_tabs.setTabText(i, f"{base} ({got})" if got else base)

    def check_all(self, on):
        for r in getattr(self, "tgt_rows", []):
            r["chk"].setChecked(on)

    def add_plans(self):
        """把所有勾选的目标项一次性写入培养表"""
        rows = [r for r in getattr(self, "tgt_rows", []) if r["chk"].isChecked()]
        if not rows:
            self.lbl_hint.setText("先勾选要计算的目标项（可多选）")
            return
        import sqlite3
        uid = self.op["uid"]
        con = sqlite3.connect(DB)
        added = skipped = 0
        detail = []
        try:
            for r in rows:
                a = r["a"]
                cur = r["from"].value()
                tgt = r["to"].value()
                if cur >= tgt:
                    skipped += 1
                    continue
                if not self.calc.requirements(uid, a["code"], cur, tgt):
                    skipped += 1
                    continue
                con.execute("INSERT INTO plans(uid,attribute,cur,target) VALUES(?,?,?,?)",
                            (uid, a["code"], cur, tgt))
                added += 1
                detail.append(f"{a['name']} {cur}→{tgt}")
            con.commit()
        finally:
            con.close()
        self.refresh_all()
        txt = f"已加入 {added} 项：" + "、".join(detail[:4])
        if len(detail) > 4:
            txt += "…"
        if skipped:
            txt += f"（{skipped} 项区间无效，已跳过）"
        self.lbl_hint.setText(txt)

    def clear_plans(self):
        import sqlite3
        con = sqlite3.connect(DB)
        try:
            con.execute("DELETE FROM plans"); con.commit()
        finally:
            con.close()
        self.refresh_all()

    def del_plan(self, pid):
        import sqlite3
        con = sqlite3.connect(DB)
        try:
            con.execute("DELETE FROM plans WHERE id=?", (pid,)); con.commit()
        finally:
            con.close()
        self.refresh_all()

    def refresh_all(self):
        tb = self.calc.table()
        self._tb = tb
        self._rebuild_plan_tabs(tb)
        self._render_totals()

    def _rebuild_plan_tabs(self, tb):
        keep = ""
        if self.plan_tabs.count():
            keep = self.plan_tabs.tabText(self.plan_tabs.currentIndex()).split(" (")[0]
        while self.plan_tabs.count():
            w = self.plan_tabs.widget(0)
            self.plan_tabs.removeTab(0)
            w.deleteLater()
        self._tab_rows = {}
        rows = tb["rows"]
        groups = {}
        for r in rows:
            groups.setdefault(r["uid"], []).append(r)

        self._add_plan_tab("全部", rows)
        for uid, rs in groups.items():
            self._add_plan_tab(rs[0]["operator_name"], rs)

        idx = 0
        if keep:
            for i in range(self.plan_tabs.count()):
                if self.plan_tabs.tabText(i).split(" (")[0] == keep:
                    idx = i
                    break
        self.plan_tabs.blockSignals(True)
        self.plan_tabs.setCurrentIndex(idx)
        self.plan_tabs.blockSignals(False)

        s = tb["summary"]
        self.lbl_status.setText(
            f"{s['plans']} 项计划 · {len(groups)} 名干员 · {s['materials']} 种材料 · 缺 {s['missing_kinds']} 种")

    def _add_plan_tab(self, title, rows):
        area = QScrollArea()
        area.setWidgetResizable(True)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        if not rows:
            lab = QLabel("暂无培养计划 —— 左侧选择干员并加入")
            lab.setObjectName("muted")
            lab.setAlignment(Qt.AlignCenter)
            lab.setMinimumHeight(80)
            lay.addWidget(lab)
        for r in rows:
            row = PlanRow(r)
            row.remove.connect(self.del_plan)
            lay.addWidget(row)
        lay.addStretch(1)
        area.setWidget(host)
        idx = self.plan_tabs.addTab(area, f"{title} ({len(rows)})" if rows else title)
        self._tab_rows[idx] = rows

    def _current_rows(self):
        i = self.plan_tabs.currentIndex()
        return (getattr(self, "_tab_rows", {}) or {}).get(i, [])

    def _render_totals(self):
        while self.tot_layout.count():
            it = self.tot_layout.takeAt(0)
            w = it.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        rows = self._current_rows()
        items = self.calc.summarize(rows) if rows else []
        if not items:
            lab = QLabel("加入计划后自动汇总")
            lab.setObjectName("muted")
            lab.setAlignment(Qt.AlignCenter)
            self.tot_layout.addWidget(lab, 0, 0)
            return
        cols = 6
        for i, it in enumerate(items):
            self.tot_layout.addWidget(Card(it), i // cols, i % cols)

    # ---------- 库存 ----------
    def refresh_inventory(self):
        import sqlite3
        con = sqlite3.connect(DB)
        try:
            inv = dict(con.execute("SELECT material_id,quantity FROM inventory"))
            mats = con.execute("SELECT id,name,tier FROM materials ORDER BY sort_id").fetchall()
        finally:
            con.close()
        kw = self.inv_search.text().strip() if hasattr(self, "inv_search") else ""
        tb = self.calc.table()
        need = {i["id"] for i in tb["items"]}
        rows = [m for m in mats if not kw or kw in m[1]]
        rows.sort(key=lambda m: (0 if m[0] in need else 1, m[1]))
        self.inv_table.setRowCount(len(rows))
        for r, (mid, name, tier) in enumerate(rows):
            it0 = QTableWidgetItem(("● " if mid in need else "") + name)
            icon = mat_pix(mid, 22)
            if not icon.isNull():
                it0.setIcon(QIcon(icon))
            self.inv_table.setItem(r, 0, it0)
            self.inv_table.item(r, 0).setForeground(QColor(TIER.get(tier, TEXT)))
            it1 = QTableWidgetItem(str(tier or "")); it1.setForeground(QColor(MUTED))
            self.inv_table.setItem(r, 1, it1)
            spin = QSpinBox(); spin.setRange(0, 999999); spin.setValue(inv.get(mid, 0))
            spin.setMinimumHeight(26)
            spin.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            spin.setStyleSheet(
                "QSpinBox{background:#0a1218;border:1px solid #2f4356;color:#d7e3ec;"
                "font-family:Consolas;font-size:12px;padding:2px 6px;}"
                "QSpinBox:focus{border-color:#0cc3e7;}"
                "QSpinBox::up-button,QSpinBox::down-button{width:0;height:0;}")
            spin.setProperty("mid", mid)
            self.inv_table.setCellWidget(r, 2, spin)

    def save_inventory(self):
        import sqlite3
        con = sqlite3.connect(DB)
        try:
            for r in range(self.inv_table.rowCount()):
                w = self.inv_table.cellWidget(r, 2)
                if not w:
                    continue
                mid = w.property("mid")
                val = w.value()
                if val > 0:
                    con.execute("INSERT INTO inventory(material_id,quantity) VALUES(?,?) "
                                "ON CONFLICT(material_id) DO UPDATE SET quantity=excluded.quantity",
                                (mid, val))
                else:
                    con.execute("DELETE FROM inventory WHERE material_id=?", (mid,))
            con.commit()
        finally:
            con.close()
        self.refresh_all()
        self.lbl_status.setText("库存已保存")

    def clear_inventory(self):
        import sqlite3
        con = sqlite3.connect(DB)
        try:
            con.execute("DELETE FROM inventory"); con.commit()
        finally:
            con.close()
        self.refresh_inventory()
        self.refresh_all()


def make_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    import math
    cx = cy = 32
    r = 27
    poly = QPolygonF()
    for i in range(6):
        a = math.radians(60 * i - 30)
        poly.append(QPointF_(cx + r * math.cos(a), cy + r * math.sin(a)))
    p.setPen(QPen(QColor(CYAN), 3))
    p.setBrush(QColor(12, 195, 231, 60))
    p.drawPolygon(poly)
    p.setPen(QPen(QColor(GOLD), 4))
    p.drawPolyline(QPolygonF([QPointF_(cx - 11, cy + 12), QPointF_(cx, cy - 14), QPointF_(cx + 11, cy + 12)]))
    p.end()
    return QIcon(pm)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    win = MainWindow()
    win.setWindowIcon(make_icon())
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
