# -*- coding: utf-8 -*-
"""导入对话框：库存 / 干员列表（支持 MAA 导出、JSON、CSV、TXT、直接粘贴）。"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QTabWidget, QTextEdit,
                               QVBoxLayout, QWidget)

from importer import Importer

QSS_DLG = """
QDialog { background: #070a0d; }
QLabel#title { color: #cfe6f2; font-weight: 700; letter-spacing: 2px; }
QLabel#hint { color: #7c8f9e; font-size: 11.5px; }
QTabWidget::pane { border: 1px solid #1b2836; background: #0b1218; }
QTabBar::tab { background: #0a1218; color: #7c8f9e; padding: 6px 18px;
  border: 1px solid #1b2836; border-bottom: none; font-size: 12px; }
QTabBar::tab:selected { background: rgba(12,195,231,0.16); color: #cfe6f2; border-color: #0cc3e7; }
QPlainTextEdit, QLineEdit { background: #0a1218; border: 1px solid #2f4356; color: #d7e3ec;
  font-family: Consolas; font-size: 12px; }
QTextEdit { background: #0a1218; border: 1px solid #1b2836; color: #b8cbd8;
  font-family: "Microsoft YaHei UI"; font-size: 12px; }
QPushButton { background: #0d151c; border: 1px solid #2f4356; padding: 7px 14px;
  color: #d7e3ec; font-weight: 600; }
QPushButton:hover { border-color: #0cc3e7; background: #102029; }
QPushButton#primary { background: #0cc3e7; border-color: #0cc3e7; color: #04131a; }
"""


class _Page(QWidget):
    """一个导入页：文件 + 粘贴 + 预览 + 应用"""

    def __init__(self, kind, importer, parent=None):
        super().__init__(parent)
        self.kind = kind  # "inv" / "op"
        self.imp = importer
        self.result = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        tip = QLabel(
            "支持 MAA 导出的 JSON、CSV、TXT，或直接粘贴。\n"
            + ("库存：材料名/物品 id → 数量；例：`固源岩,30` 或 {\"固源岩\": 30}"
               if kind == "inv" else
               "干员：char_xxx id 或干员中文名；例：`char_002_amiya` 或 `阿米娅`"))
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        fr = QHBoxLayout()
        fr.setSpacing(6)
        self.ed_path = QLineEdit()
        self.ed_path.setPlaceholderText("选择文件（留空则用下面的粘贴内容）")
        b_br = QPushButton("浏览…")
        b_br.clicked.connect(self.browse)
        fr.addWidget(self.ed_path, 1)
        fr.addWidget(b_br)
        lay.addLayout(fr)

        self.ed_text = QPlainTextEdit()
        self.ed_text.setPlaceholderText("也可以直接粘贴内容…")
        self.ed_text.setMinimumHeight(150)
        lay.addWidget(self.ed_text, 1)

        cb = QHBoxLayout()
        b_clip = QPushButton("从剪贴板粘贴")
        b_clip.setToolTip("复制 MAA / penguin-statistics 导出的 JSON 后点这里")
        b_clip.clicked.connect(self.paste_clipboard)
        b_clear = QPushButton("清空输入")
        b_clear.clicked.connect(lambda: (self.ed_text.clear(), self.ed_path.clear()))
        cb.addWidget(b_clip)
        cb.addWidget(b_clear)
        cb.addStretch(1)
        lay.addLayout(cb)

        br = QHBoxLayout()
        b_parse = QPushButton("解析预览")
        b_parse.clicked.connect(self.do_parse)
        b_apply = QPushButton("应用导入")
        b_apply.setObjectName("primary")
        b_apply.clicked.connect(self.do_apply)
        self.lbl_state = QLabel("")
        self.lbl_state.setObjectName("hint")
        br.addWidget(b_parse)
        br.addWidget(b_apply)
        br.addWidget(self.lbl_state, 1)
        lay.addLayout(br)

        self.txt_preview = QTextEdit()
        self.txt_preview.setReadOnly(True)
        self.txt_preview.setMinimumHeight(120)
        lay.addWidget(self.txt_preview, 1)

    def paste_clipboard(self):
        from PySide6.QtWidgets import QApplication
        txt = QApplication.clipboard().text()
        if txt.strip():
            self.ed_text.setPlainText(txt)
            self.ed_path.clear()
            self.lbl_state.setText("已从剪贴板读取 %d 字符" % len(txt))
        else:
            self.lbl_state.setText("剪贴板是空的")

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择导入文件", os.path.expanduser("~"),
            "数据文件 (*.json *.csv *.txt);;所有文件 (*)")
        if path:
            self.ed_path.setText(path)

    def _content(self):
        text = self.ed_text.toPlainText().strip()
        if text:
            return text
        p = self.ed_path.text().strip()
        if p and os.path.exists(p):
            for enc in ("utf-8-sig", "utf-8", "gbk", "utf-16"):
                try:
                    return open(p, encoding=enc).read()
                except Exception:
                    continue
        return ""

    def do_parse(self):
        content = self._content()
        if not content.strip():
            self.lbl_state.setText("没有内容：请选择文件或粘贴数据")
            return
        if self.kind == "inv":
            inv, unknown = self.imp.parse_inventory_text(content)
            self.result = inv
            total = sum(inv.values())
            self.lbl_state.setText(f"解析到 {len(inv)} 种材料，共 {total:,} 个")
            lines = [f"{self.imp.item_names.get('', '')}"]
            con_rows = []
            for mid, qty in sorted(inv.items(), key=lambda kv: -kv[1]):
                con_rows.append(f"  {self.imp.mat_name(mid):<12} × {qty:,}")
            self.txt_preview.setPlainText(
                "\n".join(con_rows[:80]) + (f"\n… 共 {len(con_rows)} 项" if len(con_rows) > 80 else "")
                + (f"\n\n未识别 {len(unknown)} 个：{'、'.join(unknown[:20])}" if unknown else ""))
        else:
            uids, unknown = self.imp.parse_operators_text(content)
            self.result = uids
            self.lbl_state.setText(f"解析到 {len(uids)} 名干员")
            self.txt_preview.setPlainText(
                "\n".join("  " + u for u in uids[:80])
                + (f"\n… 共 {len(uids)} 名" if len(uids) > 80 else "")
                + (f"\n\n未识别 {len(unknown)} 个：{'、'.join(unknown[:20])}" if unknown else ""))

    def do_apply(self):
        if not self.result:
            self.do_parse()
        if not self.result:
            return
        if self.kind == "inv":
            n = self.imp.apply_inventory(self.result)
            self.lbl_state.setText(f"已写入 {n} 种材料库存")
        else:
            n = self.imp.apply_operators(self.result)
            self.lbl_state.setText(f"已导入 {n} 名干员到「我的干员」")


class ImportDialog(QDialog):
    def __init__(self, db_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导入数据 · MAA / JSON / CSV")
        self.resize(760, 620)
        self.setStyleSheet(QSS_DLG)
        self.imp = Importer(db_path)
        self.applied = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        title = QLabel("◆ 导入")
        title.setObjectName("title")
        lay.addWidget(title)

        self.tabs = QTabWidget()
        self.p_inv = _Page("inv", self.imp)
        self.p_op = _Page("op", self.imp)
        self.tabs.addTab(self.p_inv, "库存")
        self.tabs.addTab(self.p_op, "干员列表")
        lay.addWidget(self.tabs, 1)

        br = QHBoxLayout()
        b_owned = QPushButton("清空「我的干员」")
        b_owned.clicked.connect(self.clear_owned)
        b_close = QPushButton("关闭")
        b_close.setObjectName("primary")
        b_close.clicked.connect(self.accept)
        br.addWidget(b_owned)
        br.addStretch(1)
        br.addWidget(b_close)
        lay.addLayout(br)

    def clear_owned(self):
        self.imp.clear_owned()
        self.p_op.lbl_state.setText("已清空「我的干员」")
