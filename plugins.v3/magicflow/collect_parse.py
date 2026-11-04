"""魔流 · 页面解析层（collect_parse）—— 页面 / XML / JSON → 规整事实。

为什么单独一个文件（★ 19.10.31 从 ``collect.py`` 拆出）：

  ``collect.py`` 原本 2460 行，混着两件性质完全不同的事 ——
  **传输**（``Http`` / ``SiteView`` / ``Budget`` / 单飞 / PV 闸门，全是有状态的类）和
  **解析**（22 个 ``parse_*``，纯函数、零状态、零 I/O）。二者互不 import，界线是硬的。

  * 这一层是 **L0**：除 ``re / html / ET / .norm`` 外什么都不 import，尤其**不**碰
    ``.common``（``common`` 顶层 ``from app.schemas.types import ...``）→ 离线测试可以
    ``spec_from_file_location`` 直接加载，**不用再造假 ``app`` 模块**
    （此前 test_signin_parse / test_user_bar_parse / test_hr_reconcile 三处都得造）。
  * ``collect.py`` 仍是**唯一 import 面**：业务模块继续 ``from .collect import parse_xxx``，
    20 个调用点一行不改。

铁律 1（抓 + 解析归采集）不变，变的是「一个入口、两个文件」::

    采集（传输）collect.py  →  事实（解析）collect_parse.py  →  裁决  →  决策

本文件**只回答「页面说了什么」**：把 HTML / XML / JSON 折成定形的 ``dict`` / ``list`` /
``float``。「该不该」—— 算不算欠、要不要删、今天签不签 —— 一律不在这里判断（铁律 3）。
"""
from __future__ import annotations

import html
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from .norm import first_num


# ============================================================
# 数值 / 体积 / 文本 —— 一切解析的公共底座
# ============================================================
def _num(v: Any) -> Optional[float]:
    """宽松转 float：``None`` / ``""`` / 非数字一律返回 ``None``（不是 0.0）。

    为什么不用 0.0：站点 API 里「该字段没给」和「给了 0」是两件事 ——
    下载量缺失时分享率要判「无限」，填 0 会把 `ratio_inf` 算错。
    """
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


_SIZE_UNITS = {
    "B": 1.0, "K": 1024.0, "KB": 1024.0, "KIB": 1024.0,
    "M": 1024.0 ** 2, "MB": 1024.0 ** 2, "MIB": 1024.0 ** 2,
    "G": 1024.0 ** 3, "GB": 1024.0 ** 3, "GIB": 1024.0 ** 3,
    "T": 1024.0 ** 4, "TB": 1024.0 ** 4, "TIB": 1024.0 ** 4,
    "P": 1024.0 ** 5, "PB": 1024.0 ** 5, "PIB": 1024.0 ** 5,
}
_TAG_RE = re.compile(r"<[^>]+>")


def parse_size(text: Any) -> float:
    """'100.91GB' / '1,024.5 MB' → 字节数（float）。解析不出来返回 0.0。"""
    if text is None:
        return 0.0
    s = str(text).strip().replace(",", "").replace(" ", "")
    m = re.match(r"^([0-9]*\.?[0-9]+)\s*([KMGTP]?I?B?)$", s, re.IGNORECASE)
    if not m:
        return 0.0
    try:
        val = float(m.group(1))
    except (TypeError, ValueError):
        return 0.0
    unit = (m.group(2) or "B").strip().upper()
    mult = _SIZE_UNITS.get(unit)
    if mult is None:
        mult = _SIZE_UNITS.get(unit.rstrip("B")) if unit.endswith("B") else None
    if mult is None:
        mult = 1.0
    return val * mult


def _to_text(raw: Any) -> str:
    """去标签 + HTML 实体 → 纯文本（保留原换行结构成空格）。"""
    s = str(raw or "")
    s = _TAG_RE.sub(" ", s)
    s = (
        s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
        .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    )
    return re.sub(r"[ \t\r\f\v]+", " ", s)


def as_bool_arg(v: Any) -> Optional[bool]:
    """查询/表单参数是字符串 → 三态布尔（'': 未传 → None；'0'/'false'/'off' → False）。

    ★ 2026-10-31：从 ``features/reseed.py`` 搬到这里。原先它是 reseed Mixin 的
      staticmethod，却被 ``features/claim.py`` 跨文件 ``self._as_bool_arg`` 调用 ——
      正是 ``tools/check_self_calls.py`` 要拦的隐式耦合（读的人不知道这个方法归属谁）。
      纯字符串处理、无 self 状态，归 L1 解析层最合适，两边显式导入即可。
    """
    if v is None:
        return None
    s = str(v).strip().lower()
    if s == "":
        return None
    return s not in ("0", "false", "no", "off", "none")


_KW_STOP = re.compile(
    r"^(19|20)\d{2}$"
    r"|^(480|576|720|1080|2160)[pi]$"
    r"|^(web|web-?dl|webrip|bluray|blu-?ray|bdrip|brrip|hdtv|dvdrip|remux|uhd|hdcam)$"
    r"|^s\d{1,2}(e\d{1,3})?$"
    r"|^(x26[45]|h\.?26[45]|hevc|avc|av1|vp9)$"
    r"|^(aac|ac3|eac3|ddp?|dd\+|dts|flac|truehd|atmos|lpcm|opus)(\d(\.\d)?)?$"
    r"|^\d+(\.\d+)?(gb|mb|kb|g|m)$"
    r"|^(hdr|hdr10|hdr10\+|dv|dovi|10bit|8bit|hi10p|ma10p|sdr)$"
    r"|^(repack|proper|internal|readnfo|rerip|custom)$"
    r"|^(chs|cht|eng|jpn|kor|gb|big5|简|繁|中字|内封|内嵌|外挂)$",
    re.I,
)
_KW_LEAD_TAG = re.compile(r"^[\[\u3010][^\]\u3011]{0,60}[\]\u3011]\s*")
_CJK = re.compile(r"[\u4e00-\u9fff]")


def search_kw_en(title: str) -> str:
    """纯英文种名 → 站点搜索词：剥组标签后按 ``. _ 空格`` 切词，切到发布标记为止。

    存在的理由：``features/assets._clean_title_from_torrent`` **只认中文**（抽不到就返回
    空串），而实测 225 条待补资源里有 44 条纯英文名（``Toy Story``、
    ``The.Phoenician.Scheme.2025.1080p…``）—— 那一批不能没有搜索词。

    例：``Toy.Story.1995.2160p.UHD.BluRay…`` → ``Toy Story``；
        ``[VCB-Studio] Toaru Majutsu no Index III [Ma10p…`` → ``Toaru Majutsu no Index III``。
    """
    s = str(title or "").strip()
    if not s:
        return ""
    # 连续多个前缀标签（`[BDMV][Movie]`、`[组][字幕]名`）要全剥，只剥一层会残留 `[Movie]`
    for _ in range(3):
        _n = _KW_LEAD_TAG.sub("", s)
        if _n == s:
            break
        s = _n
    # `[`/`【` 也算分隔符：`… Index III [Ma10p_1080p]` 否则会把 `[Ma10p` 当词尾
    words: List[str] = []
    for t in [x for x in re.split(r"[.\s_\[\]\u3010\u3011()（）]+", s) if x]:
        if _KW_STOP.match(t):
            break
        words.append(t)
        if len(words) >= 6:
            break
    if words and _CJK.search(words[0]):
        # 防御：调用方本应先走中文清洗；万一传了中文名，只取首个中文段，别把英文尾巴带上
        return words[0]
    return " ".join(words).strip()


def parse_uid(raw: Any) -> Optional[int]:
    """从页面里抠 uid（NexusPHP 通用：userdetails.php?id=123 / userid=123）。"""
    s = str(raw or "")
    for pat in (r"userdetails\.php\?id=(\d+)", r"userid=(\d+)", r"/user/(\d+)"):
        m = re.search(pat, s)
        if m:
            try:
                return int(m.group(1))
            except (TypeError, ValueError):
                continue
    return None


def _is_free_promotion(cls: str, text: str) -> bool:
    """这一行是不是「免费」促销（**只认 2xFree 一类，不认 2x/50%**）。

    判据取 NexusPHP 的 class 名（``pro_free2up`` / ``twoupfree`` / ``2xfree`` / ``free2up``）
    再兜底整行文案里的「免费 / free」。``2x``（双倍上传）与 ``50%`` 折扣**不算**免费 ——
    它们的下载量仍要计，混进来会让「是否零下载」的判定整体失准。
    """
    blob = f"{cls} {text}".lower()
    if any(k in blob for k in ("pro_free2up", "twoupfree", "2xfree", "free2up")):
        return True
    return bool(re.search(r"\bfree\b|免费", blob))


def parse_leeching_rows(raw: Any) -> List[Dict[str, Any]]:
    """解析「正在下载」列表 → [{name, size, progress, free, ...}]。"""
    rows: List[Dict[str, Any]] = []
    try:
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", str(raw or ""), re.S | re.I):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)
            if len(cells) < 3:
                continue
            link = re.search(r'href="(details\.php\?id=\d+|/details\.php\?id=\d+)[^"]*"[^>]*>(.*?)</a>', tr, re.S | re.I)
            name = _to_text(link.group(2)) if link else ""
            if not name or len(name) < 2:
                continue
            cls = " ".join(re.findall(r'class="([^"]*)"', tr)) + tr
            size = 0.0
            progress = None
            for c in cells:
                txt = _to_text(c)
                if not size:
                    m = re.search(r"([0-9][0-9.,]*\s*[KMGTP]?i?B)\b", txt)
                    if m:
                        size = parse_size(m.group(1))
                m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", txt)
                if m and progress is None:
                    try:
                        progress = float(m.group(1))
                    except ValueError:
                        progress = None
            rows.append({
                "name": name.strip(),
                "size": size,
                "progress": progress,
                "free": _is_free_promotion(cls, tr),
            })
    except Exception:  # noqa: BLE001
        return []
    return rows

