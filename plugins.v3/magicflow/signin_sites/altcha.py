"""魔流 · Altcha 人机验证（PoW）求解器 —— 7.19.0。

Altcha 是站点签到用的人机验证（叶PT `feature=checkIn`）。挑战下发：
    POST /api/captcha/generateAltchaChallenge  {"feature": "checkIn"}
    → {"success":true,"data":{"parameters":{algorithm,nonce,salt,cost,keyLength,keyPrefix,data},
                              "signature":"..."}}

求解（与前端 `altcha-widget` 的 solveChallenge 逐行对齐）：
    枚举 counter = 0,1,2,…，令
      PBKDF2-HMAC-SHA256(
          password = nonce(16B) ++ uint32_be(counter),
          salt     = salt,
          iterations = cost,
          dklen      = keyLength)
    的前 len(keyPrefix) 字节 == keyPrefix 即命中。

提交格式（前端 `btoa(JSON.stringify(...))`）：
    altchaPayload = base64(JSON({
        "challenge": {"parameters": <原样>, "signature": <原样>},
        "solution":  {"counter": <int>, "derivedKey": <hex>, "time": <ms>},
    }))

★ 只做「自有账号的日常签到」这一件事：仅在站点明确下发挑战时按它的规则算一次
  （纯工作量证明，无视觉/行为绕过）；站点若撤销该机制，本求解器自然失效并如实回报失败。
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
import time
from typing import Any, Dict, Optional


def _derive(counter: int, nonce: bytes, salt: bytes, cost: int, dklen: int) -> bytes:
    """PBKDF2-HMAC-SHA256(password = nonce ++ uint32_be(counter), salt, cost, dklen)。"""
    return hashlib.pbkdf2_hmac("sha256", nonce + struct.pack(">I", int(counter)), salt, int(cost), int(dklen))


def solve(
    challenge: Dict[str, Any],
    max_counter: int = 5_000_000,
    time_budget: float = 45.0,
) -> Optional[Dict[str, Any]]:
    """求解 Altcha 挑战，返回 solution dict（counter / derivedKey / time），失败 None。"""
    params = dict((challenge or {}).get("parameters") or {})
    if not params:
        return None
    try:
        nonce = bytes.fromhex(str(params.get("nonce") or ""))
        salt = bytes.fromhex(str(params.get("salt") or ""))
    except Exception:  # noqa: BLE001
        return None
    if not nonce or not salt:
        return None
    cost = int(params.get("cost") or 10000)
    dklen = int(params.get("keyLength") or 32)
    kp_hex = str(params.get("keyPrefix") or "")
    kp = bytes.fromhex(kp_hex) if (kp_hex and len(kp_hex) % 2 == 0) else None
    t0 = time.time()
    counter = 0
    while counter <= int(max_counter):
        derived = _derive(counter, nonce, salt, cost, dklen)
        hit = (derived[: len(kp)] == kp) if kp else derived.hex().startswith(kp_hex)
        if hit:
            return {
                "counter": counter,
                "derivedKey": derived.hex(),
                "time": round((time.time() - t0) * 1000.0, 1),
            }
        counter += 1
        if counter % 50 == 0 and (time.time() - t0) > float(time_budget):
            return None
    return None


def build_payload(challenge: Dict[str, Any], solution: Dict[str, Any]) -> str:
    """组装站点要的 altchaPayload（base64 JSON）。"""
    body = {
        "challenge": {
            "parameters": (challenge or {}).get("parameters"),
            "signature": (challenge or {}).get("signature"),
        },
        "solution": solution,
    }
    return base64.b64encode(json.dumps(body, separators=(",", ":")).encode()).decode()


def solve_payload(challenge: Dict[str, Any], **kw: Any) -> Optional[str]:
    """一步到位：求解并返回 altchaPayload，失败 None。"""
    sol = solve(challenge, **kw)
    if not sol:
        return None
    return build_payload(challenge, sol)
