# -*- coding: utf-8 -*-
"""计算核心：从站点 bundle 抠出并移植的算法。

算法来源（cn.ark-nights.com, V2.23.20 bundle）：
  模块 2lXy.a  = levelCost(rarity, phase, cur, target)
  模块 v1ni    = { maxLevel, upgradeExpRequirement, upgradeCoinRequirement }
  模块 Ovxt    = { f:龙门币, b:经验值, c:[作战记录(2000/1000/400/200)] }
  干员对象     = { elites[].materials, skills[].materials,
                   master_skills[].upgrades[].materials, equipments[][]materials,
                   meta.max_elite_rank / max_master_skills / max_equipments }
"""
import json
import math
import sqlite3

LEVEL_ELITE_0 = "LEVEL_ELITE_0"
LEVEL_ELITE_1 = "LEVEL_ELITE_1"
LEVEL_ELITE_2 = "LEVEL_ELITE_2"
ELITE_RANK = "ELITE_RANK"
SKILL_LEVEL = "SKILL_LEVEL"
MASTER = ["MASTER_SKILL_1", "MASTER_SKILL_2", "MASTER_SKILL_3"]
EQUIP = ["ADVANCED_EQUIPMENT_1", "ADVANCED_EQUIPMENT_2", "ADVANCED_EQUIPMENT_3"]

ATTR_CN = {
    LEVEL_ELITE_0: "精0等级", LEVEL_ELITE_1: "精1等级", LEVEL_ELITE_2: "精2等级",
    ELITE_RANK: "精英阶段", SKILL_LEVEL: "技能等级",
    "MASTER_SKILL_1": "技能1专精", "MASTER_SKILL_2": "技能2专精", "MASTER_SKILL_3": "技能3专精",
    "ADVANCED_EQUIPMENT_1": "模组1", "ADVANCED_EQUIPMENT_2": "模组2", "ADVANCED_EQUIPMENT_3": "模组3",
}


