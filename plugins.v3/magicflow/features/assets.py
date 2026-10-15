# -*- coding: utf-8 -*-
"""魔流 · assets —— 库内资产识别（已整理/入库，只读判定）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ★ 10.0.0：合法「完整特征码」= sha1 十六进制（32~64 位）。写坏成 ``|2.0`` 这种体积档的
#   假码一律当「无特征码」—— 身份不够强，就不配当资源。
_FP_OK = re.compile(r"^[0-9a-f]{32,64}$")


# ★ 库内资产名「最后兜底」：把种子里明显的中文片名抽出来（如
#   ``[魔幻手机Ⅱ：傻妞归来].Magic.Phone…`` → 魔幻手机Ⅱ：傻妞归来、
#   ``不列颠之战.Battle.of.Britain…`` → 不列颠之战）。
#   **保守**：只处理「括号内中文」与「首个 . / _ 之前含中文」两种；抽不到返回空串，
#   调用方保持原种子名（不乱改、不编造）。
_TITLE_CJK = re.compile(r"[\u4e00-\u9fff]")
_TITLE_GROUP = re.compile(r"字幕|压制|发布|工作室|汉化|@|rip|studio|team", re.I)


def _clean_title_from_torrent(title: str) -> str:
    s = str(title or "").strip()
    if not s:
        return ""
    # ① 开头方括号标签：[魔幻手机Ⅱ：傻妞归来]… → 取括号内中文名；
    #    [BDMV]/[VCB-Studio] 这类无中文 / 组名标签 → 剥掉继续看下一段。
    for _ in range(3):
        m = re.match(r"^[\[\u3010]([^\]\u3011]*)[\]\u3011]\s*", s)
        if not m:
            break
        inner = m.group(1).strip()
        if _TITLE_CJK.search(inner) and not _TITLE_GROUP.search(inner) and 2 <= len(inner) <= 40:
            return inner
        s = s[m.end():]
    # ② 首个 . / _ 之前的中文段（并去掉尾部季标 S01 / S01-S04）
    seg = re.split(r"[._]", s, 1)[0].strip()
    seg = re.sub(r"\s*[Ss]\d{1,2}(\s*[-~]\s*[Ss]?\d{1,2})?\s*$", "", seg).strip()
    if _TITLE_CJK.search(seg) and 2 <= len(seg) <= 40:
        return seg
    return ""


from ..tags import (
    asset_member_hashes,
    is_asset_tags,
    is_library_asset,
    retag,
    STATE_SILENT,
    SUB_NEW,
    SUB_RESOURCE,
    parse_tag,
)


from ..common import (
    MEDIA_ASSET_TAGS,
    torrent_data_key,
)


# ★ 15.8.15（Master「希望增加魔流库内资产手动删除的入口」）：
#   「库内资产」独立列表入口 + 只破第 5 道闸的手动删除，需要这两个符号。
from app.schemas import Response

from ..models import MagicFlowAssetActPayload, MagicFlowAssetDeletePayload

from ..persistence import OperationItem
from ..ledger import get_backend
from ..recommend import episode_info, recognize


# ★ 纯英文种名清洗：剪掉画质/来源/编码/音轨/季标等，留「片名 (年份)」。
#   识别层（TMDB）实测 10 个里只对 2 个、且有 45s 超时 → 不用在列表路径上。
_EN_JUNK = re.compile(
    r"\b(?:2160p|1080[pi]|720p|480p|4k|uhd|bluray|blu-ray|bdrip|brrip|web-?dl|webrip|"
    r"hdtv|dvdrip|remux|x264|x265|h\.?264|h\.?265|hevc|avc|av1|xvid|10bit|8bit|"
    r"ddp?|dd\+|ac3|eac3|dts(?:-hd)?|truehd|atmos|flac|aac|mp3|"
    r"mult[il]|complete|internal|repack|proper|extended|remastered|edition|hdr(?:10)?|dolby|"
    r"nf|amzn|atvp|dsnp|hmax|hulu|pcok|wowow|friday|cr)\b",
    re.I,
)
_EN_SEASON = re.compile(r"\b[Ss]\d{1,2}(?:[Ee]\d{1,3})?\b")


def _clean_en_title(title: str) -> str:
    s = re.sub(r"[._]+", " ", str(title or "")).strip()
    s = re.sub(r"^[\[\u3010][^\]\u3011]*[\]\u3011]\s*", "", s)
    if not s:
        return ""
    s = _EN_SEASON.sub(" ", s)
    cut = len(s)
    ym = re.search(r"\b(19|20)\d{2}\b", s)
    if ym:
        cut = min(cut, ym.start())
    jm = _EN_JUNK.search(s)
    if jm:
        cut = min(cut, jm.start())
    head = re.sub(r"\s{2,}", " ", s[:cut]).strip(" -_[]()·,")
    year = ym.group(0) if ym else ""
    if len(head) < 2 or not re.search(r"[A-Za-z]", head):
        return ""
    return "%s (%s)" % (head, year) if year else head


def _trim_junk(name: str) -> str:
    """名字里若混进了发布标记（WEB-DL/1080p/x265…）就剪到标记前，并去掉尾部年份。

    只对「本来就像发布名」的名字生效；干净名（无标记）原样返回。
    """
    s = str(name or "").strip()
    m = _EN_JUNK.search(s)
    if not m:
        return s
    head = s[:m.start()].strip(" -_.[]()\u00b7,")
    head = re.sub(r"\s*\b(19|20)\d{2}\b\s*$", "", head).strip(" -_.[]()\u00b7,")
    return head if len(head) >= 2 else s


class AssetsMixin:
    """assets 功能集（原 MagicFlow 方法原样搬入）。"""

    def _assets_recheck(self, *, apply: bool = False, limit: int = 0) -> Dict[str, Any]:
        """★ 给「已整理（在库）」的资源**过一遍推荐流程**（Master 2026-09-28 07:57）。

        背景：qB 里 326 个种带「已整理」标、文件确实进了影视库，但**「入库」不等于「够格」**
        —— 上次那批整理行为不一定符合我们的资源标准。这里用推荐引擎（评分/榜单/订阅）复核：

        - **够格** → 保持「静默-资源」（记 ``asset_recheck=keep``）
        - **不够格** → 降为「静默-普通」（记 ``asset_recheck=fail``）→ 此后**不再享受库内资产保护**
          （库里的硬链接文件不受影响，删的只是做种副本）

        识别不出来的资源**不动**（保持现状）。
        """
        cfg = getattr(self, "_recommend_cfg", {}) or {}
        try:
            groups = self._tag_groups()
        except Exception:  # noqa: BLE001
            groups = None
        snap = self._tag_all_torrents() or {}
        buckets: Dict[str, List[str]] = {}
        for h, t in (snap or {}).items():
            hh = str(h or "").strip().lower()
            tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            if not is_asset_tags(tags):
                continue
            gid = ""
            if groups is not None:
                try:
                    gid = groups.group_of(hh)
                except Exception:  # noqa: BLE001
                    gid = ""
            buckets.setdefault(gid or ("h:" + hh), []).append(hh)
        rep: Dict[str, Any] = {"ok": True, "applied": bool(apply), "resources": len(buckets),
                               "seeds": sum(len(v) for v in buckets.values()),
                               "qualified": 0, "unqualified": 0, "unrecognized": 0,
                               "downgraded": 0, "failed": 0, "unrated": 0, "restored": 0,
                               "skip_no_ledger": 0, "skip_state": 0,
                               "samples_fail": [], "samples_keep": [], "samples_unrated": []}
        try:
            engine = self._get_recommend_engine()
        except Exception as err:  # noqa: BLE001
            rep["ok"] = False
            rep["reason"] = f"推荐引擎不可用:{err}"
            return rep
        st = self._tag_state()
        _cache: Dict[str, Any] = {}
        _limit = int(limit or 0)
        try:  # 豆瓣评分源：本轮预算（防风控，超了就回退 TMDB）
            engine.begin_round(int(cfg.get("douban_max_per_run") or 0))
        except Exception:  # noqa: BLE001
            pass
        for gid, members in buckets.items():
            t0 = snap.get(members[0])
            title = str(getattr(t0, "title", "") or "") if t0 is not None else ""
            if title not in _cache:
                try:
                    _cache[title] = (engine.evaluate(title, with_poster=False) if title
                                     else {"recognized": False})
                except Exception:  # noqa: BLE001
                    _cache[title] = {"recognized": False}
            like = _cache.get(title) or {}
            if not like.get("recognized"):
                rep["unrecognized"] += 1
                continue
            _row = {"name": title[:70], "media": like.get("title"), "year": like.get("year"),
                    "rating": like.get("rating"), "seeds": len(members), "group": gid[:36]}
            if self._recommend_worth(like, cfg):
                rep["qualified"] += 1
                if len(rep["samples_keep"]) < 12:
                    rep["samples_keep"].append(_row)
                if apply:
                    for hh in members:
                        try:
                            _was = str((st.get(hh) or {}).get("asset_recheck") or "")
                            st.put(hh, {"asset_recheck": "keep", "asset_recheck_at": time.time()})
                            # ★ 双向：上一轮被判「不达标」的，这次达标了就放回「静默-资源」
                            if _was == "fail":
                                self._silent_to_resource(hh)
                                rep["restored"] = int(rep.get("restored") or 0) + 1
                        except Exception:  # noqa: BLE001
                            continue
                continue
            rep["unqualified"] += 1
            try:
                _rtf = float(like.get("rating") or 0)
            except (TypeError, ValueError):
                _rtf = 0.0
            if _rtf <= 0:
                # ★ TMDB 无评分（没数据 ≠ 差）→ 豁免不动（Master 2026-09-28 08:33 同意）
                rep["unrated"] += 1
                if len(rep["samples_unrated"]) < 12:
                    rep["samples_unrated"].append(_row)
                continue
            if len(rep["samples_fail"]) < 15:
                rep["samples_fail"].append(_row)
            if not apply or (_limit and rep["downgraded"] >= _limit):
                continue
            for hh in members:
                try:
                    cur = st.get(hh) or {}
                    if not cur:
                        rep["skip_no_ledger"] = int(rep.get("skip_no_ledger") or 0) + 1
                        continue
                    if str(cur.get("state") or "") != STATE_SILENT:
                        rep["skip_state"] = int(rep.get("skip_state") or 0) + 1
                        continue
                    okd = self._silent_to_plain(hh)
                    st.put(hh, {"asset_recheck": "fail", "asset_recheck_at": time.time()})
                    if okd:
                        rep["downgraded"] += 1
                    else:
                        rep["failed"] += 1
                except Exception as err:  # noqa: BLE001
                    rep["failed"] += 1
                    self._log(f"资源复核:降级失败 {hh[:12]}:{err}", "warning")
        if rep["downgraded"]:
            self._log(f"资源复核:复核 {rep['resources']} 组 → 达标 {rep['qualified']} · "
                      f"不达标 {rep['unqualified']}（已转普通 {rep['downgraded']}）")
        return rep

    def _asset_untag(self, *, apply: bool = False, limit: int = 0) -> Dict[str, Any]:
        """★ 摘掉**假**「已整理 / 辅种」标（Master 2026-09-28「你整理下」）。

        现状（实测）：qB 里 326 个种子带「已整理」且**必然成对带「辅种」**；这两个标
        **不是本插件写的**（我们只读，见 ``tags.py``），抽查在影视库里**根本没有对应文件**
        → 不是可靠的入库证据，却让一批种永久豁免删除、还干扰 ``sync_tag_assets`` 的证据链。

        安全的摘法：**只摘「账本里该资源没有库记」的**（有库记的留着无害）；
        不动账本 ``asset`` 标记（保持现状保护口径），只清 qB 标签，可回滚（保留快照）。
        """
        groups = self._tag_groups()
        gdata = groups.items() or {}
        snap = self._tag_all_torrents() or {}
        rep: Dict[str, Any] = {"ok": True, "applied": bool(apply), "scanned": 0, "managed": 0,
                               "kept_inlib": 0, "fake": 0, "removed": 0, "failed": 0, "samples": []}
        _limit = int(limit or 0)
        _dl_cache: Dict[str, Any] = {}
        for h, t in snap.items():
            hh = str(h or "").strip().lower()
            tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            if not any(x in MEDIA_ASSET_TAGS for x in tags):
                continue
            rep["scanned"] += 1
            try:
                gid = groups.group_of(hh)
            except Exception:  # noqa: BLE001
                gid = ""
            if not gid:
                continue
            rep["managed"] += 1
            inlib = bool(((gdata.get(gid) or {}).get("library") or {}).get("in_library"))
            if inlib:
                rep["kept_inlib"] += 1
                continue
            rep["fake"] += 1
            if len(rep["samples"]) < 20:
                rep["samples"].append({"hash": hh[:12], "group": gid[:40], "tags": tags})
            if not apply:
                continue
            if _limit and rep["removed"] >= _limit:
                continue
            try:
                _dn = str((self._tag_state().get(hh) or {}).get("downloader") or "qbittorrent")
                if _dn not in _dl_cache:
                    _dl_cache[_dn] = self._get_downloader(_dn)
                _dl = _dl_cache.get(_dn)
                _fn = getattr(_dl, "replace_torrent_tags", None) if _dl is not None else None
                _new = [x for x in tags if x not in MEDIA_ASSET_TAGS]
                if callable(_fn) and _fn(hh, _new):
                    rep["removed"] += 1
                else:
                    rep["failed"] += 1
            except Exception as err:  # noqa: BLE001
                rep["failed"] += 1
                self._log(f"资产摘标失败 {hh[:12]}:{err}", "warning")
        return rep

    def sync_tag_assets(self, *, apply: bool = False) -> Dict[str, Any]:
        """★ 建立/刷新「库内资产」记录（真·库记）。

        证据 = 种子上 MP 写的 ``已整理`` / ``辅种`` 标签（本部署 MP 的
        downloadhistory / transferhistory / downloadfiles 三张表都是 0 行，不可依赖）。
        库内资产 → 身份「资源」（落 ``mf_resource.identity`` / ``in_library``）。
        """
        store = self._tag_state()
        snap = self._tag_all_torrents()
        data = store.items()
        asset = non = changed = tag_synced = 0
        # ★ 13.0.0（Master「辅种应该按资源的身份打标签」）：副本跟随资源身份 ——
        #   库内资产的**成员**（含同保存目录/种名的副本）一并按「资源」打标，不靠 MP 的 已整理/辅种。
        try:
            _asset_members = set(asset_member_hashes(self._tag_groups()) or set())
        except Exception:  # noqa: BLE001
            _asset_members = set()
        _asset_keys = set()
        for _ah in _asset_members:
            _at = snap.get(_ah)
            if _at is None:
                continue
            _ak = torrent_data_key(_at)
            if _ak:
                _asset_keys.add(_ak)
        _dl = None
        _dl_fn = None
        for h, t in snap.items():
            hh = str(h or "").strip().lower()
            tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            if hh not in data:
                continue
            _dk = torrent_data_key(t)
            is_a = (is_asset_tags(tags) or hh in _asset_members
                    or bool(_dk and _dk in _asset_keys))
            if is_a:
                asset += 1
            else:
                non += 1
            rec = data.get(hh) or {}
            if is_library_asset(rec) == is_a:
                continue
            # ★ 标签主权（Master 2026-09-29）：真值源在魔流账本；
            #   MP 标签只是「证据输入」之一 → **只升不降**（摘掉标签后不会把库内身份抹掉）。
            if not is_a and is_library_asset(rec):
                continue
            changed += 1
            if apply:
                store.set_asset(hh, sub=(SUB_RESOURCE if is_a else SUB_NEW))
                # 副本的 qB 标签也要跟着资源身份走（老标签可能是「静默-新」）
                if is_a and tags:
                    _site = str(rec.get("site") or "") or self._torrent_site_name(tags, "")
                    _state = str(rec.get("state") or STATE_SILENT)
                    _new = retag(tags, site=_site, state=_state, sub=SUB_RESOURCE)
                    if sorted(_new) != sorted(tags):
                        if _dl is None:
                            _dl = self._get_downloader()
                            _dl_fn = getattr(_dl, "replace_torrent_tags", None) if _dl is not None else None
                        try:
                            if callable(_dl_fn) and _dl_fn(hh, _new):
                                tag_synced += 1
                        except Exception:  # noqa: BLE001
                            pass
        return {"ok": True, "applied": bool(apply), "asset": asset, "non_asset": non,
                "changed": changed, "tag_synced": tag_synced, "ledger": len(data)}

    def _resource_gid(self, title: Any, size_gb: Any, fp: Any = "") -> str:
        """资源 ID：**只用完整文件特征码**（同内容 = 同资源）。

        ★ 10.0.0（Master 2026-10-05「相同资源要避免下载；如果下载了，算两个资源」）：
        **没有（合法）特征码 → 不建资源**（返回 ``""``）。旧版退回「关键词|体积档」，导致体积
        相同、内容完全不同的种被并成一条资源（实测 71 条弱资源吃进 113 个种，还把 CARPT 的
        H&R 债来源记成「咖啡」→ 低效换种误删 24 个）。身份不够强，就不配当资源。

        合法特征码 = ``fingerprint.py`` 产出的 sha1 十六进制（32~64 位）。历史上被写坏成
        ``|2.0`` 这种「体积档」假码 → 同样当**无特征码**处理。
        """
        _fp = str(fp or "").strip().lower()
        if not _FP_OK.match(_fp):
            return ""
        return f"fp:{_fp}"

    def sync_resources(self, *, apply: bool = False) -> Dict[str, Any]:
        """★ 建/刷 资源账本（Master 20:38 模型）：资源 1 : N 种子。

        - 资源有 **来源站**（真下回来的那个站）与 **H&R 账单**（靠来源站的种子挂种结清）
        - 资源有 **库记**（命中 ``已整理``/``辅种`` → 该资源已入库）
        - **只有下完的才有资源**（``progress >= 1``）；没下完的只有种子
        """
        if not bool(self._tags_cfg.get("enabled", True)):
            return {"ok": False, "reason": "标签模型未启用"}
        store = self._tag_groups()
        ledger = self._tag_state().items()
        snap = self._tag_all_torrents()
        stat: Dict[str, Any] = {"ok": True, "applied": bool(apply), "resources": 0,
                                "members": 0, "multi": 0, "in_library": 0, "hr_bills": 0,
                                "joined_by_dir": 0}

        def _dirkey(_t: Any) -> str:
            """数据路径 key（同一 Release = 同一份内容；也是「共用目录」判据用的 key）。

            ★ 与 `features/silent.py::_data_key` 同口径：优先 ``content_path``，退回 ``save_path/标题``
            —— ``TorrentInfo`` 没有 ``name`` 字段（qB 的 name 映射到 title），取 ``.name`` 恒空。
            """
            return torrent_data_key(_t)

        # ★ 13.0.0（Master「辅种应该按资源的身份打标签」）：副本要**进资源成员表**，身份才能跟着资源走。
        #   有特征码的种子先建组；没有特征码的（旧种/别路径加进来的），按**同一保存目录/种名**归到那个组。
        _key2gid: Dict[str, str] = {}
        for _h0, _t0 in snap.items():
            _h0 = str(_h0 or "").strip().lower()
            _r0 = ledger.get(_h0) or {}
            _g0 = self._resource_gid(getattr(_t0, "title", "") or getattr(_t0, "name", ""),
                                     float(getattr(_t0, "size_gb", 0) or _r0.get("size_gb") or 0.0),
                                     str(_r0.get("fp") or ""))
            _k0 = _dirkey(_t0)
            if _g0 and _k0:
                _key2gid.setdefault(_k0, _g0)
        for h, t in snap.items():
            hh = str(h or "").strip().lower()
            rec = ledger.get(hh)
            if not rec:
                continue
            # ★ 10.0.0：TorrentInfo 字段是 ``title``（旧代码写 ``name`` → 恒空 → 退化成「|体积档」）
            title = getattr(t, "title", "") or getattr(t, "name", "") or rec.get("title") or ""
            size = float(getattr(t, "size_gb", 0) or rec.get("size_gb") or 0.0)
            try:
                prog = float(getattr(t, "progress", 1.0) or 0.0)
            except (TypeError, ValueError):
                prog = 1.0
            _fp = str(rec.get("fp") or "").strip()
            tags = [str(x).strip() for x in (getattr(t, "tags", None) or [])]
            gid = self._resource_gid(title, size, _fp)
            stat["members"] = int(stat["members"]) + 1
            if _fp:
                stat["with_fp"] = int(stat.get("with_fp") or 0) + 1
            else:
                # ★ 10.0.0：没有完整特征码 → **不拿「体积档」冒充身份**；
                #   ★ 13.0.0：但若它和某个已有资源**同一个保存目录/种名**，就归到那个资源（副本归户）。
                stat["no_fp"] = int(stat.get("no_fp") or 0) + 1
                _k = _dirkey(t)
                if _k and _k in _key2gid:
                    gid = _key2gid[_k]
                    stat["joined_by_dir"] = int(stat.get("joined_by_dir") or 0) + 1
            if apply and gid:
                # ★ 2026-10-11：透传 qB「每份事实」给来源站判据（真下载字节/完成时刻/加入时刻）
                store.add_member(gid, hh, site=rec.get("site") or "", size_gb=size,
                                 downloaded=prog >= 0.999, progress=prog,
                                 state=rec.get("state") or "", fp=_fp,
                                 dl_bytes=float(getattr(t, "downloaded", 0) or 0),
                                 completed_at=float(getattr(t, "completion_on", 0) or 0),
                                 added_at=float(getattr(t, "added_on", 0) or 0))
                if (is_asset_tags(tags) or is_library_asset(rec)) and store.set_library(gid, True):
                    stat["in_library"] = int(stat["in_library"]) + 1
                # ★ 资源身份（Master 2026-09-30）：入库/推荐过 → 资源；种子身份跟它走
                if is_asset_tags(tags) or is_library_asset(rec):
                    store.set_identity(gid, SUB_RESOURCE, by="sync")
        # 来源站 + H&R 账单：跨站来源份账本里的义务挂到「资源」上
        try:
            srcs = self._crossseed_sources().items()
        except Exception:  # noqa: BLE001
            srcs = {}
        for sib, srec in (srcs or {}).items():
            if not isinstance(srec, dict):
                continue
            _sib_fp = (str((ledger.get(str(sib).lower()) or {}).get("fp") or "").strip()
                       or str(srec.get("resource_id") or "").strip())
            gid = self._resource_gid(srec.get("title"), srec.get("size_gb"), _sib_fp)
            if not gid:
                # ★ 10.0.0：无完整特征码 → 不建资源、不开账单（H&R 靠种子级兜底）
                stat["sib_no_fp"] = int(stat.get("sib_no_fp") or 0) + 1
                continue
            _site_group_site = str(srec.get("site_b") or srec.get("site_b_domain") or "")
            a_hash = str(srec.get("a_hash") or "").strip().lower()
            # 来源站优先级：来源份记录 → 种子标签/标题后缀 → 账本站点（账本可能被同站纳管改错）
            _site = str(srec.get("site_b") or srec.get("site_b_domain") or "")
            if not _site:
                # 兜底：按种子标签 / 标题后缀（@HDFans 之类）猜
                _live = snap.get(str(sib).lower())
                _site, _dom = self._guess_site_of_torrent(
                    getattr(_live, "tags", None), srec.get("title")
                )
                if _site and not srec.get("site_b"):
                    srec["site_b"] = _site
                    try:
                        self._crossseed_sources().put(str(sib).lower(), {"site_b": _site, "site_b_domain": _dom})
                    except Exception:  # noqa: BLE001
                        pass
                    stat["hr_site_fixed"] = int(stat.get("hr_site_fixed") or 0) + 1
            if not _site:
                _site = str((ledger.get(str(sib).lower()) or {}).get("site") or "")
            if not _site and a_hash:
                _site = str((ledger.get(a_hash) or {}).get("site") or "")
            if apply:
                _sib_live = snap.get(str(sib).lower())
                store.add_member(gid, str(sib).lower(), site=_site_group_site,
                                 size_gb=float(srec.get("size_gb") or 0.0), downloaded=True,
                                 dl_bytes=(float(getattr(_sib_live, "downloaded", 0) or 0)
                                           if _sib_live is not None else None),
                                 completed_at=(float(getattr(_sib_live, "completion_on", 0) or 0)
                                               if _sib_live is not None else 0.0),
                                 added_at=(float(getattr(_sib_live, "added_on", 0) or 0)
                                           if _sib_live is not None else 0.0),
                                 fp=_sib_fp)
                if a_hash:
                    _a_live = snap.get(str(a_hash).lower())
                    store.add_member(gid, a_hash, site=str(srec.get("site_a") or ""),
                                     size_gb=float(srec.get("size_gb") or 0.0), downloaded=True,
                                     dl_bytes=(float(getattr(_a_live, "downloaded", 0) or 0)
                                               if _a_live is not None else None),
                                     completed_at=(float(getattr(_a_live, "completion_on", 0) or 0)
                                                   if _a_live is not None else 0.0),
                                     added_at=(float(getattr(_a_live, "added_on", 0) or 0)
                                               if _a_live is not None else 0.0),
                                     fp=(str((ledger.get(a_hash) or {}).get("fp") or "").strip() or _sib_fp))
                # ★ 19.0.0：``store.set_hr(...)`` 已退役（mf_resource.hrs 停写）；
                #   跨站来源份的 H&R 义务真值在 mf_bills（hrbills 开账）。
                stat["sib_hr_seen"] = int(stat.get("sib_hr_seen") or 0) + 1
        if apply:
            # ★ 10.0.0 迁徙：清掉「弱身份」（按体积档归的）资源组 —— 幂等，跑完就没有弱组了
            try:
                _pw = self._purge_weak_groups(apply=True)
                if _pw.get("weak"):
                    stat["weak_purged"] = _pw
                    self._log(f"资源:弱身份清理 弱组 {_pw.get('weak')} → 迁走 {_pw.get('moved')} · "
                              f"丢弃 {_pw.get('dropped')}（无特征码）")
            except Exception as err:  # noqa: BLE001
                self._dbg(f"弱资源清理异常:{err}")
            _gc_fn = getattr(store, "gc_empty_groups", None)
            if callable(_gc_fn):
                _gc = _gc_fn()
                if _gc:
                    stat["gc_empty_groups"] = _gc
            _rc_fn = getattr(store, "recompute_sources", None)
            if callable(_rc_fn):
                _rc = _rc_fn()
                if _rc:
                    stat["sources_recomputed"] = _rc
            try:
                _pend_n = len(store.pending_library())
                _flushed = store.flush_pending_library()
                if _pend_n:
                    stat["lib_pending"] = _pend_n
                if _flushed:
                    stat["lib_pending_applied"] = _flushed
                    self._log(f"库记:补齐待办 {_flushed} 条")
            except Exception:  # noqa: BLE001
                pass
        info = store.stats()
        stat["resources"] = info.get("groups") or 0
        stat["multi"] = info.get("multi_site_groups") or 0
        try:
            stat["in_library"] = sum(
                1 for r in store.items().values() if (r.get("library") or {}).get("in_library")
            )
            # ★ 19.0.0：``mf_resource.hrs`` 退役 → 账单统计改读 ``mf_bills``（真值源）
            try:
                _bst = self._hrbills_store().stats()
                stat["hr_bills"] = int(_bst.get("total") or 0)
                stat["hr_settled"] = int((_bst.get("by_state") or {}).get("settled") or 0)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
        return stat

    def _purge_weak_groups(self, *, apply: bool = False) -> Dict[str, Any]:
        """★ 10.0.0 迁徙：清掉「弱身份」资源组（``group_id`` 不以 ``fp:`` 开头）。

        弱组（``|2.0`` / ``关键词|3.4``）是按「体积档」归的，会把**不同内容**并成一条资源
        → 来源站 / H&R 全串味。处理：能算出完整特征码的成员 → 迁到 ``fp:<fp>`` 组；算不出
        （不在下载器 / 下载器不给特征码）的 → 随弱组一起消失（种子账本本身不动）。幂等。
        """
        try:
            store = self._tag_groups()
            items = dict(store.items() or {})
        except Exception as err:  # noqa: BLE001
            return {"ok": False, "error": str(err)}
        weak = [g for g in items if not _FP_OK.match(str(g)[3:] if str(g).startswith("fp:") else str(g))]
        if not weak:
            return {"ok": True, "weak": 0, "moved": 0, "dropped": 0}
        rep: Dict[str, Any] = {"ok": True, "weak": len(weak), "moved": 0, "dropped": 0}
        if not apply:
            rep["members"] = sum(len((items[g] or {}).get("members") or {}) for g in weak)
            return rep
        try:
            dl = self._get_downloader()
        except Exception:  # noqa: BLE001
            dl = None
        for gid in weak:
            rec = dict(items.get(gid) or {})
            for h, m in (rec.get("members") or {}).items():
                hh = str(h or "").strip().lower()
                if not hh:
                    continue
                fp = ""
                try:
                    if dl is not None and callable(getattr(dl, "get_torrent_fingerprint", None)):
                        fp = str(dl.get_torrent_fingerprint(hh) or "").strip()
                except Exception:  # noqa: BLE001
                    fp = ""
                if not fp:
                    rep["dropped"] = int(rep["dropped"]) + 1
                    # ★ 与弱组**解绑**：否则账本里这粒种仍指着那条弱资源行 → `save_groups` 会因
                    #   「还有种子指着它」把资源行留下 → 下次重载弱组复活（10.0.0 踩过：8 粒）。
                    try:
                        store.remove_member(hh)
                    except Exception:  # noqa: BLE001
                        pass
                    continue
                try:
                    store.add_member(
                        self._resource_gid("", 0.0, fp), hh,
                        site=str((m or {}).get("site") or ""),
                        size_gb=float((m or {}).get("size_gb") or rec.get("size_gb") or 0.0),
                        downloaded=bool((m or {}).get("downloaded", True)),
                        progress=float((m or {}).get("progress") or 1.0),
                        state=str((m or {}).get("state") or ""),
                        fp=fp,
                    )
                    rep["moved"] = int(rep["moved"]) + 1
                except Exception:  # noqa: BLE001
                    rep["dropped"] = int(rep["dropped"]) + 1
        # 收尾：弱组若已被搬空（add_member 会自动摘出），直接删掉残留
        try:
            data = dict(store.items() or {})
            changed = False
            for gid in [g for g in data
                        if not _FP_OK.match(str(g)[3:] if str(g).startswith("fp:") else str(g))]:
                data.pop(gid, None)
                changed = True
            if changed:
                store._write(data)
        except Exception:  # noqa: BLE001
            pass
        rep["left"] = len([g for g in (store.items() or {})
                           if not _FP_OK.match(str(g)[3:] if str(g).startswith("fp:") else str(g))])
        return rep

    def backfill_fingerprints(self, *, limit: int = 0) -> Dict[str, Any]:
        """给托管种补文件特征码（``branding``：资源按特征码归并、辅种配对直接用）。

        ``limit=0`` = 全部补齐（一次 HTTP/种，本地 qB 很快）；否则只补前 N 个。
        """
        downloader = self._get_downloader()
        if downloader is None or not getattr(downloader, "is_available", False):
            return {"ok": False, "reason": "下载器不可用"}
        store = self._tag_state()
        ledger = store.items()
        snap = self._tag_all_torrents()
        todo = [h for h, t in snap.items()
                if str(h).lower() in ledger
                and not _FP_OK.match(str((ledger.get(str(h).lower()) or {}).get("fp") or "").strip().lower())]
        if limit and limit > 0:
            todo = todo[:int(limit)]
        got = fail = 0
        for h in todo:
            try:
                fp = downloader.get_torrent_fingerprint(str(h).lower())
            except Exception:  # noqa: BLE001
                fp = None
            if fp:
                store.put(str(h).lower(), {"fp": fp})
                got += 1
            else:
                fail += 1
        if got:
            self.sync_resources(apply=True)
        return {"ok": True, "checked": len(todo), "got": got, "failed": fail,
                "remaining": max(0, len([h for h in snap if str(h).lower() in ledger]) - len(
                    [h for h in ledger if str((ledger.get(h) or {}).get('fp') or "").strip()]) - got)}

    # ------------------------------------------------------------------ ★ 15.8.15
    # Master：「希望增加魔流库内资产手动删除的入口」——
    #   「库内资产」独立列表入口 + **只破第 5 道闸**（库内资产）的手动删除。
    #   其余 4 道硬拦（手动保留 / 跨站来源份 / 已认领 / 欠 H&R）与两条豁免
    #   （在途点播 / 未下完的音乐线）**照旧硬拦**。
    # ------------------------------------------------------------------

    def _asset_rows(self, snap: Any = None, include_stale: bool = False) -> List[Dict[str, Any]]:
        """库内资产逐条明细（只读）——「库内资产」列表入口的唯一真值源。

        ★ Master 2026-10-10：这里列的是**资产（= 一份资源）**，不是单个种子。
        一行 = 资源账本里的一条（一份内容 = 多站各挂一个种）：
        ``name`` 显示**资源名**（不是单个种名），``members`` = 该资源的**全部种**
        （本体 + 各站辅种），``sites``/``member_count``/``members_in_qb`` 是它的组成。
        ``size_gb`` = **资源本身体积（一份，绝不把多站副本相加）**；``source_site`` = 来源站。

        身份判据与删除闸门第 5 类同口径（资源账本 ``library.in_library`` /
        ``identity == 资源``；``asset_recheck == fail`` 已降级的不算）。
        ``deletable`` 与 ``block`` 由 ``_delete_gate_manual``（跳过库内资产那一类）**预演**得到：
        只要该资源里**任一个**在下载器的成员被硬保护，整条即标被拦（不做「删一半」）。

        ``members_in_qb == 0``（仅账本残留，下载器里已无此种）的条目默认**不返回**；
        ``include_stale=1`` 才带上（标 ``stale`` + ``block="不在下载器（仅账本残留）"``）。
        """
        if snap is None:
            snap = self._tag_all_torrents() or {}
        try:
            groups = self._tag_groups()
            gitems = dict(groups.items() or {}) if groups is not None else {}
        except Exception:  # noqa: BLE001
            gitems = {}

        # ★ 15.8.18：媒体库内容名索引（media_id → 干净剧名/片名），供 name 优先显示，
        #   查不到的回退种子标题兜底。一次拉取、全列表复用。
        try:
            _media_titles = dict(get_backend(self)._media_titles() or {})
        except Exception:  # noqa: BLE001
            _media_titles = {}
        # ★ 15.8.18x：整理历史（download_hash → MP 识别媒体名），覆盖比 media_id 广得多。
        try:
            _xfer_titles = dict(get_backend(self)._transfer_titles() or {})
        except Exception:  # noqa: BLE001
            _xfer_titles = {}

        rows: List[Dict[str, Any]] = []
        for gid, grec in gitems.items():
            rec = dict(grec or {})
            if str(rec.get("asset_recheck") or "").strip().lower() == "fail":
                continue                      # 推荐复核不达标（已降级）不再享受资产保护
            in_lib = bool((rec.get("library") or {}).get("in_library"))
            ident = str(rec.get("identity") or "").strip() == SUB_RESOURCE
            if not (in_lib or ident):
                continue
            members = dict(rec.get("members") or {})
            if not members:
                continue
            src = str(rec.get("source_hash") or "").strip().lower()

            mrows: List[Dict[str, Any]] = []
            sites: List[str] = []
            for h, mrec in members.items():
                hh = str(h or "").strip().lower()
                if not hh:
                    continue
                m = dict(mrec or {})
                t = snap.get(hh)
                title = str(getattr(t, "title", "") or m.get("title") or "")
                site = str(m.get("site") or "")
                if not site:
                    # ★ 15.8.18：跨站辅种副本的站点只写了 qB 标签、没回写 mf_seed.site_id，
                    #   账本 site 为空 → 从标签兜底解析（如「魔流-聆音-静默-资源」→ 聆音）。
                    for _tg in (getattr(t, "tags", None) or []):
                        _pp = parse_tag(str(_tg))
                        if _pp and _pp.get("site"):
                            site = _pp["site"]
                            break
                try:
                    _sz = float(getattr(t, "size_gb", 0) or m.get("size_gb") or 0)
                except Exception:  # noqa: BLE001
                    _sz = 0.0
                if t and site and site not in sites:
                    sites.append(site)
                mrows.append({
                    "hash": hh,
                    "site": site,
                    "title": title,
                    "in_qb": bool(t),
                    "size_gb": round(_sz, 2),
                    "state": str(m.get("state") or ""),
                    "qb_state": str(getattr(t, "state", "") or "") if t else "",
                    "progress": round(float(getattr(t, "progress", 0) or m.get("progress") or 0), 4) if t else 0.0,
                    "tags": [str(x) for x in (getattr(t, "tags", None) or [])] if t else [],
                })
            live = [m for m in mrows if m["in_qb"]]
            if not live and not include_stale:
                continue
            # ★ 15.8.18：资源名优先用**媒体库内容名**（media_id → mediaserveritem.title，
            #   如「鬼灭之刃」），其次才回退种子标题（如「[鬼灭之刃].Demon.Slayer…2019…」）。
            # ★ 名称口径（Master 2026-10-11）：**以发布种自身的中文片名为准**——
            #   种名里的中文名 = 作品真名；MP 的识别名只兜底（MP 会把「高达00 剧场版」
            #   误认成「机动战士高达0079」，故不能让它反客为主）。
            name = ""
            _src_title = ""
            for m in mrows:
                if m["hash"] == src and m["title"]:
                    _src_title = m["title"]
                    break
            if not _src_title:
                for m in (live or mrows):
                    if m["title"]:
                        _src_title = m["title"]
                        break
            # ① 种子名里的中文片名（最可信）
            name = _clean_title_from_torrent(_src_title)
            # ② 整理历史（download_hash → MP 识别媒体名）—— 种子名没中文片名时用
            if not name:
                for _h in [src] + [m["hash"] for m in mrows]:
                    _nm = _xfer_titles.get(str(_h or "").lower())
                    if _nm:
                        name = _nm
                        break
            # ③ 媒体库内容名（media_id → mediaserveritem.title）
            _mid = str(((rec.get("library") or {}).get("media_id")) or "").strip()
            if not name and _mid and _media_titles.get(_mid):
                name = _media_titles[_mid]
            # ④ 全抽不到 → 保持原种子名
            if not name:
                name = _src_title
            # ⑤ 仍是纯英文种名 → 确定性清洗成「片名 (年份)」（不走网络）
            if name and not _TITLE_CJK.search(name):
                name = _clean_en_title(name) or name
            # ⑥ 收尾：任何还带发布标记的名字都剪掉标记（含带中文的混合名）
            name = _trim_junk(name)
            try:
                _sg = float(rec.get("size_gb") or 0)
            except Exception:  # noqa: BLE001
                _sg = 0.0
            if _sg <= 0:
                # 兜底：资源账本没记体积 → 取最大成员体积（≈一份，绝不把多站副本相加）
                try:
                    _sg = max([float(m.get("size_gb") or 0) for m in mrows] or [0.0])
                except Exception:  # noqa: BLE001
                    _sg = 0.0
            rows.append({
                "resource_id": str(gid),
                "name": name or "(未命名资源)",
                "source_hash": src,
                "source_site": str(rec.get("source_site") or ""),
                "identity": str(rec.get("identity") or ""),
                "in_library": in_lib,
                "sites": sites,
                "site_count": len(sites),
                "member_count": len(mrows),
                "members_in_qb": len(live),
                "size_gb": round(_sg, 2),
                "members": mrows,
                "stale": len(live) == 0,
                "deletable": False,
                "protected": False,
                "protected_hashes": [],
                "block": "",
            })

        _hs = [m["hash"] for r in rows for m in r["members"] if m["in_qb"]]
        why: Dict[str, str] = {}
        if _hs:
            try:
                why = dict(self._delete_gate_detail(_hs, snap=snap, allow_asset=True) or {})
            except Exception as e:  # noqa: BLE001
                self._log(f"库内资产列表：闸门预演失败 {e}", "error")
                why = {h: "闸门不可用（fail-closed）" for h in _hs}
        # ★ 15.9.0：把「手动保留」标到行上（供「库内资源管理」展示 + 取消保护）
        _keep = self._asset_manual_keep()
        for r in rows:
            _ph = [m["hash"] for m in r["members"]
                   if m.get("in_qb") and str(m["hash"]).lower() in _keep]
            r["protected_hashes"] = _ph
            r["protected"] = bool(_ph)
        for r in rows:
            if r["stale"]:
                r["block"] = "不在下载器（仅账本残留）"
                continue
            _reasons = sorted({str(why.get(m["hash"]) or "") for m in r["members"]
                               if m["in_qb"] and str(why.get(m["hash"]) or "")})
            if _reasons:
                r["block"] = "；".join(_reasons)
                continue
            r["deletable"] = True
        rows.sort(key=lambda x: (-float(x.get("size_gb") or 0), str(x.get("name") or "")))
        return rows

    # ------------------------------------------------------------------
    # ★ 15.9.0 库内资源管理：行内动作（保护 / 订阅 / 整理 / 刮削）
    #   Master 2026-10-11：「删除 保护 订阅 整理 刮削 的功能都放在这里」——
    #   推荐链路只负责「要不要入库」，入库之后的养护动作全部归口到本页。
    # ------------------------------------------------------------------

    def _asset_manual_keep(self) -> Set[str]:
        """手动保留 hash 并集（跨所有任务 + 空 task_id 桶）——与删除闸门口径**同源**。"""
        out: Set[str] = set()
        store = getattr(self, "_store", None)
        if store is None:
            return out
        tids = list((getattr(self, "_task_configs", None) or {}).keys())
        tids.append("")
        for tid in tids:
            try:
                out |= set(store.get_protected_torrents(tid) or set())
            except Exception:  # noqa: BLE001
                continue
        return {str(h).strip().lower() for h in out if str(h or "").strip()}

    def _asset_live_hashes(self, item: Dict[str, Any]) -> List[str]:
        return [str(m.get("hash") or "").lower() for m in (item.get("members") or [])
                if m.get("in_qb") and str(m.get("hash") or "").strip()]

    def _asset_protect(self, hashes: List[str], on: bool) -> Tuple[bool, str, List[str]]:
        """保护 / 取消保护：写入「手动保留」桶（task_id = ""，闸门认这个桶 → 整份资源永不自动删）。"""
        store = getattr(self, "_store", None)
        if store is None:
            return False, "存储不可用", []
        tids = list((getattr(self, "_task_configs", None) or {}).keys())
        tids.append("")
        done: List[str] = []
        for h in hashes:
            hh = str(h or "").strip().lower()
            if not hh:
                continue
            try:
                if on:
                    store.protect_torrent("", hh)
                else:
                    for tid in tids:
                        try:
                            store.unprotect_torrent(tid, hh)
                        except Exception:  # noqa: BLE001
                            continue
                done.append(hh)
            except Exception as err:  # noqa: BLE001
                self._log(f"库内资源{('保护' if on else '取消保护')}失败 {hh[:12]}: {err}", "warning")
        if not done:
            return False, "没有可操作的种（不在下载器）", []
        try:
            self._store.journal.record(
                task_id="", kind=("protection" if on else "unprotection"),
                items=[OperationItem(hash=h, title="", reason=("手动保留（库内资源管理）" if on
                                                              else "取消保留（库内资源管理）"))
                       for h in done],
            )
        except Exception:  # noqa: BLE001
            pass
        return True, (f"已保护 {len(done)} 个种（永不自动删）" if on
                      else f"已取消保护 {len(done)} 个种"), done

    def _asset_subscribe(
        self, name: str, seed_title: str, on: bool, season: int = 0
    ) -> Tuple[bool, str]:
        """订阅 / 退订「作品+季」（MP 侧按 标题+年份+季 自行识别；单集在库 → 抓齐其余集）。"""
        title = str(name or "").strip()
        src = str(seed_title or "").strip() or title
        if not title and not src:
            return False, "缺少资源名"
        info = dict(episode_info(src) or {})
        if int(season or 0) > 0:
            info["season"] = str(int(season))
        season_no = int("".join(ch for ch in str(info.get("season") or "") if ch.isdigit()) or 0)
        year = ""
        try:
            mi = recognize(src)
            if mi is not None:
                title = str(getattr(mi, "title", "") or title).strip() or title
                year = str(getattr(mi, "year", "") or "").strip()
        except Exception:  # noqa: BLE001
            mi = None
        if not title:
            return False, "未能识别资源名"
        if not season_no and str(getattr(mi, "type", "") or "").lower().find("movie") < 0 \
                and str(info.get("kind") or "") != "movie":
            return False, "无季号（电影或非剧集），暂不订阅"
        if not on:
            if not season_no:
                return False, "无季号，无法定位要退订的订阅"
            return self._recommend_unsubscribe_season(0, title, season_no)
        try:
            return self._recommend_subscribe_season(
                {"title": title, "season": season_no},
                {"title": title, "year": year},
            )
        except Exception as err:  # noqa: BLE001
            return False, str(err)

    def _asset_organize(self, item: Dict[str, Any]) -> Tuple[bool, str]:
        """重新整理入库：让 MP 把这份资源的文件**再换个地方**（复用推荐链路的整理实现）。"""
        seed = ""
        for m in (item.get("members") or []):
            if str(m.get("hash") or "").lower() == str(item.get("source_hash") or "").lower():
                seed = str(m.get("title") or "")
                break
        if not seed:
            for m in (item.get("members") or []):
                if m.get("in_qb") and m.get("title"):
                    seed = str(m.get("title") or "")
                    break
        live = self._asset_live_hashes(item)
        if not live:
            return False, "不在下载器（仅账本残留），无法整理"
        best = ""
        if str(item.get("source_hash") or "").lower() in live:
            best = str(item.get("source_hash") or "").lower()
        else:
            best = live[0]
        ok, msg = self._recommend_import(best, {"title": seed or str(item.get("name") or "")})
        return bool(ok), str(msg)

    def _asset_scrape(self, name: str, source: str = "", hashes: Optional[List[str]] = None
                      ) -> Tuple[bool, str]:
        """重新刮削：按资源名在媒体库里找到对应目录，走**多源兜底引擎**重刮（可纠正刮错）。"""
        title = str(name or "").strip()
        if not title:
            return False, "缺少资源名"
        try:
            eng = self._get_fallback_engine()
        except Exception as err:  # noqa: BLE001
            return False, f"刮削引擎不可用：{err}"
        if source:
            try:
                eng.set_cfg({**dict(getattr(eng, "cfg", {}) or {}), "sources": [source]})
            except Exception:  # noqa: BLE001
                pass
        hits: List[Any] = []
        # ① 优先：这份资源**整理落点**目录（transferhistory.dest → 剧集目录）
        try:
            dests = dict(get_backend(self)._transfer_dests() or {})
        except Exception:  # noqa: BLE001
            dests = {}
        for h in ([str(item_h or "").lower() for item_h in (hashes or [])]):
            _d = dests.get(h)
            if not _d:
                continue
            try:
                d = Path(_d)
                if not d.exists():
                    continue
                d = d if d.is_dir() else d.parent
                # 剧集：…/剧名 (年)/Season 01/xxx.mkv → 上跳到「剧名」层
                if re.match(r"^(season\s*\d+|s\d{1,2}|specials?|特别篇)$", str(d.name).strip(), re.I):
                    d = d.parent
                if d.exists() and d not in hits:
                    hits.append(d)
            except Exception:  # noqa: BLE001
                continue
        # ② 回退：按名字在媒体库根下模糊匹配
        key = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", title.lower())
        for root in ([] if hits else (eng.library_paths() or [])):
            try:
                for d in eng._collect_show_dirs(Path(root)):
                    _k = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(d.name).lower())
                    if not _k:
                        continue
                    if _k == key or (len(key) >= 2 and key in _k) or (len(_k) >= 2 and _k in key):
                        if d not in hits:
                            hits.append(d)
            except Exception:  # noqa: BLE001
                continue
        if not hits:
            return False, f"媒体库里没找到「{title}」的目录（先在 设置→元数据兜底 里配好媒体库路径）"
        done: List[str] = []
        for d in hits[:5]:
            try:
                rep = eng._scan_show(d, apply=True) or {}
                done.append(f"{d.name}（源：{rep.get('resolved') or '未命中'}·集 {len(rep.get('episodes') or [])}）")
            except Exception as err:  # noqa: BLE001
                done.append(f"{d.name}（失败：{err}）")
        return True, "重刮 " + "；".join(done)

    def assets_act(self, payload: MagicFlowAssetActPayload) -> Response:
        """★ 15.9.0「库内资源管理」行内动作统一入口（保护 / 订阅 / 整理 / 刮削）。

        - 参 ``resource_ids``（资源 id）；删除请走 ``/assets/delete``（默认干跑）。
        - 逐条返回 ``results``（ok / message），任何一条失败不影响其余。
        - **不删任何东西**：本入口只做「保留、订阅、整理、刮削」四类可逆/养护动作。
        """
        action = str(payload.action or "").strip().lower()
        if action not in ("protect", "unprotect", "subscribe", "unsubscribe", "organize", "scrape"):
            return Response(success=False, message="action 需为 protect/unprotect/subscribe/unsubscribe/organize/scrape")
        rids = [str(x or "").strip() for x in (payload.resource_ids or []) if str(x or "").strip()]
        try:
            rows = {str(r.get("resource_id") or ""): r
                    for r in self._asset_rows(include_stale=True)}
        except Exception as e:  # noqa: BLE001
            return Response(success=False, message=f"读取库内资源失败：{e}")
        items: List[Dict[str, Any]] = []
        for rid in rids:
            row = rows.get(rid)
            if row is not None:
                items.append(row)
        if not items and payload.hashes:
            _hset = {str(h or "").lower() for h in (payload.hashes or [])}
            for row in rows.values():
                if _hset & {str(m.get("hash") or "").lower() for m in (row.get("members") or [])}:
                    items.append(row)
        if not items:
            return Response(success=False, message="未找到对应资源（resource_ids / hashes 无效）")

        # ★ 15.10.0：默认**扔后台队列**跑（Master：「加个队列后台跑，让用户等体验不好」）——
        #   整理/订阅/刮削都是重活（网络 + 磁盘），同步等会把页面卡死、关页面还会断。
        background = bool(int(getattr(payload, "background", 1) or 0))
        results: List[Dict[str, Any]] = []
        for it in items:
            rid = str(it.get("resource_id") or "")
            name = str(it.get("name") or "")
            hs = self._asset_live_hashes(it)
            if background:
                try:
                    from .jobs import KIND_TEXT as _JT  # noqa: WPS433
                    _kt = _JT.get(f"asset_{action}", action)
                except Exception:  # noqa: BLE001
                    _kt = action
                job = self._job_submit(
                    kind=f"asset_{action}", title=f"{_kt}「{name}」",
                    fn=(lambda _it=it, _a=action, _p=payload: self._asset_act_one(_a, _it, _p)),
                    dedup_key=f"asset:{action}:{rid}",
                    params={"resource_id": rid},
                )
                results.append({"resource_id": rid, "name": name, "hashes": hs, "ok": True,
                                "job_id": job.get("id"), "queued": True,
                                "message": "已加入后台队列（关掉页面也会继续跑）"})
                continue
            ok, msg = self._asset_act_one(action, it, payload)
            results.append({"resource_id": rid, "name": name, "hashes": hs,
                            "ok": bool(ok), "message": str(msg)})
        _okn = sum(1 for r in results if r["ok"])
        return Response(
            success=_okn > 0,
            message=(f"{action}：已加入后台队列 {_okn} 条（可在「后台任务」看结果）" if background
                     else f"{action}：成功 {_okn}/{len(results)}"),
            data={"action": action, "results": results, "background": background},
        )

    def _asset_act_one(self, action: str, it: Dict[str, Any],
                       payload: MagicFlowAssetActPayload) -> Tuple[bool, str]:
        """单条资源的养护动作（同步体；后台任务里也是它）。"""
        rid = str(it.get("resource_id") or "")
        name = str(it.get("name") or "")
        hs = self._asset_live_hashes(it)
        if not hs and action in ("protect", "unprotect", "organize"):
            return False, "不在下载器（仅账本残留）"
        try:
            if action in ("protect", "unprotect"):
                ok, msg, _ = self._asset_protect(hs, action == "protect")
                return bool(ok), str(msg)
            if action in ("subscribe", "unsubscribe"):
                _seed = ""
                for m in (it.get("members") or []):
                    if str(m.get("hash") or "").lower() == str(it.get("source_hash") or "").lower():
                        _seed = str(m.get("title") or "")
                        break
                if not _seed:
                    for m in (it.get("members") or []):
                        if m.get("title"):
                            _seed = str(m.get("title") or "")
                            break
                return self._asset_subscribe(name, _seed, action == "subscribe",
                                             season=int(payload.season or 0))
            if action == "organize":
                return self._asset_organize(it)
            if action == "scrape":
                return self._asset_scrape(name, source=str(payload.scrape_source or ""), hashes=hs)
        except Exception as e:  # noqa: BLE001
            return False, f"执行异常：{e}"
        return False, f"未执行（未知动作 {action} / {rid[:12]}）"

    def assets_library(self, limit: int = 0, include_stale: int = 0) -> Response:
        """★ 15.8.15：「库内资产」列表（只读，独立入口的数据源）。

        ★ Master 2026-10-10：**资产（资源）粒度**——一条 = 一份资源（本体 + 各站辅种）。
        ``include_stale=1`` 才带上「不在下载器（仅账本残留）」条目（默认不显示，纯噪声）。
        """
        try:
            rows = self._asset_rows(include_stale=bool(int(include_stale or 0)))
            if limit and int(limit) > 0:
                rows = rows[: int(limit)]
            by_reason: Dict[str, int] = {}
            for r in rows:
                _b = str(r.get("block") or "")
                if _b:
                    by_reason[_b] = by_reason.get(_b, 0) + 1
            counts = {
                "total": len(rows),
                "deletable": sum(1 for r in rows if r.get("deletable")),
                "blocked": sum(1 for r in rows if r.get("block")),
                "manual_keep": sum(1 for r in rows if r.get("protected")),
                "by_reason": by_reason,
            }
            return Response(
                success=True,
                message=(f"库内资产 {counts['total']} 份资源"
                         f"（可删 {counts['deletable']} / 被拦 {counts['blocked']}）"),
                data={"items": rows, "counts": counts, "scanned_at": time.time()},
            )
        except Exception as e:  # noqa: BLE001
            self._log(f"库内资产列表失败: {e}", "error")
            return Response(success=False, message=str(e))

    def assets_view(self, view: str = "summary", q: str = "", resource_id: str = "",
                    sort: str = "size", limit: int = 50, cursor: str = "",
                    include_stale: int = 0, group_by: str = "") -> Response:
        """★ 15.19.0：库内资产的 **AI 读取面**（只读投影；唯一真值源 = :meth:`_asset_rows`）。

        Master 2026-10-12：「我有哪些资源、他们的情况」这类问题原来答不全 —— 全量资产
        ~390KB / 239 份，而 MCP 单次结果上限 30k 字符 → 只剩前 19 份。这里**不新造真值**，
        只把 ``assets_library`` 用的同一批行做**瘦身视图 + 筛选 + 排序 + 分页 + 聚合**：

        - ``view=summary``（默认）：每条去掉 ``members``/``source_hash``，只留
          name/size_gb/site_count/member_count/members_in_qb/sites/deletable/block（连
          ``sites`` 也截前 8 + ``sites_more``）→ 单条约 130 字符，默认 50 条 ≈ 6KB，
          30k 上限可容 ~220 条；再大的用 ``cursor`` 翻页（``next_cursor``）。
        - ``view=full``：含全部成员明细（原有粒度，单条中位 1.5KB）。
        - ``resource_id=<fp:…>``：**单份详情**（完整成员；给了它就忽略 q/sort/分页）。
        - ``q=``：关键词，匹配**资源名或任一成员种名**（不区分大小写）。
        - ``sort=size|sites|members|name``（默认 size 降序）。
        - ``group_by=site``：按站点聚合（每站份数/体积/可删数）→ 只回 ``groups`` + ``counts``。
        - ``limit``（默认 50；``0`` = 全部）/ ``cursor``（上次的 ``next_cursor``）。

        ``counts``（总数/可删/被拦/原因）**永远按全量**统计 —— AI 与前端口径一致。
        """
        try:
            rows = self._asset_rows(include_stale=bool(int(include_stale or 0)))
        except Exception as e:  # noqa: BLE001
            self._log(f"库内资产列表失败: {e}", "error")
            return Response(success=False, message=str(e))
        by_reason: Dict[str, int] = {}
        for r in rows:
            _b = str(r.get("block") or "")
            if _b:
                by_reason[_b] = by_reason.get(_b, 0) + 1
        counts = {
            "total": len(rows),
            "deletable": sum(1 for r in rows if r.get("deletable")),
            "blocked": sum(1 for r in rows if r.get("block")),
            "manual_keep": sum(1 for r in rows if r.get("protected")),
            "by_reason": by_reason,
        }
        msg = (f"库内资产 {counts['total']} 份资源"
               f"（可删 {counts['deletable']} / 被拦 {counts['blocked']}）")
        base: Dict[str, Any] = {"counts": counts, "scanned_at": time.time(), "message": msg}

        def _brief(r: Dict[str, Any]) -> Dict[str, Any]:
            _sites = [str(s) for s in (r.get("sites") or [])]
            return {
                "resource_id": r.get("resource_id"),
                "name": r.get("name"),
                "source_site": r.get("source_site"),
                "size_gb": r.get("size_gb"),
                "site_count": r.get("site_count"),
                "sites": _sites[:8],
                "sites_more": max(0, len(_sites) - 8),
                "member_count": r.get("member_count"),
                "members_in_qb": r.get("members_in_qb"),
                "deletable": bool(r.get("deletable")),
                "block": str(r.get("block") or ""),
                "stale": bool(r.get("stale")),
            }

        rid = str(resource_id or "").strip()
        if rid:
            hit = next((r for r in rows if str(r.get("resource_id") or "") == rid), None)
            if hit is None:
                return Response(
                    success=False,
                    message=(f"没找到资源 {rid}（只认 /agent/assets 里的 resource_id；"
                             f"「不在下载器（仅账本残留）」的要带 include_stale=1）"))
            return Response(
                success=True,
                message=(f"{hit.get('name')}：{hit.get('site_count')} 站 "
                         f"{hit.get('member_count')} 种 / {hit.get('size_gb')}GB"),
                data=dict(base, view="detail", item=hit))

        kw = str(q or "").strip().lower()
        sel = rows
        if kw:
            def _qhit(r: Dict[str, Any], _kw: str = kw) -> bool:
                if _kw in str(r.get("name") or "").lower():
                    return True
                for m in (r.get("members") or []):
                    if _kw in str((m or {}).get("title") or "").lower():
                        return True
                return False
            sel = [r for r in sel if _qhit(r)]

        gb = str(group_by or "").strip().lower()
        if gb == "site":
            agg: Dict[str, Dict[str, Any]] = {}
            for r in sel:
                for s in ([str(x) for x in (r.get("sites") or [])] or ["(未知)"]):
                    a = agg.setdefault(s, {"site": s, "resources": 0, "size_gb": 0.0, "deletable": 0})
                    a["resources"] = int(a["resources"]) + 1
                    a["size_gb"] = round(float(a["size_gb"]) + float(r.get("size_gb") or 0), 2)
                    a["deletable"] = int(a["deletable"]) + (1 if r.get("deletable") else 0)
            groups = sorted(agg.values(), key=lambda x: -int(x["resources"]))
            return Response(
                success=True,
                message=f"按站点聚合：{len(groups)} 个站 / {len(sel)} 份资源",
                data=dict(base, view="group", group_by="site", matched=len(sel), groups=groups))

        _ks = str(sort or "size").strip().lower()
        _key = {
            "size": lambda r: -float(r.get("size_gb") or 0),
            "sites": lambda r: -int(r.get("site_count") or 0),
            "members": lambda r: -int(r.get("member_count") or 0),
            "name": lambda r: str(r.get("name") or ""),
        }.get(_ks) or (lambda r: -float(r.get("size_gb") or 0))
        sel = sorted(sel, key=_key)

        try:
            off = max(0, int(str(cursor or "0").strip() or 0))
        except Exception:  # noqa: BLE001
            off = 0
        try:
            lim = int(limit)
        except Exception:  # noqa: BLE001
            lim = 50
        page = sel[off:] if lim <= 0 else sel[off:off + lim]
        nxt = str(off + len(page)) if (lim > 0 and off + len(page) < len(sel)) else ""
        _full = str(view or "").strip().lower() == "full"
        items = list(page) if _full else [_brief(r) for r in page]
        data = dict(base, view=("full" if _full else "summary"), matched=len(sel),
                    returned=len(items), offset=off, next_cursor=nxt, items=items)
        if nxt:
            data["hint"] = f"还有 {len(sel) - off - len(page)} 份，接着带 cursor={nxt} 再调"
        return Response(success=True, message=f"{msg}；本次返回 {len(items)}/{len(sel)}", data=data)

    def assets_delete(self, payload: MagicFlowAssetDeletePayload) -> Response:
        """★ 15.8.15 / 2026-10-10 / 15.10.0：手动删除库内资产（唯一允许突破「已入库永不删」的入口）。

        ★ 15.10.0：``confirm=1`` 时**默认扔后台队列**跑（删多个资源 + 连文件删可能很慢，
        别让页面转圈、关掉页面还会断）；``confirm=0``（干跑）仍**同步**算，方便先看会删什么。
        同步执行体 = :meth:`_assets_delete_sync`。
        """
        if int(payload.confirm or 0) == 1 and bool(int(getattr(payload, "background", 1) or 0)):
            _n = len([x for x in (payload.resource_ids or []) if str(x or "").strip()]) \
                or len([x for x in (payload.hashes or []) if str(x or "").strip()])
            job = self._job_submit(
                kind="asset_delete", title=f"删除库内资源 ×{_n or 1}",
                fn=(lambda _p=payload: self._assets_delete_sync(_p)),
                dedup_key="asset:delete:" + ",".join(
                    sorted(str(x or "").strip() for x in (payload.resource_ids or [])))[:80],
            )
            return Response(success=True,
                            message=f"已加入后台队列（删除 {_n or 1} 份资源，可在「后台任务」看结果）",
                            data={"queued": True, "job_id": job.get("id")})
        return self._assets_delete_sync(payload)

    def _assets_delete_sync(self, payload: MagicFlowAssetDeletePayload) -> Response:
        """★ 15.8.15 / 2026-10-10：手动删除库内资产（**唯一**允许突破「库内资产（已入库，永不删）」的入口）。

        ★ Master 2026-10-10：这里删的是**资产（一份资源）**——删除动作 = 把该资源的
        **全部在下载器的种**（本体 + 各站所有辅种）**一次批量删**；``delete_files=1`` 连文件删。
        一次删全组 → 文件就不再「被别的种共用」→ 内置共享护栏不会再把连文件删降级成只摘种。

        安全口径（每层 fail-closed）：
          1. 只受理**在本插件库内资产列表里**的资源（``resource_ids``；兼容只给 hash 时反查所属资源），
             其余拒收（连闸门都不进）；
          2. 真删前**重新**跑 ``_delete_gate_manual`` —— 手动保留 / 跨站来源份 / 已认领 /
             欠 H&R 四类照旧硬拦；该资源**任一**在库成员被硬保护 → 整条不动；
          3. ``confirm != 1`` → 干跑，**零写入**（不碰下载器、不写冷却、不写 journal）；
          4. 真删走唯一物理入口 ``delete_torrents(..., allow_library_asset=True)``。
        """
        rid_list: List[str] = []
        for _x in (payload.resource_ids or []):
            _r = str(_x or "").strip()
            if _r and _r not in rid_list:
                rid_list.append(_r)
        # 兼容：只给了 hash → 反查它属于哪个资源
        if not rid_list and payload.hashes:
            try:
                groups = self._tag_groups()
            except Exception:  # noqa: BLE001
                groups = None
            for _x in (payload.hashes or []):
                _h = str(_x or "").strip().lower()
                if not _h:
                    continue
                _gid = ""
                try:
                    _gid = str(groups.group_of(_h) or "") if groups is not None else ""
                except Exception:  # noqa: BLE001
                    _gid = ""
                if _gid and _gid not in rid_list:
                    rid_list.append(_gid)
        if not rid_list:
            return Response(success=False, message="未选择库内资产")
        confirm = int(payload.confirm or 0) == 1
        delete_files = int(payload.delete_files or 0) == 1
        reason = str(payload.reason or "").strip() or "手动删除库内资产"
        try:
            snap = self._tag_all_torrents() or {}
            known = {r["resource_id"]: r for r in self._asset_rows(snap=snap, include_stale=True)}

            results: List[Dict[str, Any]] = []
            for rid in rid_list:
                row = known.get(rid)
                if row is None:
                    results.append({"resource_id": rid, "name": "", "hashes": [], "ok": False,
                                    "deleted": False, "dry_run": not confirm,
                                    "message": "不是库内资产", "block": "不是库内资产"})
                    continue
                _name = str(row.get("name") or "")
                hs = [m["hash"] for m in (row.get("members") or []) if m.get("in_qb")]
                if not hs:
                    results.append({"resource_id": rid, "name": _name, "hashes": [], "ok": False,
                                    "deleted": False, "dry_run": not confirm,
                                    "message": "不在下载器（仅账本残留）",
                                    "block": "不在下载器（仅账本残留）"})
                    continue
                _blk = ""
                if confirm:
                    try:
                        _why = dict(self._delete_gate_detail(hs, snap=snap, allow_asset=True) or {})
                    except Exception as e:  # noqa: BLE001
                        self._log(f"库内资产删除：闸门复检失败 {e}", "error")
                        _why = {h: f"闸门复检失败（fail-closed）：{e}" for h in hs}
                    if _why:
                        _blk = "；".join(sorted({str(v) for v in _why.values()}))
                else:
                    _blk = str(row.get("block") or "")
                if _blk:
                    results.append({"resource_id": rid, "name": _name, "hashes": hs, "ok": False,
                                    "deleted": False, "dry_run": not confirm,
                                    "message": _blk, "block": _blk})
                    continue
                if not confirm:
                    results.append({"resource_id": rid, "name": _name, "hashes": hs, "ok": True,
                                    "deleted": False, "dry_run": True,
                                    "message": (f"将删除该资源全部 {len(hs)} 个种及文件" if delete_files
                                                else f"将删除该资源全部 {len(hs)} 个种（保留文件）"),
                                    "block": ""})
                    continue
                downloader = None
                try:
                    _rec0 = dict((self._tag_state() or {}).get(hs[0]) or {})
                    downloader = self._get_downloader(str(_rec0.get("downloader") or "qbittorrent"))
                except Exception:  # noqa: BLE001
                    downloader = None
                if downloader is None or not getattr(downloader, "is_available", False):
                    results.append({"resource_id": rid, "name": _name, "hashes": hs, "ok": False,
                                    "deleted": False, "dry_run": False,
                                    "message": "下载器不可用", "block": "下载器不可用"})
                    continue
                try:
                    _n, _err = downloader.delete_torrents(
                        hashes=hs, delete_file=delete_files, reason=reason,
                        source="assets.assets_delete", allow_library_asset=True,
                    )
                except Exception as e:  # noqa: BLE001
                    _n, _err = 0, str(e)
                if _n:
                    try:
                        _led = dict((self._tag_state() or {}).items() or {})
                    except Exception:  # noqa: BLE001
                        _led = {}
                    _items: List[Any] = []
                    for h in hs:
                        # ★ 15.8.18：删成功把 hash 从种子账本摘掉（清 mf_seed 行），
                        #   否则资源组成员残留 → 下次「含账本残留」又冒出来。
                        try:
                            if self._store and hasattr(self._store, "drop"):
                                self._store.drop(h)
                        except Exception:  # noqa: BLE001
                            pass
                        _rec = dict(_led.get(h) or {})
                        _tid = str(_rec.get("taken_by") or "")
                        try:
                            self._note_deleted(_tid, [h])
                        except Exception as e:  # noqa: BLE001
                            self._log(f"库内资产删除：冷却记账失败 {e}", "error")
                        _items.append(OperationItem(hash=h, title=_name, reason=reason))
                    try:
                        self._store.journal.record(task_id="", kind="deletion", items=_items)
                        self._invalidate_summary()
                    except Exception as e:  # noqa: BLE001
                        self._log(f"库内资产删除：journal 记账失败 {e}", "error")
                    results.append({"resource_id": rid, "name": _name, "hashes": hs, "ok": True,
                                    "deleted": True, "dry_run": False,
                                    "message": (f"已删除该资源 {int(_n)} 个种及文件" if delete_files
                                                else f"已删除该资源 {int(_n)} 个种（保留文件）"),
                                    "block": ""})
                else:
                    results.append({"resource_id": rid, "name": _name, "hashes": hs, "ok": False,
                                    "deleted": False, "dry_run": False,
                                    "message": str(_err or "删除失败"), "block": ""})

            deleted = sum(1 for r in results if r["deleted"])
            blocked = sum(1 for r in results if r.get("block"))
            failed = sum(1 for r in results if not r["ok"] and not r.get("block"))
            if not confirm:
                _ok = sum(1 for r in results if r["ok"])
                return Response(
                    success=True,
                    message=f"干跑（未做任何改动）：可删 {_ok} 份资源 / 被拦 {blocked} 份",
                    data={"dry_run": True, "deleted": 0, "blocked": blocked, "failed": 0,
                          "results": results},
                )
            return Response(
                success=bool(deleted > 0 or failed == 0),
                message=f"已删除 {deleted} 份资源（含文件：{'是' if delete_files else '否'}）"
                        f" / 被拦 {blocked} 份 / 失败 {failed} 份",
                data={"dry_run": False, "deleted": deleted, "blocked": blocked,
                      "failed": failed, "results": results},
            )
        except Exception as e:  # noqa: BLE001
            self._log(f"库内资产删除失败: {e}", "error")
            return Response(success=False, message=str(e))