# ============================================================
# API 站 JSON 档案归一（各站字段名不一，折成统一 bar）
# ============================================================
def _pick_num(*sources: Any, keys: Tuple[str, ...]) -> Optional[float]:
    """按顺序从多个 dict 取第一个非 None 的数值（★ 15.16.2 API 档案字段归一）。"""
    for _s in sources:
        if not isinstance(_s, dict):
            continue
        for _k in keys:
            _v = _s.get(_k)
            if _v is not None:
                return _num(_v)
    return None


def normalize_api_profile(payload: Any) -> Optional[Dict[str, Any]]:
    """★ API 站档案归一（module-level，便于离线测试）——把各站 JSON 差异折成统一 bar。

    已知形态：
      * 馒头 / 叶PT：``memberCount{bonus,uploaded,downloaded,shareRate}`` + ``memberStatus{id,vip,warned}``
      * 野马PT：``data{id,bonus,level,status,promotionUploadSize,promotionDownloadSize}``
        （**无** shareRate → 用上传/下载现算；下载=0 → 分享率「无限」→ ``ratio_inf``）
    返回 ``None`` 表示载荷为空/不可识别。
    """
    if not isinstance(payload, dict) or not payload:
        return None
    d = payload
    cnt = d.get("memberCount") if isinstance(d.get("memberCount"), dict) else {}
    st = d.get("memberStatus") if isinstance(d.get("memberStatus"), dict) else {}
    up = _pick_num(cnt, d, keys=("uploaded", "promotionUploadSize", "upload", "uploadSize"))
    dl = _pick_num(cnt, d, keys=("downloaded", "promotionDownloadSize", "download", "downloadSize"))
    rt = _pick_num(cnt, d, keys=("shareRate", "ratio", "shareRatio"))
    if rt is None and up is not None:
        if dl and float(dl) > 0:
            rt = round(float(up) / float(dl), 4)
    return {
        "ok": True,
        "source": "api",
        "uid": str(st.get("id") or d.get("id") or ""),
        "ratio": rt,
        "ratio_inf": bool(rt is None and up and float(up) > 0 and not dl),
        "upload": up,
        "download": dl,
        "bonus": _pick_num(cnt, d, keys=("bonus",)),
        "seeding": _num(d.get("seeding")),
        "leeching": _num(d.get("leeching")),
        "bonus_per_hour": None,
        # ★ 19.11.21：等级字段各站不同——野马 data.level / 馒头 data.role（PTD 同款）
        "level": _pick_num(d, keys=("level", "role")),
        "name": str(d.get("name") or ""),
        "created": str(d.get("createdDate") or st.get("createdDate") or ""),
        # ★ 7.17.0 账号保活：站点记录的「最后登入 / 最后浏览」（第三方工具的调用**不会**刷新它们）
        "last_login": str(st.get("lastLogin") or d.get("lastLogin") or ""),
        "last_browse": str(st.get("lastBrowse") or d.get("lastBrowse") or ""),
        "logged_in": str(d.get("status") or st.get("status") or "").upper()
        in ("CONFIRMED", "ENABLE", "ENABLED", "ACTIVE", "")
        and (bool(d) or bool(st)),
        "vip": bool(st.get("vip")),
        "warned": bool(st.get("warned") or st.get("leechWarn")),
    }

# ============================================================
# 用户栏（页头一眼能读到的事实：上传/下载/分享率/魔力/做种/H&R 计数）
# ============================================================
#: NexusPHP 用户栏里「等级」的常见写法（按可信度排序；都只取**标签内纯文本**）。
#  实测模板差异很大：老模板是 ``[<a href=userdetails...><font class='Color_UserBar'>Power User</font></a>]``，
#  新模板只有 ``<font class='Color_UserBar'>``，中文站有的写成「等级：骨灰」。
_LEVEL_PATTERNS = (
    r"class=['\"]Color_UserBar['\"][^>]*>\s*([^<]{1,40}?)\s*<",
    # 必须以 ``[`` 开头：用户栏里**用户名**那条链接长得一模一样（``欢迎回来, <a ...><b>名字</b>``），
    # 不加这个前缀约束会把用户名当成等级 —— 宁可空着也不能报错一个像真的值。
    r"\[\s*<a[^>]*userdetails\.php\?id=\d+[^>]*>\s*(?:<font[^>]*>|<b>)?\s*([A-Za-z\u4e00-\u9fa5][^<\[\]]{0,39})",
    r"(?:等级|級別|级别)\s*[：:]\s*(?:<[^>]+>\s*)*([^<\s][^<]{0,39})",
    # ★ 19.11.18：NPHP 等级图标（pic/class_N.gif）的 title/alt —— 部分模板首页用户栏
    #   就印等级图标（title 即等级名，与 PTD userdetails 取值同源）。src 含 class_
    #   是 NPHP 等级图标的强特征，避免把普通 tooltip 当等级。
    r"<img[^>]+src=['\"][^'\"]*class_[^'\"]*['\"][^>]*?title=['\"]([^'\"]{1,40})['\"]",
    r"<img[^>]+?title=['\"]([^'\"]{1,40})['\"][^>]*src=['\"][^'\"]*class_[^'\"]*['\"]",
)
#: 这些词长得像等级但不是等级（防止把「退出」「邀请」这类链接文本当等级；
#: ★ 19.11.18 真机 PT时间 实测「个人中心」被 Color_UserBar 模式误判成等级 —— 导航词进表）
_LEVEL_NOISE = (
    "退出", "登出", "logout", "登录", "login", "邀请", "invite", "设置", "消息",
    "个人中心", "控制面板", "签到", "勋章", "收藏", "任务", "搜索", "上传", "下载",
    "usercp", "profile", "home",
)


def parse_user_level(raw: Any) -> Optional[str]:
    """站点页面 → 用户等级文本（解不出返回 ``None``，**不猜**）。

    只从**已抓到的页面**里认，不额外请求 —— 等级不是能算出来的量（每站规则不同），
    拿不到就如实空着，让 UI 显示「未知」，而不是显示一个看起来像真的错误结论。
    """
    raw_s = str(raw or "")
    if not raw_s:
        return None
    for pat in _LEVEL_PATTERNS:
        for m in re.finditer(pat, raw_s, re.IGNORECASE):
            v = _to_text(m.group(1)).strip(" \t\r\n[]（）()")
            if not v or len(v) > 40:
                continue
            if any(n.lower() in v.lower() for n in _LEVEL_NOISE):
                continue
            return v
    return None


#: NexusPHP 用户详情页（``userdetails.php``）里「等级」行的行头写法
_LEVEL_ROW_LABELS = r"(?:用户)?(?:等级|等級|级别|級別|Class)"
#: 详情页行头单元格：``class="rowhead nowrap"``（**多 class**，carpt 实测）—— 必须按词匹配，
#: 不能写死 ``class="rowhead"``，否则整页都打不中。
_DETAIL_ROW_HEAD = r"<td[^>]*class=['\"][^'\"]*\brow(?:head|follow)\b[^'\"]*['\"][^>]*>"


def _detail_cell(raw_s: str, label_pat: str) -> Optional[str]:
    """详情页「行头标签 + 右侧单元格」→ 右侧单元格 inner HTML（打不中返回 ``None``）。

    实测 carpt 标准形态：``<td class="rowhead nowrap">等级</td><td class="rowfollow"><img title=…>``；
    行头格文本收尾支持 ``</td>`` / 冒号（部分模板「等级：」写在同一格里）。
    """
    m = re.search(
        _DETAIL_ROW_HEAD + r"\s*" + label_pat
        + r"\s*(?:</td>|：|:)[\s\S]{0,80}?<td[^>]*>([\s\S]{0,900}?)</td>",
        raw_s, re.IGNORECASE,
    )
    return m.group(1) if m else None


