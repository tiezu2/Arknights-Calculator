# -*- coding: utf-8 -*-
"""企鹅物流（penguin-stats）掉落数据同步：每次游戏版本更新后重拉一次。

接口（官方 v2，前缀 /PenguinStats/api/v2）：
    GET /stages?server=CN&show_closed_zones=true   1630 条，1.3 MB
    GET /items                                      155 条，70 KB
    GET /zones                                      169 条，112 KB
    GET /result/matrix?server=CN&show_closed_zones=true   12566 行，1.6 MB
        matrix: [{stageId, itemId, times, quantity, stdDev, start, end}]

版本判断：
    接口没有「游戏版本号」，用 stages 的 stageId 集合哈希做指纹；每次启动先拉 stages，
    指纹变化（新关卡上线）才重拉 items/zones/matrix，实现「每次版本更新重拉一次」。

用法：
    python app/penguin.py            # 按指纹判断是否需要更新
    python app/penguin.py --force    # 强制重拉
    python app/penguin.py --status   # 只看缓存状态
"""
import hashlib
import json
import os
import sys
import time
import urllib.request

# 主站有时被墙，按顺序回退
BASES = [
    "https://penguin-stats.io/PenguinStats/api/v2",
    "https://penguin-stats.cn/PenguinStats/api/v2",
]
BASE = BASES[0]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0"
SERVER = "CN"
HERE = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    # 打包成 exe：缓存与设置放在 exe 同目录（_MEIPASS 是临时目录）
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(HERE)
CACHE = os.path.join(APP_DIR, "data", "penguin")


def _get(path, timeout=120):
    last = None
    for base in BASES:
        url = f"{base}/{path}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            data = json.loads(raw.decode("utf-8"))
            global BASE
            BASE = base
            return data, len(raw), time.time() - t0
        except Exception as e:
            last = e
            continue
    raise last if last else RuntimeError("no endpoint")


def fingerprint(stages):
    ids = sorted(s.get("stageId", "") for s in stages)
    return hashlib.sha256("|".join(ids).encode("utf-8")).hexdigest()


