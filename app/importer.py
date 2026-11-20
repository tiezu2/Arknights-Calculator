# -*- coding: utf-8 -*-
"""MAA / 通用格式 导入：库存（材料数量）与干员列表。

支持：
- JSON：MAA 仓库识别、{"items": {...}}、{材料名: 数量}、[{"itemId":..,"count":..}] 等
  任意嵌套结构都会递归扫描「名字或 id → 数字」的配对
- CSV / TXT：每行 `名称,数量` / `id,数量` / `名称<TAB>数量`，忽略 # 注释行
- 直接粘贴文本，同样解析

干员：识别 char_xxx id 或干员中文名，映射到本地库 uid。
"""
import csv
import io
import json
import os
import re
import sqlite3

if getattr(__import__("sys"), "frozen", False):
    import sys as _sys
    BASE = os.path.dirname(_sys.executable)
    _RES = getattr(_sys, "_MEIPASS", BASE)
else:
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _RES = BASE

_CANDS = [
    os.path.join(_RES, "data", "items_map.json"),
    os.path.join(BASE, "_src", "data", "items_map.json"),
    os.path.join(BASE, "data", "items_map.json"),
]
ITEMS_MAP = next((c for c in _CANDS if os.path.exists(c)), _CANDS[1])


def _norm(s):
    s = str(s).strip()
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("　", " ")
    s = re.sub(r"\s+", "", s)
    return s