class Calc:
    def __init__(self, db_path):
        self.db = db_path
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        meta = dict(cur.execute("SELECT k, v FROM meta"))
        self.tables = json.loads(meta["levelTables"])
        self.ovxt = json.loads(meta["ovxt"])
        self.materials = {}
        for mid, name, tier, typ, val, formula, sort_id in cur.execute(
                "SELECT id, name, tier, type, value, formula, sort_id FROM materials"):
            self.materials[mid] = {
                "id": mid, "name": name, "tier": tier, "type": typ,
                "value": val, "formula": json.loads(formula or "{}"), "sort_id": sort_id or 0,
            }
        con.close()

    # ---------------- 等级成本（2lXy 移植） ----------------
    def level_cost(self, rarity, phase, cur, target):
        """rarity: 0..5（0=1星）, phase: 0/1/2, cur/target: 等级"""
        out = []
        if cur == target:
            return out
        coin_tab = self.tables["upgradeCoinRequirement"][phase]
        exp_tab = self.tables["upgradeExpRequirement"][phase]

        def val(arr, idx):
            if idx < 0 or idx >= len(arr):
                return 0
            v = arr[idx]
            return v if isinstance(v, (int, float)) and v > 0 else 0

        coin = 0
        exp = 0
        i = cur - 1
        n = 0
        while i < target - 1 and n < 90:
            coin += val(coin_tab, i)
            exp += val(exp_tab, i)
            i += 1
            n += 1

        if coin:
            out.append((self.ovxt["coinId"], coin))
        if exp > 0:
            t = 200 * math.ceil(exp / 200)
            for rec in self.ovxt["records"]:
                qty = 0
                while t >= rec["value"]:
                    qty += 1
                    t -= rec["value"]
                if qty:
                    out.append((rec["id"], qty))
            out.append((self.ovxt["expId"], exp))
        return out

    # ---------------- 干员 / 属性 ----------------
    def operator(self, uid):
        con = sqlite3.connect(self.db)
        cur = con.cursor()
        row = cur.execute(
            "SELECT uid,name,pinyin,profession,rarity,max_elite,max_master,max_equip,skill_names FROM operators WHERE uid=?",
            (uid,)).fetchone()
        if not row:
            con.close()
            return None
        op = {
            "uid": row[0], "name": row[1], "pinyin": row[2], "profession": row[3],
            "rarity": row[4], "max_elite": row[5], "max_master": row[6], "max_equip": row[7],
            "skill_names": json.loads(row[8] or "[]"),
        }
        op["elites"] = [{"rank": r, "materials": json.loads(m)}
                        for r, m in cur.execute("SELECT rank, materials FROM op_elites WHERE uid=? ORDER BY rank", (uid,))]
        op["skills"] = [{"level": l, "materials": json.loads(m)}
                        for l, m in cur.execute("SELECT level, materials FROM op_skills WHERE uid=? ORDER BY level", (uid,))]
        op["master_skills"] = []
        for slot in range(3):
            ups = [{"level": l, "materials": json.loads(m), "name": n}
                   for l, n, m in cur.execute(
                       "SELECT level, skill_name, materials FROM op_master WHERE uid=? AND slot=? ORDER BY level", (uid, slot))]
            if ups:
                op["master_skills"].append({"slot": slot, "name": ups[0]["name"] or "", "upgrades": ups})
        op["equipments"] = []
        for slot in range(3):
            items = [{"level": l, "equipment_id": eid, "code": code, "materials": json.loads(m)}
                     for l, eid, code, m in cur.execute(
                         "SELECT level, equipment_id, code, materials FROM op_equip WHERE uid=? AND slot=? ORDER BY level", (uid, slot))]
            op["equipments"].append(items)
        con.close()
        return op

    def attributes(self, op):
        """返回该干员可选的属性及范围（复刻站点的可用性判断）"""
        attrs = []
        maxl = self.tables["maxLevel"][op["rarity"]]
        for phase, code in enumerate([LEVEL_ELITE_0, LEVEL_ELITE_1, LEVEL_ELITE_2]):
            if phase > op["max_elite"]:
                continue
            if phase < len(maxl) and maxl[phase]:
                lo = 1
                hi = maxl[phase]
                attrs.append({"code": code, "name": ATTR_CN[code], "min": lo, "max": hi,
                              "cur": lo, "target": hi, "t": "level"})
        if op["max_elite"] >= 1:
            attrs.append({"code": ELITE_RANK, "name": ATTR_CN[ELITE_RANK], "min": 0,
                          "max": op["max_elite"], "cur": 0, "target": op["max_elite"], "t": "rank"})
        if op["skills"]:
            attrs.append({"code": SKILL_LEVEL, "name": ATTR_CN[SKILL_LEVEL], "min": 1, "max": 7,
                          "cur": 1, "target": min(7, len(op["skills"]) + 1), "t": "skill"})
        for slot, code in enumerate(MASTER):
            if slot < op["max_master"]:
                attrs.append({"code": code, "name": ATTR_CN[code] + (f"（{op['skill_names'][slot]}）" if slot < len(op["skill_names"]) else ""),
                              "min": 0, "max": 3, "cur": 0, "target": 3, "t": "master"})
        for slot, code in enumerate(EQUIP):
            if slot < op["max_equip"] and op["equipments"][slot]:
                levels = len(op["equipments"][slot])
                attrs.append({"code": code, "name": ATTR_CN[code], "min": 0, "max": levels,
                              "cur": 0, "target": levels, "t": "equip"})
        return attrs

    # ---------------- 需求计算 ----------------
    def requirements(self, uid, attribute, cur, target):
        """返回 [(material_id, quantity)]，算法与站点一致"""
        op = self.operator(uid)
        if not op:
            return []
        cur = int(cur)
        target = int(target)
        out = []

        if cur >= target:
            return []

        if attribute in (LEVEL_ELITE_0, LEVEL_ELITE_1, LEVEL_ELITE_2):
            phase = {LEVEL_ELITE_0: 0, LEVEL_ELITE_1: 1, LEVEL_ELITE_2: 2}[attribute]
            out = self.level_cost(op["rarity"], phase, cur, target)
        elif attribute == ELITE_RANK:
            # rank 0→2 表示升到 2：每一步 cur+1 取 elites[cur]
            for step in range(cur, min(target, len(op["elites"]))):
                for m in op["elites"][step]["materials"]:
                    out.append((m["resource"], m["quantity"]))
        elif attribute == SKILL_LEVEL:
            # 技能 1→7：每一步取 skills[step-1]
            for step in range(cur, min(target, len(op["skills"]) + 1)):
                if 1 <= step <= len(op["skills"]):
                    for m in op["skills"][step - 1]["materials"]:
                        out.append((m["resource"], m["quantity"]))
        elif attribute in MASTER:
            slot = MASTER.index(attribute)
            if slot < len(op["master_skills"]):
                ups = op["master_skills"][slot]["upgrades"]
                for step in range(cur, min(target, len(ups))):
                    for m in ups[step]["materials"]:
                        out.append((m["resource"], m["quantity"]))
        elif attribute in EQUIP:
            slot = EQUIP.index(attribute)
            if slot < len(op["equipments"]):
                items = op["equipments"][slot]
                for step in range(cur, min(target, len(items))):
                    for m in items[step]["materials"]:
                        out.append((m["resource"], m["quantity"]))
        # 合并同名
        agg = {}
        for mid, q in out:
            agg[mid] = agg.get(mid, 0) + int(q)
        return sorted(agg.items(), key=lambda kv: self.materials.get(kv[0], {}).get("sort_id") or 999999)

    # ---------------- 表：合计 / 缺少 ----------------
    def table(self):
        con = sqlite3.connect(self.db)
        cur = con.cursor()
        plans = [dict(zip(["id", "uid", "attribute", "cur", "target", "hidden"],
                          r)) for r in cur.execute(
            "SELECT id, uid, attribute, cur, target, hidden FROM plans ORDER BY id")]
        inv = {mid: q for mid, q in cur.execute("SELECT material_id, quantity FROM inventory")}
        con.close()

        rows = []
        totals = {}
        for p in plans:
            op = self.operator(p["uid"])
            name = op["name"] if op else p["uid"]
            reqs = self.requirements(p["uid"], p["attribute"], p["cur"], p["target"])
            for mid, q in reqs:
                totals[mid] = totals.get(mid, 0) + q
            rows.append({**p, "operator_name": name,
                         "profession": (op or {}).get("profession"),
                         "rarity": (op or {}).get("rarity", 1),
                         "attr_name": ATTR_CN.get(p["attribute"], p["attribute"]),
                         "reqs": [{"id": mid, "name": self.materials.get(mid, {}).get("name", mid),
                                   "qty": q, "tier": self.materials.get(mid, {}).get("tier")} for mid, q in reqs]})

        items = self.summarize(plans, inv)
        return {"rows": rows, "items": items,
                "summary": {"plans": len(rows), "materials": len(items),
                            "missing_kinds": len([i for i in items if i["miss"] > 0])}}

    def inventory(self):
        con = sqlite3.connect(self.db)
        try:
            return {mid: qty for mid, qty in
                    con.execute("SELECT material_id, quantity FROM inventory")}
        finally:
            con.close()

    def summarize(self, rows, inv=None):
        """把若干计划行汇总成材料表（需/存/缺/可合成）"""
        if inv is None:
            inv = self.inventory()
        totals = {}
        for r in rows:
            for mid, q in self.requirements(r["uid"], r["attribute"], r["cur"], r["target"]):
                totals[mid] = totals.get(mid, 0) + q
        items = []
        for mid, q in sorted(totals.items(),
                             key=lambda kv: self.materials.get(kv[0], {}).get("sort_id") or 999999):
            m = self.materials.get(mid, {})
            stock = inv.get(mid, 0)
            miss = max(0, q - stock)
            craft = self.max_craftable(mid, inv) if (miss > 0 and m.get("formula")) else 0
            items.append({"id": mid, "name": m.get("name", mid), "tier": m.get("tier"),
                          "need": q, "stock": stock, "miss": miss, "craftable": craft,
                          "formula": m.get("formula") or {}})
        return items

    def max_craftable(self, mid, inv):
        """用库存能合成多少个该材料（递归，只看一级原料）"""
        m = self.materials.get(mid)
        if not m or not m.get("formula"):
            return 0
        best = None
        for rid, need in m["formula"].items():
            if need <= 0:
                continue
            have = inv.get(rid, 0)
            n = have // need
            best = n if best is None else min(best, n)
        return best or 0
