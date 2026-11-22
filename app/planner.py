# -*- coding: utf-8 -*-
"""刷图规划 v0.2：三种模式 + 多方案候选

候选方案（每个材料都会给出，供界面/AI 取舍）：
  direct  : 直接刷某个关卡（topN）
  synth   : 按配方合成（原料递归展开）
  buy     : 凭证商店兑换（价格来自 data/purchase.json，可留空）
  pack    : 已购礼包抵扣（内容来自 data/purchase.json）

三种模式（目标函数不同）：
  normal  : 省理智——min(直刷, 合成) 的理智
  fast    : 省次数/时间——min(刷图次数)，合成按「原料刷图次数之和 + 1 次加工」
  buy     : 先用礼包/凭证，剩余再 min 理智

配置 data/purchase.json：
{
  "originium_sanity": 135,                 # 1 源石 = 135 理智
  "credit_shop": {"固源岩组": 30},          # 材料名 -> 采购凭证价格
  "packs": [{"name": "新手礼包", "price_rmb": 6, "items": [{"name": "固源岩组", "qty": 5}]}]
}
"""
import json
import os
import sqlite3

LMD_ID = "G-4-1"
LMD_PER_AP = 10000 / 36.0
LMD2AP = 1.0 / LMD_PER_AP
EXP_PER_AP = 8000 / 36.0            # LS-6：高级作战记录 ×4 = 8000 exp / 36 理智
EXP2AP = 1.0 / EXP_PER_AP

PERM_PREFIX = ("main_", "sub_", "wk_", "pro_", "tough_")

# 货币类来源（不是掉落物品，按固定关卡产出折算）
CURRENCY_SOURCE = {
    "龙门币": {"stage": "CE-6", "ap": 36, "yield": 10000},
    "采购凭证": {"stage": "剿灭/任务", "ap": 0, "yield": 1},   # 免费资源（不占刷图理智）
}
# 经验值不单独规划：已经通过「作战记录」计算过了
EXP_MATERIAL = "经验值"
MIN_TIMES = 30
MAX_RATE = 50.0          # 单次掉落超过 50 个视为异常数据

MODE_NORMAL = "normal"
MODE_FAST = "fast"
MODE_BUY = "buy"