def parse_user_details(raw: Any) -> Dict[str, Any]:
    """NexusPHP 用户详情页（``userdetails.php?id=…``）→ 等级 / 做种积分 / 入站时间。

    ★ 19.11.18：抄 **PT-depiler** 的 NexusPHP userInfo 口径 —— 实测（carpt / hdtime /
    cyanbug / dstudio 快照）首页用户栏**根本不印等级**，等级图标只在详情页的
    「等级」行里：``<td class="rowhead">等级</td><td><img title="Power User">``。
    PTD 取的是 ``img`` 的 ``title`` 属性（NPHP 等级图标模板），这里同款：

      ① 行头（rowhead/rowfollow）文本命中「等级/等級/级别/Class」→ 取同行另一格；
      ② 格里 ``<img title=…>``（alt 兜底）→ 等级名；
      ③ 无 img → 格内纯文本（40 字内、过滤噪音）。

    做种积分 / 加入日期同页顺路取（升级要求要用）——数值一律取**格内纯文本**，
    不在整页上正则摸数字（行头格自带 ``width="99%"``，摸整页会把 99 当做种积分）。
    **解不出就 None，不猜**。
    """
    out: Dict[str, Any] = {"level": None, "seeding_bonus": None, "join_time": None}
    raw_s = str(raw or "")
    if not raw_s:
        return out
    # ── 等级行：PTD `td.rowhead:contains('等级') + td > img` → title ──
    cell = _detail_cell(raw_s, _LEVEL_ROW_LABELS)
    if cell is not None:
        img = re.search(r"<img[^>]+?title=['\"]([^'\"]{1,40})['\"]", cell, re.IGNORECASE)
        if not img:
            img = re.search(r"<img[^>]+?alt=['\"]([^'\"]{1,40})['\"]", cell, re.IGNORECASE)
        if img:
            out["level"] = _to_text(img.group(1)).strip() or None
        else:
            # ★ 19.11.21：PT时间真机等级在 `<b class="fcr" title="(幼儿园)User">`（PTD
            #   pttime 同款 `td > b` 的 title 属性）——img 之后先认内联标签的 title。
            ttl = re.search(r"<(?:b|font|span)[^>]*?title=['\"]([^'\"]{1,40})['\"]",
                            cell, re.IGNORECASE)
            if ttl:
                out["level"] = _to_text(ttl.group(1)).strip() or None
            else:
                # 纯文本兜底只取第一个链接/换行**之前**的片段（PT时间格里跟了一串
                # 「🩺校验等级 加群参考…」导航文案，整格剥标签会超长被误扔）。
                head = re.split(r"<(?:a|br)\b", cell, maxsplit=1, flags=re.IGNORECASE)[0]
                txt = re.sub(r"<[^>]+>", " ", head)
                txt = _to_text(txt).strip(" \t\r\n[]（）()·|")
                if txt and len(txt) <= 40:
                    out["level"] = txt or None
    # ── 做种积分：PTD createUserBonusSelectorFn(["做种积分", ...]) 口径 ──
    cell = _detail_cell(raw_s, r"(?:做种积分|做種積分|保种积分|Seeding Points)")
    if cell is not None:
        txt = _to_text(re.sub(r"<[^>]+>", " ", cell)).replace(",", "")
        out["seeding_bonus"] = first_num(r"([0-9]+(?:\.[0-9]+)?)", txt)
    if out["seeding_bonus"] is None:
        # ★ 19.11.21：学校真机做种积分在**嵌套表**里（`<strong>做种积分</strong>: 24379.8`，
        #   PTD 第二选择器 `td.rowfollow:contains('做种积分')` 同场景），行头行匹配不到。
        #   锚定标签后紧跟数字：「做种积分自2020年…」这类注释里的年份**不会**被吃
        #   （标签后必须是收尾标签/冒号/空白再跟数字，"自"直接拦掉）。
        m = re.search(
            r"(?:做种积分|做種積分|保种积分|Seeding Points)"
            r"(?:</\w+>)?\s*[:：]?\s*(?:<[^>]+>\s*)*([0-9][0-9,]*(?:\.[0-9]+)?)",
            raw_s)
        if m:
            try:
                out["seeding_bonus"] = float(m.group(1).replace(",", ""))
            except (TypeError, ValueError):
                pass
    # ── 加入日期：PTD joinTime 同款行头 ──
    cell = _detail_cell(raw_s, r"(?:加入日期|入站日期|Join\s*date)")
    if cell is not None:
        txt = _to_text(re.sub(r"<[^>]+>", " ", cell)).strip()
        # PTD：`query.split(" (")[0]` —— 括号里的相对时间丢掉
        out["join_time"] = txt.split(" (")[0].strip() or None
    return out


def parse_user_bar(raw: Any) -> Dict[str, Any]:
    """解析站点用户栏页（NexusPHP ``index.php``）→ 规整事实。

    一次抓全：分享率 / 上传 / 下载 / 当前做种 / 当前下载 / 时魔 / 现魔力 / uid / 登录态。
    """
    text = _to_text(raw)
    raw_s = str(raw or "")
    out: Dict[str, Any] = {
        "ratio": None,
        "ratio_inf": False,
        "upload": None,
        "download": None,
        "seeding": None,
        "leeching": None,
        "bonus_per_hour": None,
        "bonus": None,
        "uid": parse_uid(raw_s),
        # ★ 19.11.16：等级（站点域的事实，算不出来 → None，不拿推算值冒充）
        "level": parse_user_level(raw_s),
        "logged_in": bool(
            re.search(r"logout\.php|退出|我的分享率|魔力值", raw_s)
        ) and not re.search(r'name="password"', raw_s),
    }
    # ★ 15.16.1：分隔符**可选**（部分模板「分享率 1.202」不带冒号，旧正则直接漏掉比例/上传/下载）。
    val = first_num(r"分享率\s*[：:]?\s*([0-9]+(?:\.[0-9]+)?)", text)
    if val is not None:
        out["ratio"] = val
    elif re.search(r"分享率\s*[：:]?\s*(?:无限|无穷|∞)", text):
        # 下载量为 0 时站点显示「无限」——这是**有效事实**，必须与「没解析出来」区分
        out["ratio_inf"] = True
    m = re.search(r"上传(?:量)?\s*[：:]?\s*([0-9][0-9.,]*\s*[KMGTP]?I?B)", text, re.IGNORECASE)
    if m:
        out["upload"] = parse_size(m.group(1))
    m = re.search(r"下载(?:量)?\s*[：:]?\s*([0-9][0-9.,]*\s*[KMGTP]?I?B)", text, re.IGNORECASE)
    if m:
        out["download"] = parse_size(m.group(1))
    val = first_num(r"魔力值?\(?\s*([0-9][0-9.,]*)\s*魔力?\s*/\s*(?:小时|時|h)", text)
    if val is None:
        val = first_num(r"每小时\s*([0-9][0-9.,]*)\s*个?魔力", text)
    if val is not None:
        out["bonus_per_hour"] = val
    _m = re.search(r"魔力值?\([^)]*\)", text)
    val = None
    if _m:
        val = first_num(r"[^0-9]{0,40}?([0-9][0-9,]*(?:\.[0-9]+)?)", text[_m.end():])
    if val is None:
        val = first_num(r"魔力值[^0-9]{0,30}?([0-9][0-9,]*(?:\.[0-9]+)?)", text)
    if val is None:
        # ★ 15.16.1：魔力值**别名**（各站自定义币名：财神「元宝」/ 蟹黄堡「蟹币值」/ 金币…）。
        #   要求数字带千分位或小数（≥3 字符）→ 避开「签到得金元宝] … 0(0)」这类误命中。
        val = first_num(
            r"(?:元宝|蟹币值?|金币|魔力币)[^0-9]{0,30}?([0-9][0-9,]{2,}(?:\.[0-9]+)?)", text
        )
    if val is not None:
        out["bonus"] = val
    m = re.search(r"title\s*=\s*[\"']?(?:当前做种|做种中|做种)[\"']?[^>]*>[^<]*</font>?\s*([0-9]+)", raw_s)
    if m:
        out["seeding"] = int(m.group(1))
    m = re.search(r"title\s*=\s*[\"']?(?:当前下载|下载中)[\"']?[^>]*>[^<]*</font>?\s*([0-9]+)", raw_s)
    if m:
        out["leeching"] = int(m.group(1))
    if out["seeding"] is None:
        val = first_num(r"⬆\s*([0-9]+)", text)
        if val is None:
            val = first_num(r"(?:做种中|正在做种|做种)[：:]?\s*([0-9]+)\s*(?:个|条)?", text)
        if val is not None:
            out["seeding"] = int(val)
    if out["leeching"] is None:
        val = first_num(r"⬇\s*([0-9]+)", text)
        if val is None:
            val = first_num(r"(?:下载中|正在下载)[：:]?\s*([0-9]+)\s*(?:个|条)?", text)
        if val is not None:
            out["leeching"] = int(val)
    # ★ 17.2.2：H&R 计数（用户栏页头）——形态「H&R: [考核中/未完成/上限]」。
    #   ① ``assessing`` 考核中：仍在考核窗口内（计时中）；**到期没做够就记一条 ``unfinished``**；
    #   ② ``unfinished`` 未完成：欠账成立 —— **它达到 ``limit`` 时账号就被禁用**（封号判据看 y，不看 x+y）；
    #   ③ ``limit`` 上限：**未完成数达到该数即禁用账号**（非「配额」，是封号线）。实证 Depth Studio=10，
    #      与其 rules.php 原文「H&R 记录为 10 时账号将被禁用」一致；聆音=15；学校页头只有
    #      ``H&R: 0/0``（不给第三个数）→ ``limit=None``，**不伪造 0**。
    #   这里只采事实、不做判断（禁用线预警由健康检查 H7 负责）。
    #   口径：页面没有这一栏 → ``None``（**不等于 0**）；有栏但解不出数字 → 只留 ``raw``
    #   （供健康检查区分「采集没读懂」与「确实没有」）；只有单个数（形态罕见）→ 归入
    #   ``unfinished``（**保守**：宁可早报禁用线，也不把欠账读没）。
    #   ★ 17.2.2 收口（2026-10-14 真机取证，修三处实机漏读/误报）：
    #   ① cyanbug.net 页头**没有这一栏**，只剩模板注释 ``<!-- H&R -->`` → 必须先剥 HTML 注释，
    #      否则注释被当成「有栏但没读懂」，H7 误报 warning；
    #   ② cspt.top 形态 ``[H&R]:``——标签在 ``R`` 后多一个右括号才跟冒号，旧正则整条漏（真机漏读）；
    #   ③ 计数数字可能被 ``<font>`` 切开（``0/<font color="red">0</font>/15``）→ 先去标签再匹配；
    #   ④ 真栏必挂 ``myhr.php`` 链接（各站实证）→ 只留 raw 的兜底**要求上下文含 myhr**，
    #      免得把导航文案/占位符当计数。
    out["hr"] = None
    _hraw = re.sub(r"<!--.*?-->", " ", f"{raw_s or ''}\n{text or ''}", flags=re.DOTALL)
    _hsrc = re.sub(r"\s+", " ", re.sub(r"<[^>]{0,200}>", " ", _hraw))  # 去标签 + 压空白
    _hrlab = r"H\s*&\s*R\s*[\])]?\s*[：:]?"  # 标签尾部容忍 ``]``/``)``（[H&R]: 形态）
    _mhr = re.search(
        rf"{_hrlab}\s*[\[(]?\s*(\d+)\s*/\s*(\d+)\s*(?:/\s*(\d+))?\s*[\])]?",
        _hsrc, re.IGNORECASE,
    )
    if _mhr:
        out["hr"] = {
            "raw": " ".join(_mhr.group(0).split())[:40],
            "assessing": int(_mhr.group(1)),
            "unfinished": int(_mhr.group(2)),
            "limit": int(_mhr.group(3)) if _mhr.group(3) else None,
        }
    else:
        _mhr1 = re.search(rf"{_hrlab}\s*[\[(]?\s*(\d+)\s*[\])]?", _hsrc, re.IGNORECASE)
        if _mhr1:
            out["hr"] = {"raw": " ".join(_mhr1.group(0).split())[:40],
                         "assessing": None, "unfinished": int(_mhr1.group(1)), "limit": None}
        else:
            _mr = re.search(r"H\s*&\s*R[^\n]{0,60}", _hraw, re.IGNORECASE)
            _mctx = _hraw[max(0, _mr.start() - 80):(_mr.end() + 80)] if _mr else ""
            if _mr and "myhr" in _mctx.lower():  # 只有真栏（挂在 myhr.php 上）才留 raw
                out["hr"] = {"raw": " ".join(_mr.group(0).split())[:40],
                             "assessing": None, "unfinished": None, "limit": None}
    if out["ratio"] in (None, 0.0) and (out["upload"] or 0) > 0 and (out["download"] or 0) > 0:
        out["ratio"] = round(float(out["upload"]) / float(out["download"]), 3)
    return out

