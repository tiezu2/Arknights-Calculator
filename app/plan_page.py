# -*- coding: utf-8 -*-
"""刷图计划页：三种模式（省理智 / 最快 / 礼包凭证）+ 每材料候选方案。"""
import json
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                               QTextEdit, QVBoxLayout, QWidget)

from planner import Planner, MODE_NORMAL, MODE_FAST, MODE_BUY

MODE_LABEL = {MODE_NORMAL: "正常（省理智）", MODE_FAST: "最快（少次数）", MODE_BUY: "礼包 / 凭证"}
MODE_TIP = {
    MODE_NORMAL: "每个材料取「直刷 / 合成」里理智最少的方式",
    MODE_FAST: "取刷取次数最少的方式（合成按原料刷图次数算），理智可能略高",
    MODE_BUY: "优先用已购礼包与凭证兑换，剩下的再刷（需在 data/purchase.json 配置）",
}
COLOR = {"直接刷": "#4aa8e0", "合成": "#f2c14e", "凭证兑换": "#b07fe0",
         "礼包抵扣": "#7fb069", "farm": "#4aa8e0", "已够": "#7fb069",
         "已包含": "#7c8f9e", "不可获取": "#e5484d"}


class PlanPage(QWidget):
    def __init__(self, db_path=None, calc=None, icons_dir=None, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.calc = calc
        self.mode = MODE_NORMAL
        self.uid = None
        self.evt = "open"
        self.result = None
        self.planner = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 顶部：模式 + 操作
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 10, 14, 8)
        bl.setSpacing(8)
        self.mode_btns = {}
        for m in (MODE_NORMAL, MODE_FAST, MODE_BUY):
            b = QPushButton(MODE_LABEL[m])
            b.setCheckable(True)
            b.setChecked(m == self.mode)
            b.setToolTip(MODE_TIP[m])
            b.clicked.connect(lambda _=False, mm=m: self.set_mode(mm))
            bl.addWidget(b)
            self.mode_btns[m] = b
        bl.addSpacing(10)
        self.lbl_op = QLabel("养成目标")
        self.lbl_op.setObjectName("muted")
        bl.addWidget(self.lbl_op)
        self.cmb_op = QComboBox()
        self.cmb_op.setMinimumWidth(200)
        self.cmb_op.currentIndexChanged.connect(self._on_op_change)
        bl.addWidget(self.cmb_op)
        bl.addSpacing(10)
        self.lbl_evt = QLabel("活动关")
        self.lbl_evt.setObjectName("muted")
        bl.addWidget(self.lbl_evt)
        self.cmb_evt = QComboBox()
        for label, val in (("不含活动关", "none"), ("当期开放", "open"),
                           ("当期 + 近 14 天", "recent"), ("全部活动（含已关）", "all")):
            self.cmb_evt.addItem(label, val)
        self.cmb_evt.setCurrentIndex(1)
        self.cmb_evt.setToolTip("当期开放：只算正在开放的活动关；近 14 天：包含刚结束的；全部：含历史活动（仅供对比）")
        self.cmb_evt.currentIndexChanged.connect(self._on_evt_change)
        bl.addWidget(self.cmb_evt)
        bl.addStretch(1)
        self.btn_reload = QPushButton("重新计算")
        self.btn_reload.clicked.connect(self.refresh)
        self.btn_copy = QPushButton("复制清单")
        self.btn_copy.clicked.connect(self.copy_plan)
        bl.addWidget(self.btn_reload)
        bl.addWidget(self.btn_copy)
        lay.addWidget(bar)

        self.lbl_state = QLabel("基于当前培养表计算中…")
        self.lbl_state.setObjectName("muted")
        self.lbl_state.setContentsMargins(16, 0, 14, 6)
        self.lbl_state.setWordWrap(True)
        lay.addWidget(self.lbl_state)

        # 主表：材料 → 方案
        self.tbl = QTableWidget(0, 8)
        self.tbl.setHorizontalHeaderLabels(
            ["材料", "需", "存", "缺", "采用方式", "单位理智", "次数", "小计理智"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 8):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.tbl.itemSelectionChanged.connect(self._on_select)
        lay.addWidget(self.tbl, 3)

        # 候选方案区
        self.lbl_opts = QLabel("选中上方材料可查看候选方案（直刷各关 / 合成 / 凭证 / 礼包）")
        self.lbl_opts.setObjectName("muted")
        self.lbl_opts.setContentsMargins(16, 8, 14, 0)
        lay.addWidget(self.lbl_opts)
        self.txt_opts = QTextEdit()
        self.txt_opts.setReadOnly(True)
        self.txt_opts.setMinimumHeight(150)
        self.txt_opts.setStyleSheet("QTextEdit{background:#0a1116;border:1px solid #223140;"
                                    "color:#b8cbd8;font-family:Consolas;font-size:12px;}")
        lay.addWidget(self.txt_opts, 2)

        self.lbl_total = QLabel("")
        self.lbl_total.setStyleSheet("color:#cfe6f2;font-weight:700;padding:8px 16px;"
                                     "background:rgba(12,195,231,0.08);")
        lay.addWidget(self.lbl_total)

        self.set_mode(MODE_NORMAL, refresh=False)
        self.refresh()

    # ---------------- 交互 ----------------
    def set_mode(self, mode, refresh=True):
        self.mode = mode
        for m, b in self.mode_btns.items():
            on = (m == mode)
            b.setChecked(on)
            b.setStyleSheet(
                "QPushButton{background:%s;border:1px solid %s;color:%s;font-weight:700;padding:6px 14px;}"
                % ("#0cc3e7", "#0cc3e7", "#04131a") if on else
                "QPushButton{background:transparent;border:1px solid #223140;color:#7c8f9e;padding:6px 14px;}")
        if refresh:
            self.refresh()

    def refresh(self):
        try:
            if self.planner is None:
                self.planner = Planner(self.db_path, calc=self.calc)
            self.planner.load()
            self._fill_operators()
            self.result = self.planner.plan(mode=self.mode, uid=self.uid,
                                            include_events=self.evt, include_rerun=True)
        except Exception as e:
            self.lbl_state.setText(f"计算失败：{e}")
            return
        r = self.result
        rows = r["rows"]
        keep_row = self.tbl.currentRow()
        self.tbl.setRowCount(len(rows))
        for i, row in enumerate(rows):
            chosen = row["chosen"] or {}
            mode_txt = row["mode"]
            if chosen.get("event"):
                mode_txt += "（复刻）" if chosen.get("rerun") else "（活动）"
            vals = [row["name"], str(row["need"]), str(row["stock"]), str(row["miss"]),
                    mode_txt,
                    (("%.4f" % row["unit"]) if (row["unit"] or 0) < 1 else ("%.2f" % row["unit"]))
                    if row.get("unit") is not None and row["mode"] not in ("已够", "已包含") else "—",
                    str((row["chosen"] or {}).get("runs", "—")),
                    "%.0f" % row["subtotal"]]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c >= 1:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 4:
                    it.setForeground(QColor(COLOR.get(v, "#d7e3ec")))
                self.tbl.setItem(i, c, it)

        # 状态
        try:
            ev = self.planner.event_summary() if self.planner else {"open": [], "recent": []}
        except Exception:
            ev = {"open": [], "recent": []}
        md = r["missing_data"]
        op_name = self._op_label()
        tip = (f"{op_name}：{len(rows)} 种材料 · 缺 {sum(1 for x in rows if x['miss']>0)} 种 · "
               f"模式「{MODE_LABEL[self.mode]}」")
        if not r["has_drop_data"]:
            tip += "  ⚠ 掉落数据还没同步（去「掉落查询」页点刷新）"
        if md:
            tip += f"  ⚠ 无获取途径：{'、'.join(md[:5])}"
        if self.evt == "open":
            if ev["open"]:
                tip += "  ● 活动中：" + "、".join(f"{x['name']}（{x['close']} 结束）" for x in ev["open"][:2])
            elif ev["recent"]:
                tip += f"  ● 当前无开放活动（最近：{ev['recent'][0]['name']} {ev['recent'][0]['close']} 结束）"
        elif self.evt == "recent" and ev["recent"]:
            tip += "  ● 含近期活动：" + "、".join(x["name"] for x in ev["recent"][:2])
        self.lbl_state.setText(tip)

        # 总计
        self.lbl_total.setText(
            f"合计 {r['total']:,.0f} 理智　|　刷图 {r['runs_total']:.0f} 次　|　"
            f"合成 {r['synth_total']:,.0f} + 刷图 {r['farm_total']:,.0f}　|　"
            f"约 {r['days']:.1f} 天（240 理智/天）")
        if 0 <= keep_row < len(rows):
            self.tbl.selectRow(keep_row)
        else:
            self.txt_opts.setPlainText("选中上方材料可查看候选方案")
            self._summary_stages()

    def _fill_operators(self):
        ops = self.planner.operators() if self.planner else []
        want = self.uid
        self.cmb_op.blockSignals(True)
        self.cmb_op.clear()
        self.cmb_op.addItem("全部（所有干员合计）", None)
        for o in ops:
            self.cmb_op.addItem(f"{o['name']}（{o['count']} 项）", o["uid"])
        idx = 0
        for i in range(self.cmb_op.count()):
            if self.cmb_op.itemData(i) == want:
                idx = i
                break
        self.cmb_op.setCurrentIndex(idx)
        self.uid = self.cmb_op.itemData(idx)
        self.cmb_op.blockSignals(False)

    def _op_label(self):
        i = self.cmb_op.currentIndex() if hasattr(self, "cmb_op") else 0
        return self.cmb_op.itemText(i) if i >= 0 else "全部"

    def _on_evt_change(self, idx):
        self.evt = self.cmb_evt.itemData(idx) or "open"
        self.refresh()

    def _on_op_change(self, idx):
        self.uid = self.cmb_op.itemData(idx)
        self.refresh()

    def _summary_stages(self):
        stages = self.result["stages"] if self.result else []
        if not stages:
            return
        lines = ["刷图清单（按理智排序）", ""]
        for s in stages:
            names = "、".join(s["items"][:4])
            tag = ""
            if s.get("event"):
                tag = ("  【复刻·" if s.get("rerun") else "  【活动·") + (s.get("until") or "?") + " 结束】"
            lines.append(f"  {s['stage']:<10} {s['ap']:>3} 理智/次   ×{s['runs']:<7.1f} "
                         f"= {s['ap_total']:>8.0f} 理智   {names}{tag}")
        lines.append("")
        lines.append("提示：选中上方某一行，可查看该材料的全部候选方案（直刷各关 / 合成 / 凭证 / 礼包）")
        self.txt_opts.setPlainText("\n".join(lines))

    def _on_select(self):
        i = self.tbl.currentRow()
        if i < 0 or not self.result:
            return
        row = self.result["rows"][i]
        self.lbl_opts.setText(f"{row['name']}　缺 {row['miss']}　候选方案 {len(row['options'])} 个")
        lines = []
        for k, o in enumerate(row["options"], 1):
            head = f"[{k}] {o['type']:<6} "
            if o["type"] == "direct":
                tag = ""
                if o.get("event"):
                    tag = ("  [复刻]" if o.get("rerun") else "  [活动]") + (f" {o['until']} 结束" if o.get("until") else "")
                lines.append(head + f"{o['stage']:<8} 掉率 {o['rate']:.3f}/次 · {o['ap']} 理智/次 · "
                                    f"{o['ap_item']} 理智/个 · 需 {o['runs']:.0f} 次 · 样本 {o['times']:,}{tag}")
            elif o["type"] == "synth":
                lines.append(head + f"合成 {o['ap_item']} 理智/个 · 共 {o['sanity']:,} 理智")
                for p in o.get("parts") or []:
                    lines.append(f"        ├ {p['name']:<12} ×{p['qty']:<3} 来源 {p['from']:<10} ≈ {p['unit']}")
            elif o["type"] == "buy":
                lines.append(head + o.get("note", ""))
            elif o["type"] == "pack":
                lines.append(head + o.get("note", ""))
            else:
                lines.append(head + o.get("note", ""))
        chosen = row["chosen"]
        if chosen:
            lines.insert(0, f"当前采用：{row['mode']}（候选 {chosen['id']}）")
        self.txt_opts.setPlainText("\n".join(lines))

    def copy_plan(self):
        if not self.result:
            return
        lines = [f"刷图计划 · {self._op_label()} · {MODE_LABEL[self.mode]}"]
        for row in self.result["rows"]:
            if row["miss"] <= 0:
                continue
            lines.append(f"{row['name']}\t缺{row['miss']}\t{row['mode']}\t{row['subtotal']:.0f}理智")
        for s in self.result["stages"]:
            lines.append(f"刷 {s['stage']}\t{s['runs']:.0f}次\t{s['ap_total']:.0f}理智")
        lines.append(f"合计 {self.result['total']:.0f} 理智")
        text = "\n".join(lines)
        try:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
            self.lbl_state.setText("已复制刷图清单到剪贴板")
        except Exception:
            self.txt_opts.setPlainText(text)
