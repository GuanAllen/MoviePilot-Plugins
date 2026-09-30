"""站点实时数据抓取 + 站点流量监控。

背景：MoviePilot 的站点账号数据（上传 / 下载 / 分享率 / 魔力 / 做种数）由 MP 自己的
「站点数据刷新」定时任务写入数据库（默认 **6 小时**一轮）。对"展示"够用，但魔流是拿它
**做决策**的（任务目标达标、救号分享率、兑换提醒、下载量异常增长），滞后 6 小时就是真偏差。

本模块直接抓**站点自身的用户栏页**（NexusPHP `index.php`），解析出**实时值**：

    分享率 / 上传 / 下载 / 当前做种 / 当前下载 / 每小时魔力 / 当前魔力

- 站点级缓存（默认 240s，可配）+ **single-flight**（同站并发只抓一次）+ 失败冷却；
- 抓不到时返回 `ok=False`，由调用方回退 MoviePilot 的数据（可选 + 回退）；
- 维护**采样环形缓冲**（内存 + 插件 data 持久化），据此算上传/下载速率与净增，
  供「站点流量监控」判定：Δ下载超阈值 → 告警（免费种不吃下载，涨下载=吃到促销尾巴）。

security：cookie 只发给该站点自己的域名；不落盘、不外传、不写日志。
"""
from __future__ import annotations

import html as _html
import json
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

# ★ 解析归采集（docs/PLAN-collect.md）：这些解析器本体在 collect，这里只做 re-export
from .collect import (  # noqa: E402
    is_pv_limited,
    next_day_ts,
    parse_leeching_rows,
    parse_size,
    parse_uid,
    parse_user_bar,
)

# 采样历史：每站保留多少个点（按 240s 一点 ≈ 8 小时）
SAMPLE_MAX = 120
# 速率默认窗口（秒）
RATE_WINDOW_SEC = 3600.0
# 抓取默认 TTL（秒）——与候选列表抓取同口径，避免站点吃力
DEFAULT_TTL = 240.0
# 抓取失败后的站点级冷却（秒）
FAIL_COOLDOWN = 180.0
# 连续失败时的指数退避上限（秒）——避免对长期无响应的站点无限重试
FAIL_COOLDOWN_MAX = 3600.0
# 同一站点连续失败超过此次数后，日志由 warning 降为 debug（防刷屏）
FAIL_LOG_AFTER = 3
# 站点用户栏页（NexusPHP 通用）
DEFAULT_PAGE = "/index.php"
# ★ 站点「每日访问次数已达上限」页面特征（实测 PTT：用户等级控制量 300PV/天）
PV_LIMIT_MARKERS = ("访问次数已达上限", "访问次数已达", "今日访问次数")
# 注:原标记里有一个裸 "PV",会误判普通页面（只要正文出现 PV 二字就当成封禁页）。
# 已移除，只保留「访问次数已达上限」这类完整语义的标记。
# 命中访问上限后的封禁时长：到次日凌晨 + 这个宽限（秒）
PV_BLOCK_GRACE = 600.0
# 「正在下载」列表页（NexusPHP 通用，带促销标记）
LEECH_PAGE = "/getusertorrentlist.php?type=leeching&userid={uid}"
# 回退页：站点没getusertorrentlist 时用 userdetails 的「当前下载」表
LEECH_PAGE_ALT = "/userdetails.php?id={uid}"
# 正在下载列表的缓存（秒）—— 只在告警时抓，抓完短缓存避免连环请求
LEECH_TTL = 120.0

_SIZE_UNITS = {
    "B": 1.0,
    "K": 1024.0, "KB": 1024.0, "KIB": 1024.0,
    "M": 1024.0 ** 2, "MB": 1024.0 ** 2, "MIB": 1024.0 ** 2,
    "G": 1024.0 ** 3, "GB": 1024.0 ** 3, "GIB": 1024.0 ** 3,
    "T": 1024.0 ** 4, "TB": 1024.0 ** 4, "TIB": 1024.0 ** 4,
    "P": 1024.0 ** 5, "PB": 1024.0 ** 5, "PIB": 1024.0 ** 5,
}

_TAG_RE = re.compile(r"<[^>]+>")


def _to_text(raw: str) -> str:
    """HTML → 纯文本（去标签 + 反转义 + 归空白，保留 ⬆/⬇ 这类符号）。"""
    s = _TAG_RE.sub(" ", str(raw or ""))
    s = _html.unescape(s)
    s = s.replace("\xa0", " ").replace("\u3000", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", s)


def _first_num(pattern: str, text: str) -> Optional[float]:
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return float(str(m.group(1)).replace(",", ""))
    except (TypeError, ValueError, IndexError):
        return None


def _is_free_promotion(cls: str, text: str) -> bool:
    """促销标记 → 是否「完全免费」（免费 / 2X免费 都算免费；50%免费 **不算**）。"""
    c = str(cls or "").lower()
    t = str(text or "").strip()
    if any(k in c for k in ("halfdown", "50pct", "30pct", "25pct", "1down")) or "%" in t:
        return False
    return bool("free" in c or ("免费" in t and "%" not in t))


# ---------------------------------------------------------------- 新手考核（考核/任务）
EXAM_WINDOW_RE = re.compile(
    r"名称\s*[:：]\s*(.{2,40}?)\s*[\|｜]?\s*时间\s*[:：]\s*"
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*~\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
)
EXAM_ITEM_RE = re.compile(
    r"指标\s*(\d)\s*[:：]\s*(.+?)\s*[,，]\s*要求\s*[:：]\s*(.+?)\s*[,，]\s*"
    r"当前\s*[:：]\s*(.+?)\s*[,，]\s*结果\s*[:：]\s*(通过|未通过)"
)
# ★ 站点实际写的是「17天21小时」（有「小」）——旧正则写成 `\d+\s*时` 永远匹配不上，PT时间这类简版考核一直解析不出来
EXAM_LEFT_RE = re.compile(r"离新人考核结束还有\s*(\d+)\s*天\s*(\d+)\s*小?时")
# 简版（PT时间等）：`上传： 已通过` / `下载： 未通过` / `魔力: 已通过`（标签可能不带「量/值」）
EXAM_SIMPLE_RE = re.compile(
    r"(上传量|下载量|魔力值|做种积分|做种时间|分享率|上传|下载|魔力|积分)"
    r"\s*[:：]\s*(已通过|未通过)"
)
SITE_FREE_RE = re.compile(
    r"全站\s*\[?\s*Free\s*\]?[^0-9]{0,40}?"
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*~\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})",
    re.IGNORECASE,
)