def load_meta():
    p = os.path.join(CACHE, "meta.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_json(name, obj):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    return p, os.path.getsize(p)


def sync(force=False):
    os.makedirs(CACHE, exist_ok=True)
    meta = load_meta()
    print("拉取 stages…", flush=True)
    stages, n, dt = _get(f"stages?server={SERVER}&show_closed_zones=true")
    fp = fingerprint(stages)
    print(f"  stages {len(stages)} 条 / {n/1024/1024:.2f} MB / {dt:.1f}s  指纹 {fp[:16]}")

    if not force and meta.get("fingerprint") == fp and os.path.exists(os.path.join(CACHE, "matrix.json")):
        print("指纹未变（同一游戏版本），跳过重拉。")
        return meta

    changed = meta.get("fingerprint") not in (None, fp)
    print("拉取 items / zones / matrix…", flush=True)
    items, n1, d1 = _get("items")
    zones, n2, d2 = _get("zones")
    matrix, n3, d3 = _get(f"result/matrix?server={SERVER}&show_closed_zones=true")
    print(f"  items {len(items)} 条 {n1/1024:.0f}KB")
    print(f"  zones {len(zones)} 条 {n2/1024:.0f}KB")
    rows = matrix.get("matrix") if isinstance(matrix, dict) else matrix
    print(f"  matrix {len(rows)} 行 {n3/1024/1024:.2f} MB / {d3:.1f}s")

    save_json("stages.json", stages)
    save_json("items.json", items)
    save_json("zones.json", zones)
    save_json("matrix.json", rows)

    # 顺便生成「材料 → 各关掉落率」索引，供刷图/缺口计算使用
    item_name = {i.get("itemId"): i.get("name") for i in items}
    stage_by_id = {s.get("stageId"): s for s in stages}
    zone_name = {z.get("zoneId"): z.get("zoneName") for z in zones}
    index = {}
    for m in rows:
        sid, iid = m.get("stageId"), m.get("itemId")
        times = m.get("times") or 0
        qty = m.get("quantity") or 0
        if not sid or not iid or times <= 0:
            continue
        st = stage_by_id.get(sid) or {}
        index.setdefault(iid, []).append({
            "stage": st.get("code") or sid,
            "stageId": sid,
            "zone": zone_name.get(st.get("zoneId"), ""),
            "apCost": st.get("apCost") or 0,
            "rate": round(qty / times, 4),
            "times": times,
            "quantity": qty,
        })
    for iid in index:
        index[iid].sort(key=lambda r: -r["rate"])
    save_json("drop_index.json", {
        "generated_at": int(time.time()),
        "item_name": item_name,
        "by_item": index,
    })

    meta = {
        "fingerprint": fp,
        "fetched_at": int(time.time()),
        "fetched_at_text": time.strftime("%Y-%m-%d %H:%M:%S"),
        "server": SERVER,
        "counts": {"stages": len(stages), "items": len(items), "zones": len(zones), "matrix": len(rows)},
        "version_hint": next((s.get("stageId") for s in reversed(stages)
                              if str(s.get("stageId", "")).startswith("act")), ""),
        "changed": bool(changed),
    }
    save_json("meta.json", meta)
    print(f"已更新缓存：{CACHE}")
    return meta


def status():
    meta = load_meta()
    if not meta:
        print("还没有缓存，请运行: python app/penguin.py")
        return
    print(f"缓存目录: {CACHE}")
    print(f"  版本指纹: {meta.get('fingerprint', '')[:16]}")
    print(f"  抓取时间: {meta.get('fetched_at_text')}")
    print(f"  数据量: {meta.get('counts')}")
    print(f"  最新活动关卡: {meta.get('version_hint')}")
    for f in ("stages.json", "items.json", "zones.json", "matrix.json", "drop_index.json"):
        p = os.path.join(CACHE, f)
        print(f"  {f:<18} {'%.2f MB' % (os.path.getsize(p)/1024/1024) if os.path.exists(p) else '缺失'}")




# ---------------- 设置与自动更新 ----------------
SETTINGS = os.path.join(APP_DIR, "settings.json")
DEFAULT_SETTINGS = {"auto_drop_sync": True, "drop_ttl_hours": 24}


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        if os.path.exists(SETTINGS):
            s.update(json.load(open(SETTINGS, encoding="utf-8")) or {})
    except Exception:
        pass
    return s


def save_settings(s):
    try:
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


def needs_sync(ttl_hours=24):
    """返回 (是否需要更新, 原因)"""
    meta = load_meta()
    if not meta:
        return True, "还没有掉落数据缓存"
    if not os.path.exists(os.path.join(CACHE, "matrix.json")):
        return True, "缓存文件缺失"
    age = time.time() - int(meta.get("fetched_at") or 0)
    if ttl_hours > 0 and age > ttl_hours * 3600:
        return True, f"缓存已过期（{age/3600:.1f} 小时 > {ttl_hours} 小时）"
    return True, "启动检查版本指纹"


def quick_check(ttl_hours=24):
    """只看本地缓存是否需要更新（不联网）"""
    meta = load_meta()
    if not meta or not os.path.exists(os.path.join(CACHE, "matrix.json")):
        return True, "无缓存"
    age = time.time() - int(meta.get("fetched_at") or 0)
    if ttl_hours > 0 and age > ttl_hours * 3600:
        return True, f"缓存 {age/3600:.1f} 小时"
    return False, "缓存较新"


def summary():
    """给 UI 展示的缓存摘要"""
    meta = load_meta()
    if not meta:
        return None
    return {
        "fingerprint": (meta.get("fingerprint") or "")[:16],
        "fetched_at_text": meta.get("fetched_at_text") or "",
        "counts": meta.get("counts") or {},
        "version_hint": meta.get("version_hint") or "",
        "cache_dir": CACHE,
        "size_mb": sum(os.path.getsize(os.path.join(CACHE, f))
                       for f in os.listdir(CACHE)
                       if os.path.isfile(os.path.join(CACHE, f))) / 1024 / 1024,
    }


def run_sync(force=False, log=print):
    """同步入口（可在后台线程调用）；log 用于把进度回传 UI"""
    meta_old = load_meta()
    log("拉取 stages（约 1.3 MB）…")
    stages, n, dt = _get(f"stages?server={SERVER}&show_closed_zones=true")
    fp = fingerprint(stages)
    log(f"stages {len(stages)} 条，指纹 {fp[:16]}")
    if not force and meta_old.get("fingerprint") == fp and \
            os.path.exists(os.path.join(CACHE, "matrix.json")):
        log("版本指纹未变，掉落数据已是最新")
        return {"changed": False, "fingerprint": fp}
    log("版本有变化或强制更新，拉取 items / zones / matrix…")
    items, n1, _ = _get("items")
    zones, n2, _ = _get("zones")
    matrix, n3, _ = _get(f"result/matrix?server={SERVER}&show_closed_zones=true")
    rows = matrix.get("matrix") if isinstance(matrix, dict) else matrix
    log(f"items {len(items)} / zones {len(zones)} / matrix {len(rows)} 行")
    save_json("stages.json", stages)
    save_json("items.json", items)
    save_json("zones.json", zones)
    save_json("matrix.json", rows)

    item_name = {i.get("itemId"): i.get("name") for i in items}
    stage_by_id = {s.get("stageId"): s for s in stages}
    zone_name = {z.get("zoneId"): z.get("zoneName") for z in zones}
    index = {}
    for m in rows:
        sid, iid = m.get("stageId"), m.get("itemId")
        times, qty = m.get("times") or 0, m.get("quantity") or 0
        if not sid or not iid or times <= 0:
            continue
        st = stage_by_id.get(sid) or {}
        index.setdefault(iid, []).append({
            "stage": st.get("code") or sid,
            "stageId": sid,
            "zone": zone_name.get(st.get("zoneId"), ""),
            "apCost": st.get("apCost") or 0,
            "rate": round(qty / times, 4),
            "times": times,
            "quantity": qty,
        })
    for iid in index:
        index[iid].sort(key=lambda r: -r["rate"])
    save_json("drop_index.json", {"generated_at": int(time.time()),
                                  "item_name": item_name, "by_item": index})
    meta = {
        "fingerprint": fp,
        "fetched_at": int(time.time()),
        "fetched_at_text": time.strftime("%Y-%m-%d %H:%M:%S"),
        "server": SERVER,
        "counts": {"stages": len(stages), "items": len(items),
                   "zones": len(zones), "matrix": len(rows)},
        "version_hint": next((s.get("stageId") for s in reversed(stages)
                              if str(s.get("stageId", "")).startswith("act")), ""),
        "changed": True,
    }
    save_json("meta.json", meta)
    log(f"完成：{len(index)} 种材料掉落率已索引")
    return {"changed": True, "fingerprint": fp, "counts": meta["counts"]}


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--status" in args:
        status()
    else:
        meta = sync(force="--force" in args)
        print()
        status()