class Planner:
    def __init__(self, db_path=None, calc=None, cache_dir=None, config_path=None):
        self.db_path = db_path
        self.calc = calc
        self.cache_dir = cache_dir
        self.config_path = config_path
        self.materials = {}
        self.by_item = {}
        self.pid_by_name = {}
        self.config = {}
        self._synth_memo = {}
        self._direct_memo = {}
        self.load()

    # ---------------- 数据 ----------------
    def load(self):
        self._synth_memo = {}
        self._direct_memo = {}
        if self.calc is not None:
            self.materials = dict(self.calc.materials)
        elif self.db_path and os.path.exists(self.db_path):
            con = sqlite3.connect(self.db_path)
            try:
                for mid, nm, tier, typ, formula in con.execute(
                        "SELECT id,name,tier,type,formula FROM materials"):
                    self.materials[mid] = {"id": mid, "name": nm, "tier": tier, "type": typ,
                                           "formula": json.loads(formula or "{}")}
            finally:
                con.close()
        path = None
        if self.cache_dir:
            path = os.path.join(self.cache_dir, "drop_index.json")
        if not path or not os.path.exists(path):
            try:
                import penguin
                path = os.path.join(penguin.CACHE, "drop_index.json")
            except Exception:
                path = None
        if path and os.path.exists(path):
            try:
                data = json.load(open(path, encoding="utf-8"))
                self.by_item = data.get("by_item") or {}
                self.pid_by_name = {str(n).strip(): i for i, n in (data.get("item_name") or {}).items()}
            except Exception:
                pass
        self.config = self._load_config()

    def _load_config(self):
        cands = []
        if self.config_path:
            cands.append(self.config_path)
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cands.append(os.path.join(base, "data", "purchase.json"))
        for p in cands:
            if p and os.path.exists(p):
                try:
                    return json.load(open(p, encoding="utf-8"))
                except Exception:
                    pass
        return {}

    @property
    def has_drop_data(self):
        return bool(self.by_item)

    def name2mid(self, name):
        for mid, m in self.materials.items():
            if m.get("name") == name:
                return mid
        return None

    # ---------------- 掉落 ----------------
    def stages_of(self, name, min_times=MIN_TIMES, perm_only=True):
        pid = self.pid_by_name.get(name)
        if not pid:
            return []
        out, seen = [], set()
        for r in self.by_item.get(pid, []):
            times = r.get("times") or 0
            rate = r.get("rate") or 0
            ap = r.get("apCost") or 0
            if times < min_times or rate <= 0 or rate > MAX_RATE or ap <= 0:
                continue
            if perm_only and not str(r.get("stageId", "")).startswith(PERM_PREFIX):
                continue
            code = r.get("stage")
            if code in seen:          # 同名关卡（标准/磨难、多时间窗）只留最优
                continue
            seen.add(code)
            out.append({"stage": code, "stage_id": r.get("stageId"), "zone": r.get("zone"),
                        "ap": ap, "rate": rate, "times": times, "ap_item": ap / rate})
        out.sort(key=lambda x: x["ap_item"])
        return out

    def direct_best(self, name, **kw):
        key = (name, tuple(sorted(kw.items())))
        if key in self._direct_memo:
            return self._direct_memo[key]
        s = self.stages_of(name, **kw)
        best = s[0] if s else None
        self._direct_memo[key] = best
        return best

    # ---------------- 合成 ----------------
    def synth_cost(self, mid, depth=0):
        key = (mid, depth)
        if key in self._synth_memo:
            return self._synth_memo[key]
        if depth > 3:
            return None
        m = self.materials.get(mid) or {}
        formula = m.get("formula") or {}
        if not formula:
            return None
        total = 0.0
        for rid, qty in formula.items():
            if rid == LMD_ID:
                total += qty * LMD2AP
                continue
            rname = (self.materials.get(rid) or {}).get("name", rid)
            if rname == "采购凭证":          # 免费资源：剿灭/任务产出
                continue
            d = self.direct_best(rname)
            if d:
                total += qty * d["ap_item"]
                continue
            sub = self.synth_cost(rid, depth + 1)
            if sub is None:
                return None
            total += qty * sub
        self._synth_memo[key] = total
        return total

    def synth_parts(self, mid):
        m = self.materials.get(mid) or {}
        out = []
        for rid, qty in (m.get("formula") or {}).items():
            if rid == LMD_ID:
                out.append({"name": "龙门币", "qty": qty, "from": "CE-6 折算", "unit": qty * LMD2AP})
                continue
            rname = (self.materials.get(rid) or {}).get("name", rid)
            d = self.direct_best(rname)
            if d:
                out.append({"name": rname, "qty": qty, "from": d["stage"], "unit": qty * d["ap_item"]})
            else:
                sub = self.synth_cost(rid) or 0.0
                out.append({"name": rname, "qty": qty, "from": "合成", "unit": qty * sub})
        return out

    def synth_runs(self, mid, depth=0):
        """合成一件需要的刷图次数（原料递归累加）+ 1 次加工"""
        if depth > 3:
            return None
        m = self.materials.get(mid) or {}
        formula = m.get("formula") or {}
        if not formula:
            return None
        total = 1.0                      # 加工一次
        for rid, qty in formula.items():
            if rid == LMD_ID:
                continue                 # 龙门币不靠刷图（CE 关另算）
            rname = (self.materials.get(rid) or {}).get("name", rid)
            d = self.direct_best(rname)
            if d and d["rate"] > 0:
                total += qty / d["rate"] * 0.0 + 1.0    # 原料一关刷一次就够买 qty？简化：按 1 次算
            else:
                sub = self.synth_runs(rid, depth + 1)
                if sub:
                    total += sub
        return total

    # ---------------- 需求 ----------------
    def needs(self):
        if self.calc is None:
            return []
        tb = self.calc.table()
        return [{"id": it["id"], "name": it["name"], "tier": it.get("tier"),
                 "need": it["need"], "stock": it["stock"], "miss": it["miss"]} for it in tb["items"]]

    # ---------------- 候选方案 ----------------
    def options_for(self, name, mid, miss, topn=3):
        """返回该材料的全部候选方案（direct / synth / buy / pack）"""
        opts = []
        # 货币类（龙门币/采购凭证）：按固定关卡产出折算
        if name in CURRENCY_SOURCE:
            src = CURRENCY_SOURCE[name]
            per_ap = src["yield"] / src["ap"] if src["ap"] else 0
            opts.append({
                "id": f"c:{src['stage']}", "type": "farm", "stage": src["stage"],
                "ap": src["ap"], "rate": src["yield"], "times": 0,
                "ap_item": round(src["ap"] / src["yield"], 4) if src["yield"] else 0,
                "runs": round(miss / src["yield"]) if src["yield"] else 0,
                "sanity": round(miss / per_ap) if per_ap else 0,
                "time_min": round((miss / src["yield"]) * 1.5) if src["yield"] else 0,
                "note": f"{src['stage']}：{src['ap']} 理智换 {src['yield']:,}",
            })
            return opts
        # 直刷
        for s in self.stages_of(name)[:topn]:
            opts.append({
                "id": f"d:{s['stage']}", "type": "direct", "stage": s["stage"],
                "ap": s["ap"], "rate": s["rate"], "times": s["times"],
                "ap_item": round(s["ap_item"], 1),
                "runs": round(miss / s["rate"], 1),
                "sanity": round(s["ap_item"] * miss),
                "time_min": round(miss / s["rate"] * 1.5),      # 每关约 1.5 分钟
            })
        # 合成
        syn = self.synth_cost(mid) if mid else None
        if syn is not None:
            parts = self.synth_parts(mid)
            import math
            runs = 1                      # 加工一次
            for p in parts:
                if p["from"] in ("CE-6 折算", "合成"):
                    if p["from"] == "合成":
                        runs += 1
                    continue
                d2 = self.direct_best(p["name"])
                if d2 and d2["rate"] > 0 and p["qty"] > 0:
                    runs += math.ceil(miss * p["qty"] / d2["rate"])
            opts.append({
                "id": "s:synth", "type": "synth", "ap_item": round(syn, 1),
                "sanity": round(syn * miss), "runs": runs, "time_min": round(runs * 1.5),
                "parts": [{"name": p["name"], "qty": p["qty"], "from": p["from"],
                           "unit": round(p["unit"], 1)} for p in parts],
            })
        # 凭证商店（需要用户在配置里填 credit_amount > 0）
        price = (self.config.get("credit_shop") or {}).get(name)
        credit_have = int(self.config.get("credit_amount") or 0)
        if price and credit_have > 0:
            cover = min(miss, credit_have // price)
            opts.append({
                "id": "b:credit", "type": "buy", "currency": "采购凭证", "price": price,
                "unit_cost": price, "sanity": 0, "runs": 0, "time_min": 0,
                "cover": cover, "left": max(0, miss - cover),
                "note": f"{price} 采购凭证/个（可换 {cover} 个，剩 {max(0, miss - cover)} 个需刷）",
            })
        # 礼包
        for pk in self.config.get("packs") or []:
            for item in pk.get("items") or []:
                if item.get("name") == name and item.get("qty"):
                    cover = min(miss, item["qty"])
                    opts.append({
                        "id": f"p:{pk.get('name')}", "type": "pack", "pack": pk.get("name"),
                        "price_rmb": pk.get("price_rmb"), "cover": cover,
                        "sanity": 0, "runs": 0, "time_min": 0,
                        "note": f"{pk.get('name')} 覆盖 {cover} 个",
                    })
        return opts

    def _pick(self, opts, mode):
        if not opts:
            return None
        if mode in (MODE_NORMAL, MODE_FAST):
            opts = [o for o in opts if o["type"] not in ("buy", "pack")] or opts
        if mode == MODE_FAST:
            return min(opts, key=lambda o: (o["runs"], o["sanity"]))
        if mode == MODE_BUY:
            # 礼包/凭证能用就用，否则按理智最省
            free = [o for o in opts if o["type"] in ("pack", "buy")]
            if free:
                order = {"pack": 0, "buy": 1}
                return min(free, key=lambda o: (order.get(o["type"], 9), o.get("price_rmb") or 0))
            return min(opts, key=lambda o: (o["sanity"], o["runs"]))
        return min(opts, key=lambda o: (o["sanity"], o["runs"]))

    # ---------------- 规划 ----------------
    def plan(self, needs=None, mode=MODE_NORMAL):
        needs = self.needs() if needs is None else needs
        rows = []
        for n in needs:
            name, mid, miss = n["name"], n["id"], max(0, n["miss"])
            opts = self.options_for(name, mid, miss) if miss > 0 else []
            chosen = self._pick(opts, mode) if opts else None
            if name == EXP_MATERIAL:
                rows.append({**n, "options": [], "chosen": None, "mode": "已包含",
                             "unit": 0.0, "subtotal": 0})
                continue
            if miss <= 0:
                mode_one, unit = "已够", 0.0
            elif chosen:
                mode_one = {"direct": "直接刷", "synth": "合成", "buy": "凭证兑换",
                            "pack": "礼包抵扣", "farm": "固定关"}.get(chosen["type"], chosen["type"])
                unit = chosen.get("ap_item", 0) or 0
            else:
                mode_one, unit = "不可获取", None
            rows.append({
                **n, "options": opts, "chosen": chosen, "mode": mode_one,
                "unit": unit, "subtotal": (chosen or {}).get("sanity", 0),
            })

        # 汇总：刷图类按关卡合并（同关只算一次）
        stages = {}
        for r in rows:
            c = r["chosen"]
            if not c or c["type"] != "direct":
                continue
            st = c["stage"]
            rec = stages.setdefault(st, {"stage": st, "ap": c["ap"], "runs": 0.0,
                                         "ap_total": 0.0, "items": []})
            rec["runs"] = max(rec["runs"], c["runs"])
            rec["items"].append(r["name"])
        for rec in stages.values():
            rec["ap_total"] = rec["runs"] * rec["ap"]
        stage_list = sorted(stages.values(), key=lambda x: -x["ap_total"])

        synth_total = sum(r["subtotal"] for r in rows if r["chosen"] and r["chosen"]["type"] == "synth")
        farm_total = sum(s["ap_total"] for s in stage_list)
        total = synth_total + farm_total
        return {
            "mode": mode, "rows": rows, "stages": stage_list,
            "synth_total": synth_total, "farm_total": farm_total,
            "total": total, "days": total / 240.0 if total else 0.0,
            "runs_total": sum(s["runs"] for s in stage_list),
            "has_drop_data": self.has_drop_data,
            "missing_data": [r["name"] for r in rows if r["mode"] == "不可获取" and r["miss"] > 0],
        }

    def plan_all_modes(self, needs=None):
        return {m: self.plan(needs, m) for m in (MODE_NORMAL, MODE_FAST, MODE_BUY)}