# ============================================================
# 签到结果（★ 19.2.3 判据：以站点回显为准，读不到就 ambiguous，绝不猜成功）
# ============================================================
# 签到结果特征
# ★ 19.2.3 签到判据修正：**以站点「签到状态/记录」为准，不再「没识别到就算成功」**。
#   铁证（2026-10-16）：通用路径多站记录写着「签到成功」，可本函数根本产不出该文案 → 假成功。
#   现约定：
#     1) 明确读到「已签」记录（NexusPHP 标准回显）→ signed=True；
#     2) 页面是**未签态**（「待签到 / 立即签到 / 未签到 / is-pending」）→ signed=False（未签，非失败）；
#     3) 什么都读不到（异常页 / 空页 / 抓错页）→ **ambiguous=True**（不再默认成功）。
SIGNED_RE = re.compile(r"已得\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:个)?魔力")
# 「今日已签」类回显（NexusPHP 标准）+ 与专用处理器口径对齐（ttg/tjupt/hdsky/pttime 认这些）
#   ★ 19.2.3 加固（2026-10-17）：剔除 `每日签到` 与裸 `已签` —— 它们不是「已签事实」，是
#     **页面常驻文案**（导航栏 / 板块标题 / 历史表头都可能出现）。实测铁证：未签页只因导航含
#     「每日签到」四个字就命中旧表 → 记「今日已签到」= 假成功。此处只收**整短语**，不收半截词；
#     半截语义（如 pttime 的「今日已签」）另列整词，不靠子串兜。
SIGNED_TEXTS = (
    "签到成功", "已签到", "签到已得", "签到已得魔力",
    "今日已签到", "已经签到", "今天已签到", "无需再签", "您今天已签到", "已签到过",
    "今日已签", "今天已签", "已经签过",
)
# ★ 未签态：页面明确在**要你去签**（而非已签）→ 直接判「未签」，压过任何肯定文案
#   （治 dstudio 那种页 `<h1>` 固定写「签到成功」的误报）。
UNSIGNED_TEXTS = ("待签到", "立即签到", "未签到", "尚未签到", "is-pending")
# ★ 弱未签判据（原始 HTML，19.2.3 加固）：摆着裸「签到」**提交控件** = 站方在等你签
#   （NexusPHP 标准未签页的 form）。只认 `<input>/<button>` 控件，**不认 `<a>` 导航链接**
#   （已签页导航里仍可能留「签到」入口）。故它排在弱成功判据**之后**：只要页面给得出任何
#   已签回显/记录，就不因这个控件翻案（否则会把真成功记成未签、白刷 PV）。
UNSIGNED_CTRL_RE = re.compile(
    r"<(?:input|button)[^>]*\bvalue\s*=\s*[\"']?\s*签到\s*[\"']?"
    r"|<(?:input|button)[^>]*>\s*签到\s*<",
    re.I,
)
LOGIN_HINT_RE = re.compile(r"login\.php|name=\"password\"|登录|登陆")
# ★ 19.2.3：**标题即登录页**。部分 NexusPHP 站 cookie 失后 ``attendance.php`` 返回的登录页
#   不含 ``login.php``/``name="password"`` 字面（只 title 写「登录」）→ 旧判据漏判 → 掉兜底假成功。
#   铁证（2026-10-16，财神/高清时间）：早上 cookie 已失效却报「签到成功」。
LOGIN_TITLE_RE = re.compile(r"<title>[^<]*(登录|登入|簽到登录|login)\s*[-–—]?\s*(Powered by|::)?", re.I)
PV_LIMIT_RE = re.compile(r"访问次数已达上限|今日访问次数")


def parse_signin(raw: Any) -> Dict[str, Any]:
    """解析签到页 → {ok, signed, already, bonus, cookie_dead, pv_limited, ambiguous, message}。

    ★ 19.2.3：**未识别到就返回 ambiguous（不再默认 signed=True）**。上层的 recorded
    成功只认「明确读到已签记录」这一种；其余交给 signin.py 记为「未识别（建议手动确认）」。

    ★ 19.2.3 加固（2026-10-17）判据顺序 —— **强到弱，互相不越权**：
      ① 强未签：`UNSIGNED_TEXTS`（待签到/未签到/…）→ 未签（压过一切肯定文案）；
      ② 强已签：`SIGNED_RE`（已得 N 魔力）→ 已签（记录证据，最硬）；
      ③ 弱已签：`SIGNED_TEXTS`（已签回显整短语）→ 已签；
      ④ 弱未签：`UNSIGNED_CTRL_RE`（裸「签到」提交控件）→ 未签；
      ⑤ 都读不到 → `ambiguous=True`（不猜成功）。
    """
    text = str(raw or "")
    flat = _to_text(text)
    if PV_LIMIT_RE.search(flat):
        return {"ok": False, "pv_limited": True, "message": "站点每日访问次数已达上限"}
    # Cookie 失效判据（★ 19.2.3 修正）。**顺序很关键**：先看「是否已登录」。
    #   铁证（2026-10-16）：财神/高清时间的 attendance.php 带 cookie 是**「签到」页且含 `logout.php`**
    #   （已登录）；裸抓ー时看到的重定向中间态才是「登录」页。若只看 title 含「登录」就判失效 →
    #   **把已登录的站误判成失效**（Master 原话：MP 那边没失效）。
    #   故：① 有 `logout.php`（登出链接 = 已登录）→ **绝不判失效**；
    #       ② 否则才看密码框 / login.php 等登录特征。
    _has_logout = "logout.php" in text
    cookie_dead = False
    if not _has_logout:
        cookie_dead = (
            bool(re.search(r'name="password"', text))
            or bool(re.search(r"<title>[^<]*(登录|登入|login)", text, re.I))
            or bool(LOGIN_HINT_RE.search(flat))
        )
    if cookie_dead:
        return {"ok": False, "cookie_dead": True, "message": "Cookie 已失效或未登录"}
    m = SIGNED_RE.search(flat)
    bonus = None
    if m:
        try:
            bonus = float(m.group(1).replace(",", ""))
        except ValueError:
            bonus = None
    # ★ 否定态优先：明确「待签到/立即签到」→ 未签（不给成功）
    if any(t in flat for t in UNSIGNED_TEXTS):
        return {
            "ok": False,
            "signed": False,
            "ambiguous": False,
            "bonus": bonus,
            "message": "未签到（页面显示待签到）",
        }
    # ★ 硬成功（19.2.3 加固）：回显「已得 N 魔力」= 有**记录证据**，比文案硬。
    #   它排在弱未签控件判据之前 —— 已签页若残留一个「签到」按钮，真成功不能被翻成未签。
    if m:
        return {
            "ok": True,
            "signed": True,
            "already": True,
            "bonus": bonus,
            "message": "今日已签到",
        }
    # ★ 弱成功：站点「已签」回显整短语（与专用处理器口径对齐：ttg/tjupt/hdsky/pttime 等）
    if any(t in flat for t in SIGNED_TEXTS):
        # `already` 只为**文案**（signin.py:446）：`签到成功` 是「本次刚签」，
        # 其余整短语（已签到/无需再签/今日已签…）都是「已签态」→ 文案记「今日已签到」。
        signed_already = any(t in flat for t in SIGNED_TEXTS if t != "签到成功")
        return {
            "ok": True,
            "signed": True,
            "already": signed_already,
            "bonus": bonus,
            "message": "今日已签到" if signed_already else "签到成功",
        }
    # ★ 弱未签（19.2.3 加固）：页面没有任何已签回显，却摆着裸「签到」提交控件 → 未签
    if UNSIGNED_CTRL_RE.search(text):
        return {
            "ok": False,
            "signed": False,
            "ambiguous": False,
            "bonus": bonus,
            "message": "未签到（页面显示待签到）",
        }
    # ★ 什么都读不到 → 不猜成功
    return {
        "ok": False,
        "signed": False,
        "ambiguous": True,
        "bonus": bonus,
        "message": "未识别到签到结果（页面可能异常，建议手动确认）",
    }

# ============================================================
# 「今日访问次数已达上限」拦截页 / 跨天时刻
# ============================================================
# 站点「每日访问次数已达上限」拦截页特征
PV_LIMIT_MARKERS = ("访问次数已达上限", "访问次数已达", "今日访问次数")
PV_BLOCK_GRACE = 600.0
def is_pv_limited(text: Any) -> bool:
    """页面是否就是「今日访问次数已达上限」的拦截页。"""
    t = str(text or "")
    if not t or len(t) > 2000:
        return False
    return ("访问次数已达上限" in t) or ("访问次数已达" in t and "上限" in t)


def next_day_ts(now: Optional[float] = None) -> float:
    """下一个本地凌晨（+宽限）的时间戳。"""
    t = float(now if now is not None else time.time())
    local = time.localtime(t)
    nxt = time.mktime(
        (local.tm_year, local.tm_mon, local.tm_mday, 0, 0, 0, local.tm_wday, local.tm_yday, -1)
    ) + 86400.0
    return nxt + PV_BLOCK_GRACE

