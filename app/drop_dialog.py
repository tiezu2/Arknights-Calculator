# -*- coding: utf-8 -*-
"""掉落数据同步对话框：显示缓存状态、立即更新、启动自动更新开关。"""
import threading

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton,
                               QSpinBox, QTextEdit, QVBoxLayout)

import penguin

QSS = """
QDialog { background: #070a0d; }
QLabel#title { color: #cfe6f2; font-weight: 700; letter-spacing: 2px; }
QLabel#hint { color: #7c8f9e; font-size: 11.5px; }
QLabel#ok { color: #7fb069; font-size: 12px; }
QLabel#err { color: #f2a2a4; font-size: 12px; }
QTextEdit { background: #0a1218; border: 1px solid #1b2836; color: #b8cbd8;
  font-family: Consolas, "Microsoft YaHei UI"; font-size: 11.5px; }
QCheckBox { color: #d7e3ec; font-size: 12px; }
QSpinBox { background: #0a1218; border: 1px solid #2f4356; color: #d7e3ec; padding: 3px 6px; }
QPushButton { background: #0d151c; border: 1px solid #2f4356; padding: 7px 14px;
  color: #d7e3ec; font-weight: 600; }
QPushButton:hover { border-color: #0cc3e7; background: #102029; }
QPushButton#primary { background: #0cc3e7; border-color: #0cc3e7; color: #04131a; }
QPushButton:disabled { color: #4b5a66; border-color: #223140; }
"""


class _Bridge(QObject):
    log = Signal(str)
    done = Signal(bool)


class DropDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("企鹅物流 · 关卡掉落数据")
        self.resize(640, 480)
        self.setStyleSheet(QSS)
        self.bridge = _Bridge(self)
        self.bridge.log.connect(self._append)
        self.bridge.done.connect(self._finished)
        self.busy = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        t = QLabel("◆ 关卡掉落数据（企鹅物流）")
        t.setObjectName("title")
        lay.addWidget(t)
        tip = QLabel("数据为社区实时上传统计；接口没有版本号，用「关卡集合指纹」判断版本，"
                     "每次版本更新后会自动重拉一次。")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.lbl_meta = QLabel("读取中…")
        self.lbl_meta.setObjectName("hint")
        self.lbl_meta.setWordWrap(True)
        lay.addWidget(self.lbl_meta)

        row = QHBoxLayout()
        self.chk_auto = QCheckBox("每次打开软件时自动检查/更新")
        self.sp_ttl = QSpinBox()
        self.sp_ttl.setRange(0, 720)
        self.sp_ttl.setSuffix(" 小时")
        self.sp_ttl.setFixedWidth(110)
        lbl_ttl = QLabel("缓存有效期")
        lbl_ttl.setObjectName("hint")
        self.chk_force = QCheckBox("强制重拉")
        row.addWidget(self.chk_auto)
        row.addSpacing(10)
        row.addWidget(lbl_ttl)
        row.addWidget(self.sp_ttl)
        row.addWidget(self.chk_force)
        row.addStretch(1)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        self.btn_sync = QPushButton("立即更新掉落数据")
        self.btn_sync.setObjectName("primary")
        self.btn_sync.clicked.connect(lambda: self.start_sync(force=self.chk_force.isChecked()))
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.accept)
        self.lbl_state = QLabel("")
        self.lbl_state.setObjectName("hint")
        row2.addWidget(self.btn_sync)
        row2.addWidget(self.btn_close)
        row2.addWidget(self.lbl_state, 1)
        lay.addLayout(row2)

        self.txt = QTextEdit()
        self.txt.setReadOnly(True)
        self.txt.setMinimumHeight(180)
        lay.addWidget(self.txt, 1)

        s = penguin.load_settings()
        self.chk_auto.setChecked(bool(s.get("auto_drop_sync", True)))
        self.sp_ttl.setValue(int(s.get("drop_ttl_hours", 24)))
        self.chk_auto.toggled.connect(self._save_settings)
        self.sp_ttl.valueChanged.connect(self._save_settings)
        self.refresh_meta()

    def _save_settings(self, *_):
        penguin.save_settings({
            "auto_drop_sync": self.chk_auto.isChecked(),
            "drop_ttl_hours": self.sp_ttl.value(),
        })
        self.lbl_state.setText("设置已保存")

    def refresh_meta(self):
        m = penguin.summary()
        if not m:
            self.lbl_meta.setText("还没有掉落数据缓存 —— 点下面「立即更新」拉取（约 3 MB）")
        else:
            c = m["counts"]
            self.lbl_meta.setText(
                f"缓存：关卡 {c.get('stages', 0)} / 物品 {c.get('items', 0)} / "
                f"区域 {c.get('zones', 0)} / 掉落 {c.get('matrix', 0)} 行"
                f"　|　版本指纹 {m['fingerprint']}　|　最新活动 {m['version_hint']}"
                f"　|　抓取于 {m['fetched_at_text']}　|　{m['size_mb']:.1f} MB")
        need, why = penguin.quick_check(self.sp_ttl.value())
        self.lbl_state.setText(("需要更新：" + why) if need else "缓存较新")

    def _append(self, msg):
        self.txt.append(msg)

    def start_sync(self, force=False):
        if self.busy:
            return
        self.busy = True
        self.btn_sync.setEnabled(False)
        self.btn_close.setEnabled(False)
        self.lbl_state.setText("更新中…（约 10–30 秒，取决于网络）")
        self.txt.clear()

        def work():
            try:
                res = penguin.run_sync(force=force, log=lambda m: self.bridge.log.emit(m))
                self.bridge.log.emit("结果：" + ("已更新" if res.get("changed") else "无需更新"))
                self.bridge.done.emit(True)
            except Exception as e:
                self.bridge.log.emit(f"失败：{type(e).__name__}: {e}")
                self.bridge.done.emit(False)

        threading.Thread(target=work, daemon=True).start()

    def _finished(self, ok):
        self.busy = False
        self.btn_sync.setEnabled(True)
        self.btn_close.setEnabled(True)
        self.refresh_meta()
        self.lbl_state.setText("✅ 更新完成" if ok else "❌ 更新失败")