def _amount(text: Any) -> Tuple[Optional[float], str]:
    """把 '30 GB' / '3000' / '30 Hour' / '7,890.60 Hour' 拆成 (数值, 单位)。取不到返回 (None, '')。"""
    s = _to_text(text)
    m = re.search(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*([A-Za-z%]{0,6})", s)
    if not m:
        return None, ""
    try:
        return float(m.group(1).replace(",", "")), (m.group(2) or "").strip()
    except (TypeError, ValueError):
        return None, ""


def to_gb(value: Any, unit: str = "") -> Optional[float]:
    """把带单位的大小换算成 GB（只认字节单位；其他单位原值返回）。"""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    u = (unit or "").strip().upper()
    if u in ("", "GB", "G", "GIB", "GBYTES"):
        return v
    if u in ("KB", "K"):
        return v / (1024 ** 2)
    if u in ("MB", "M"):
        return v / 1024.0
    if u in ("TB", "T"):
        return v * 1024.0
    if u in ("PB", "P"):
        return v * 1024.0 * 1024.0
    if u in ("B",):
        return v / (1024 ** 3)
    return v


def parse_site_free(raw: Any) -> Optional[Dict[str, Any]]:
    """解析「全站 Free 生效中！时间：A ~ B」→ {on, start, end, days_left}。"""
    text = _to_text(raw)
    if "全站" not in text or "Free" not in text:
        return None
    m = SITE_FREE_RE.search(text)
    if not m:
        return None
    start, end = m.group(1), m.group(2)
    days = None
    try:
        e = time.mktime(time.strptime(end, "%Y-%m-%d %H:%M:%S"))
        days = round((e - time.time()) / 86400.0, 2)
    except (ValueError, OverflowError):
        pass
    return {"on": bool(days is None or days > 0), "start": start, "end": end, "days_left": days}


# ── ★ 5.7.0：JS/API 类站点的考核（站点后台接口直接给结构化考核）────────────
#   YemaPT 这类站首页是 JS 单页应用，HTML 里只有空壳 → 网页解析永远读不到；
#   但它的 `/api/user/profile` 直接返回 examTask{taskName,beginTime,endTime,itemList[]}。
#   通道表里配 ``exam_api: {path, field, metrics}`` 即可（采集层只认表）。
EXAM_METRIC_LABELS = {
    "promotionuploadamount": "上传增量",
    "promotiondownloadamount": "下载增量",
    "promotionupload": "上传增量",
    "promotiondownload": "下载增量",
    "promotionbonus": "魔力增量",
    "promotionpoint": "积分增量",
    "promotionseedtime": "做种时间增量",
    "promotionseedingcount": "做种数增量",
}


def _fmt_bytes(value: Any) -> str:
    """字节 → 人读字符串（`32212254720` → `30 GB`）。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    for unit, div in (("TB", 1024.0 ** 4), ("GB", 1024.0 ** 3), ("MB", 1024.0 ** 2), ("KB", 1024.0), ("B", 1.0)):
        if abs(v) >= div or unit == "B":
            got = v / div
            txt = f"{got:.2f}".rstrip("0").rstrip(".")
            return f"{txt} {unit}"
    return ""


def parse_exam_task(raw: Any, metrics: Any = None) -> Optional[Dict[str, Any]]:
    """解析接口式考核对象 → **与 ``parse_exam`` 完全同一 schema**（前端不用分支）。

    YemaPT ``/api/user/profile`` → ``data.examTask``:
    ``{taskName, status, beginTime, endTime, completedCount, requiredCount, itemList:[{metric, targetValue, currentValue, isCompleted}]}``
    单位为**字节**；`metric` 由通道表的 ``metrics`` 映射成中文标签。
    """
    if not isinstance(raw, dict):
        return None
    items_raw = raw.get("itemList")
    if not raw.get("taskName") and not items_raw:
        return None
    labels = dict(EXAM_METRIC_LABELS)
    if isinstance(metrics, dict):
        labels.update({str(k).strip().lower(): str(v) for k, v in metrics.items() if str(k).strip()})
    out: Dict[str, Any] = {
        "name": str(raw.get("taskName") or ""),
        "start": str(raw.get("beginTime") or ""),
        "end": str(raw.get("endTime") or ""),
        "days_left": None,
        "items": [],
        "source": "api",
    }
    for it in items_raw or []:
        if not isinstance(it, dict):
            continue
        metric = str(it.get("metric") or "").strip()
        tgt, cur = it.get("targetValue"), it.get("currentValue")
        try:
            gb_req = float(tgt) / (1024.0 ** 3)
        except (TypeError, ValueError):
            gb_req = None
        try:
            gb_cur = float(cur) / (1024.0 ** 3)
        except (TypeError, ValueError):
            gb_cur = None
        item: Dict[str, Any] = {
            "idx": "",
            "label": labels.get(metric.lower(), metric or "指标"),
            "req": _fmt_bytes(tgt),
            "cur": _fmt_bytes(cur),
            "pass": bool(it.get("isCompleted")),
            "req_num": gb_req,
            "cur_num": gb_cur,
            "unit": "GB",
        }
        if gb_req is not None:
            item["req_gb"] = gb_req
            item["cur_gb"] = gb_cur
            item["short_gb"] = max(0.0, round(gb_req - (gb_cur or 0.0), 3))
        out["items"].append(item)
    if out["end"] and out["days_left"] is None:
        try:
            e = time.mktime(time.strptime(out["end"], "%Y-%m-%d %H:%M:%S"))
            out["days_left"] = round((e - time.time()) / 86400.0, 2)
        except (ValueError, OverflowError):
            pass
    out["failed"] = [i["label"] for i in out["items"] if not i.get("pass")]
    out["all_pass"] = bool(out["items"]) and not out["failed"]
    out["active"] = bool(out["all_pass"] is False and out["items"])
    if out["days_left"] is not None and out["days_left"] <= 0:
        out["ended"] = True
        out["active"] = False
    return out


def parse_exam_rule(bar: Any, rule: Any, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """★ 5.8.0：**规则式考核** —— 站点不给考核区块，但官方标准是**固定阈值**时，
    用白名单接口里的自己数据推算（馒头：上传>30G / 下载>15G / 魔力>6000，注册后 30 天）。

    ★ 合规性：数据全部来自**官方 API 白名单端点**（``/member/profile``），不读网页会话。
    ``rule`` 来自通道表 ``exam_rule``；``bar`` 是采集归一后的用户栏（含 created）。
    """
    if not isinstance(bar, dict) or not isinstance(rule, dict):
        return None
    metas = rule.get("metrics") or []
    if not metas:
        return None
    now = time.time() if now is None else float(now)
    out: Dict[str, Any] = {
        "name": str(rule.get("name") or "新手考核"),
        "start": str(bar.get("created") or ""),
        "end": "",
        "days_left": None,
        "items": [],
        "source": "api-rule",
    }
    win = rule.get("window_days")
    if out["start"] and win:
        try:
            s = time.mktime(time.strptime(out["start"], "%Y-%m-%d %H:%M:%S"))
            e = s + float(win) * 86400.0
            out["start"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s))
            out["end"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e))
            out["days_left"] = round((e - now) / 86400.0, 2)
        except (ValueError, OverflowError, TypeError):
            pass

    def _mk(label, cur_n, tgt_n, ok, req_h, bytes_unit):
        item: Dict[str, Any] = {
            "idx": "",
            "label": label,
            "req": req_h,
            "cur": _fmt_bytes(cur_n) if bytes_unit else ("" if cur_n is None else f"{cur_n:g}"),
            "pass": bool(ok),
            "req_num": tgt_n,
            "cur_num": cur_n,
            "unit": "GB" if bytes_unit else "",
        }
        if tgt_n is not None and cur_n is not None:
            if bytes_unit:
                item["req_gb"] = tgt_n / (1024.0 ** 3)
                item["cur_gb"] = cur_n / (1024.0 ** 3)
                item["short_gb"] = max(0.0, round(item["req_gb"] - item["cur_gb"], 3))
            else:
                item["short_num"] = max(0.0, tgt_n - cur_n)
        return item

    for i, m in enumerate(metas, 1):
        if not isinstance(m, dict):
            continue
        field = str(m.get("field") or "")
        bytes_unit = str(m.get("unit") or "bytes") == "bytes"
        try:
            cur_n = float(bar.get(field))
        except (TypeError, ValueError):
            cur_n = None
        try:
            tgt_n = float(m.get("target"))
        except (TypeError, ValueError):
            tgt_n = None
        op = str(m.get("op") or ">")
        ok = cur_n is not None and tgt_n is not None
        if ok:
            ok = {
                ">": cur_n > tgt_n,
                ">=": cur_n >= tgt_n,
                "<": cur_n < tgt_n,
                "<=": cur_n <= tgt_n,
            }.get(op, cur_n > tgt_n)
        item = _mk(str(m.get("label") or field), cur_n, tgt_n, ok, str(m.get("target_h") or ""), bytes_unit)
        item["idx"] = str(i)
        out["items"].append(item)

    # 附加安全线（复合条件，如馒头「注冊未満 30 天下載>10G 且分享率<0.3 → 直接禁用」）
    g = rule.get("guard")
    if isinstance(g, dict):
        try:
            cur_n = float(bar.get(str(g.get("field") or "ratio")))
        except (TypeError, ValueError):
            cur_n = None
        try:
            when_cur = float(bar.get(str(g.get("when_field") or "")))
            when_gt = float(g.get("when_gt"))
            triggered = when_cur > when_gt
        except (TypeError, ValueError):
            triggered = False
        try:
            mn = float(g.get("min"))
        except (TypeError, ValueError):
            mn = None
        ok = not (triggered and cur_n is not None and mn is not None and cur_n < mn)
        item = _mk(
            str(g.get("label") or "安全线"),
            None if triggered else cur_n,
            None,
            ok,
            str(g.get("hint") or ""),
            False,
        )
        item["cur"] = "" if cur_n is None else f"{cur_n:g}"
        item["pass"] = bool(ok)
        item["idx"] = str(len(out["items"]) + 1)
        out["items"].append(item)

    out["failed"] = [i["label"] for i in out["items"] if not i.get("pass")]
    out["all_pass"] = bool(out["items"]) and not out["failed"]
    out["active"] = bool(out["all_pass"] is False and out["items"])
    if out["days_left"] is not None and out["days_left"] <= 0:
        out["ended"] = True
        out["active"] = False
    return out


def parse_exam(raw: Any) -> Optional[Dict[str, Any]]:
    """解析 NexusPHP「新手考核 / 新人进站考核」区块。

    两种版式都吃：
    1) 4 指标表：`名称：X | 时间：A ~ B` + `指标N：标签, 要求：R, 当前：C, 结果：通过/未通过`；
    2) 简版：`离新人考核结束还有 X天Y时` + `上传量：已通过` 这类逐项。
    解析不出返回 None（不猜）。
    """
    text = _to_text(raw)
    if "考核" not in text:
        return None
    flat = re.sub(r"\s*\n\s*", " ", text)
    out: Dict[str, Any] = {
        "name": "",
        "start": "",
        "end": "",
        "days_left": None,
        "items": [],
    }
    m = EXAM_WINDOW_RE.search(flat)
    if m:
        out["name"] = m.group(1).strip(" |｜")
        out["start"], out["end"] = m.group(2), m.group(3)
    for mm in EXAM_ITEM_RE.finditer(flat):
        req_v, req_u = _amount(mm.group(3))
        cur_v, cur_u = _amount(mm.group(4))
        unit = req_u or cur_u
        item: Dict[str, Any] = {
            "idx": mm.group(1),
            "label": mm.group(2).strip(),
            "req": mm.group(3).strip(),
            "cur": mm.group(4).strip(),
            "pass": mm.group(5) == "通过",
            "req_num": req_v,
            "cur_num": cur_v,
            "unit": unit,
        }
        if unit and unit.upper() in ("KB", "K", "MB", "M", "GB", "G", "GIB", "TB", "T", "PB", "P", "B"):
            item["req_gb"] = to_gb(req_v, unit)
            item["cur_gb"] = to_gb(cur_v, unit)
            item["short_gb"] = max(
                0.0, round((item["req_gb"] or 0.0) - (item["cur_gb"] or 0.0), 3)
            )
        elif req_v is not None:
            item["short_num"] = max(0.0, req_v - (cur_v or 0.0))
        out["items"].append(item)
    left = EXAM_LEFT_RE.search(flat)
    if left:
        out["days_left"] = round(int(left.group(1)) + int(left.group(2)) / 24.0, 2)
        for mm in EXAM_SIMPLE_RE.finditer(flat):
            out["items"].append(
                {
                    "idx": "",
                    "label": mm.group(1),
                    "req": "",
                    "cur": "",
                    "pass": mm.group(2) == "已通过",
                }
            )
    if out["end"] and out["days_left"] is None:
        try:
            e = time.mktime(time.strptime(out["end"], "%Y-%m-%d %H:%M:%S"))
            out["days_left"] = round((e - time.time()) / 86400.0, 2)
        except (ValueError, OverflowError):
            pass
    if not out["items"] and not out["end"] and out["days_left"] is None:
        return None
    out["failed"] = [i["label"] for i in out["items"] if not i.get("pass")]
    out["all_pass"] = bool(out["items"]) and not out["failed"]
    out["active"] = bool(out["all_pass"] is False and out["items"])
    if out["days_left"] is not None and out["days_left"] <= 0:
        out["ended"] = True
        out["active"] = False
    out["site_free"] = parse_site_free(text)
    return out


def _norm_title(text: Any) -> frozenset:
    """标题归一化：小写、去 [组名]、非字母数字/汉字都当分隔符、去年代 → 词集合。"""
    s = str(text or "").lower()
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    s = re.sub(r"\b(19[0-9]{2}|20[0-9]{2})\b", " ", s)
    return frozenset(t for t in s.split() if len(t) > 1)


def title_match(a: Any, b: Any) -> bool:
    """两个标题是否同一 Release（处理「点 vs 空格」「站上带年代」这类差异）。

    规则：① 归一化后词集合完全相同 → 是；② Jaccard ≥ 0.8 → 是；
    ③ 弱一些但重叠过半且双方都不是空 → 交/并 ≥ 0.5。绝不靠猜。
    """
    sa, sb = _norm_title(a), _norm_title(b)
    if not sa or not sb:
        return False
    if sa == sb:
        return True
    inter = len(sa & sb)
    union = len(sa | sb)
    if union <= 0:
        return False
    j = inter / union
    return j >= 0.8 or (inter >= 3 and j >= 0.5)


# 实时数据缓存上限 TTL：只是给冷层一个上限，真正的新鲜度由 LiveStats.ttl 自判。
LIVE_CACHE_TTL = 7200.0


class _LiveCache:
    """LiveStats 的实时数据缓存：优先走插件的 TierCache（分层、跨热重载存活）。

    旧版是纯内存 dict → 每次插件热重载都清空 → 下次看门狗/页面刷新又真抓一遍
    （实测一天 120 次重载，把每站的实时抓取放大了几十倍）。
    拿不到分层缓存时自动退化为本地 dict，行为与旧版一致。
    """

    def __init__(self, tier: Any = None) -> None:
        self._tc = tier
        self._mem: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        key = str(key)
        if self._tc is not None:
            try:
                val = self._tc.get(key, LIVE_CACHE_TTL)
                if isinstance(val, dict):
                    return dict(val)
            except Exception:  # noqa: BLE001
                pass
        v = self._mem.get(key)
        return dict(v) if isinstance(v, dict) else None

    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        if not isinstance(value, dict):
            return
        key = str(key)
        self._mem[key] = dict(value)
        if self._tc is not None:
            try:
                self._tc.set(key, dict(value), LIVE_CACHE_TTL)
            except Exception:  # noqa: BLE001
                pass

    def pop(self, key: str, default: Any = None) -> Any:
        key = str(key)
        val = self._mem.pop(key, None)
        if self._tc is not None:
            try:
                self._tc.delete(key)
            except Exception:  # noqa: BLE001
                pass
        return (dict(val) if isinstance(val, dict) else default)


class LiveStats:
    """站点实时数据 + 采样历史（速率/净增/告警判定）。"""

    def __init__(self, plugin: Any, ttl: float = DEFAULT_TTL) -> None:
        self._plugin = plugin
        self.ttl = float(ttl or DEFAULT_TTL)
        # ★ 3.7.1：实时数据缓存改为分层（内存热层 + FileCache 冷层），跨热重载存活。
        _tier = None
        try:
            _factory = getattr(plugin, "live_cache", None)
            if callable(_factory):
                _tier = _factory()
        except Exception:  # noqa: BLE001
            _tier = None
        self._cache: Any = _LiveCache(_tier)
        self._locks: Dict[str, threading.Lock] = {}
        self._cooldown: Dict[str, float] = {}
        self._fail_count: Dict[str, int] = {}
        self._samples: Dict[str, List[List[float]]] = {}
        self._loaded = False
        self._leech: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._pv_block: Dict[str, float] = {}
        self._pv_loaded = False
        # 「新手考核」总开关（由 插件设置 → 考核 控制；关则不解析考核块）
        self.exam_enabled = False

    # ---------------------------------------------------------------- 抓取
    def _log(self, msg: str, level: str = "info") -> None:
        try:
            self._plugin._log(f"[站点实时] {msg}", level)
        except Exception:  # noqa: BLE001
            pass

    def _site(self, site_id: int) -> Any:
        try:
            return self._plugin._get_site(int(site_id))
        except Exception:  # noqa: BLE001
            return None

    def _get_text(self, site_id: int, page: str, kind: str = "live") -> Tuple[str, Optional[str], int]:
        """抓一页正文。返回 (text, error, status)。

        ★ 3.38.0：站点请求**只出自采集模块**（``collect.http``）——这里只是一层兼容壳，
        配额闸门 / 熔断 / 编码 / PV 拦截页识别全在采集模块里做（唯一出口）。
        """
        c = getattr(self._plugin, "collect", None)
        if c is not None:
            try:
                res = c.site(int(site_id)).page(page, kind=str(kind or "live"), ttl=0.0)
                if res.ok:
                    return res.text, None, int(res.status or 200)
                return "", res.error or "抓取失败", int(res.status or 0)
            except Exception as err:  # noqa: BLE001
                return "", f"采集模块异常: {err}", 0
        # 采集模块不可用（极早启动阶段）→ 不自行发请求（唯一出口纪律）
        return "", "采集模块不可用", 0

    def _exam_from_rule(self, site_id: int, site: Any, bar: Any = None) -> Optional[Dict[str, Any]]:
        """★ 5.8.0：**规则式考核** —— 站点不给考核区块、但官方标准是固定阈值时，
        用**官方 API 白名单字段**推算（馒头：上传>30G/下载>15G/魔力>6000，注册后 30 天）。

        数据源＝``/member/profile``（官方明确允许第三方调用），**不读网页会话 → 合规**。
        """
        try:
            try:
                from . import collect as _C  # noqa: WPS433
            except ImportError:
                import collect as _C  # type: ignore  # noqa: WPS433
            rule = _C.exam_rule(site) if hasattr(_C, "exam_rule") else {}
        except Exception:  # noqa: BLE001
            rule = {}
        if not isinstance(rule, dict) or not rule.get("metrics"):
            return None
        if bar is None:
            c = getattr(self._plugin, "collect", None)
            if c is None:
                return None
            try:
                bar = c.site(int(site_id)).user_bar(force=True)
            except Exception:  # noqa: BLE001
                return None
        if not isinstance(bar, dict) or not bar.get("ok"):
            return None
        try:
            return parse_exam_rule(bar, rule)
        except Exception:  # noqa: BLE001
            return None

    def _exam_from_api(self, site_id: int, site: Any) -> Optional[Dict[str, Any]]:
        """★ 5.7.0：从站点**后台接口**读考核（JS 单页站专用；通道表 ``exam_api`` 驱动）。

        例：YemaPT 首页是 JS 空壳，但 ``GET /api/user/profile``（带站点 cookie）
        直接返回 ``data.examTask``。读不到/没配 → None（不猜）。
        """
        try:
            try:
                from . import collect as _C  # noqa: WPS433
            except ImportError:
                import collect as _C  # type: ignore  # noqa: WPS433
            ep = _C.exam_api(site) if hasattr(_C, "exam_api") else {}
        except Exception:  # noqa: BLE001
            ep = {}
        if not isinstance(ep, dict) or not ep:
            return None
        path = str(ep.get("path") or "").strip()
        if not path:
            return None
        if path.startswith("http"):
            url = path
        else:
            base = str(getattr(site, "url", "") or f"https://{getattr(site, 'domain', '')}")
            try:
                from urllib.parse import urlsplit  # noqa: WPS433

                sp = urlsplit(base)
                root = f"{sp.scheme}://{sp.netloc}" if sp.scheme else base.rstrip("/")
            except Exception:  # noqa: BLE001
                root = base.rstrip("/")
            url = f"{root}/{path.lstrip('/')}"
        c = getattr(self._plugin, "collect", None)
        if c is None:
            return None
        try:
            res = c.http.text(int(site_id), url, kind="exam", ttl=1800.0)
        except Exception:  # noqa: BLE001
            return None
        if not getattr(res, "ok", False):
            return None
        try:
            payload = json.loads(getattr(res, "text", "") or "{}")
        except Exception:  # noqa: BLE001
            return None
        field = str(ep.get("field") or "examTask")
        node = payload.get(field) if isinstance(payload, dict) else None
        if node is None and isinstance(payload, dict):
            inner = payload.get("data")
            if isinstance(inner, dict):
                node = inner.get(field)
        return parse_exam_task(node, ep.get("metrics"))

    def _fetch_once(self, site_id: int, page: str = DEFAULT_PAGE) -> Dict[str, Any]:
        """真抓一次（无缓存）。返回 {ok, ...}；异常一律 ok=False（绝不抛出）。"""
        site = self._site(site_id)
        if not site:
            return {"ok": False, "error": "站点不存在"}
        # ★ 3.42.0：API 鉴权站（馒头）→ 走站点 API（x-api-key），不抓网页用户栏
        _c = getattr(self._plugin, "collect", None)
        try:
            _api = bool(_c is not None and _c.is_api_site(int(site_id)))
        except Exception:  # noqa: BLE001
            _api = False
        if _api:
            try:
                bar = _c.site(int(site_id)).user_bar(force=True)
            except Exception as err:  # noqa: BLE001
                return {"ok": False, "error": f"API 抓取异常: {err}"}
            if not bar.get("ok"):
                return {"ok": False, "error": bar.get("error") or "API 抓取失败"}
            out = {
                "ok": True,
                "site_id": int(site_id),
                "url": "api:/member/profile",
                "status": 200,
                "ts": time.time(),
                "source": "api",
            }
            for _k in ("uid", "ratio", "upload", "download", "seeding", "leeching", "bonus", "bonus_per_hour", "logged_in"):
                out[_k] = bar.get(_k)
            out["fields"] = [
                _k
                for _k in ("uid", "ratio", "upload", "download", "bonus")
                if bar.get(_k) not in (None, 0.0, "")
            ]
            # ★ 5.7.0：API 站的考核（通道表 exam_api）也一并读
            try:
                if bool(getattr(self, "exam_enabled", False)):
                    _ex = self._exam_from_api(int(site_id), site)
                    if not _ex:
                        # ★ 5.8.0：没有接口式考核 → 试官方规则推算（白名单字段）
                        _ex = self._exam_from_rule(int(site_id), site, bar)
                    if _ex:
                        out["exam"] = _ex
            except Exception:  # noqa: BLE001
                pass
            return out
        # ★ 3.38.0：PV 记账与预算闸门已内置在采集模块（collect.http），这里不再重复
        base = (getattr(site, "url", "") or f"https://{getattr(site, 'domain', '')}").rstrip("/")
        text, err, status = self._get_text(site_id, page, kind="leeching")
        if err:
            if "访问次数已达上限" in str(err):
                return {"ok": False, "pv_limited": True, "error": err, "status": status}
            return {"ok": False, "error": err, "status": status}
        url = f"{base}/{str(page or DEFAULT_PAGE).lstrip('/')}"
        parsed = parse_user_bar(text)
        got = [k for k, v in parsed.items() if v not in (None, 0.0)]
        if not got:
            return {"ok": False, "error": "用户栏未解析出字段（可能未登录/模板不同）", "status": status}
        out = {"ok": True, "site_id": int(site_id), "url": url, "status": status, "ts": time.time()}
        out.update(parsed)
        out["fields"] = got
        try:
            if bool(getattr(self, "exam_enabled", False)):
                exam = parse_exam(text)
                if not exam:
                    # ★ 5.7.0：网页读不到 → 试试站点后台接口（JS 单页站）
                    exam = self._exam_from_api(int(site_id), site)
                if not exam:
                    # ★ 5.8.0：也没有接口 → 试官方规则推算
                    exam = self._exam_from_rule(int(site_id), site)
            else:
                exam = None
        except Exception:  # noqa: BLE001
            exam = None
        if exam:
            out["exam"] = exam
        return out

    def leeching(self, site_id: int, force: bool = False) -> Dict[str, Any]:
        """抓「正在下载」列表（带促销标记）→ {ok, uid, rows, url}。

        供「下载量异常增长 → 清除非免费下载种」使用。短缓存（LEECH_TTL）避免连环请求。
        """
        if not site_id:
            return {"ok": False, "error": "缺少 site_id"}
        key = str(int(site_id))
        now = time.time()
        hit = self._leech.get(key)
        if hit and not force and (now - float(hit[0])) < LEECH_TTL:
            return dict(hit[1])
        live = self.get(site_id)
        uid = live.get("uid")
        if not uid:
            text, err, _st = self._get_text(site_id, DEFAULT_PAGE, kind="live")
            uid = parse_uid(text) if not err else None
        if not uid:
            res = {"ok": False, "error": "未解析出 uid"}
            self._leech[key] = (now, res)
            return dict(res)
        page = LEECH_PAGE.format(uid=int(uid))
        text, err, status = self._get_text(site_id, page)
        rows: List[Dict[str, Any]] = []
        if not err:
            rows = parse_leeching_rows(text)
        if not rows and not err:
            # 回退：站点可能没有 getusertorrentlist，改用 userdetails.php 的「当前下载」表
            alt = LEECH_PAGE_ALT.format(uid=int(uid))
            text2, err2, _st2 = self._get_text(site_id, alt, kind="leeching")
            if not err2:
                rows = parse_leeching_rows(text2)
                if rows:
                    page = alt
        if err and not rows:
            if "访问次数已达上限" in str(err):
                self._pv_block_site(int(site_id), str(err))
            res = {"ok": False, "error": err, "uid": int(uid), "pv_limited": "访问次数已达上限" in str(err)}
            self._leech[key] = (now, res)
            return dict(res)
        res = {
            "ok": True,
            "uid": int(uid),
            "page": page,
            "rows": rows,
            "ts": time.time(),
        }
        self._leech[key] = (now, res)
        return dict(res)

    # ---------------------------------------------------------------- 访问上限
    def _load_pv(self) -> None:
        if self._pv_loaded:
            return
        self._pv_loaded = True
        try:
            data = self._plugin.get_data("live_pv_block")
        except Exception:  # noqa: BLE001
            data = None
        if isinstance(data, dict):
            now = time.time()
            for k, v in data.items():
                try:
                    ts = float(v)
                except (TypeError, ValueError):
                    continue
                if ts > now:
                    self._pv_block[str(k)] = ts

    def pv_blocked_until(self, site_id: int) -> float:
        """该站点因「每日访问上限」被封到的绝对时间戳（0 = 未封）。"""
        self._load_pv()
        return float(self._pv_block.get(str(int(site_id)), 0.0) or 0.0)

    def _pv_block_site(self, site_id: int, reason: str = "访问次数已达上限") -> float:
        self._load_pv()
        until = next_day_ts()
        self._pv_block[str(int(site_id))] = until
        try:
            self._plugin.save_data("live_pv_block", dict(self._pv_block))
        except Exception:  # noqa: BLE001
            pass
        self._log(
            f"站点 {site_id} {reason}（今日已用完配额）→ 暂停抓取至 "
            f"{time.strftime('%m-%d %H:%M', time.localtime(until))}",
            "warning",
        )
        return until

    def get(self, site_id: int, force: bool = False, page: str = DEFAULT_PAGE) -> Dict[str, Any]:
        """带缓存 + single-flight 的实时数据。抓不到时**返回上次成功值并标记 stale**。"""
        if not site_id:
            return {"ok": False, "error": "缺少 site_id"}
        key = str(int(site_id))
        now = time.time()
        until = self.pv_blocked_until(int(site_id))
        if until > now:
            hit0 = self._cache.get(key)
            if hit0:
                out = dict(hit0)
                out.update({
                    "cached": True,
                    "stale": True,
                    "pv_limited": True,
                    "error": "站点每日访问次数已达上限",
                })
                return out
            return {
                "ok": False,
                "pv_limited": True,
                "error": "站点每日访问次数已达上限",
                "until": until,
            }
        hit = self._cache.get(key)
        if hit and not force and (now - float(hit.get("_at", 0))) < self.ttl:
            out = dict(hit)
            out["cached"] = True
            return out
        if not force and float(self._cooldown.get(key, 0)) > now:
            if hit:
                out = dict(hit)
                out.update({"cached": True, "stale": True, "error": out.get("error") or "冷却中"})
                return out
            return {"ok": False, "error": "冷却中"}
        lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            hit = self._cache.get(key)
            if hit and not force and (time.time() - float(hit.get("_at", 0))) < self.ttl:
                out = dict(hit)
                out["cached"] = True
                return out
            res = self._fetch_once(int(site_id), page=page)
            res["_at"] = time.time()
            if res.get("ok"):
                self._cooldown.pop(key, None)
                self._fail_count.pop(key, None)
                self._cache[key] = res
                self._push_sample(key, res)
                self._save_samples()
            else:
                _n = self._fail_count.get(key, 0) + 1
                self._fail_count[key] = _n
                _delay = min(FAIL_COOLDOWN * (2 ** (_n - 1)), FAIL_COOLDOWN_MAX)
                self._cooldown[key] = time.time() + _delay
                if res.get("pv_limited"):
                    self._pv_block_site(int(site_id), str(res.get("error") or "访问次数已达上限"))
                else:
                    _msg = f"站点 {site_id} 实时数据抓取失败：{res.get('error')}（第 {_n} 次，退避 {int(_delay)}s）"
                    self._log(_msg, "warning" if _n <= FAIL_LOG_AFTER else "debug")
                if hit:  # 回退上次成功值（标记 stale）
                    out = dict(hit)
                    out.update({"cached": True, "stale": True, "error": res.get("error")})
                    return out
            return dict(res)

    # ---------------------------------------------------------------- 采样历史
    def _load_samples(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            data = self._plugin.get_data("live_samples")
        except Exception:  # noqa: BLE001
            data = None
        if isinstance(data, dict):
            for k, rows in data.items():
                if isinstance(rows, list):
                    cleaned: List[List[float]] = []
                    for row in rows[-SAMPLE_MAX:]:
                        if isinstance(row, (list, tuple)) and len(row) >= 6:
                            try:
                                cleaned.append([float(x) for x in row[:6]])
                            except (TypeError, ValueError):
                                continue
                    if cleaned:
                        self._samples[str(k)] = cleaned

    def _save_samples(self) -> None:
        try:
            self._plugin.save_data("live_samples", {k: v[-SAMPLE_MAX:] for k, v in self._samples.items()})
        except Exception:  # noqa: BLE001
            pass

    def _push_sample(self, key: str, res: Dict[str, Any]) -> None:
        self._load_samples()
        row = [
            float(res.get("ts") or time.time()),
            float(res.get("upload") or 0.0),
            float(res.get("download") or 0.0),
            float(res.get("seeding") or 0.0),
            float(res.get("leeching") or 0.0),
            float(res.get("bonus") or 0.0),
        ]
        rows = self._samples.setdefault(key, [])
        # 相邻采样若站点数据没变（同一秒/完全一致）就跳过，避免速率被"零间隔"污染
        if rows and row[0] - rows[-1][0] < 30:
            rows[-1] = row
        else:
            rows.append(row)
        if len(rows) > SAMPLE_MAX:
            del rows[: len(rows) - SAMPLE_MAX]

    def history(self, site_id: int) -> List[List[float]]:
        self._load_samples()
        return list(self._samples.get(str(int(site_id)), []))

    def rates(self, site_id: int, window: float = RATE_WINDOW_SEC) -> Dict[str, Any]:
        """按采样历史算速率/净增（窗口内首末两点差）。"""
        rows = self.history(site_id)
        out = {
            "ok": False, "span_sec": 0.0, "samples": len(rows),
            "up_bps": 0.0, "down_bps": 0.0, "up_mb_min": 0.0, "down_mb_min": 0.0,
            "d_up": 0.0, "d_down": 0.0, "d_bonus": 0.0,
        }
        if len(rows) < 2:
            return out
        last = rows[-1]
        cutoff = last[0] - float(window or RATE_WINDOW_SEC)
        first = rows[0]
        for row in rows:
            if row[0] >= cutoff:
                first = row
                break
        span = float(last[0] - first[0])
        if span <= 0:
            return out
        d_up = float(last[1] - first[1])
        d_down = float(last[2] - first[2])
        d_bonus = float(last[5] - first[5])
        out.update({
            "ok": True, "span_sec": span, "samples": len(rows),
            "d_up": d_up, "d_down": d_down, "d_bonus": d_bonus,
            "up_bps": max(0.0, d_up / span), "down_bps": max(0.0, d_down / span),
            "up_mb_min": max(0.0, d_up / span) * 60.0 / (1024 ** 2),
            "down_mb_min": max(0.0, d_down / span) * 60.0 / (1024 ** 2),
        })
        return out

    # ---------------------------------------------------------------- 监控判定
    def evaluate(
        self,
        site_id: int,
        cfg: Optional[Dict[str, Any]] = None,
        live: Optional[Dict[str, Any]] = None,
        local_managed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """产出告警列表（纯函数式判断，不做任何写操作）。"""
        cfg = cfg or {}
        live = live if live is not None else self.get(site_id)
        rates = self.rates(site_id)
        alerts: List[Dict[str, Any]] = []
        if not live.get("ok"):
            if live.get("pv_limited"):
                alerts0 = [{
                    "kind": "pv_limit",
                    "level": "warn",
                    "text": (
                        "站点「每日访问次数已达上限」→ 已暂停抓取（含刷流浏览）至明日凌晨；"
                        "说明抓得太频，建议拉长选种/采样间隔"
                    ),
                }]
                return {"ok": False, "alerts": alerts0, "level": "warn", "rates": rates, "live": live}
            return {"ok": False, "alerts": [], "rates": rates, "live": live}

        # ① 下载量增长（唯一真危险信号：免费种不吃下载）
        thr_mb = float(cfg.get("download_alert_mb") or 50.0)
        down_mb_min = float(rates.get("down_mb_min") or 0.0)
        if rates.get("ok") and down_mb_min >= thr_mb:
            alerts.append({
                "kind": "download_rising",
                "level": "warn",
                "text": (
                    f"下载量在涨：近 {rates['span_sec'] / 60:.0f} 分钟 "
                    f"+{rates['d_down'] / (1024 ** 3):.2f}GB（≈{down_mb_min:.1f}MB/分钟）"
                    f"—— 可能有非免费/促销过期的种在跑"
                ),
            })
        # ② 分享率低于目标线
        tgt = float(cfg.get("ratio_target") or 0.0)
        ratio = live.get("ratio")
        if tgt > 0 and ratio is not None and float(ratio) < tgt:
            need = tgt * float(live.get("download") or 0.0) - float(live.get("upload") or 0.0)
            alerts.append({
                "kind": "ratio_low",
                "level": "warn",
                "text": (
                    f"分享率 {float(ratio):.3f} < 目标 {tgt:.2f}"
                    + (f"，还差 {max(0.0, need) / (1024 ** 3):.1f}GB 上传" if need > 0 else "")
                ),
            })
        # ③ 魔力够档（可提醒去兑换）
        bonus = float(live.get("bonus") or 0.0)
        if bonus >= 2000:
            alerts.append({
                "kind": "bonus_ready",
                "level": "info",
                "text": f"当前魔力 {bonus:.0f} ≥ 2000，可兑换 10GB 上传（留够考核余量再换）",
            })
        elif bonus >= 1200:
            alerts.append({
                "kind": "bonus_ready",
                "level": "info",
                "text": f"当前魔力 {bonus:.0f} ≥ 1200，可兑换 5GB 上传（留够考核余量再换）",
            })
        # ④ 站点视角做种数 vs 本地托管数
        if local_managed is not None and live.get("seeding") is not None:
            try:
                site_seed = int(live.get("seeding") or 0)
                local_seed = int(local_managed or 0)
            except (TypeError, ValueError):
                site_seed = local_seed = 0
            if local_seed >= 5 and site_seed * 2 < local_seed:
                alerts.append({
                    "kind": "seeding_mismatch",
                    "level": "warn",
                    "text": f"站内只认 {site_seed} 个做种，本地托管 {local_seed} 个 → 可能有种子未 announce/被暂停",
                })
        # ⑤ 新手考核：有未通过项（临期 → warn，否则 info）
        exam = live.get("exam") or {}
        if exam.get("items"):
            failed = [i for i in exam.get("items") or [] if not i.get("pass")]
            if failed:
                left = exam.get("days_left")
                detail = "、".join(
                    f"{i.get('label')}({i.get('cur') or '?'}→{i.get('req') or '?'})" for i in failed
                )
                alerts.append(
                    {
                        "kind": "exam_fail",
                        "level": "warn" if (left is not None and float(left) <= 5) else "info",
                        "text": f"新手考核有 {len(failed)} 项未通过：{detail}"
                        + (f"（剩 {float(left):.1f} 天）" if left is not None else ""),
                    }
                )
        level = "info"
        for a in alerts:
            if a.get("level") == "warn":
                level = "warn"
                break
        return {"ok": True, "alerts": alerts, "level": level, "rates": rates, "live": live}

    def snapshot(
        self,
        site_id: int,
        cfg: Optional[Dict[str, Any]] = None,
        local_managed: Optional[int] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """实时数据 + 速率 + 告警 的组合快照（供 API 展示/看门狗使用）。"""
        live = self.get(site_id, force=force)
        ev = self.evaluate(site_id, cfg=cfg, live=live, local_managed=local_managed)
        return {
            "live": live,
            "rates": ev.get("rates") or {},
            "alerts": ev.get("alerts") or [],
            "level": ev.get("level") or "ok",
        }