# ============================================================
# passkey / 框架识别
# ============================================================
_PASSKEY_RE = re.compile(r"passkey=([0-9a-fA-F]{16,64})")
_HASH_RE = re.compile(r"(?:downhash|hash)=([0-9a-zA-Z]{8,64})")
_UID_RE = re.compile(r"[?&]id=(\d+)")
# ★ 5.12.0：不少 NexusPHP 站不把 passkey 写成 `passkey=xxx`，而是在个人页/导航里
# 以「密钥」这一行展示（值可能是 hex/字母数字，偶尔包在 <span> 里）→ 补一条容错抽法。
_KEY_LABEL_RE = re.compile(r"密钥|密鑰|Passkey|PassKey")
_ALNUM_RUN_RE = re.compile(r"[0-9a-zA-Z]{16,64}")


def _passkey_from_label(s: str) -> str:
    """从「密钥」标签后面的片段里抠出 passkey（先剥标签再取第一段字母数字）。"""
    for m in _KEY_LABEL_RE.finditer(s):
        frag = re.sub(r"<[^>]*>", " ", s[m.end(): m.end() + 400])
        hit = _ALNUM_RUN_RE.search(frag)
        if hit:
            return hit.group(0)
    return ""


def parse_passkey(raw: Any) -> Dict[str, Any]:
    """从浏览页/个人页抽 passkey / uid / downhash（长期事实）。"""
    s = str(raw or "")
    pk = _PASSKEY_RE.search(s)
    dh = _HASH_RE.search(s)
    uid = _UID_RE.search(s)
    pk_val = pk.group(1) if pk else _passkey_from_label(s)
    return {
        "passkey": pk_val,
        "downhash": dh.group(1) if dh else "",
        "uid": uid.group(1) if uid else "",
    }


def detect_framework(html: str, domain: str = "") -> Tuple[str, str]:
    """框架识别（NexusPHP / Gazelle / UNIT3D / M-Team …）→ (framework, evidence)。

    识别表本体在 ``sitecap``（站点能力库，属于「数据」），这里只做流水线调用，
    避免把能力表复制两份。
    """
    try:
        from .sitecap import detect_framework as _df  # noqa: WPS433

        return _df(html, domain)
    except Exception:  # noqa: BLE001
        return "", ""
# ------------------------------------------------------------
# H&R 记录页（``myhr.php``）→ 事实
#   铁律 1：解析归采集。这几行原在 ``features/hrbills.py``（19.10.30 搬回），
#   当时只把「抓」放进了 collect，「解析」留在了业务模块 → 半个遵守。
#   产出全是**事实**（站点说这颗种还欠多久），不含「算不算欠」的裁决。
# ------------------------------------------------------------

_MYHR_SIZE_RE = re.compile(r"([\d.]+)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB)", re.I)
# ★ 11.9.2："还需做种时间"列有两种渲染 —— 剩余 ≥1h 为 ``H:MM:SS``/``HH:MM:SS``，
#   剩余 <1h 为 ``MM:SS``（实测 CARPT：如 ``48:00``）。旧正则只认三段
#   ``H:MM:SS`` → 把 <1h 的行判成「布局不兼容」→ 整站 ``myhr`` 对账整页跳过。
#   放宽为「可选第三段」，两种都收。
_MYHR_NEED_RE = re.compile(r"^(\d+):([0-5]\d)(?::([0-5]\d))?$")
_MYHR_TID_RE = re.compile(r"details\.php\?id=(\d+)", re.I)
_MYHR_ID_RE = re.compile(r"<td[^>]*>\s*(\d{5,})\s*</td>", re.I)
_MYHR_MARKERS = ("myhr", "h&r", "hit and run", "hit-and-run", "details.php", "hr.php")


def _myhr_cell_text(cell: str) -> str:
    """单元格 → 纯文本（去标签 + 还原实体 + 压缩空白）。

    ★ 不复用本模块的 ``_to_text``：那个**不压 ``\\n`` 也不 strip**（它面向整页文本，
    要保留换行结构）。而单元格必须压掉换行，否则 ``_MYHR_NEED_RE`` 的 ``^...$``
    匹配不上「还需做种时间」→ 整页判成布局不兼容。两者语义不同，别合并。
    """
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(cell or "")))).strip()


