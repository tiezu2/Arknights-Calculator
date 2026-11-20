# -*- coding: utf-8 -*-
"""把抓下来的 JSON 建成 SQLite 数据库。"""
import json
import os
import sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(BASE), "_src", "data")
DB = os.path.join(BASE, "arknights.db")

operators = json.load(open(os.path.join(SRC, "operators.json"), encoding="utf-8"))
materials = json.load(open(os.path.join(SRC, "allMaterials.json"), encoding="utf-8"))
tables = json.load(open(os.path.join(SRC, "levelTables.json"), encoding="utf-8"))
ovxt = json.load(open(os.path.join(SRC, "ovxt.json"), encoding="utf-8"))

# 材料库再补上 stocks 里出现的 id（可能不全）
extra_mats = {
    "G-4-1": ("龙门币", "T4", "gold", 0),
    "EO-4-1": ("经验值", "T5", "exp", 0),
    "PC-3-1": ("采购凭证", "T3", "tkt", 0),
}
for mid, (name, tier, typ, val) in extra_mats.items():
    materials.setdefault(mid, {"id": mid, "name": name, "tier": tier, "type": typ, "value": val})

if os.path.exists(DB):
    os.remove(DB)
con = sqlite3.connect(DB)
cur = con.cursor()
cur.executescript("""
CREATE TABLE operators (
  uid TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  pinyin TEXT,
  profession TEXT,
  rarity INTEGER,
  max_elite INTEGER,
  max_master INTEGER,
  max_equip INTEGER,
  skill_names TEXT,
  sub TEXT,
  available INTEGER DEFAULT 1
);
CREATE TABLE op_elites (uid TEXT, rank INTEGER, materials TEXT, PRIMARY KEY(uid, rank));
CREATE TABLE op_skills (uid TEXT, level INTEGER, materials TEXT, PRIMARY KEY(uid, level));
CREATE TABLE op_master (uid TEXT, slot INTEGER, level INTEGER, skill_name TEXT, materials TEXT, PRIMARY KEY(uid, slot, level));
CREATE TABLE op_equip (uid TEXT, slot INTEGER, level INTEGER, equipment_id TEXT, code TEXT, materials TEXT, PRIMARY KEY(uid, slot, level));
CREATE TABLE materials (id TEXT PRIMARY KEY, name TEXT, tier TEXT, type TEXT, value INTEGER, formula TEXT, sort_id INTEGER);
CREATE TABLE inventory (material_id TEXT PRIMARY KEY, quantity INTEGER NOT NULL DEFAULT 0);
CREATE TABLE plans (id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT, attribute TEXT, cur INTEGER, target INTEGER, hidden INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now','localtime')));
CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
""")

cur.execute("INSERT INTO meta VALUES (?,?)", ("levelTables", json.dumps(tables, ensure_ascii=False)))
cur.execute("INSERT INTO meta VALUES (?,?)", ("ovxt", json.dumps(ovxt, ensure_ascii=False)))

n_op = n_el = n_sk = n_ms = n_eq = 0
CT = os.path.join(BASE, "_src", "data", "character_table.json")
ctable = json.load(open(CT, encoding="utf-8")) if os.path.exists(CT) else {}


def is_available(uid, name):
    if "预备干员" in (name or ""):
        return 0
    ch = ctable.get(uid) or {}
    return 0 if ch.get("isNotObtainable") else 1


for o in operators:
    meta = o.get("meta") or {}
    cur.execute(
        "INSERT OR REPLACE INTO operators VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            o["unique_id"], o["name"],
            ",".join(o.get("pinyin") or []) if isinstance(o.get("pinyin"), list) else (o.get("pinyin") or ""),
            o.get("profession"), (o.get("rarity") if o.get("rarity") is not None else 0),  # rarity: 0..5（0=1★）
            meta.get("max_elite_rank", 0), meta.get("max_master_skills", 0), meta.get("max_equipments", 0),
            json.dumps(o.get("skill_names") or [], ensure_ascii=False), None,
            is_available(o["unique_id"], o["name"]),
        ),
    )
    n_op += 1
    for e in o.get("elites") or []:
        cur.execute("INSERT OR REPLACE INTO op_elites VALUES (?,?,?)",
                    (o["unique_id"], e.get("rank"), json.dumps(e.get("materials") or [], ensure_ascii=False)))
        n_el += 1
    for s in o.get("skills") or []:
        cur.execute("INSERT OR REPLACE INTO op_skills VALUES (?,?,?)",
                    (o["unique_id"], s.get("level"), json.dumps(s.get("materials") or [], ensure_ascii=False)))
        n_sk += 1
    for si, ms in enumerate(o.get("master_skills") or []):
        for u in ms.get("upgrades") or []:
            cur.execute("INSERT OR REPLACE INTO op_master VALUES (?,?,?,?,?)",
                        (o["unique_id"], si, u.get("level"), ms.get("name"), json.dumps(u.get("materials") or [], ensure_ascii=False)))
            n_ms += 1
    for si, slot in enumerate(o.get("equipments") or []):
        for ei, eq in enumerate(slot or []):
            cur.execute("INSERT OR REPLACE INTO op_equip VALUES (?,?,?,?,?,?)",
                        (o["unique_id"], si, ei, eq.get("equipment_id"), eq.get("code"), json.dumps(eq.get("materials") or [], ensure_ascii=False)))
            n_eq += 1

for mid, m in materials.items():
    cur.execute("INSERT OR REPLACE INTO materials VALUES (?,?,?,?,?,?,?)",
                (mid, m.get("name") or mid, m.get("tier"), m.get("type"), m.get("value") or 0,
                 json.dumps(m.get("formula") or {}, ensure_ascii=False), m.get("sort_id")))

cur.execute("CREATE INDEX idx_op_name ON operators(name)")
cur.execute("CREATE INDEX idx_op_py ON operators(pinyin)")
con.commit()

print("数据库:", DB)
print("  干员", n_op, " 精英化", n_el, " 技能", n_sk, " 专精", n_ms, " 模组", n_eq, " 材料", len(materials))
print("  大小 %.1f KB" % (os.path.getsize(DB) / 1024))
con.close()
