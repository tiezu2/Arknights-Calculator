# -*- coding: utf-8 -*-
"""森空岛（Skland）客户端：扫码/凭据登录 + 拉取干员练度。

签名算法参考社区逆向实现（nonebot-plugin-skland 的 get_sign_header）：
    header_for_sign = {"platform":"","timestamp":"","dId":"","vName":""}
    ts = now - 1
    secret = path + (query 或 json(body)) + ts + json({**header_for_sign,"timestamp":ts})
    sign = md5(hex(hmac_sha256(cred.token, secret)))

数据来源：
    GET /game/player/binding          绑定角色
    GET /game/player/info?uid=UID     玩家数据（含 chars 练度）
"""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://zonai.skland.com/api/v1"
AS_BASE = "https://as.hypergryph.com"
UA = ("Skland/1.32.1 (com.hypergryph.skland; build:103201004; Android 33; ) "
      "Okhttp/4.11.0")
SKLAND_APP_CODE = "4ca99fa6b56cc2ba"
WEB_APP_CODE = "be36d44aa36bfb5b"


class SklandError(Exception):
    pass


def _headers(extra=None):
    h = {
        "User-Agent": UA,
        "Accept-Encoding": "identity",
        "Connection": "close",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _post_json(url, body, headers=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(headers), method="POST")
    return _do(req)


def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers=_headers(headers), method="GET")
    return _do(req)


def _do(req):
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            j = json.loads(raw)
        except Exception:
            raise SklandError(f"HTTP {e.code}: {raw[:200]}")
        msg = j.get("message") or j.get("msg") or raw[:200]
        code = j.get("code") or j.get("status")
        raise SklandError(f"[{code}] {msg}")
    except Exception as e:
        raise SklandError(f"网络错误: {type(e).__name__}: {e}")
    try:
        return json.loads(raw)
    except Exception:
        raise SklandError(f"返回不是 JSON: {raw[:200]}")


def sign_headers(cred_token, url, method, body=None):
    ts = str(int(time.time()) - 1)
    parsed = urllib.parse.urlparse(url)
    header_for_sign = {"platform": "", "timestamp": "", "dId": "", "vName": ""}
    if method == "post":
        query = json.dumps(body, ensure_ascii=False) if body is not None else ""
    else:
        query = parsed.query
    ca = json.dumps({**header_for_sign, "timestamp": ts}, separators=(",", ":"))
    secret = f"{parsed.path}{query}{ts}{ca}"
    hexd = hmac.new(cred_token.encode("utf-8"), secret.encode("utf-8"), hashlib.sha256).hexdigest()
    signature = hashlib.md5(hexd.encode("utf-8")).hexdigest()
    return {"sign": signature, **header_for_sign, "timestamp": ts}


# ---------------- 登录 ----------------
def gen_scan():
    j = _post_json(f"{AS_BASE}/general/v1/gen_scan/login", {"appCode": SKLAND_APP_CODE})
    if j.get("status") not in (0, None):
        raise SklandError(f"获取二维码失败: {j.get('msg')}")
    d = j.get("data") or {}
    return d.get("scanId"), d.get("scanUrl") or ""


def scan_status(scan_id):
    """返回 (scanCode, status)；未扫码时 scanCode 为 None（不是错误）"""
    q = urllib.parse.urlencode({"scanId": scan_id})
    j = _get_json(f"{AS_BASE}/general/v1/scan_status?{q}")
    msg = str(j.get("msg") or j.get("message") or "")
    d = j.get("data") or {}
    code = d.get("scanCode")
    if j.get("status") not in (0, None):
        if "未扫码" in msg or "not scan" in msg.lower() or not code:
            return None, "WAITING"
        raise SklandError(f"查询扫码状态失败: {msg}")
    return code, d.get("scanStatus")


def token_by_scan_code(scan_code):
    j = _post_json(f"{AS_BASE}/user/auth/v1/token_by_scan_code", {"scanCode": scan_code})
    if j.get("status") not in (0, None):
        raise SklandError(f"换取 token 失败: {j.get('msg')}")
    return (j.get("data") or {}).get("token")


