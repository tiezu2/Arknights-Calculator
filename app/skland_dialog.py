# -*- coding: utf-8 -*-
"""森空岛（Skland）登录与练度同步对话框。"""
import json
import os
import sqlite3
import time

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QTabWidget,
                               QTextEdit, QVBoxLayout, QWidget)

from skland import (Cred, SklandError, cred_by_code, gen_scan, get_binding,
                    get_player_info, grant_code, parse_chars, scan_status,
                    token_by_scan_code)

QSS = """
QDialog { background: #070a0d; }
QLabel#title { color: #cfe6f2; font-weight: 700; letter-spacing: 2px; }
QLabel#hint { color: #7c8f9e; font-size: 11.5px; }
QLabel#ok { color: #7fb069; font-size: 12px; }
QLabel#err { color: #f2a2a4; font-size: 12px; }
QTabWidget::pane { border: 1px solid #1b2836; background: #0b1218; }
QTabBar::tab { background: #0a1218; color: #7c8f9e; padding: 6px 18px;
  border: 1px solid #1b2836; border-bottom: none; font-size: 12px; }
QTabBar::tab:selected { background: rgba(12,195,231,0.16); color: #cfe6f2; border-color: #0cc3e7; }
QLineEdit { background: #0a1218; border: 1px solid #2f4356; color: #d7e3ec; padding: 6px 8px;
  font-family: Consolas; font-size: 12px; }
QTextEdit { background: #0a1218; border: 1px solid #1b2836; color: #b8cbd8;
  font-family: "Microsoft YaHei UI"; font-size: 12px; }
QListWidget { background: #0a1218; border: 1px solid #1b2836; color: #d7e3ec; font-size: 12px; }
QListWidget::item { padding: 6px 8px; border-bottom: 1px solid #101b24; }
QListWidget::item:selected { background: #0e2130; }
QPushButton { background: #0d151c; border: 1px solid #2f4356; padding: 7px 14px;
  color: #d7e3ec; font-weight: 600; }
QPushButton:hover { border-color: #0cc3e7; background: #102029; }
QPushButton#primary { background: #0cc3e7; border-color: #0cc3e7; color: #04131a; }
"""


def _qrcode_pixmap(text, size=214):
    try:
        import qrcode
    except Exception:
        return None
    try:
        qr = qrcode.QRCode(border=1, box_size=6)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img = img.convert("RGBA") if hasattr(img, "convert") else img
        buf = os.path.join(os.environ.get("TEMP", "."), "_skland_qr.png")
        img.save(buf)
        pm = QPixmap(buf)
        return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    except Exception:
        return None


