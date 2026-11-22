# -*- coding: utf-8 -*-
"""掉落查询页：材料分「芯片 / 养成材料（按稀有度 T1–T5）」，每项带图标。

有掉落的给关卡表（次均 / 每理智 / 样本数）；无掉落的标注合成/兑换。
掉落索引是企鹅物品 id（30012…），图标是本地材料 id（M-2-1…），按名称对上。
"""
import json
import os
import sqlite3
import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

import penguin

TIER_CN = {"T1": "T1 一星", "T2": "T2 二星", "T3": "T3 三星", "T4": "T4 四星", "T5": "T5 五星", "T6": "T6 六星"}
TIER_COLOR = {"T1": "#8a939c", "T2": "#7fb069", "T3": "#4aa8e0", "T4": "#b07fe0",
              "T5": "#f2c14e", "T6": "#f0863f"}


class _Bridge(QObject):
    done = Signal(str)


class DropPage(QWidget):
    def __init__(self, db_path=None, icons_dir=None, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.icons_dir = icons_dir
        self.materials = []      # [(id, name, tier, type, sort_id)]
        self.pid_by_name = {}
        self.index = {}
        self.current = None
        self.busy = False
        self.bridge = _Bridge(self)
        self.bridge.done.connect(self._on_synced)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 10, 14, 8)
        bl.setSpacing(8)
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("搜索材料（如 固源岩 / 扭转醇 / D32钢 / 先锋芯片）")
        self.ed_search.textChanged.connect(self._refresh_list)
        self.btn_sync = QPushButton("刷新掉落数据")
        self.btn_sync.clicked.connect(self.do_sync)
        self.lbl_state = QLabel("")
        self.lbl_state.setObjectName("muted")
        bl.addWidget(self.ed_search, 1)
        bl.addWidget(self.btn_sync)
        bl.addWidget(self.lbl_state)
        lay.addWidget(bar)

        body = QHBoxLayout()
        body.setContentsMargins(14, 0, 14, 12)
        body.setSpacing(12)

        # 左：分类树
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(6)
        self.lbl_count = QLabel("材料")
        self.lbl_count.setObjectName("muted")
        lv.addWidget(self.lbl_count)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(False)
        self.tree.setStyleSheet(
            "QTreeWidget{background:#0a1116;border:1px solid #223140;outline:none;}"
            "QTreeWidget::item{height:26px;padding:2px 4px;}"
            "QTreeWidget::item:hover{background:#0d1a22;}"
            "QTreeWidget::item:selected{background:#0e2130;color:#eaf6fb;}")
        self.tree.setIconSize(QPixmap(22, 22).size())
        self.tree.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.tree.itemSelectionChanged.connect(self._on_select)
        lv.addWidget(self.tree, 1)
        body.addWidget(left, 1)

        # 右：掉落明细
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(6)
        head = QHBoxLayout()
        self.icon_big = QLabel()
        self.icon_big.setFixedSize(34, 34)
        self.lbl_title = QLabel("选择左侧材料查看掉落")
        self.lbl_title.setStyleSheet("color:#cfe6f2; font-weight:700; letter-spacing:1px;")
        head.addWidget(self.icon_big)
        head.addWidget(self.lbl_title, 1)
        rv.addLayout(head)
        self.lbl_best = QLabel("")
        self.lbl_best.setObjectName("muted")
        self.lbl_best.setWordWrap(True)
        rv.addWidget(self.lbl_best)

        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["关卡", "区域", "理智/次", "掉落率（次均）", "每理智"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        rv.addWidget(self.tbl, 1)
        self.lbl_tip = QLabel("掉落率 = 掉落数量 ÷ 样本次数（玩家上传数据实时聚合）")
        self.lbl_tip.setObjectName("muted")
        rv.addWidget(self.lbl_tip)
        body.addWidget(right, 2)

        lay.addLayout(body, 1)
        self.reload()
        QTimer.singleShot(400, self._refresh_list)

    # ---------------- 数据 ----------------
    def reload(self):
        self.materials = []
        if self.db_path:
            try:
                con = sqlite3.connect(self.db_path)
                rows = con.execute("SELECT id, name, tier, type, sort_id FROM materials").fetchall()
                con.close()
                self.materials = [(r[0], str(r[1]).strip(), r[2] or "", r[3] or "", r[4] or 0)
                                  for r in rows]
                self.materials.sort(key=lambda m: (m[4], m[1]))
            except Exception:
                self.materials = []
        self.index, names = {}, {}
        try:
            p = os.path.join(penguin.CACHE, "drop_index.json")
            if os.path.exists(p):
                data = json.load(open(p, encoding="utf-8"))
                self.index = data.get("by_item") or {}
                names = data.get("item_name") or {}
        except Exception:
            pass
        self.pid_by_name = {str(nm).strip(): iid for iid, nm in names.items()}
        self._refresh_list()

    def _is_chip(self, m):
        return m[3] == "chip" or "芯片" in m[1]

    def _groups(self):
        """[(标题, 颜色, [材料...])]，顺序：芯片 → 养成材料 T1..T5"""
        PROF_ORDER = ["先锋", "近卫", "重装", "狙击", "术师", "医疗", "辅助", "特种"]

        def chip_key(m):
            name = m[1]
            prof = next((i for i, p in enumerate(PROF_ORDER) if name.startswith(p)), 99)
            if name == "芯片助剂":
                kind = 9
            elif name.endswith("双芯片"):
                kind = 2
            elif name.endswith("芯片组"):
                kind = 1
            else:
                kind = 0
            return (prof, kind)

        chips = sorted([m for m in self.materials if self._is_chip(m)], key=chip_key)
        mats = [m for m in self.materials if not self._is_chip(m)]
        out = []
        if chips:
            out.append(("芯片", "#0cc3e7", chips))
        for tier in ("T1", "T2", "T3", "T4", "T5", "T6"):
            items = [m for m in mats if m[2] == tier]
            if items:
                out.append((TIER_CN.get(tier, tier), TIER_COLOR.get(tier, "#d7e3ec"), items))
        rest = [m for m in mats if m[2] not in ("T1", "T2", "T3", "T4", "T5", "T6")]
        if rest:
            out.append(("其他", "#8a939c", rest))
        return out

    def _refresh_list(self, *_):
        kw = (self.ed_search.text() or "").strip()
        self.tree.blockSignals(True)
        self.tree.clear()
        first = None
        total = 0
        for title, color, items in self._groups():
            items = [m for m in items if not kw or kw in m[1]]
            if not items:
                continue
            top = QTreeWidgetItem([f"{title}   {len(items)}"])
            top.setFlags(Qt.ItemIsEnabled)
            f = QFont("Microsoft YaHei UI", 9)
            f.setBold(True)
            top.setFont(0, f)
            top.setForeground(0, QColor(color))
            self.tree.addTopLevelItem(top)
            for mid, name, tier, typ, _ in items:
                it = QTreeWidgetItem([f"  {name}"])
                it.setData(0, Qt.UserRole, mid)
                icon = self._icon(mid)
                if icon:
                    it.setIcon(0, icon)
                it.setForeground(0, QColor("#d7e3ec"))
                top.addChild(it)
                total += 1
                if first is None:
                    first = it
        self.tree.expandAll()
        self.tree.blockSignals(False)
        self.lbl_count.setText(f"共 {total} 种")
        if first is not None:
            self.tree.setCurrentItem(first)
            self.show_item(first.data(0, Qt.UserRole))
        else:
            self._clear_panel("没有匹配的材料")

    def _icon(self, mid, size=22):
        if not self.icons_dir:
            return None
        for ext in (".png", ".webp"):
            p = os.path.join(self.icons_dir, str(mid) + ext)
            if os.path.exists(p):
                pm = QPixmap(p)
                if not pm.isNull():
                    return QIcon(pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return None

    def select_material(self, mid):
        """外部跳转：选中指定材料（不在列表里就返回 False）"""
        mid = str(mid)
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                it = top.child(j)
                if str(it.data(0, Qt.UserRole)) == mid:
                    self.tree.setCurrentItem(it)
                    self.tree.scrollToItem(it, QAbstractItemView.PositionAtCenter)
                    self.show_item(mid)
                    return True
        # 不在当前过滤结果里：清空搜索再找
        if self.ed_search.text():
            self.ed_search.clear()
            return self.select_material(mid)
        return False

    def _on_select(self):
        it = self.tree.currentItem()
        if not it:
            return
        mid = it.data(0, Qt.UserRole)
        if mid:
            self.show_item(mid)

    def _clear_panel(self, msg):
        self.lbl_title.setText(msg)
        self.lbl_best.setText("")
        self.tbl.setRowCount(0)
        self.icon_big.clear()

    # ---------------- 展示 ----------------
    def show_item(self, our_id):
        self.current = our_id
        row = next((m for m in self.materials if m[0] == our_id), None)
        if not row:
            self._clear_panel("未知材料")
            return
        _, name, tier, typ, _ = row
        icon = self._icon(our_id, 32)
        if icon:
            self.icon_big.setPixmap(icon.pixmap(32, 32))
        else:
            self.icon_big.clear()

        drops = self.index.get(self.pid_by_name.get(name, "")) or []
        label = f"{name}　{'芯片' if self._is_chip(row) else '养成材料'} · {tier}"
        if not drops:
            self.lbl_title.setText(f"{label}  ·  无掉落数据")
            self.lbl_best.setText("该材料通常靠合成 / 兑换 / 活动获取，企鹅物流没有掉落记录。")
            self.tbl.setRowCount(0)
            self.lbl_tip.setText("")
            return

        self.lbl_title.setText(f"{label}  ·  掉落关卡 {len(drops)} 个")
        best = sorted(drops, key=lambda d: -d.get("rate", 0))[0]
        txt = f"最高掉落率：{best['stage']}（{best['rate']:.3f}/次"
        if best.get("apCost"):
            txt += f"，{best['rate']/best['apCost']:.3f}/理智"
        txt += f"，样本 {best.get('times', 0):,}）"
        by_ap = sorted([d for d in drops if d.get("apCost")],
                       key=lambda d: -(d.get("rate", 0) / d["apCost"]))
        if by_ap and by_ap[0].get("stage") != best["stage"]:
            txt += f"　|　最省理智：{by_ap[0]['stage']}（{by_ap[0]['rate']/by_ap[0]['apCost']:.3f}/理智）"
        self.lbl_best.setText(txt)

        rows = sorted(drops, key=lambda d: -(d.get("rate", 0) / (d.get("apCost") or 1)))[:60]
        self.tbl.setRowCount(len(rows))
        for i, d in enumerate(rows):
            ap = d.get("apCost") or 0
            rate = d.get("rate", 0)
            vals = [d.get("stage", ""), d.get("zone", ""),
                    str(ap) if ap else "—", f"{rate:.3f}",
                    f"{rate/ap:.3f}" if ap else "—"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignCenter if c >= 2 else Qt.AlignLeft | Qt.AlignVCenter)
                if i == 0:
                    it.setForeground(QColor("#f2c14e"))
                self.tbl.setItem(i, c, it)
        self.lbl_tip.setText(f"共 {len(drops)} 个关卡有样本，按「每理智」排序显示前 60 个")

    # ---------------- 同步 ----------------
    def do_sync(self):
        if self.busy:
            return
        self.busy = True
        self.btn_sync.setEnabled(False)
        self.lbl_state.setText("正在更新…（约 10–30 秒）")

        def work():
            try:
                res = penguin.run_sync(force=False, log=lambda m: None)
                msg = "已更新到最新数据" if res.get("changed") else "当前已是最新数据"
            except Exception as e:
                msg = f"更新失败：{type(e).__name__}"
            try:
                self.bridge.done.emit(msg)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _on_synced(self, msg):
        self.busy = False
        self.btn_sync.setEnabled(True)
        self.lbl_state.setText(msg)
        cur = self.current
        self.reload()
        if cur:
            self.show_item(cur)