def grant_code(token, grant_type=0):
    app = SKLAND_APP_CODE if grant_type == 0 else WEB_APP_CODE
    j = _post_json(f"{AS_BASE}/user/oauth2/v2/grant",
                   {"appCode": app, "token": token, "type": grant_type})
    if j.get("status") not in (0, None):
        raise SklandError(f"grant 失败: {j.get('msg')}")
    d = j.get("data") or {}
    return d.get("code") if grant_type == 0 else d.get("token")


def cred_by_code(code):
    j = _post_json("https://zonai.skland.com/api/v1/user/auth/generate_cred_by_code",
                   {"code": code, "kind": 1})
    if j.get("status") not in (0, None):
        raise SklandError(f"生成 cred 失败: {j.get('message')}")
    d = j.get("data") or {}
    if not d.get("cred") or not d.get("token"):
        raise SklandError("生成 cred 失败：返回缺少 cred/token")
    return {"cred": d["cred"], "token": d["token"], "userId": d.get("userId")}


def refresh_token(cred):
    j = _get_json(f"{BASE}/auth/refresh", {"cred": cred})
    if j.get("status") not in (0, None):
        raise SklandError(f"刷新 token 失败: {j.get('message')}")
    return (j.get("data") or {}).get("token")


# ---------------- 数据 ----------------
class Cred:
    def __init__(self, cred, token, user_id=None, file=None):
        self.cred = cred
        self.token = token
        self.user_id = user_id
        self.file = file

    def save(self):
        if not self.file:
            return
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump({"cred": self.cred, "token": self.token, "userId": self.user_id,
                       "saved_at": int(time.time())}, f, ensure_ascii=False, indent=1)

    @classmethod
    def load(cls, file):
        if not file or not os.path.exists(file):
            return None
        try:
            j = json.load(open(file, encoding="utf-8"))
            if j.get("cred") and j.get("token"):
                return cls(j["cred"], j["token"], j.get("userId"), file)
        except Exception:
            pass
        return None


def get_binding(cred):
    url = f"{BASE}/game/player/binding"
    j = _get_json(url, {"cred": cred.cred, **sign_headers(cred.token, url, "get")})
    if j.get("code") not in (0, None):
        raise SklandError(f"[{j.get('code')}] {j.get('message')}")
    return ((j.get("data") or {}).get("list")) or []


def get_player_info(cred, uid):
    url = f"{BASE}/game/player/info?uid={urllib.parse.quote(str(uid))}"
    j = _get_json(url, {"cred": cred.cred, **sign_headers(cred.token, url, "get")})
    if j.get("code") not in (0, None):
        raise SklandError(f"[{j.get('code')}] {j.get('message')}")
    return j.get("data") or {}


def parse_chars(info):
    """把 /game/player/info 的 chars 转成 [(uid, elite, level, main_skill, skills, modules, potential)]"""
    out = []
    for c in info.get("chars") or []:
        cid = c.get("charId")
        if not cid:
            continue
        skills = []
        for s in (c.get("skills") or []):
            skills.append({"id": s.get("id"), "level": int(c.get("mainSkillLvl") or 1),
                           "spec": int(s.get("specializeLevel") or 0)})
        modules = []
        for e in (c.get("equip") or []):
            modules.append(int(e.get("level") or 0))
        out.append({
            "uid": cid,
            "elite": int(c.get("evolvePhase") or 0),
            "level": int(c.get("level") or 0),
            "main_skill": int(c.get("mainSkillLvl") or 1),
            "skills": skills,
            "modules": modules,
            "potential": int(c.get("potentialRank") or 0),
            "name": ((info.get("charInfoMap") or {}).get(cid) or {}).get("name")
                    or ((info.get("charInfoMap") or {}).get(cid) or {}).get("charName"),
        })
    return out
