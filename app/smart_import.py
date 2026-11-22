# -*- coding: utf-8 -*-
"""智能导入：一条粘贴/一个文件，自动识别来源并同时导入「库存 + 干员练度」。

支持的来源：
1. penguin-statistics 仓库   {"@type":"@penguin-statistics/depot","items":[{"id":"4001","have":664000}]}
2. MAA 干员识别 JSON         [{"id":"char_002_amiya","name":"阿米娅","elite":2,"level":80,"own":true,...}]
3. MAA 干员识别 CSV/Markdown 表格（表头含 干员/精英/等级/技能/模组）
4. 森空岛 player/info JSON   {"chars":[{"charId":"char_002_amiya","level":80,"evolvePhase":2,
                              "skills":[{"id":"skchr_...","specializeLevel":3}],"equip":[{"level":1}]}]}
5. 纯文本 / CSV             "固源岩,30" / "char_002_amiya" / "阿米娅"
6. 上述任意混合（逐行）
"""
import io
import json
import os
import re
import sqlite3

from importer import Importer, _norm


def _split_table_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s.strip("|")
        return [c.strip() for c in s.split("|")]
    return [c.strip() for c in re.split(r"\t+|,{1,}", s)]


class SmartImporter:
    def __init__(self, db_path):
        self.base = Importer(db_path)
        self.db = db_path
        con = sqlite3.connect(db_path)
        try:
            self.op_uids = {r[0] for r in con.execute("SELECT uid FROM operators")}
            self.op_names = {_norm(r[1]): r[0] for r in con.execute("SELECT uid, name FROM operators")}
        finally:
            con.close()

    # ---------------- 对外 ----------------
    def parse(self, text):
        """返回 {'inventory': {mid:qty}, 'operators': [uid...], 'levels': {uid:{...}},
                 'unknown_mat': [...], 'unknown_op': [...], 'sources': [...]}"""
        out = {"inventory": {}, "operators": [], "levels": {},
               "unknown_mat": [], "unknown_op": [], "sources": []}
        text = (text or "").strip()
        self._last_header = None
        if not text:
            return out

        # 1) 整段 JSON
        obj = None
        if text[0] in "{[":
            try:
                obj = json.loads(text)
            except Exception:
                obj = None
        if obj is not None:
            self._from_json(obj, out)
            if out["inventory"] or out["operators"]:
                return out

        # 2) 逐行（JSON 行 / 表格行 / 键值行）
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line[0] in "{[":
                try:
                    self._from_json(json.loads(line), out)
                    continue
                except Exception:
                    pass
            self._from_table_line(line, out)

        self._dedupe(out)
        return out

    # ---------------- JSON ----------------
    def _from_json(self, obj, out):
        if isinstance(obj, dict):
            handled_depot = False
            # 森空岛 player/info
            if isinstance(obj.get("chars"), list) and obj.get("chars") and \
               isinstance(obj["chars"][0], dict) and ("charId" in obj["chars"][0] or "evolvePhase" in obj["chars"][0]):
                self._from_skland(obj, out)
                return
            # 仓库 {items:[{id,have}]} / {items:{id:qty}} / {名字: 数字}
            handled_depot = False
            if "items" in obj:
                self._walk_numbers(obj["items"], out)
                handled_depot = True
            if "depot" in obj:
                self._walk_numbers(obj["depot"], out)
                handled_depot = True
            if handled_depot and "penguin-statistics/仓库" not in out["sources"]:
                out["sources"].append("penguin-statistics/仓库")
            # 干员数组字段
            for key in ("chars", "operators", "box", "charList", "list"):
                if isinstance(obj.get(key), list) and obj[key] and isinstance(obj[key][0], dict):
                    self._from_operator_list(obj[key], out)
            if not handled_depot:
                self._walk_numbers(obj, out)
        elif isinstance(obj, list):
            if obj and isinstance(obj[0], dict) and any(
                    k in obj[0] for k in ("charId", "char_id", "evolvePhase", "elite", "level")):
                self._from_operator_list(obj, out)
            else:
                self._walk_numbers(obj, out)

    def _from_skland(self, obj, out):
        if "森空岛 player/info" not in out["sources"]:
            out["sources"].append("森空岛 player/info")
        for c in obj.get("chars") or []:
            uid = c.get("charId")
            if not uid:
                continue
            if uid not in self.op_uids:
                out["unknown_op"].append(uid)
                continue
            skills = []
            for s in (c.get("skills") or []):
                skills.append({"id": s.get("id"), "level": int(c.get("mainSkillLvl") or 1),
                               "spec": int(s.get("specializeLevel") or 0)})
            out["levels"][uid] = {
                "elite": int(c.get("evolvePhase") or 0),
                "level": int(c.get("level") or 0),
                "potential": int(c.get("potentialRank") or 0),
                "skills": skills,
                "modules": [int(e.get("level") or 0) for e in (c.get("equip") or [])],
            }
            if uid not in out["operators"]:
                out["operators"].append(uid)
        # 森空岛不提供仓库；不扫数字，避免 level/evolvePhase 被当成材料

    def _from_operator_list(self, arr, out):
        for it in arr:
            if not isinstance(it, dict):
                continue
            uid = it.get("id") or it.get("charId") or it.get("char_id") or ""
            name = it.get("name") or it.get("charName") or ""
            own = it.get("own")
            if own is False:
                continue
            if uid and uid in self.op_uids:
                pass
            elif name and _norm(name) in self.op_names:
                uid = self.op_names[_norm(name)]
            else:
                if name or uid:
                    out["unknown_op"].append(name or uid)
                continue
            if uid not in out["operators"]:
                out["operators"].append(uid)
            skills = []
            raw_sk = it.get("skills") or []
            if isinstance(raw_sk, list):
                for sk in raw_sk:
                    if isinstance(sk, dict):
                        skills.append({"id": sk.get("id") or sk.get("skillId"),
                                       "level": int(sk.get("level") or it.get("mainSkillLvl") or 1),
                                       "spec": int(sk.get("specializeLevel", sk.get("mastery", 0)) or 0)})
                    elif isinstance(sk, (int, float)):
                        skills.append({"id": None, "level": int(sk), "spec": 0})
            modules = []
            for key in ("modules", "equips", "equipment"):
                raw = it.get(key)
                if isinstance(raw, list):
                    for m in raw:
                        if isinstance(m, dict):
                            modules.append(int(m.get("level") or m.get("stage") or 0))
                        elif isinstance(m, (int, float)):
                            modules.append(int(m))
                    break
            elite = it.get("elite", it.get("evolvePhase", 0)) or 0
            level = it.get("level", 0) or 0
            if level or skills or modules:
                out["levels"][uid] = {"elite": int(elite), "level": int(level),
                                      "potential": int(it.get("potential") or 0),
                                      "skills": skills, "modules": modules}
        if "MAA/干员识别（列表）" not in out["sources"]:
            out["sources"].append("MAA/干员识别（列表）")

    def _walk_numbers(self, obj, out, ops_only=False, depth=0):
        """递归收 (材料 id/名 → 数字)"""
        if depth > 8:
            return
        if isinstance(obj, dict):
            low = {_norm(k).lower(): k for k in obj}
            cid = None
            for ck in ("itemid", "item_id", "id", "materialid", "material_id", "name", "item"):
                kk = low.get(ck)
                if kk is not None and isinstance(obj[kk], str):
                    cid = obj[kk]
                    break
            if cid:
                for qk in ("have", "count", "quantity", "num", "number", "qty", "amount", "value", "cnt"):
                    kk = low.get(qk)
                    if kk is not None and isinstance(obj[kk], (int, float)) and not isinstance(obj[kk], bool):
                        mid = self.base.resolve_material(cid)
                        if mid:
                            out["inventory"][mid] = out["inventory"].get(mid, 0) + int(obj[kk])
                        elif str(cid).strip():
                            out["unknown_mat"].append(str(cid))
                        return
            for k, v in obj.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    mid = self.base.resolve_material(k)
                    if mid:
                        out["inventory"][mid] = out["inventory"].get(mid, 0) + int(v)
                    elif str(k).strip() and not str(k).isdigit():
                        out["unknown_mat"].append(str(k))
                elif isinstance(v, str) and v.strip().isdigit():
                    mid = self.base.resolve_material(k)
                    if mid:
                        out["inventory"][mid] = out["inventory"].get(mid, 0) + int(v)
                else:
                    self._walk_numbers(v, out, ops_only, depth + 1)
        elif isinstance(obj, list):
            for v in obj:
                self._walk_numbers(v, out, ops_only, depth + 1)

    # ---------------- 表格 / 文本 ----------------
    def _from_table_line(self, line, out):
        cells = _split_table_row(line)
        if not cells:
            return
        low = [c.lower() for c in cells]
        # 表头行：识别列含义后跳过
        if any(c in ("干员", "精英", "等级", "潜能", "技能", "模组", "材料", "数量", "材料名") for c in cells):
            self._last_header = cells
            return
        header = getattr(self, "_last_header", None)

        # 干员行：第一列是 char_ id 或干员名
        first = cells[0]
        uid = None
        if first.lower().startswith("char_") and first in self.op_uids:
            uid = first
        elif _norm(first) in self.op_names:
            uid = self.op_names[_norm(first)]
        if uid:
            rec = {"elite": 0, "level": 0, "potential": 0, "skills": [], "modules": []}
            nums = [int(c) for c in cells[1:] if c.strip().isdigit()]
            if header:
                for h, c in zip(header, cells):
                    hn = _norm(h)
                    if not c.strip().isdigit():
                        continue
                    v = int(c)
                    if "精英" in hn or hn.lower() in ("elite", "evolvephase"):
                        rec["elite"] = v
                    elif "等级" in hn or hn.lower() in ("level", "lv"):
                        rec["level"] = v
                    elif "潜能" in hn or hn.lower() == "potential":
                        rec["potential"] = v
                    elif hn.startswith("专精") or "mastery" in hn.lower():
                        rec["skills"].append({"id": None, "level": 7, "spec": v})
                    elif "技能" in hn:
                        rec["skills"].append({"id": None, "level": v, "spec": 0})
                    elif "模组" in hn:
                        rec["modules"].append(v)
            elif len(nums) >= 2:
                rec["elite"], rec["level"] = nums[0], nums[1]
            out["levels"][uid] = rec
            if uid not in out["operators"]:
                out["operators"].append(uid)
            tag = "MAA/干员识别（表格）" if header else "干员名单（文本）"
            if tag not in out["sources"]:
                out["sources"].append(tag)
            return

        # 材料行：名称/数字 或 id/数量
        if len(cells) >= 2:
            mid = self.base.resolve_material(first)
            num = None
            for c in cells[1:]:
                cc = c.strip().replace(",", "")
                if cc.isdigit():
                    num = int(cc)
                    break
            if mid and num is not None:
                out["inventory"][mid] = out["inventory"].get(mid, 0) + num
                return
        # 单独一行干员名
        if _norm(first) in self.op_names:
            u = self.op_names[_norm(first)]
            if u not in out["operators"]:
                out["operators"].append(u)

    # ---------------- 去重 ----------------
    IGNORE_KEYS = {"level", "evolvephase", "potentialrank", "mainskilllvl", "specializelevel",
                   "rarity", "potential", "own", "skillid", "charid", "equip",
                   "skills", "modules", "equips", "equipment", "chars", "appcode", "type",
                   "status", "code", "message", "timestamp", "data", "profile", "building"}

    def _dedupe(self, out):
        out["unknown_mat"] = sorted({str(x) for x in out["unknown_mat"]
                                     if str(x).strip()
                                     and str(x).strip().lower() not in self.IGNORE_KEYS})[:30]
        out["unknown_op"] = sorted({str(x) for x in out["unknown_op"] if str(x).strip()})[:30]

    # ---------------- 写库 ----------------
    def apply(self, parsed):
        base = self.base
        if parsed["levels"]:
            base.pending_levels = {u: {"elite": v["elite"], "level": v["level"],
                                       "potential": v.get("potential", 0),
                                       "skills": v.get("skills", []),
                                       "modules": v.get("modules", [])}
                                   for u, v in parsed["levels"].items()}
            base.apply_operators(list(parsed["levels"].keys()))
        elif parsed["operators"]:
            base.apply_operators(parsed["operators"])
        if parsed["inventory"]:
            base.apply_inventory(parsed["inventory"])
        return {"inventory": len(parsed["inventory"]), "operators": len(parsed["levels"] or parsed["operators"])}