class Importer:
    def __init__(self, db_path):
        self.db = db_path
        self.item_names = {}
        if os.path.exists(ITEMS_MAP):
            self.item_names = {k: v["name"] for k, v in
                               json.load(open(ITEMS_MAP, encoding="utf-8")).items()}
        con = sqlite3.connect(db_path)
        try:
            self.mat_by_name = {}
            for mid, name in con.execute("SELECT id, name FROM materials"):
                self.mat_by_name[_norm(name)] = mid
            self.mat_id_set = {r[0] for r in con.execute("SELECT id FROM materials")}
            self.op_by_name = {}
            self.op_uids = set()
            for uid, name in con.execute("SELECT uid, name FROM operators"):
                self.op_by_name[_norm(name)] = uid
                self.op_uids.add(uid)
        finally:
            con.close()
        # 常见别名
        self.alias = {
            "源石": None,  # 不是材料
            "lmd": "G-4-1", "龙门币": "G-4-1",
            "合成玉": None,
        }

    def mat_name(self, mid):
        for k, v in self.mat_by_name.items():
            if v == mid:
                return k
        return mid

    # ---------------- 材料 ----------------
    def resolve_material(self, key):
        """把一个 key（中文名 / 物品 id / MAA id）解析成本库材料 id"""
        k = _norm(key)
        if k in self.mat_by_name:
            return self.mat_by_name[k]
        # 物品 id → 名称 → 材料
        if str(key).strip() in self.item_names:
            nm = _norm(self.item_names[str(key).strip()])
            if nm in self.mat_by_name:
                return self.mat_by_name[nm]
        # MAA / ArkPlanner 常用 id（3001 等）
        if str(key).strip().isdigit():
            nm = self.item_names.get(str(int(str(key).strip())))
            if nm and _norm(nm) in self.mat_by_name:
                return self.mat_by_name[_norm(nm)]
        low = k.lower()
        if low in self.alias and self.alias[low]:
            return self.alias[low]
        return None

    def _walk_pairs(self, obj, out):
        """递归找 名字/id → 数字 的配对"""
        if isinstance(obj, dict):
            # 形如 {"itemId": "3001", "count": 12}
            # key 统一小写比较（MAA 用 itemId/count 驼峰）
            low = {}
            for k in obj:
                low.setdefault(_norm(k).lower(), k)
            cand_id = None
            for k in ("itemid", "item_id", "id", "materialid", "material_id", "name", "item", "charid", "char_id"):
                kk = low.get(k)
                if kk is not None and isinstance(obj[kk], str):
                    cand_id = obj[kk]
                    break
            if cand_id:
                for ck in ("count", "quantity", "num", "number", "qty", "amount", "value", "have", "cnt"):
                    kk = low.get(ck)
                    if kk is not None and isinstance(obj[kk], (int, float)) and not isinstance(obj[kk], bool):
                        out.append((cand_id, int(obj[kk])))
                        return
                    if kk is not None and isinstance(obj[kk], str) and obj[kk].strip().isdigit():
                        out.append((cand_id, int(obj[kk].strip())))
                        return
            for k, v in obj.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    out.append((k, int(v)))
                elif isinstance(v, str) and v.strip().isdigit():
                    out.append((k, int(v)))
                else:
                    self._walk_pairs(v, out)
        elif isinstance(obj, list):
            for v in obj:
                self._walk_pairs(v, out)

    def parse_inventory_text(self, text):
        text = (text or "").strip()
        if not text:
            return {}, []
        # JSON?
        if text[0] in "{[":
            try:
                obj = json.loads(text)
                pairs = []
                self._walk_pairs(obj, pairs)
                return self._pairs_to_inventory(pairs)
            except Exception:
                pass
        # 文本 / CSV
        pairs = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # 行内是 JSON（混在文本里也给解析）
            if line[0] in "{[":
                try:
                    self._walk_pairs(json.loads(line), pairs)
                    continue
                except Exception:
                    pass
            parts = re.split(r"[,\t;:|]+", line)
            if len(parts) < 2:
                continue
            name = parts[0].strip().strip('"')
            num = None
            for p in parts[1:]:
                p = p.strip().strip('"')
                if p.lstrip("-").replace(",", "").isdigit():
                    num = int(p.replace(",", ""))
                    break
            if name and num is not None:
                pairs.append((name, num))
        return self._pairs_to_inventory(pairs)

    def _pairs_to_inventory(self, pairs):
        inv, unknown = {}, []
        for key, qty in pairs:
            mid = self.resolve_material(key)
            if not mid:
                if str(key).strip():
                    unknown.append(str(key))
                continue
            inv[mid] = inv.get(mid, 0) + int(qty)
        return inv, unknown

    # ---------------- 干员 ----------------
    def parse_operators_json(self, obj):
        """解析 MAA 干员练度数组：[{id,name,elite,level,own,...}]"""
        uids, unknown, levels = [], [], {}
        if isinstance(obj, list):
            for it in obj:
                if not isinstance(it, dict):
                    continue
                uid = it.get("id") or it.get("charId") or ""
                if not isinstance(uid, str):
                    continue
                own = it.get("own")
                if own is False:
                    continue          # 未拥有，跳过
                if uid not in self.op_uids:
                    nm = it.get("name")
                    if nm and _norm(nm) in self.op_by_name:
                        uid = self.op_by_name[_norm(nm)]
                    else:
                        unknown.append(it.get("name") or uid)
                        continue
                if uid not in uids:
                    uids.append(uid)
                # 技能：skills / skillLevels / skills[].specializeLevel
                skills = []
                raw_sk = it.get("skills") or it.get("skillLevels") or []
                if isinstance(raw_sk, list):
                    for sk in raw_sk:
                        if isinstance(sk, dict):
                            lv = sk.get("level") or sk.get("skillLevel") or 1
                            spec = sk.get("specializeLevel", sk.get("mastery", 0)) or 0
                            skills.append({"level": int(lv), "spec": int(spec),
                                           "id": sk.get("skillId") or sk.get("id") or ""})
                        elif isinstance(sk, (int, float)):
                            skills.append({"level": int(sk), "spec": 0, "id": ""})
                elif isinstance(raw_sk, dict):
                    for k, v in raw_sk.items():
                        if isinstance(v, (int, float)):
                            skills.append({"level": int(v), "spec": 0, "id": str(k)})
                # 模组：modules / equips / equipment[].level
                modules = []
                raw_md = it.get("modules") or it.get("equips") or it.get("equipment") or []
                if isinstance(raw_md, list):
                    for md in raw_md:
                        if isinstance(md, dict):
                            modules.append(int(md.get("level") or md.get("stage") or 0))
                        elif isinstance(md, (int, float)):
                            modules.append(int(md))
                elif isinstance(raw_md, dict):
                    for k, v in raw_md.items():
                        if isinstance(v, (int, float)):
                            modules.append(int(v))
                levels[uid] = {
                    "elite": int(it.get("elite") or it.get("evolvePhase") or 0),
                    "level": int(it.get("level") or 0),
                    "potential": int(it.get("potential") or 0),
                    "skills": skills,
                    "modules": modules,
                }
        return uids, unknown, levels

    def parse_operators_text(self, text):
        text = (text or "").strip()
        if not text:
            return [], []
        uids, unknown = [], []
        found = set()

        def add(uid):
            if uid and uid not in found:
                found.add(uid)
                uids.append(uid)

        if text[0] in "{[":
            try:
                obj = json.loads(text)
                u2, un2, lv2 = self.parse_operators_json(obj)
                if u2:
                    self.pending_levels = lv2
                    return u2, un2
                self._walk_ops(obj, add, unknown)
                return uids, unknown
            except Exception:
                pass
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            tok = re.split(r"[,\t;:|]+", line)[0].strip().strip('"')
            if tok.lower().startswith("char_") and tok in self.op_uids:
                add(tok)
                continue
            nm = _norm(tok)
            if nm in self.op_by_name:
                add(self.op_by_name[nm])
            elif nm:
                unknown.append(tok)
        return uids, unknown

    def _walk_ops(self, obj, add, unknown, depth=0):
        if depth > 8:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                ks = str(k)
                if ks.lower().startswith("char_") and ks in self.op_uids:
                    add(ks)
                    continue
                nm = _norm(ks)
                if nm in self.op_by_name and (isinstance(v, (dict, int, float, bool)) or v):
                    add(self.op_by_name[nm])
                    continue
                self._walk_ops(v, add, unknown, depth + 1)
        elif isinstance(obj, list):
            for v in obj:
                self._walk_ops(v, add, unknown, depth + 1)
        elif isinstance(obj, str):
            s = obj.strip()
            if s.lower().startswith("char_") and s in self.op_uids:
                add(s)
            elif _norm(s) in self.op_by_name:
                add(self.op_by_name[_norm(s)])

    # ---------------- 写库 ----------------
    def apply_inventory(self, inv):
        con = sqlite3.connect(self.db)
        try:
            for mid, qty in inv.items():
                if qty <= 0:
                    con.execute("DELETE FROM inventory WHERE material_id=?", (mid,))
                else:
                    con.execute("INSERT INTO inventory(material_id,quantity) VALUES(?,?) "
                                "ON CONFLICT(material_id) DO UPDATE SET quantity=excluded.quantity",
                                (mid, int(qty)))
            con.commit()
        finally:
            con.close()
        return len(inv)

    def _ensure_owned(self, con):
        con.execute("CREATE TABLE IF NOT EXISTS owned "
                    "(uid TEXT PRIMARY KEY, elite INTEGER DEFAULT 0, level INTEGER DEFAULT 0)")
        cols = [r[1] for r in con.execute("PRAGMA table_info(owned)")]
        for col, ddl in [("elite", "ALTER TABLE owned ADD COLUMN elite INTEGER DEFAULT 0"),
                         ("level", "ALTER TABLE owned ADD COLUMN level INTEGER DEFAULT 0"),
                         ("potential", "ALTER TABLE owned ADD COLUMN potential INTEGER DEFAULT 0"),
                         ("skills", "ALTER TABLE owned ADD COLUMN skills TEXT DEFAULT ''"),
                         ("modules", "ALTER TABLE owned ADD COLUMN modules TEXT DEFAULT ''")]:
            if col not in cols:
                con.execute(ddl)

    def apply_operators(self, uids):
        levels = getattr(self, "pending_levels", {}) or {}
        con = sqlite3.connect(self.db)
        try:
            self._ensure_owned(con)
            con.execute("DELETE FROM owned")
            for u in uids:
                info = levels.get(u) or {}
                con.execute("INSERT OR REPLACE INTO owned"
                            "(uid, elite, level, potential, skills, modules) VALUES(?,?,?,?,?,?)",
                            (u, int(info.get("elite") or 0), int(info.get("level") or 0),
                             int(info.get("potential") or 0),
                             json.dumps(info.get("skills") or [], ensure_ascii=False),
                             json.dumps(info.get("modules") or [], ensure_ascii=False)))
            con.commit()
        finally:
            con.close()
        return len(uids)

    def owned_levels(self):
        """uid -> {elite, level, potential, skills, modules}"""
        con = sqlite3.connect(self.db)
        try:
            self._ensure_owned(con)
            out = {}
            for r in con.execute("SELECT uid, elite, level, potential, skills, modules FROM owned"):
                try:
                    sk = json.loads(r[4] or "[]")
                except Exception:
                    sk = []
                try:
                    md = json.loads(r[5] or "[]")
                except Exception:
                    md = []
                out[r[0]] = {"elite": r[1] or 0, "level": r[2] or 0,
                             "potential": r[3] or 0, "skills": sk, "modules": md}
            return out
        finally:
            con.close()

    def owned_uids(self):
        con = sqlite3.connect(self.db)
        try:
            con.execute("CREATE TABLE IF NOT EXISTS owned (uid TEXT PRIMARY KEY)")
            return [r[0] for r in con.execute("SELECT uid FROM owned")]
        finally:
            con.close()

    def clear_owned(self):
        con = sqlite3.connect(self.db)
        try:
            con.execute("CREATE TABLE IF NOT EXISTS owned (uid TEXT PRIMARY KEY)")
            con.execute("DELETE FROM owned")
            con.commit()
        finally:
            con.close()