def _myhr_row_segments(raw: str) -> Any:
    """定位 H&R 表并切出行（兼容嵌套表 / 行内嵌套 ``<table>``）。

    ★ 为什么不用「按 ``<tr>`` 嵌套层级切」：NexusPHP 把内容表嵌套在版式表的 ``<tr>``
    里 → 顶层行只剩少数几个，真正数据行全被包住。
    ★ 为什么不用「以链接为锚向前后找 <tr></tr>」：行内可能有多个 ``details.php?id=``
    链接（头像/用户名/引用）→ 会产生错行（实测 btschool 多出 tid=<uid> 的假行）。
    做法：**以表头行（含「还需做种时间」）为分界**，之后的 ``<tr>`` 按 ``</tr>`` 切开；
    只有同时拿到「还需做种时间」单元格 + ``details.php?id=`` 链接 + ≥ 3 个 ``<td>``
    的行才算数据行（其余表不会同时满足）。

    Returns:
        ``(rows, candidates)``：``candidates`` = 「看着像数据行但可能没解出来」的候选数
        （≥3 个 ``<td>`` + 标题链接）；两者不等 → 布局不兼容 → 调用方按不可识别处理。
    """
    raw = str(raw or "")
    m = re.search(r"<tr[^>]*>(?:(?!</tr>).)*还需做种时间(?:(?!</tr>).)*</tr>", raw, re.S)
    start = m.end() if m else 0
    rows: List[str] = []
    candidates = 0
    for seg in raw[start:].split("</tr>"):
        if "details.php?id=" not in seg:
            continue
        if len(re.findall(r"<td", seg, re.I)) < 3:
            continue
        candidates += 1
        cells = [_myhr_cell_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", seg, re.S | re.I)]
        if not any(_MYHR_NEED_RE.match(c) for c in cells):
            continue
        rows.append(seg)
    return rows, candidates


def parse_myhr_rows(text: Any) -> Optional[List[Dict[str, Any]]]:
    """NexusPHP ``myhr.php`` 页 → H&R 记录列表（**保守解析**）。

    ★ 语义（实测 CARPT / btschool）：行首 id = H&R 记录 id（CARPT）/ 种子 id（btschool）；
    真种子 id 在行内 ``details.php?id=<tid>``。列序（实测）：
    ``上传量 | 下载量 | 分享率 | 还需做种时间 | 下载完成时间 | 剩余考察时间 | 操作``。

    ★★ 两个已踩的坑（11.8.1 修）：
      1. 页面头部（用户名 / 新人考核公告）也含 ``details.php?id=<uid>`` 链接 → 必须靠
         「还需做种时间」单元格把这类噪声行剔掉，否则产生**假记录**（还会白拉 .torrent）；
      2. 行内有嵌套 ``<table>`` 时，``<tr[^>]*>(.*?)</tr>`` 非贪婪会**重复匹配**同一行
         （实测 CARPT 22 行 → 51 条）→ 改为按 ``</tr>`` 切分 + 取最近的 ``<tr`` + 按 tid 去重。

    Returns:
        ``None`` = **页面不可识别**（布局不兼容 / 登录页）→ 调用方整页跳过并退避；
        ``[]``   = 页面可识别但**无未完成记录**（= 无欠）；
        列表     = 逐条 ``{hr_id, tid, title, up_gb, down_gb, size_gb, need_left,
                   done_at, keep_left, ratio}``；``size_gb`` 是**站点口径的下载量**
                   （非种子体积，保留旧字段兼容）。
    """
    raw = str(text or "")
    if not raw.strip():
        return []
    low = raw.lower()
    rows: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    has_header = ("还需做种时间" in raw) or ("下载完成时间" in raw) or ("hr-table" in low)
    segs, candidates = _myhr_row_segments(raw)
    for seg in segs:
        if "details.php?id=" not in seg:
            continue
        mtid = _MYHR_TID_RE.search(seg)
        # ★ 取**最长锚文本**的链接 = 标题链接（行内可能有其他 link）
        best_id = ""
        best_txt = ""
        for ma in re.finditer(r"<a[^>]*details\.php\?id=(\d+)[^>]*>(.*?)</a>", seg, re.S | re.I):
            txt = _myhr_cell_text(ma.group(2))
            if len(txt) >= len(best_txt):
                best_txt, best_id = txt, ma.group(1)
        if not best_id and mtid:
            best_id = mtid.group(1)
        if not best_id:
            continue
        tid = best_id
        if tid in seen:
            continue
        cells = [_myhr_cell_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", seg, re.S | re.I)]
        need = ""
        for c in cells:
            if _MYHR_NEED_RE.match(c):
                need = c
                break
        if not need:
            continue          # 头部/公告/导航行 → 丢弃（不是 H&R 记录）
        seen.add(tid)
        mid = _MYHR_ID_RE.search(seg)
        hr_id = mid.group(1) if mid else ""
        title = best_txt
        if not title:
            mtitle = re.search(r"details\.php\?id=\d+['\"][^>]*>(.*?)</a>", seg, re.S | re.I)
            if mtitle:
                title = _myhr_cell_text(mtitle.group(1))
        if not title:
            title = re.sub(r"<[^>]+>", " ", seg).strip()[:120]
        up_gb = down_gb = 0.0
        ratio = done_at = keep_left = ""
        n_size = 0
        for c in cells:
            msz = _MYHR_SIZE_RE.fullmatch(c)
            if msz:
                n_size += 1
                try:
                    v = float(msz.group(1))
                    unit = msz.group(2).lower()
                    if unit.startswith("t"):
                        v *= 1024.0
                    elif unit.startswith("m"):
                        v /= 1024.0
                    elif unit.startswith("k"):
                        v /= (1024.0 * 1024.0)
                except Exception:  # noqa: BLE001
                    v = 0.0
                if n_size == 1:
                    up_gb = round(v, 3)
                elif n_size == 2:
                    down_gb = round(v, 3)
                continue
            if not ratio and n_size >= 1 and re.fullmatch(r"\d+(?:\.\d+)?", c):
                ratio = c
                continue
            if not done_at and re.match(r"\d{4}-\d{2}-\d{2}", c):
                done_at = c
                continue
            if not keep_left and re.fullmatch(r"\d+\s*天\s*\d{1,2}:\d{2}:\d{2}", c):
                keep_left = c
        rows.append({"hr_id": hr_id, "tid": tid, "title": title[:120],
                     "up_gb": up_gb, "down_gb": down_gb,
                     "size_gb": down_gb or up_gb,
                     "ratio": ratio, "need_left": need,
                     "done_at": done_at, "keep_left": keep_left})
    if candidates > len(rows):
        # ★ 守门：表区里还有「像数据行但没解出来」的候选（如标题被套在子表里）
        #   → 布局不兼容；宁可整页跳过（退避）也**绝不**当「无欠」。
        return None
    if rows:
        return rows
    if has_header:
        return []       # 表头在但无数据行（含全部已达标的情况）→ 无欠
    if any(mk in low for mk in _MYHR_MARKERS):
        return []   # 可识别但无记录（= 无欠）
    return None     # 不可识别 → 不当作「无欠」

# ------------------------------------------------------------
# 站点认领页（``claim.php``）→ 事实
#   铁律 1：解析归采集。原在 ``features/claim.py::_claim_parse_table``（19.10.30 搬回）。
#   表头驱动：兼容 11/12/13 列与学校 ``viewclaims`` 版式 —— 按列名映射，不按列序硬编码。
# ------------------------------------------------------------

_CLAIM_TID_RE = re.compile(r"detail\w*\s*\.php\?id=(\d+)")


def parse_claim_page(html_text: Any) -> Dict[str, Any]:
    """解析 NexusPHP 认领页（表头驱动，兼容 11/12/13 列与学校 viewclaims）。

    Returns:
        ``{"summary": {total, qualified, unqualified, next_settle}, "by_tid": {tid: {...}}}``；
        页面无表头 → ``{"summary": {}, "by_tid": {}}``（调用方据此判「不是认领页」）。
    """
    out: Dict[str, Any] = {"summary": {}, "by_tid": {}}
    text = str(html_text or "")
    m = re.search(r"本月认领总数：\s*(\d+).*?已达标：\s*(\d+).*?未达标：\s*(\d+)", text, re.S)
    if m:
        out["summary"] = {"total": int(m.group(1)), "qualified": int(m.group(2)),
                          "unqualified": int(m.group(3))}
    m = re.search(r"下次结算时间：\s*([0-9:\- ]+)", text)
    if m:
        out["summary"]["next_settle"] = m.group(1).strip()

    def clean(x: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x or "")).strip()

    def hours_of(v: str) -> float:
        tm = re.match(r"(?:(\d+)天)?\s*(\d+):(\d+):(\d+)", v or "")
        if not tm:
            return 0.0
        return (int(tm.group(1) or 0) * 24 + int(tm.group(2))
                + int(tm.group(3)) / 60.0 + int(tm.group(4)) / 3600.0)

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S)
    header = None
    for tr in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        vals = [clean(c) for c in cells]
        if any("种子名称" in v for v in vals) and any(
            ("认领时间" in v or "添加时间" in v) for v in vals
        ):
            header = vals
            break
    if not header:
        return out
    idx: Dict[str, int] = {}
    for i, name in enumerate(header):
        # ★ 19.10.58：表头单元格可能被外层 ``<tr>`` 的 ``<td>`` 吞掉——财神 / 咖啡的认领页
        #   把整个「本月认领进度统计」面板塞进第一格，清理后变成
        #   ``📊 本月认领进度统计 本月认领总数：2 个 … ID``，``n == "ID"`` 永远不成立
        #   → ``claim_id`` 恒为空 → 「放弃认领」拿不到站点认领记录 id（实测财神两行全空）。
        #   列名一律取**最后一个空白分隔 token**（干净表头本来就只有一个 token，行为不变）。
        n = (name.strip().split() or [""])[-1]
        if n == "ID":
            idx["id"] = i
        elif n == "用户":
            idx["user"] = i
        elif "种子名称" in n:
            idx["title"] = i
        elif "种子大小" in n or n == "大小":
            idx["size"] = i
        elif "种子存活" in n:
            idx["alive"] = i
        elif "认领时间" in n or "添加时间" in n:
            idx["claimed_at"] = i
        elif "上次结算" in n:
            idx["last_settle"] = i
        elif "本月做种" in n or n == "做种时间":
            idx["seed_time"] = i
        elif "本月上传" in n or n == "上传":
            idx["upload"] = i
        elif "是否达标" in n:
            idx["qualified"] = i
        elif "预计奖励" in n or "获得魔力" in n:
            idx["reward"] = i
        elif "下次结账" in n:
            idx["next_settle"] = i

    def at(vals: Any, key: str, default: Any = "") -> Any:
        i = idx.get(key)
        return vals[i] if i is not None and i < len(vals) else default

    for tr in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) < len(header):
            continue
        vals = [clean(c) for c in cells]
        # ★ 19.10.58：表头行本身也会走到这里（它的 td 数正好等于 header 数），
        #   而咖啡表头的第一格被外层 td 吞进了 `userdetails.php?id=31565` ——
        #   `_CLAIM_TID_RE` 会把 **uid 当成 torrent_id** 造出一条幽灵认领行。
        #   表头里必然含「种子名称」，直接跳掉。
        if any("种子名称" in v for v in vals):
            continue
        title_cell = at(cells, "title", "")
        tid_m = _CLAIM_TID_RE.search(title_cell) or _CLAIM_TID_RE.search(tr)
        if not tid_m:
            continue
        seed_time = at(vals, "seed_time")
        reward = at(vals, "reward")
        reward_num = None
        rm = re.search(r"([\d,]+)", reward)
        if rm:
            reward_num = float(rm.group(1).replace(",", ""))
        qv = at(vals, "qualified")
        # ★ 19.10.58：达标与否改成**三态**，因为「放弃认领」要按它判「能不能安全放弃」：
        #   True  = 站点写「是/Yes」→ 本月已达标，放弃只失去 ×2 奖励；
        #   False = 站点写「No/否」或该列存在但空 → 未达标（放弃可能扣罚）；
        #   None  = 站点**既没有**「是否达标」列也没有「预计奖励」列 → 无法判断，
        #           必须让「算不出来」向上可见（铁律 8），不能在调用方静默当成未达标。
        if "qualified" in idx:
            qualified: Optional[bool] = (qv.strip().lower() in ("yes", "是", "达标", "√", "y"))
        elif reward_num is not None:
            qualified = reward_num > 0
        else:
            qualified = None
        out["by_tid"][tid_m.group(1)] = {
            "claim_id": at(vals, "id"),
            "title": clean(title_cell),
            "size": at(vals, "size"),
            "alive": at(vals, "alive"),
            "claimed_at": at(vals, "claimed_at"),
            "last_settle": at(vals, "last_settle"),
            "next_settle": at(vals, "next_settle"),
            "seed_time": seed_time,
            "seed_hours": round(hours_of(seed_time), 2),
            "upload": at(vals, "upload"),
            "qualified": qualified,
            "reward": reward,
            "reward_num": reward_num,
        }
    if not out["summary"]:
        out["summary"] = {"total": len(out["by_tid"])}
        first = next(iter(out["by_tid"].values()), None)
        if first and first.get("next_settle"):
            out["summary"]["next_settle"] = first["next_settle"]
    return out

# ------------------------------------------------------------
# 站点 RSS → 事实
#   铁律 1：解析归采集。原在 ``features/rss.py::_rss_parse``（19.10.30 搬回）。
#   ★ 与 ``reseed._rss_fetch`` 内联的 RSS 解析**不是同一件事**：那份为入库（库表口径
#     ``{tid,size(GB),downhash,download_url,pub_at}``），这份为 UI 展示（含 promo/做种数）。
#     输出契约不同 → 只搬位置、不强行合并成同一个函数。
# ------------------------------------------------------------


def parse_rss_items(xml_text: str, limit: int = 30) -> List[Dict[str, Any]]:
    """站点 RSS → 展示用条目列表（``ET`` 解析，含促销/做种数启发式提取）。

    体积优先取 ``<enclosure length>``（字节串）；没有则从标题里的 ``[1.5 GB]`` 反推。
    promo / seeders / leechers 全部从「标题 + 描述前 1200 字」正则提取 —— 各站格式不一，
    取不到就留空，不猜。解析失败（非 XML）直接抛 —— 调用方按「不是 RSS」处理。
    """
    root = ET.fromstring(xml_text)
    out: List[Dict[str, Any]] = []
    promo_re = re.compile(r"[\[\(【]\s*(免费|Freeleech|Free|2x|2X|50%|30%|70%)\s*[\]\)】]", re.I)
    seed_re = re.compile(r"(?:seeders?|做种(?:数|者)?|种(?:子)?数)\D{0,8}(\d+)", re.I)
    leech_re = re.compile(r"(?:leechers?|下载(?:数|者)?|完成(?:数)?)\D{0,8}(\d+)", re.I)
    for it in root.iter("item"):
        def _g(tag: str) -> str:
            el = it.find(tag)
            return (el.text or "").strip() if el is not None else ""
        size = ""
        enc = it.find("enclosure")
        if enc is not None:
            size = str(enc.get("length") or "")
        if not size:
            # 有些站把体积写进标题（M-Team 的 [大小] 格式）
            msz = re.search(r"(\d+(?:\.\d+)?)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB)", _g("title"), re.I)
            if msz:
                _num = float(msz.group(1))
                _unit = msz.group(2).upper().rstrip("IB").rstrip("B")
                _mult = {"T": 1024 ** 4, "G": 1024 ** 3, "M": 1024 ** 2, "K": 1024}.get(_unit[:1], 0)
                if _mult:
                    size = str(int(_num * _mult))
        title = _g("title")
        desc = _g("description")
        blob = f"{title} {desc[:1200]}"
        m = promo_re.search(blob)
        ms = seed_re.search(blob)
        ml = leech_re.search(blob)
        out.append({
            "title": title,
            "link": _g("link"),
            "guid": _g("guid"),
            "pub": _g("pubDate"),
            "category": _g("category"),
            "comments": _g("comments"),
            "size": size,
            "enclosure": (enc.get("url") if enc is not None else "") or "",
            "promo": m.group(1) if m else "",
            "seeders": int(ms.group(1)) if ms else None,
            "leechers": int(ml.group(1)) if ml else None,
            "desc": desc[:200],
        })
        if len(out) >= limit:
            break
    return out


