"""魔流 · 标签 —— 媒体加种编排（带 ``host``：调下载器 / 账本 / 候选缓存）。

★ 19.10.27 拆分：标签编解码（纯函数 + 全部常量）已下沉 L0 ``tagspec.py``。
  本模块只留 11 个媒体编排函数，并把 tagspec 的公开面**原样 re-export**，
  于是 26 个文件的 189 处 ``from .tags import …`` 一行都不用改。

留在本模块（都要 ``host``）：
  ``duty_assign``（挂 ``<kind>`` 伪任务）/ ``media_fetch_torrent`` / ``media_pin_location`` /
  ``media_grab`` / ``media_row_from_ti`` / ``media_totals`` / ``media_act`` /
  ``media_cand_put`` / ``media_cand_get`` / ``media_cand_hydrate``。
  调用方只有 ``features/musicgrab.py`` 与 ``features/ondemand.py``（加测试），不是公共模块。

⚠ **不要在本模块重新定义** ``set_site_names`` 或任何 ``tagspec`` 里的常量：重定义 = 两份状态，
  ``parse_tag`` 立刻读不到站点表（站点名解析静默走错分支），详见 ``tagspec`` docstring。

原文件的前半曾同时装着这两件事，为判分层制造过误判（``check_module_doc.py`` 记录在案）。
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Sequence

# tagspec 的公开面原样转出 —— 调用方（26 个文件）零改动。
# 不导出 _SITE_NAMES：它是可变 global，set_site_names 会 rebind，转出只会拿到过期空表。
from .tagspec import (
    PREFIX,
    STATE_BRUSH,
    STATE_BONUS,
    STATE_SILENT,
    STATE_RECOMMEND,
    STATE_HR,
    STATE_KEEP,
    STATE_ONDEMAND,
    STATE_CLAIM,
    STATE_MUSIC,
    SUB_NEW,
    SUB_RESOURCE,
    SUB_PLAIN,
    STATES,
    DUTY_STATES,
    SUBS,
    STATES_WITH_SUB,
    ASSET_TAGS,
    KEEP_FOREIGN_TAGS,
    SILENT_NEW_TIMEOUT,
    LEASE_TTL,
    MUSIC_CATEGORY,
    ONDEMAND_CATEGORY,
    MEDIA_CAND_TTL,
    MARK_REUSE,
    MARK_HR,
    RESCUE_TAG,
    EXTERNAL_TAG,
    SPECIAL_TAGS,
    NON_DOWNLOAD_TAGS,
    _MARK_TAGS,
    DEFAULT_SORT_RULES,
    MEDIA_KINDS,
    is_asset_tags,
    is_library_asset,
    resource_of_hash,
    resource_is_asset,
    resource_asset_hash,
    asset_member_hashes,
    _clean,
    tag_for,
    set_site_names,
    is_music_line,
    parse_tag,
    is_magicflow_tag,
    is_managed_tag,
    needs_magicize,
    is_reuse_copy,
    is_external_candidate,
    identity_of,
    duty_of,
    retag,
    media_kind_spec,
    fmt_iso_ts,
    is_freeleech,
    strip_media_prefix,
)

__all__ = [
    "PREFIX",
    "STATE_BRUSH",
    "STATE_BONUS",
    "STATE_SILENT",
    "STATE_RECOMMEND",
    "STATE_HR",
    "STATE_KEEP",
    "STATE_ONDEMAND",
    "STATE_MUSIC",
    "STATE_CLAIM",
    "DUTY_STATES",
    "SUB_NEW",
    "SUB_RESOURCE",
    "SUB_PLAIN",
    "STATES",
    "SUBS",
    "SILENT_NEW_TIMEOUT",
    "LEASE_TTL",
    "MARK_REUSE",
    "MARK_HR",
    "RESCUE_TAG",
    "EXTERNAL_TAG",
    "NON_DOWNLOAD_TAGS",
    "tag_for",
    "parse_tag",
    "is_magicflow_tag",
    "is_managed_tag",
    "needs_magicize",
    "identity_of",
    "duty_of",
    "is_reuse_copy",
    "is_external_candidate",
    "KEEP_FOREIGN_TAGS",
    "retag",
    "DEFAULT_SORT_RULES",
    "MEDIA_KINDS",
    "media_kind_spec",
    "fmt_iso_ts",
    "is_freeleech",
    "strip_media_prefix",
    "duty_assign",
    "media_fetch_torrent",
    "media_pin_location",
    "media_grab",
    "media_row_from_ti",
    "media_totals",
    "media_act",
    "media_cand_put",
    "media_cand_get",
    "media_cand_hydrate",
]

def duty_assign(host: Any, hashes: Any, *, kind: Any,
                task_id: str, task_name: str,
                site: str = "", sub: str = "", reason: str = "") -> int:
    """把「在途」的种挂到 ``<kind>`` 伪任务（贴职务标签 + 写账本 ``taken_by``）。

    ★ 19.10.11：音乐/点播同一条流水线，只差 type —— 本函数是两边共用的唯一实现。
    职务标签（身份轴 ``魔流-<站>-静默-<子类>`` 永久保留）+ 账本 ``taken_by=<task_id>``。
    效果：账本 ``state=<职务>`` ≠ 静默 → 静默池的**暂停闸**与**清理闸**双双跳过
    → 「没下完的在途种」不再被当静默半成品删/暂停。**不动下载状态**（不 pause、不 force_start）。

    幂等：账本已挂 ``<task_id>`` **且** qB 职务标签在位 → 跳过。只看账本会在
    「加种 ↔ qB 登记」抢跑时漏写标签、事后又永不补回。

    ``host`` = 插件主对象，需提供 ``_get_downloader`` / ``_tag_state`` / ``_tag_all_torrents``
    / ``_torrent_site_name`` / ``_log``。做成自由函数而非 mixin 方法，是为了不让两个媒体
    模块再多一层跨文件 ``self._`` 耦合（见 ``tools/check_self_calls.py`` 棘轮）。
    """
    spec = media_kind_spec(kind)
    state = spec["state"]
    label = spec["label"]
    # ★ 19.10.12：流程本体在 ``dutyops.assign``（与 H&R 保种 / 手动保种 / 认领共用一套）。
    #   这里只剩「取下载器 → 调一次 → 打日志」的薄壳。
    #   延迟导入：``dutyops`` → ``dutyreg`` → 本模块（模块级导入会成环）。
    from .dutyops import assign  # noqa: PLC0415
    try:
        downloader = host._get_downloader("qbittorrent")
    except Exception:  # noqa: BLE001
        downloader = None
    if downloader is None or not getattr(downloader, "is_available", False):
        return 0
    rep = assign(host, hashes, taker=task_id, state=state, name=task_name,
                 site=site, sub=sub, label=label)
    if rep.get("error"):
        try:
            host._log(f"{label}:挂伪任务取账本失败:{rep['error']}", "warning")
        except Exception:  # noqa: BLE001
            pass
        return 0
    n = int(rep.get("adopted") or 0)
    if n:
        try:
            host._log(f"{label}:挂 {task_id} {n} 个（{reason or '在途'}）")
        except Exception:  # noqa: BLE001
            pass
    if int(rep.get("blocked") or 0):
        try:
            host._log(f"{label}:跳过 {rep['blocked']} 个（已在别的岗位名下，本岗不跨岗挑人）",
                      "debug")
        except Exception:  # noqa: BLE001
            pass
    return n


# ------------------------------------------------------------ 媒体加种（★ 19.10.11 合一）
#
# 音乐与点播的加种链路**形状完全一样**：取 .torrent → 打「身份+职务」双标签 →
# add_torrent → 提 hash。历史上两边各写一份（`_music_grab_one` / `_od_fetch_torrent`
# + `_ondemand_download`），九处差异里八处是「一边有优点」而非「必须不同」——
# 这里取并集，两边只剩「挂哪个伪任务 + 尾段记账」由包装层做（task_id 真值源在 common.py）。
#
# 取种通道：两边本就都是宿主 SDK `fetch_torrent_bytes`（`_crossseed_torrent_bytes`
# 只是包了一层），统一走这里。PV 口径收成一个开关：
#   · 一律 `_pv_spend` 记账 —— 请求打到站点上就该进账本；
#   · `pv_gate=True`（自动流）额外过 `_pv_allow` 预算闸；
#   · `pv_gate=False`（用户点名要下的点播）只查站点是否被封，不因预算拦人。


def media_fetch_torrent(host: Any, row: Dict[str, Any], *,
                        downloader_name: str = "qbittorrent",
                        pv_gate: bool = True) -> Any:
    """取 `.torrent` 字节（媒体线统一通道）。返回 `(content, code, message)`。

    成功时 code/message 为 `("", "")`。每条失败都带 code，调用方可直接回前端/写日志。
    """
    r = row if isinstance(row, dict) else {}
    url = str(r.get("enclosure") or "")
    name = str(r.get("site_name") or r.get("site") or "")
    if not url:
        return None, "torrent_fetch_failed", "缺少种子链接（enclosure）"
    try:
        sid = int(r.get("site") or 0)
    except (TypeError, ValueError):
        sid = 0
    try:
        until = host._pv_block_reason(sid) if sid else ""
    except Exception:  # noqa: BLE001
        until = ""
    if until:
        return None, "pv_blocked", f"该站已暂停抓取至 {until}，未取种子（可到「站点」页确认后重试）"
    if pv_gate and sid:
        try:
            ok_budget = host._pv_allow(sid, "media", want=1)
        except Exception:  # noqa: BLE001
            ok_budget = True
        if not ok_budget:
            return None, "pv_blocked", "PV 闸门拦截（站点预算不足/被封，稍后再试）"
    want_dl = str(downloader_name or "").strip() or "qbittorrent"
    try:
        dl = host._get_downloader(want_dl)
    except Exception:  # noqa: BLE001
        dl = None
    if dl is None or not getattr(dl, "is_available", False):
        return None, "no_downloader", f"下载器不可用（当前配置：{want_dl}）"
    try:
        content = dl.fetch_torrent_bytes(
            url,
            cookie=r.get("site_cookie"),
            user_agent=r.get("site_ua"),
            referer=r.get("page_url") or None,
        )
    except Exception as e:  # noqa: BLE001
        return None, "torrent_fetch_failed", f"取种子失败：{e}"
    finally:
        if sid:
            try:
                host._pv_spend(sid, "media", 1)
            except Exception:  # noqa: BLE001
                pass
    if not content:
        return None, "torrent_fetch_failed", \
            "取种子失败：站点未返回内容（API 站换票失败或登录态失效，日志有明细）"
    return content, "", ""


def media_pin_location(host: Any, h: str, dest: str) -> bool:
    """把种子数据钉回指定目录（qB「自动管理」会把任务改放到默认下载目录）。

    先关该任务的自动管理，再 `setLocation`。放默认目录时属 movie project，
    硬链进 `/music` 会被 fnOS project quota 的 EXDEV 拒绝 —— 音乐踩过的坑，
    点播同样受益（保存目录就该是任务指定的那个）。
    """
    try:
        dl = host._get_downloader("qbittorrent")
        mod = getattr(dl, "_downloader", None)
        qbc = getattr(mod, "qbc", None)
        if qbc is None or mod is None:
            return False
        try:
            qbc.torrents_set_auto_management(hashes=h, enable=False)
        except Exception:  # noqa: BLE001
            pass
        return bool(mod.set_torrent_location(h, dest))
    except Exception:  # noqa: BLE001
        return False


def media_grab(host: Any, row: Dict[str, Any], save_path: str, *,
               kind: Any, existing: Any = None,
               content: Optional[bytes] = None,
               downloader_name: str = "qbittorrent",
               pv_gate: bool = True,
               infohash: Any = None) -> Dict[str, Any]:
    """媒体线统一加种：取种 → 打「身份+职务」→ add_torrent → 提 hash。

    ★ 19.10.11：两边各自的优点并集：
      · 幂等双保险 —— 加种**前**算 infohash 命中 `existing` 即 skip（音乐）∪
        加种**失败后**算 infohash 已在下载器则收养（点播 16.0.2）；
      · 分类 `MEDIA_KINDS[kind]["category"]`（音乐/点播都有，不再一边有一边没有）；
      · 下载器认 `downloader_name`（点播认 `task.downloader` 的优点），不写死；
      · 错误统一 `code + message`（点播），调用方好回前端。

    调用方只做尾段（挂伪任务 / 历史 / inflight）—— 那才是 kind 真差异。
    `infohash` 可注入（测试替身用）；缺省用 `fingerprint.info_hash`。
    """
    spec = media_kind_spec(kind)
    state = spec["state"]
    category = spec.get("category") or None
    row = dict(row or {})
    want_dl = str(downloader_name or "").strip() or "qbittorrent"
    if not content:
        content, code, msg = media_fetch_torrent(host, row, downloader_name=want_dl,
                                                 pv_gate=pv_gate)
        if not content:
            return {"ok": False, "code": code, "message": msg}
    try:
        dl = host._get_downloader(want_dl)
    except Exception:  # noqa: BLE001
        dl = None
    if dl is None or not getattr(dl, "is_available", False):
        return {"ok": False, "code": "no_downloader",
                "message": f"未找到可用下载器（当前配置：{want_dl}）"}
    _ih = infohash
    if _ih is None:
        try:
            from .fingerprint import info_hash as _ih  # noqa: WPS433
        except Exception:  # noqa: BLE001
            _ih = None
    h0 = ""
    if _ih is not None:
        try:
            h0 = str(_ih(content) or "").lower()
        except Exception:  # noqa: BLE001
            h0 = ""
    # 幂等（音乐口径）：加种前算 infohash，已在下载器 → skip
    if h0 and existing and h0 in existing:
        return {"ok": True, "hash": h0, "skipped": True, "message": "已在下载器"}
    site_name = str(row.get("site_name") or "")
    if site_name:
        # ★ 19.10.46：分隔符**不能带空格**。qB 的 ``torrents/add`` 只按 ``,`` 拆、
        #   **不 trim**（与 ``torrents/addTags`` 行为不同，后者会 trim）。写成
        #   ``", ".join`` 时第二个标签会带前导空格落库成 ``␠魔流-X-音乐``，
        #   而 qB 4.6.4 的 removeTags/deleteTags 会先 trim 入参 → 那个脏标签
        #   此后**任何 API 都删不掉**（现场 21 个种中招，最久的挂了 22 天）。
        tag = ",".join([tag_for(site_name, STATE_SILENT, SUB_RESOURCE),
                        tag_for(site_name, state)])
    else:
        tag = ""
    try:
        dom = host._site_domain_by_name(site_name) or ""
    except Exception:  # noqa: BLE001
        dom = ""
    try:
        hs, err = dl.add_torrent(content=content, download_dir=save_path, tag=tag,
                                 category=category, site_domain=dom,
                                 hit_and_run=bool(row.get("hit_and_run")))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "code": "add_failed", "message": f"添加失败: {e}"}
    if not hs:
        # 幂等（点播口径 16.0.2）：添加失败但 infohash 已在下载器 → 收养
        if h0 and h0 in (host._tag_all_torrents() or {}):
            h = h0
        else:
            return {"ok": False, "code": "add_failed",
                    "message": f"添加失败: {err or '未知'}"}
    else:
        h = str(hs[0] if isinstance(hs, (list, tuple)) else hs).lower()
    # 钉目录（音乐/点播都受益：保存目录就该是任务指定的那个）
    media_pin_location(host, h, save_path)
    return {"ok": True, "hash": h, "tag": tag, "save_path": save_path}


_ZH_RE = re.compile(r"[\u4e00-\u9fff]")
# 副标题里表示地区的括注（「(台湾)」「（台）」）—— 不属于片名本体，展示时去掉
_REGION_RE = re.compile(r"[（(]\s*(?:台湾|台|香港|港|大陆|内地|新马|新加坡|马来西亚)\s*[）)]")
# 片名段里夹带的规格词（「小猪佩奇第八季 全45集 国语中字」）—— 从第一个命中处切开
_SPEC_ZH_RE = re.compile(
    r"(?:全\s*\d+\s*集|共\s*\d+\s*集|已完结|完结|国配|国语|粤语|双语|国英|中字|英字"
    r"|简中|繁中|中英|内嵌|内封|无删减|高清|杜比视界|原盘|REMUX|[48][kK])"
)


def display_title(description: Any, title: Any = "") -> Dict[str, str]:
    """站点副标题 → 可读中文主标题 + 规格串（★ 19.11.0）。

    根因（Master 2026-11-01「搜出的内容都是拼音或者英文，要不能看懂要不副标题」）：
    站点把中文片名转成拼音/英文写进 ``torrent_info.title``，但 MP 的 ``TorrentInfo``
    另有 ``description`` = 「种子副标题」，**实测 1262/1264 条含中文**（馒头/织梦/
    蟹黄堡/咖啡/CARPT 等站原文：``小猪佩奇 第九季 / 粉红猪小妹 第九季 (台湾) |
    国英双语 内嵌简中 | 全63集``）。中文名一直在数据里，只是没取。

    切分口径（只在 ``|`` 分段上做，不做语义推断）：

      · 第 1 段 = 片名段 → 去地区括注 → 按 ``/`` 拆「主名 / 别名」；
      · 片名段里夹带的规格词（``全45集`` / ``国语中字``）→ 剥进规格串；
      · 第 2+ 段 = 规格串，`` · `` 连接（最多 4 段，再长前端也放不下）。

    返回恒 4 键：``cn_title``（中文主名，取不到 = 空串）/ ``cn_alt``（别名）/
    ``spec``（规格串）/ ``subtitle``（副标题原文，前端 hover 用）。**不猜、不翻译**：
    副标题是英文就 ``cn_title`` 留空，由前端退回站点原标题。
    """
    desc = str(description or "").strip()
    if not desc:
        return {"cn_title": "", "cn_alt": "", "spec": "", "subtitle": ""}
    segs = [s.strip() for s in re.split(r"[|｜]", desc) if s.strip()]
    head = segs[0] if segs else ""
    tail = segs[1:]
    head = _REGION_RE.sub("", head).strip(" /·-")
    # 括注里是别名，不是片名本体（「小猪佩奇（粉红猪小妹）」「咖喱辣椒（Curry & Pepper /
    # Curry and Pepper）」）—— 先整段摘下，主体才不会被里面的 `/` 切坏。
    paren = " ".join(re.findall(r"[（(]([^（()）]+)[）)]", head))
    if paren:
        head = re.sub(r"[（(][^（()）]*[）)]", " ", head).strip(" /·-")
    # 方头括号是**标注**不是片名（「流浪地球2 [简中字幕] IMAX版」）→ 进规格串；
    # 但「【流浪地球】mUHD作品」这种**以【】开头**的是片名带出处 → 括号内才是片名。
    extra: List[str] = []
    _m0 = re.match(r"^【([^】]{1,40})】\s*(.*)$", head)
    if _m0 and _ZH_RE.search(_m0.group(1)):
        head = _m0.group(1).strip()
        _rest = _m0.group(2).strip(" ·-")
        if _rest:
            extra.append(_rest)
    _mb = re.search(r"[\[［]", head)
    if _mb and head[: _mb.start()].strip(" ·-"):
        # 片名在前、方括号在后（「流浪地球2 [简中字幕] IMAX版 郭帆导演作品」）——
        # 方括号起**到结尾**都是标注，一律进规格串，片名只留前半段。
        _rest_all = head[_mb.start():]
        extra.extend(x.strip() for x in re.findall(r"[\[［]([^\[\]［］]{1,40})[\]］]", _rest_all) if x.strip())
        _after = re.sub(r"[\[［][^\[\]［］]*[\]］]", " ", _rest_all).strip(" ·-")
        if _after:
            extra.append(_after)
        head = head[: _mb.start()].strip(" ·-")
    else:
        # 开头就是方括号（「[电影天堂]不列颠之战」）→ 那是站名标记，直接丢掉
        head = re.sub(r"[\[［][^\[\]［］]*[\]］]", " ", head).strip(" /·-")
    tail = extra + tail
    names = [x.strip(" ·-") for x in re.split(r"\s*/\s*", head) if x.strip()]
    alts = [x.strip(" ·-") for x in re.split(r"\s*/\s*", paren) if x.strip()]
    cn = names[0] if names and _ZH_RE.search(names[0]) else ""
    # 别名只留「短且有中文」的前两个 —— 实测有的站挂 5 个别名（「小猪佩琦 / 粉红猪小妹 /
    # 萌萌小猪佩奇 / …」），全展开比原名还长，反而把主标题挤没了；纯英文别名也不留
    # （「Curry and Pepper」对认片没帮助，只占位置）。
    alt = ""
    if cn:
        picks = [x for x in (names[1:] + alts)
                 if _ZH_RE.search(x) and len(x) <= 20 and x != cn][:2]
        alt = " / ".join(picks)
    if cn:
        m = _SPEC_ZH_RE.search(cn)
        if m and m.start() > 0:          # 片名在前、规格词在后 → 切开
            tail = [cn[m.start():]] + tail
            cn = cn[:m.start()].strip(" ·-")
    return {
        "cn_title": cn,
        "cn_alt": alt,
        "spec": " · ".join([x for x in tail if x][:4]),
        "subtitle": desc,
    }


def promo_factor(v: Any, default: float = 1.0) -> float:
    """促销系数归一：``None`` / 空串 / 解析不了 → ``default``（**不是 0**）。

    ★ 19.11.14：``dvf=0`` 在语义上是「免费」，而 ``float(x or 0.0)`` 会把 ``None`` 变成
    ``0.0`` —— 于是「促销未知」被当成免费：计费体积算成 0、选源还排第一。口径与
    ``tagspec.is_freeleech`` 一致：宁可把免费当收费记账，也不把收费当免费白嫖。
    """
    if v is None or (isinstance(v, str) and not v.strip()):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def promo_label(dv: float, uvf: float = 1.0) -> str:
    """``(下载系数, 上传系数)`` → 人话促销标签（点播候选的可见面）。

    例：``(0,2)`` → ``免费 2X`` / ``(0,1)`` → ``免费`` / ``(0.5,2)`` → ``2X 50%`` /
    ``(0.3,1)`` → ``30%`` / ``(1,1)`` → ``普通``。
    """
    try:
        dv = float(dv)
    except (TypeError, ValueError):
        dv = 1.0
    try:
        uvf = float(uvf)
    except (TypeError, ValueError):
        uvf = 1.0
    parts: List[str] = []
    if uvf > 1.0:
        parts.append("2X" if abs(uvf - 2.0) < 1e-6 else f"{uvf:g}X")
    if dv <= 0.0:
        # 免费在前（「免费 2X」读起来比「2X 免费」自然）
        return ("免费 " + " ".join(parts)) if parts else "免费"
    if dv < 1.0:
        parts.append(f"{round(dv * 100):d}%")
    return " ".join(parts) if parts else "普通"


def media_row_from_ti(ti: Any) -> Optional[Dict[str, Any]]:
    """TorrentInfo（对象 / dict）→ 媒体候选行（只读归一，真值源 = MP 的 TorrentInfo）。

    ★ 19.10.11：音乐 ``_music_row_from_ti`` 与点播 ``_od_row_from_ti`` 是**同一件事的两份写法**
    ——都在做「对象/dict 通吃 → enclosure 必填 → 数字兜底」。这里收成一个，字段取**并集**：

      · 双方都有：``title`` / ``size`` / ``seeders`` / ``site`` / ``site_name`` /
        ``downloadvolumefactor`` / ``hit_and_run`` / ``enclosure`` / ``page_url`` / 站点凭据；
      · 音乐侧：``uploadvolumefactor``（点播原本不取，现在也有）；
      · 点播侧：``peers`` / ``free`` / ``counted_gb``（派生字段，音乐原本要自己算）。

    ★ 19.11.0 新增可读面（两边都要「看得懂」）：原字段 ``description``（站点副标题）/
    ``category`` / ``labels`` / ``volume_factor`` / ``date_elapsed`` / ``grabs``，
    以及 ``display_title`` 派生出的 ``cn_title`` / ``cn_alt`` / ``spec`` / ``subtitle``。
    纯增量：老调用方读的键一个没动。

    缺 ``enclosure`` → ``None``（两边口径一致）。
    """
    def _g(k: str, d: Any = None) -> Any:
        if isinstance(ti, dict):
            return ti.get(k, d)
        return getattr(ti, k, d)

    url = str(_g("enclosure", "") or "")
    if not url:
        return None

    def _f(k: str, d: float) -> float:
        try:
            return float(_g(k, d) or 0.0)
        except Exception:  # noqa: BLE001
            return d

    def _i(k: str, d: int = 0) -> int:
        try:
            return int(_g(k, d) or 0)
        except Exception:  # noqa: BLE001
            return d

    size = _f("size", 0.0)
    # ★ 19.11.14：系数不能走 ``_f``（它把 ``None`` 吃成 0.0 = 免费），要按「未知=全额」。
    dv = promo_factor(_g("downloadvolumefactor", None))
    uvf = promo_factor(_g("uploadvolumefactor", None))
    doc = str(_g("title", "") or "")
    desc = str(_g("description", "") or "")
    view = display_title(desc, doc)
    return {
        "title": doc,
        "size": size,
        "seeders": _i("seeders"),
        "peers": _i("peers"),
        "site": _i("site"),
        "site_name": str(_g("site_name", "") or ""),
        "downloadvolumefactor": dv,
        "uploadvolumefactor": uvf,
        "hit_and_run": bool(_g("hit_and_run", False)),
        "enclosure": url,
        "page_url": str(_g("page_url", "") or ""),
        "site_cookie": _g("site_cookie", None),
        "site_ua": _g("site_ua", None),
        "site_proxy": bool(_g("site_proxy", False)),
        "free": is_freeleech(dv),
        # 计费体积 = 体积 × 下载系数（**真正扣流量**的量；免费 = 0，五折 = 一半）
        "counted_gb": round(size / 1e9 * dv, 2),
        # ★ 19.11.14 可见面：促销人话（免费 / 2X / 50% / 普通），选源与展示共用同一口径
        "promo": promo_label(dv, uvf),
        # ★ 19.11.0 可读面（原字段 + 派生）：站点副标题是点播候选唯一的中文来源
        "description": desc,
        "category": str(_g("category", "") or ""),
        "labels": [str(x) for x in (_g("labels", []) or [])],
        "volume_factor": str(_g("volume_factor", "") or ""),
        "date_elapsed": str(_g("date_elapsed", "") or ""),
        "grabs": _i("grabs"),
        "cn_title": view["cn_title"],
        "cn_alt": view["cn_alt"],
        "spec": view["spec"],
        "subtitle": view["subtitle"],
    }


def media_totals(rows: Any) -> Dict[str, Any]:
    """干净清单的 ``totals`` 汇总（按 stage 分桶 + 剩余体积）。

    ★ 19.10.11：音乐 ``_music_items`` 与点播 ``_ondemand_items`` 里这 7 行**逐字相同**。
    """
    rows = list(rows or [])
    return {
        "count": len(rows),
        "downloading": sum(1 for r in rows if r.get("stage") == "downloading"),
        "settling": sum(1 for r in rows if r.get("stage") == "settling"),
        "resource": sum(1 for r in rows if r.get("stage") == "resource"),
        "gone": sum(1 for r in rows if r.get("stage") == "gone"),
        "left_gb": round(sum(float(r.get("left_gb") or 0.0) for r in rows), 3),
    }


def media_act(host: Any, hash: str, action: str, *, kind: Any,
              acts: Sequence[str] = ("pause", "resume", "remove"),
              downloader_name: str = "qbittorrent",
              belong: Any = None,
              removed: Any = None) -> Dict[str, Any]:
    """媒体线行内操作（暂停 / 继续 / 移除）——回执**恒 5 键** ``{ok,hash,action,message,blocked}``。

    ★ 19.10.11：音乐 ``_music_act`` 与点播 ``_ondemand_act`` 的**写口**合并。
    这两处的「形状」必须字面一致 —— 尤其 ``remove`` 走的是**同一个删除闸门**
    （``DownloaderAdapter.delete_torrents``），两边各写一遍就是漂移的温床：
    一边改了闸门调用招牌而另一边没改，就是一次静默绕过。

    真正的差异只有两处，用回调注入（不传 = 该步跳过）：

      · ``belong(h)`` —— 「这颗种算不算我家的」→ ``None`` 放行，返回字符串 = 拒绝原因。
        音乐：在下载器 + qB 分类=音乐；点播：在 pending 槽里。
      · ``removed(h)`` —— 移除**成功后**的收尾。点播靠它撤 pending 槽并把历史标
        ``removed``（否则撤单过的种会一直在清单里复活）；音乐没有这一步。

    ``source`` 严格取 ``kind``（``music`` / ``ondemand``）：删除台账靠它分线
    （``_music_deleted_hashes`` 只认 ``source=="music"``），不能统一成一个值。
    """
    spec = media_kind_spec(kind)
    label = spec.get("label") or "媒体"
    h = str(hash or "").strip().lower()
    act = str(action or "").strip().lower()

    def _rep(ok: bool, msg: str, *, blocked: bool = False) -> Dict[str, Any]:
        return {"ok": bool(ok), "hash": h, "action": act,
                "message": str(msg or ""), "blocked": bool(blocked)}

    if not h:
        return _rep(False, "缺少 hash")
    if act not in tuple(acts or ()):
        return _rep(False, f"未知操作:{action}")
    if belong is not None:
        try:
            why = belong(h)
        except Exception as e:  # noqa: BLE001
            why = f"归属校验异常:{e}"
        if why:
            return _rep(False, str(why))
    want_dl = str(downloader_name or "").strip() or "qbittorrent"
    try:
        dl = host._get_downloader(want_dl)
    except Exception as e:  # noqa: BLE001
        return _rep(False, f"下载器不可用:{e}")
    if dl is None or not getattr(dl, "is_available", False):
        return _rep(False, "下载器不可用")
    if act in ("pause", "resume"):
        try:
            n, err = (dl.pause_torrents([h]) if act == "pause" else dl.resume_torrents([h]))
        except Exception as e:  # noqa: BLE001
            return _rep(False, f"{act} 失败:{e}")
        if err or not n:
            return _rep(False, f"{act} 失败:{err or '未命中'}")
        try:
            host._log(f"{label}:{'暂停' if act == 'pause' else '继续'} {h[:12]}")
        except Exception:  # noqa: BLE001
            pass
        return _rep(True, "已暂停" if act == "pause" else "已继续")
    # ---- remove：**唯一删除闸门**（fail-closed，不绕过）
    try:
        n, err = dl.delete_torrents(hashes=[h], delete_file=True,
                                    reason=f"{label}移除", source=str(kind or ""))
    except Exception as e:  # noqa: BLE001
        return _rep(False, f"移除失败:{e}")
    if not n:
        return _rep(False, err or "被删除闸门拦下（欠 H&R / 受保护），未移除", blocked=True)
    if removed is not None:
        try:
            removed(h)
        except Exception as e:  # noqa: BLE001
            try:
                host._log(f"{label}:{h[:12]} 移除后收尾失败:{e}", "warning")
            except Exception:  # noqa: BLE001
                pass
    try:
        host._log(f"{label}:移除 {h[:12]}（删种+删文件）")
    except Exception:  # noqa: BLE001
        pass
    return _rep(True, "已移除（删种+删文件）")


def media_cand_put(host: Any, region: str, key: str, row: Dict[str, Any], ttl: float) -> None:
    """候选入池**唯一出口**：脱敏（pop 凭据）后落缓存层。

    ★ 19.10.11：音乐 ``_music_cand_put`` 与点播 ``_od_pool_store`` 的写入纪律合并。
    两者的候选缓存是**同一个东西**（search→挑选→下载 之间的候选暂存，人/AI 同一入口），
    唯一真分歧是底座 —— 音乐原来是进程内存 dict（``reload 即清空``），点播是 TierCache
    （落盘、跨 reload 存活）。统一到 TierCache：

      · 凭据（``site_cookie`` / ``site_ua``，passkey 就在里面）**永不落缓存**
        （Redis / 散文件都可能被读到）—— 这是点播 19.10.0 就定下的纪律，音乐侧原来是
        「裸存进程内存 dict 靠不落盘兜底」，统一后一并收进来，反而堵上「core dump / 日志
        repr 泄漏 passkey」的口子。
      · 取回时按 site id 回填（见 ``media_cand_hydrate``）。

    ``key`` 由调用方决定（音乐=cid hex，点播=enclosure url）—— 那是各自的**对外引用
    契约**（AI 通道传 cid / 对话框传 enclosure），不是缓存内部实现，不该强统一。
    """
    item = dict(row or {})
    item.pop("site_cookie", None)
    item.pop("site_ua", None)
    item["_at"] = time.time()
    host._cache_set(region, str(key or ""), item, ttl)


def media_cand_get(host: Any, region: str, key: str, ttl: float) -> Optional[Dict[str, Any]]:
    """取候选：未命中 / 过期 → ``None``；命中则清内部字段并回填凭据（**绝不在此回退重搜**）。"""
    it = host._cache_get(region, str(key or ""), ttl)
    if not isinstance(it, dict):
        return None
    row = dict(it)
    row.pop("_at", None)
    row.pop("_kw", None)
    return media_cand_hydrate(host, row)


def media_cand_hydrate(host: Any, row: Dict[str, Any]) -> Dict[str, Any]:
    """按 ``site`` id 回填 cookie / ua / site_name（内存查站点表，**不是网络**）。

    站点查不到（已删）→ 原样返回（不带凭据）→ 加种时报 ``torrent_fetch_failed`` /
    明确的缺凭据错误，而不是静默用旧凭据 —— 这比音乐原来的「凭据裸存、站点删了也能下」
    更正确：凭据本就该从站点表现取，站点没了就不该还能用它下载。
    """
    try:
        sid = int(row.get("site") or 0)
    except (TypeError, ValueError):
        sid = 0
    if not sid:
        return row
    try:
        site = host._get_site(sid)
    except Exception:  # noqa: BLE001
        return row
    if site is None:
        return row
    row["site_cookie"] = getattr(site, "cookie", None) or row.get("site_cookie")
    row["site_ua"] = str(getattr(site, "ua", "") or "").strip() or row.get("site_ua")
    row["site_name"] = str(row.get("site_name") or getattr(site, "name", "") or "")
    return row