class SklandDialog(QDialog):
    def __init__(self, db_path, parent=None):
        super().__init__(parent)
        self.db = db_path
        self.cred_file = os.path.join(os.path.dirname(db_path), "skland_cred.json")
        self.cred = Cred.load(self.cred_file)
        self.scan_id = None
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_scan)
        self.poll_left = 0
        self.synced = 0

        self.setWindowTitle("森空岛 · 同步干员练度")
        self.resize(720, 620)
        self.setStyleSheet(QSS)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)
        title = QLabel("◆ 森空岛登录")
        title.setObjectName("title")
        lay.addWidget(title)
        tip = QLabel("扫码用「森空岛 App」登录；登录后可一键同步账号内全部干员练度"
                     "（精英/等级/技能专精/模组/潜能）。库存数据森空岛不提供，请用导入功能。")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_scan_tab(), "扫码登录")
        self.tabs.addTab(self._build_cred_tab(), "凭据登录")
        lay.addWidget(self.tabs, 1)

        lay.addWidget(self._build_role_box())

        br = QHBoxLayout()
        self.lbl_state = QLabel("")
        self.lbl_state.setObjectName("hint")
        b_close = QPushButton("关闭")
        b_close.setObjectName("primary")
        b_close.clicked.connect(self.accept)
        br.addWidget(self.lbl_state, 1)
        br.addWidget(b_close)
        lay.addLayout(br)

        if self.cred:
            self._load_roles()

    # ---------------- 扫码页 ----------------
    def _build_scan_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        row = QHBoxLayout()
        self.btn_gen = QPushButton("生成登录二维码")
        self.btn_gen.setObjectName("primary")
        self.btn_gen.clicked.connect(self.make_qr)
        self.btn_check = QPushButton("我已扫码，检查状态")
        self.btn_check.setEnabled(False)
        self.btn_check.clicked.connect(self.check_scan_once)
        row.addWidget(self.btn_gen)
        row.addWidget(self.btn_check)
        row.addStretch(1)
        lay.addLayout(row)

        self.lbl_qr = QLabel("点击上面按钮生成二维码")
        self.lbl_qr.setAlignment(Qt.AlignCenter)
        self.lbl_qr.setMinimumHeight(246)
        self.lbl_qr.setMaximumHeight(246)
        self.lbl_qr.setStyleSheet("background:#fff; border:1px solid #2f4356; color:#333;")
        lay.addWidget(self.lbl_qr)

        self.lbl_scan = QLabel("")
        self.lbl_scan.setObjectName("hint")
        self.lbl_scan.setWordWrap(True)
        self.lbl_scan.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.lbl_scan)
        lay.addStretch(1)
        return w

    # ---------------- 凭据页 ----------------
    def _build_cred_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(QLabel("贴入抓包得到的 cred 与 token（森空岛 App → 抓包工具）"))
        self.ed_cred = QLineEdit()
        self.ed_cred.setPlaceholderText("cred")
        self.ed_token = QLineEdit()
        self.ed_token.setPlaceholderText("token")
        if self.cred:
            self.ed_cred.setText(self.cred.cred)
            self.ed_token.setText(self.cred.token)
        lay.addWidget(self.ed_cred)
        lay.addWidget(self.ed_token)
        row = QHBoxLayout()
        b_save = QPushButton("保存并读取角色")
        b_save.setObjectName("primary")
        b_save.clicked.connect(self.save_cred_manual)
        row.addWidget(b_save)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    # ---------------- 角色列表 ----------------
    def _build_role_box(self):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        head = QLabel("角色列表")
        head.setObjectName("title")
        lay.addWidget(head)
        self.lst = QListWidget()
        self.lst.setMaximumHeight(150)
        lay.addWidget(self.lst)
        row = QHBoxLayout()
        self.btn_sync = QPushButton("同步选中角色的练度")
        self.btn_sync.setObjectName("primary")
        self.btn_sync.setEnabled(False)
        self.btn_sync.clicked.connect(self.sync_selected)
        self.btn_reload = QPushButton("刷新角色")
        self.btn_reload.clicked.connect(self._load_roles)
        row.addWidget(self.btn_sync)
        row.addWidget(self.btn_reload)
        row.addStretch(1)
        lay.addLayout(row)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(90)
        lay.addWidget(self.txt_log)
        return box

    # ---------------- 扫码流程 ----------------
    def make_qr(self):
        try:
            self.scan_id, scan_url = gen_scan()
        except SklandError as e:
            self._say(f"生成二维码失败：{e}", err=True)
            return
        self.btn_check.setEnabled(True)
        self.lbl_scan.setText(f"scanId: {self.scan_id}\n链接: {scan_url}")
        pm = _qrcode_pixmap(scan_url or self.scan_id)
        if pm:
            self.lbl_qr.setPixmap(pm)
            self.lbl_qr.setText("")
        else:
            self.lbl_qr.setText(f"（未安装 qrcode 库，无法显示二维码）\n\n"
                                f"请用森空岛 App 扫码：\n{scan_url}\n\n或改用「凭据登录」")
        self._say("请用森空岛 App 扫码（60 秒内有效）")
        self.poll_left = 40
        self.poll_timer.start(1500)

    def _poll_scan(self):
        if not self.scan_id:
            self.poll_timer.stop()
            return
        if self.poll_left <= 0:
            self.poll_timer.stop()
            self._say("二维码已超时，请重新生成", err=True)
            return
        self.poll_left -= 1
        self.check_scan_once(quiet=True)

    def check_scan_once(self, quiet=False):
        if not self.scan_id:
            return
        try:
            code, status = scan_status(self.scan_id)
        except SklandError as e:
            if not quiet:
                self._say(f"查询状态失败：{e}", err=True)
            return
        if not code:
            if not quiet:
                self._say("还没扫码（请在森空岛 App 里确认登录）")
            return
        self.poll_timer.stop()
        self._say("已扫码，正在换取凭据…")
        try:
            token = token_by_scan_code(code)
            grant = grant_code(token, 0)
            data = cred_by_code(grant)
            self.cred = Cred(data["cred"], data["token"], data.get("userId"), self.cred_file)
            self.cred.save()
            self.ed_cred.setText(self.cred.cred)
            self.ed_token.setText(self.cred.token)
            self._say("登录成功，已保存凭据", ok=True)
            self._load_roles()
        except SklandError as e:
            self._say(f"登录失败：{e}", err=True)

    # ---------------- 凭据 ----------------
    def save_cred_manual(self):
        cred = self.ed_cred.text().strip()
        token = self.ed_token.text().strip()
        if not cred or not token:
            self._say("cred 和 token 都要填", err=True)
            return
        self.cred = Cred(cred, token, None, self.cred_file)
        self.cred.save()
        self._say("凭据已保存", ok=True)
        self._load_roles()

    # ---------------- 角色与同步 ----------------
    def _load_roles(self):
        if not self.cred:
            self._say("还没有凭据，请先扫码登录", err=True)
            return
        self.lst.clear()
        try:
            apps = get_binding(self.cred)
        except SklandError as e:
            self._say(f"读取角色失败：{e}", err=True)
            return
        n = 0
        for app in apps:
            for b in (app.get("bindingList") or []):
                uid = b.get("uid")
                nick = b.get("nickName") or b.get("nickname") or ""
                if not uid:
                    continue
                it = QListWidgetItem(f"{nick}   (uid {uid})   {b.get('channelName') or ''}")
                it.setData(Qt.UserRole, {"uid": uid, "nick": nick,
                                         "cid": b.get("channelMasterId") or app.get("channelMasterId")})
                self.lst.addItem(it)
                n += 1
        self.btn_sync.setEnabled(n > 0)
        if n:
            self.lst.setCurrentRow(0)
            self._say(f"找到 {n} 个角色，选择后点「同步」", ok=True)
        else:
            self._say("账号下没有绑定明日方舟角色", err=True)

    def sync_selected(self):
        it = self.lst.currentItem()
        if not it or not self.cred:
            return
        uid = it.data(Qt.UserRole)["uid"]
        self._say(f"正在拉取 uid {uid} 的练度…")
        QApplication.processEvents()
        try:
            info = get_player_info(self.cred, uid)
        except SklandError as e:
            self._say(f"拉取失败：{e}", err=True)
            return
        chars = parse_chars(info)
        if not chars:
            self._say("返回里没有干员数据", err=True)
            return
        n = self._write_owned(chars)
        self.synced = n
        self._say(f"已同步 {n} 名干员练度（含精英/等级/技能专精/模组/潜能）", ok=True)
        self.txt_log.append(f"profile: {(info.get('profile') or {}).get('name') or ''} "
                            f"等级 {(info.get('profile') or {}).get('level') or ''}")
        self.txt_log.append("示例: " + ", ".join(
            f"{c['name'] or c['uid']}(E{c['elite']} L{c['level']} M{sum(s['spec'] for s in c['skills'])})"
            for c in chars[:6]))

    def _write_owned(self, chars):
        con = sqlite3.connect(self.db)
        try:
            con.execute("CREATE TABLE IF NOT EXISTS owned "
                        "(uid TEXT PRIMARY KEY, elite INTEGER DEFAULT 0, level INTEGER DEFAULT 0)")
            cols = [r[1] for r in con.execute("PRAGMA table_info(owned)")]
            for col, ddl in [("potential", "ALTER TABLE owned ADD COLUMN potential INTEGER DEFAULT 0"),
                             ("skills", "ALTER TABLE owned ADD COLUMN skills TEXT DEFAULT ''"),
                             ("modules", "ALTER TABLE owned ADD COLUMN modules TEXT DEFAULT ''")]:
                if col not in cols:
                    con.execute(ddl)
            known = {r[0] for r in con.execute("SELECT uid FROM operators")}
            n = 0
            for c in chars:
                if c["uid"] not in known:
                    continue
                con.execute("INSERT OR REPLACE INTO owned"
                            "(uid, elite, level, potential, skills, modules) VALUES(?,?,?,?,?,?)",
                            (c["uid"], c["elite"], c["level"], c["potential"],
                             json.dumps(c["skills"], ensure_ascii=False),
                             json.dumps(c["modules"], ensure_ascii=False)))
                n += 1
            con.commit()
            return n
        finally:
            con.close()

    # ---------------- 提示 ----------------
    def _say(self, msg, ok=False, err=False):
        self.lbl_state.setObjectName("ok" if ok else ("err" if err else "hint"))
        self.lbl_state.style().unpolish(self.lbl_state)
        self.lbl_state.style().polish(self.lbl_state)
        self.lbl_state.setText(msg)