def parse_rss_torrents(xml_text: Any) -> List[Dict[str, Any]]:
    """站点 RSS → **入库口径**的种子目录行（正则切 ``<item>``，不依赖 XML 良构）。

    ★ 与 ``parse_rss_items`` 的区别：那份走 ``ET`` 且面向 UI 展示（promo/做种数）；
    这份走正则、面向 ``mf_rss`` 落库（``{tid, title, size(GB), downhash, download_url, pub_at}``）。
    两份**输出契约不同，故意不合并** —— 合并只会变成一堆可选字段。
    ★ 兼容两种 enclosure 形态：``download.php?id=X&downhash=...``（HDDolby 类）
    与带 passkey/token 的直链。

    原在 ``features/reseed.py::_rss_fetch`` 内联（19.10.30 搬回 collect）。
    ⚠ ``size`` 的单位换算是**原样搬运**（``KB`` 的乘数大于 ``MB``，看着像历史笔误），
    本次只搬位置不改口径 —— 要修另开一轮，别混在搬迁里。
    """
    out: List[Dict[str, Any]] = []
    text = str(xml_text or "")
    for mt in re.finditer(r"<item>.*?</item>", text, flags=re.S):
        item = mt.group(0)
        m_tid = re.search(r"torrents\.php\?id=(\d+)|details\.php\?id=(\d+)|download\.php\?id=(\d+)", item)
        tid = (m_tid.group(1) or m_tid.group(2) or m_tid.group(3)) if m_tid else None
        if not tid:
            continue
        title = ""
        m_t = re.search(r"<title>(.*?)</title>", item, re.S)
        if m_t:
            title = m_t.group(1).strip()
        size = None
        m_s = re.search(r"<size>([\d.]+) ?(GB|MB|KB|B)?</size>", item, re.I)
        if m_s:
            try:
                sz = float(m_s.group(1))
                unit = (m_s.group(2) or "B").upper()
                mult = {"B": 1, "KB": 1024 ** 2, "MB": 1024, "GB": 1}.get(unit, 1)
                size = sz * mult / (1024 ** 3)
            except ValueError:
                size = None
        pub_at = None
        m_p = re.search(r"<pubDate>(.*?)</pubDate>", item, re.S)
        if m_p:
            from email.utils import parsedate_to_datetime
            try:
                pub_at = parsedate_to_datetime(m_p.group(1).strip()).timestamp()
            except Exception:  # noqa: BLE001
                pub_at = None
        downhash = ""
        m_dh = re.search(r"download\.php\?id=\d+&(?:amp;)?downhash=([0-9a-zA-Zx]+)", item)
        if m_dh:
            downhash = m_dh.group(1)
        m_enc = re.search(r"<enclosure[^>]+url=['\"]([^'\"]+)['\"]", item, re.I)
        download_url = m_enc.group(1) if m_enc else ""
        if "&amp;" in download_url:
            download_url = download_url.replace("&amp;", "&")  # XML 实体回退真参
        out.append({
            "tid": tid, "title": title, "size": size,
            "downhash": downhash, "download_url": download_url, "pub_at": pub_at,
        })
    return out


# ============================================================
# 种子详情页 → 一次性下载链
#   铁律 1：解析归采集。原在 ``features/reseed.py::_reseed_details_link`` 内联
#   （19.10.31 搬回）。**只搬 xpath 那一段**：抓取留在 reseed —— 它用的是
#   **云端连接**（IYUU 那套 conn）里的 cookie/ua/referer，不是站点表里存的
#   cookie，换门面就等于换掉登录态来源，那是行为变更不是重构。
# ============================================================
# 详情页里下载链的抠法（顺序即优先级；与隔壁 IYUU 插件 `_torrent_xpaths` 逐条一致）
DETAIL_LINK_XPATHS: Tuple[str, ...] = (
    "//form[contains(@action, 'download.php?id=')]/@action",
    "//a[contains(@href, 'download.php?hash=')]/@href",
    "//a[contains(@href, 'download.php?id=')]/@href",
    "//a[@class='index'][contains(@href, '/dl/')]/@href",
)
# 原因码（本层**不产中文文案**：HTTP 状态只有抓取方知道，文案由它拼）
DETAIL_LINK_OK = ""
DETAIL_LINK_PARSE_FAILED = "parse_failed"
DETAIL_LINK_EMPTY_HTML = "empty_html"
DETAIL_LINK_NO_HIT = "no_xpath_hit"


def parse_detail_download_link(text: str, base: str = "",
                               xpaths: Tuple[str, ...] = DETAIL_LINK_XPATHS,
                               ) -> Tuple[Optional[str], str, str]:
    """种子详情页 HTML → ``(下载链, 原因码, 异常原文)``。

    为什么需要它：HDDolby / HDChina 这类站的下载链带 **per-tid 一次性令牌**
    （``download.php?id=…&hash=…``），那串 ``hash`` 是站点详情页里的，不是账号级
    配置，拼不出来 ⇒ 只能带 cookie 进详情页抠出来。命中时返回的链一律**绝对化**。

    · 原因码四选一（``DETAIL_LINK_*``），命中时是空串 ``DETAIL_LINK_OK``。
    · 第三条只在解析抛异常时非空 —— 「lxml 没装」和「HTML 畸形到建不出树」只有
      靠这条原文才分得开，别把它吞成空串。
    · lxml **故意延迟导入**：本模块要在没有 ``app.*`` 的离线环境里能 import，而
      lxml 是三方包；与 ``features/reseed.py`` 原实现同口径（那里也是函数内导入）。
    """
    try:
        from lxml import etree  # noqa: WPS433
    except Exception as err:  # noqa: BLE001
        return None, DETAIL_LINK_PARSE_FAILED, str(err)
    try:
        root = etree.HTML(text)
    except Exception as err:  # noqa: BLE001
        return None, DETAIL_LINK_PARSE_FAILED, str(err)
    if root is None:
        return None, DETAIL_LINK_EMPTY_HTML, ""
    for xp in xpaths:
        try:
            got = root.xpath(xp)
        except Exception:  # noqa: BLE001
            continue          # 单条 xpath 引擎差异不该终止整轮
        if not got:
            continue
        link = str(got[0] or "").strip()
        if not link:
            continue
        if link.startswith("http"):
            return link, DETAIL_LINK_OK, ""
        if not base:
            # 死分支：调用方（reseed._reseed_details_link）在抓之前就要求 base 非空。
            #   留着是为了本函数被直接调用时不产 ``/download.php?...`` 这种畸形链。
            return link, DETAIL_LINK_OK, ""
        return f"{base}/{link.lstrip('/')}", DETAIL_LINK_OK, ""
    return None, DETAIL_LINK_NO_HIT, ""


# ============================================================
# 站内短讯（收件箱 / 欢迎短讯 / 正文抽取）
# ============================================================
# 「欢迎来**」主题特征（NexusPHP 注册欢迎短讯）
_WELCOME_SUBJ_RE = re.compile(r"欢迎|welcome|注册成功|新人", re.I)
_MAIL_ROW_RE = re.compile(
    r"viewmessage(?:&amp;|&)id=(\d+)[^>]*>\s*([^<]{0,80})", re.I
)
# 邮件正文的**结束**标记（注意：不能把紧随主题的「收件箱/发件箱」表头当结尾）
_MAIL_FOOT_RE = re.compile(r"删除.*转发|转发短讯|短讯箱|\[\s*删除\s*\]")
# 邮件页面里的界面噪声行（表头/时间戳），正文里不该有
_MAIL_NOISE = {"收件箱", "发件箱", "自", "日期", "系统", "搜索短讯", "短讯箱", "MESSAGES", "短讯"}
_MAIL_TIME_RE = re.compile(
    r"^(?:\d+\s*(?:天|日|小时|時|分钟|分|秒))+\s*前$|^信息来自|^\d+\s*分钟前$"
)
def parse_mail_list(html_text: Any) -> List[Tuple[str, str]]:
    """收件箱列表 → ``[(短讯 id, 主题), …]``（事实，不做判断）。"""
    t = str(html_text or "")
    if not t:
        return []
    out: List[Tuple[str, str]] = []
    seen = set()
    for mid, subj in _MAIL_ROW_RE.findall(t):
        mid = str(mid).strip()
        subj = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(subj))).strip()
        if not mid or mid in seen or not subj:
            continue
        seen.add(mid)
        out.append((mid, subj))
    return out


def pick_welcome_mail(rows: Any) -> Optional[Tuple[str, str]]:
    """从短讯列表里挑「欢迎短讯」（挑不到 → None；**不猜**）。"""
    for mid, subj in (rows or []):
        if _WELCOME_SUBJ_RE.search(str(subj or "")):
            return str(mid), str(subj)
    return None


_MAIL_LINK_RE = re.compile(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.S | re.I)


def parse_mail_links(html_text: Any) -> List[Dict[str, str]]:
    """短讯页面里的链接 → ``[{"href","label"}]``（去重保序；**事实**，不挑不筛）。"""
    t = str(html_text or "")
    if not t:
        return []
    out: List[Dict[str, str]] = []
    seen = set()
    for href, label in _MAIL_LINK_RE.findall(t):
        href = str(href or "").strip()
        label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(label or ""))).replace("&nbsp;", " ").strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript"):
            continue
        key = (href, label)
        if key in seen:
            continue
        seen.add(key)
        out.append({"href": href, "label": label[:60]})
    return out


def parse_mail_body(html_text: Any, subject: str = "") -> str:
    """短讯正文（去掉站点导航/用户栏/页脚 —— 用户栏里的「H&R 0/0/10」是**假的**）。"""
    t = str(html_text or "")
    if not t:
        return ""
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</p>|</div>|</tr>|</li>|</td>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = (t.replace("&nbsp;", " ").replace("&#039;", "'")
          .replace("&amp;", "&").replace("&quot;", '"').replace("&#x2022;", " "))
    lines = [re.sub(r"[ \t]+", " ", x).strip() for x in t.split("\n")]
    lines = [x for x in lines if x]
    start = 0
    key = str(subject or "")[:12].strip()
    if key:
        idxs = [i for i, x in enumerate(lines) if key in x]
        if len(idxs) >= 2:
            start = idxs[1] + 1
        elif idxs:
            start = idxs[0] + 1
        else:
            # 标题行被截断/变形时：退到「短讯箱 / 收件箱」表头之后
            for i, x in enumerate(lines):
                if x in ("短讯箱", "收件箱") and i + 1 < len(lines):
                    start = i + 1
    end = len(lines)
    for i in range(start, len(lines)):
        if _MAIL_FOOT_RE.search(lines[i]) or lines[i].startswith("(c) "):
            end = i
            break
    body = [x for x in lines[start:end] if x not in _MAIL_NOISE and not _MAIL_TIME_RE.search(x)]
    return "\n".join(body)[:4000]


# ============================================================
# 站点搜索结果行（NexusPHP 皮肤）—— 直连搜索辅种的候选目录
# ============================================================
# ★ 2026-10-31 实测（PT时间 torrents.php?search=…）：这一版皮肤有三个必踩的坑，都写进代码：
#   ① **不能用非贪婪 `<tr>…</tr>` 切行** —— 行内嵌 `<table class="torrentname"><tr>…</tr>`
#      会在内层 `</tr>` 处提前截断，于是体积 / 做种数 / 促销全部读空（表现成「解析出 0 行」
#      或「行里没体积」，极易误判成站点没货）。
#   ② 体积是 `<td class="rowfollow">24.35<br>GB</td>` —— 数字与单位之间夹 `<br>`，
#      `\d+(\.\d+)?\s*[KMGT]i?B` 这类通用写法匹配不到。要先去掉标签再交给 parse_size。
#   ③ 下载直链就在行里，自带 `passkey` 与 `uid`（`download.php?id=&passkey=&uid=`）——
#      所以**不需要给站点单独配 passkey**，把整条链存进 `mf_rss.download_url` 即可复用。
#
# ★★ 2026-10-31 加第二站（Depth Studio）时发现：**按行标签切行本身就不通用**。
#   同一份 NexusPHP，PT时间的行是 `<tr data=NNN>`，Depth 的置顶行是
#   `<tr class="torrent-sticky-row …" data-sticky-level="…">`、**普通行是裸 `<tr>`**
#   ——后者没有任何属性可锚，按标签切必然漏掉大部分结果（实测只切出 9/39 行）。
#   改为**按内容锚点切**：`<table class="torrentname">` 是每个种子行唯一必有的表，
#   tid 从块内 `details.php?id=` 取（两站都有），拿不到再退 `download.php?id=`。
#   实测：PT时间 2/2 行字段与旧切法**逐字段完全一致**（零回归），Depth 39/39 行齐全。
#   另注：Depth 的行内直链是**裸** `download.php?id=N`（不带 passkey）⇒ 取种必须带
#   站点 cookie。调用方 `_reseed_one` 本来就传 `cookie=conn["cookie"]`，所以天然可用。
_NP_ROW_SPLIT = re.compile(r'(<table[^>]*class="[^"]*torrentname[^"]*"[^>]*>)', re.I)
# 兜底切法：站点没有 torrentname 表（老式皮肤）时按整行属性里的 tid 切
_NP_ROW_SPLIT_LEGACY = re.compile(r"(<tr\s+data=\d+>)", re.I)
_NP_TR_DATA = re.compile(r"data=(\d+)", re.I)
_NP_TID = re.compile(r"details\.php\?id=(\d+)", re.I)
_NP_TID_ALT = re.compile(r"download\.php\?id=(\d+)", re.I)
_NP_TITLE = re.compile(r'class="torrentname_title"[^>]*>\s*<b[^>]*title="([^"]*)"', re.I)
_NP_TITLE_ALT = re.compile(r'class="torrentname_title"[^>]*>([^<]{2,300})', re.I)
# Depth Studio 皮肤：标题在 `<a title="…" href="details.php?id=…"><b>…</b></a>`，
# 没有 `torrentname_title` class；两条按「详情页锚点」顺序兜。
_NP_TITLE_B = re.compile(r'href="details\.php\?id=\d+[^"]*"[^>]*>\s*<b>([^<]{2,300})</b>', re.I)
_NP_TITLE_C = re.compile(r'title="([^"]{2,300})"\s+href="details\.php', re.I)
_NP_PROMO = re.compile(r"class='promotion (\w+)'[^>]*>([^<]*)<", re.I)
_NP_ALIAS = re.compile(r'<font title="([^"]{2,300})">([^<]{0,300})<', re.I)
_NP_SEEDS = re.compile(r'<span class="red">(\d+)</span>', re.I)
_NP_DL = re.compile(r"""href=["']([^"']*download\.php\?[^"']+)["']""", re.I)
_NP_SIZE_TD = re.compile(r'<td class="rowfollow">([^<]{1,24})</td>', re.I)
_NP_SIZE_ANY = re.compile(r"(\d+(?:\.\d+)?)\s*<br\s*/?>\s*([KMGT]i?B)", re.I)
_NP_TAG = re.compile(r"<[^>]+>")


def _np_cell_size(seg: str) -> float:
    """从行块里抠体积（GB）。先按 `<td class="rowfollow">…</td>` 逐个试，
    再退到「数字 + <br> + 单位」的裸文本形态。"""
    for cell in _NP_SIZE_TD.findall(seg):
        txt = _NP_TAG.sub(" ", cell).replace("&nbsp;", " ").strip()
        if not txt:
            continue
        val = parse_size(txt)
        if val > 0:
            return round(val / 1024 ** 3, 4)
    m = _NP_SIZE_ANY.search(seg)
    if m:
        val = parse_size(m.group(1) + m.group(2))
        if val > 0:
            return round(val / 1024 ** 3, 4)
    return 0.0


def _np_rows(html: str, split_re: Any) -> List[Dict[str, Any]]:
    """按给定行锚点切块并逐块抽字段（两种切法共用同一套字段口径）。

    ``split_re`` 必须**只有一个捕获组**且捕获的是行起始标记；块内容取自
    ``parts[i+1]``（行首到下一个行首之间的全部 HTML）。
    """
    parts = split_re.split(html)
    out: List[Dict[str, Any]] = []
    for i in range(1, len(parts) - 1, 2):
        seg = parts[i + 1]
        m_id = _NP_TID.search(seg) or _NP_TID_ALT.search(seg)
        tid = (m_id.group(1) if m_id else "").strip()
        if not tid:
            # 兜底：行标签自带 tid（`<tr data=NNN>` 老式皮肤）
            m_attr = _NP_TR_DATA.search(parts[i])
            tid = (m_attr.group(1) if m_attr else "").strip()
        if not tid:
            continue                      # 无标识（表头/过滤行/广告行）—— 不猜
        m_t = (_NP_TITLE.search(seg) or _NP_TITLE_B.search(seg)
               or _NP_TITLE_C.search(seg) or _NP_TITLE_ALT.search(seg))
        title = (m_t.group(1) if m_t else "").strip()
        title = _NP_TAG.sub("", title).strip()
        m_p = _NP_PROMO.search(seg)
        m_a = _NP_ALIAS.search(seg)
        m_s = _NP_SEEDS.search(seg)
        m_d = _NP_DL.search(seg)
        # 直链**原样保留**（两种形态：`download.php?id=&passkey=&uid=` 自带口令，
        #   或裸 `download.php?id=N` 靠站点 cookie 鉴权）——是否补域名由调用方决定；
        #   早先在这里把「非 http 且非 / 开头」的清空，等于把最有价值的凭据扔掉。
        dl = (m_d.group(1) if m_d else "").replace("&amp;", "&").strip()
        out.append({
            "tid": tid,
            "title": title,
            "alias": (m_a.group(1).strip() if m_a else ""),
            "size_gb": _np_cell_size(seg),
            "promo": (m_p.group(1) if m_p else ""),
            "promo_text": (m_p.group(2).strip() if m_p else ""),
            "seeds": (int(m_s.group(1)) if m_s else None),
            "download_url": dl,
        })
    return out


def parse_np_search_rows(html_text: Any) -> List[Dict[str, Any]]:
    """解析站点搜索/浏览结果页的种子行（NexusPHP，兼容多种行皮肤）。

    返回 ``[{tid,title,alias,size_gb,promo,promo_text,seeds,download_url}]``；
    解析不出标识的行直接跳过（**不猜**，下游靠 size + 特征码二次确证）。

    两段式：先按 `<table class="torrentname">` 内容锚点切（覆盖置顶行 / 裸 `<tr>`
    普通行两种皮肤）；一条都切不出来时才退「整行属性带 tid」的老式切法。
    """
    html = str(html_text or "")
    if not html:
        return []
    out = _np_rows(html, _NP_ROW_SPLIT)
    if not out:
        out = _np_rows(html, _NP_ROW_SPLIT_LEGACY)
    return out
