# -*- coding: utf-8 -*-
"""魔流 · siteops —— 站点规则与站点容量（事实层操作入口）。

（由原 `__init__.py` 拆分为 mixin，逐字搬运，行为不变。）
"""

import random
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


from app.schemas import Response
from app.sdk.logging import logger

from ..recommend import _norm
from ..sites.rules import (
    BUILTIN_RULES,
    SiteRules,
    framework_note,
    parse_hr_from_mail,
    parser_for_framework,
)
from ..sites.formula_fetch import (
    fetch_site_formula,
)


from ..common import (
    RULES_PROBE_DELAY,
    SITE_FORMULA_STALE_MAX,
    site_guard,
)
from ..tags import MARK_REUSE, SUB_RESOURCE, is_asset_tags, is_library_asset
from ..sitestore import get_site_store, slot_callbacks


class SiteOpsMixin:
    """siteops 功能集（原 MagicFlow 方法原样搬入）。"""

    def _framework_of(self, domain: str) -> str:
        """域名 → 框架（sitecap 查表，不联网；查不到给 ``unknown``）。★ 3.39.0

        类型级规则/解析器靠它选：同类站结构一致 → 一套解析、一个默认档。
        """
        dom = re.sub(r"^https?://", "", str(domain or "").strip().lower()).split("/")[0].strip()
        if not dom:
            return "unknown"
        try:
            cap = self.sitecaps().get(dom)
            fw = str(getattr(cap, "framework", "") or "").strip().lower()
            return fw or "unknown"
        except Exception:  # noqa: BLE001
            return "unknown"

    def _site_hr_flag(self, domain: str) -> Optional[bool]:
        """站点规则库里的 H&R 判定：``True`` 有 / ``False`` 无 / ``None`` 未知。"""
        try:
            return self._site_rules().hr_of(domain)
        except Exception:  # noqa: BLE001
            return None

    def _site_per_torrent_hr(self, domain: str) -> bool:
        """该站 H&R 是否**逐种开关**（如 YemaPT `hrPunishEnable`）。

        11.7.0：站点级无法评估具体种子的逐种标记 → 补源等「站点级预筛」场景保守排除。
        """
        try:
            return bool(self._site_rules().per_torrent_hr_of(domain))
        except Exception:  # noqa: BLE001
            return False

    def _site_rules(self) -> SiteRules:
        """站点规则账本(H&R / 保种时长 / 做种上限)，save_data 持久化。

        ★ 进程级单例（放 ``__magicflow_shared__``）：热重载会换掉插件实例，
        若新旧实例各持一份内存账本，旧实例的整表写入会把新实例的改动**盖回去**
        （踩过：探测写进去的促销规则被旧实例的旧快照覆盖）。
        """
        obj = getattr(self, "_site_rules_obj", None)
        if obj is not None:
            return obj
        try:
            import sys as _sys
            import types as _types

            _key = "__magicflow_shared__"
            mod = _sys.modules.get(_key)
            if mod is None:
                mod = _types.ModuleType(_key)
                _sys.modules[_key] = mod
            # ★ 幂等补齐所有共享属性：任一入口先建了模块，都不能少了 lock
            #   （踩过：__init__ 只建 instances/counters → persistence.__new__ 里 sh.lock 直接 AttributeError，插件加载失败）
            for _attr, _factory in (("instances", dict), ("counters", dict), ("lock", threading.Lock)):
                if not hasattr(mod, _attr):
                    setattr(mod, _attr, _factory())
            obj = mod.instances.get("site_rules")
            # ★ 热重载后模块里是「新的类」，但单例可能还是「旧类的实例」→ 新方法会 AttributeError。
            #   踩过：旧 SiteRules 没有 hr_of → H&R 判定全落到「未知保守」，规则库整块失效。
            if obj is not None and not isinstance(obj, SiteRules):
                obj = None
            if obj is None:
                _st = get_site_store(self)
                _get, _save = _st.callbacks("site_rules")
                obj = SiteRules(
                    get_data=_get,
                    save_data=_save,
                    log=self._log,
                    framework_of=self._framework_of,
                )
                mod.instances["site_rules"] = obj
        except Exception:  # noqa: BLE001
            _st = get_site_store(self)
            _get, _save = _st.callbacks("site_rules")
            obj = SiteRules(
                get_data=_get,
                save_data=_save,
                log=self._log,
                framework_of=self._framework_of,
            )
        self._site_rules_obj = obj
        return obj

    def _site_has_cookie(self, site_id: int) -> bool:
        """站点是否已配置 cookie(未配置的站点不抓考核,省 PV)。"""
        try:
            site = self._get_site(int(site_id or 0))
            return bool(str(getattr(site, "cookie", "") or "").strip())
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _url_host(value: str) -> str:
        """从未必带 scheme 的地址中取出主机名(小写)。"""
        try:
            from urllib.parse import urlsplit
            raw = value if "://" in value else f"https://{value}"
            return (urlsplit(raw).hostname or "").lower()
        except Exception:  # noqa: BLE001
            return ""

    def _url_allowed_for_site(self, url: str, site: Any) -> bool:
        """仅允许抓取该站点自身域名下的地址(防 cookie 外带 / SSRF)。"""
        try:
            from urllib.parse import urlsplit
        except Exception:  # noqa: BLE001
            return False
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        host = parsed.hostname.lower()
        site_hosts = set()
        for cand in (getattr(site, "url", "") or "", getattr(site, "domain", "") or ""):
            h = self._url_host(cand)
            if h:
                site_hosts.add(h)
        for sh in site_hosts:
            if host == sh or host.endswith("." + sh) or sh.endswith("." + host):
                return True
        return False

    def rules_watch(self) -> None:
        """站点规则库刷新(worker)：逐站探测并入库。"""
        if not bool(getattr(self, "_rules_cfg", {}).get("auto_refresh", True)):
            return
        if not self._acquire_worker_slot("站点规则"):
            return
        try:
            resp = self.probe_site_rules(site_id=0, persist=True)
            data = getattr(resp, "data", None) or {}
            n = len(data.get("results") or [])
            self._log(f"魔流:站点规则自动刷新完成（{n} 站）")
        except Exception as err:  # noqa: BLE001
            self._log(f"站点规则刷新异常:{err}", "warning")
        finally:
            self._release_worker_slot()

    def site_lifecycle(self) -> None:
        """★ 17.5.0（常驻 worker）：把「MP 侧已删站」落成台账标记（**只标记，不删行**）。

        为什么单独开一个常驻 worker：站点删除跟「有没有任务在跑」无关，而 LiveWatch
        只在有运行中/做种中任务时才注册 ⇒ 挂在那里会在全 stopped 时静默停摆。
        动作全幂等：判为已删 → ``status='deleted'``；MP 里又有该站 → 清回 NULL（复活）。
        """
        if not self._acquire_worker_slot("站点生命周期"):
            return
        try:
            r = site_deleted_mark(self)
            if not r.get("ok"):
                if r.get("skipped"):
                    logger.debug(f"魔流站点生命周期：跳过标记（{r.get('skipped')}）")
                elif r.get("error"):
                    self._log(f"站点生命周期标记失败:{r.get('error')}", "warning")
                return
            marked = int(r.get("marked") or 0)
            cleared = int(r.get("cleared") or 0)
            if not marked and not cleared:
                return
            names = [str(x) for x in (r.get("sites") or [])][:5]
            self._log(
                f"站点生命周期：MP 侧已删站 {marked} 个已标记 / {cleared} 个已复活"
                + (f"（{'、'.join(names)}）" if names else ""),
                "warning" if marked else "info",
            )
        except Exception as err:  # noqa: BLE001
            self._log(f"站点生命周期标记异常:{err}", "warning")
        finally:
            self._release_worker_slot()

    # ------------------------------------------------------- 站点规则库(H&R/保种)
    def _rules_fetch(self, site: Any, path: str) -> str:
        """抓该站自己域名下的一个页面（只读，失败返回 ""）。

        ★ 3.38.0：站点请求只出自采集模块（配额闸门 + 观测在那边）。
        """
        base = (getattr(site, "url", "") or f"https://{getattr(site, 'domain', '')}").rstrip("/")
        url = f"{base}/{str(path or '').lstrip('/')}"
        if not self._url_allowed_for_site(url, site):
            return ""
        c = self._collect_ref()
        if c is not None:
            try:
                res = c.http.text(int(getattr(site, "id", 0) or 0), url, kind="rules")
                return res.text if res.ok else ""
            except Exception:  # noqa: BLE001
                return ""
        # 采集模块不可用（极早启动阶段）→ 不自行发请求（唯一出口纪律）
        return ""

    def _clean_rule_urls(self, urls: Any) -> List[str]:
        """清掉「不是站规」的地址（faq 通用模板 / 个人信息页 / 收件箱等）。"""
        out: List[str] = []
        seen = set()
        for u in (urls or []):
            u = str(u or "").strip()
            if not u or self._RULE_URL_BAD.search(u) or u in seen:
                continue
            seen.add(u)
            out.append(u)
        return out

    def _pick_rule_links(self, links: Any) -> List[Tuple[str, str]]:
        """从欢迎短讯里的链接挑「规则地址」（强命中「规则/rules/wiki」优先，faq 次之）。

        这是 H&R 的**唯一自动入口**：站点自己在欢迎信里告诉你去哪读规则，那个地址才算数。
        """
        strong: List[Tuple[str, str]] = []
        soft: List[Tuple[str, str]] = []
        seen = set()
        for L in (links or []):
            href = str((L or {}).get("href") or "").strip()
            label = re.sub(r"\s+", " ", str((L or {}).get("label") or "").replace("&nbsp;", " ")).strip()
            if not href or href.startswith("#") or href.lower().startswith("javascript"):
                continue
            if self._RULE_LINK_BAD.search(href):
                continue
            if not (self._RULE_LINK_HARD.search(label) or self._RULE_LINK_HARD.search(href)):
                continue
            key = href.split("#")[0]
            if key in seen:
                continue
            seen.add(key)
            (strong if (self._RULE_LINK_STRONG.search(label) or self._RULE_LINK_STRONG.search(href)) else soft).append((label, href))
        return (strong + soft)[:3]

    @staticmethod
    def _hr_facts(got: Dict[str, Any]) -> Dict[str, Any]:
        """把解析结果收成「权威 H&R 事实」（来源固定 ``welcome`` = 欢迎短讯链路）。"""
        out: Dict[str, Any] = {
            "hr": (got or {}).get("hr"),
            "confidence": str((got or {}).get("confidence") or "low"),
            "evidence": str((got or {}).get("evidence") or ""),
            "source": "welcome",
            "hr_src": "welcome",
        }
        if (got or {}).get("seed_hours") is not None and str((got or {}).get("confidence")) == "high":
            out["seed_hours"] = (got or {})["seed_hours"]
        for _nk in ("seed_need_hours", "seed_window_hours"):
            if (got or {}).get(_nk) is not None:
                out[_nk] = (got or {})[_nk]
        return out

    def probe_site_rules(self, site_id: int = 0, persist: bool = True, paths: str = "") -> Response:
        """★ 逐站拉取站点规则并入库（H&R / 最短保种时长 / 做种上限）。

        ``site_id=0`` = **所有已配置站点**依次探测（每站之间随机歇 1.5~3.5s，礼貌限速；
        受该站 PV 预算约束，预算不够的直接跳过）。
        ``paths`` 可覆盖默认的探测页（逗号分隔，默认 ``myhr.php,rules.php``）。

        ★ 3.41.0：H&R **只从收件箱「欢迎短讯」里给出的规则地址**取（Master 定调：
        「所有 H&R 规则都从收件箱的欢迎邮件进，外面的是假规则」）。公开页只作名额/考核事实，
        H&R 一律不采。抓不到的**保持原样**，绝不把「没解析到」写成「没有 H&R」。
        """
        try:
            _want_override = [p.strip() for p in str(paths or "").split(",") if p.strip()]
            want = _want_override or ["myhr.php", "rules.php"]
            if site_id:
                site = self._get_site(int(site_id))
                sites = [site] if site else []
            else:
                sites = []
                for row in (self._list_sites() or []):
                    _s = self._get_site(int(row.get("id") or 0))
                    if _s is not None:
                        sites.append(_s)
            if not sites:
                return Response(success=False, message="没有可探测的站点")
            store = self._site_rules()
            results: List[Dict[str, Any]] = []
            for idx, site in enumerate(sites):
                sid = int(getattr(site, "id", 0) or 0)
                dom = str(getattr(site, "domain", "") or "").strip().lower()
                name = str(getattr(site, "name", "") or dom)
                item: Dict[str, Any] = {"site_id": sid, "name": name, "domain": dom}
                if not dom:
                    item["skipped"] = "无域名"
                    results.append(item)
                    continue
                if not getattr(site, "cookie", None):
                    item["skipped"] = "未配置 cookie"
                    store.ensure_builtin(dom, name)
                    results.append(item)
                    continue
                if not self._pv_allow(sid, "rules", 1):
                    item["skipped"] = "PV 预算不足"
                    results.append(item)
                    continue
                parsed: Dict[str, Any] = {}
                pages: List[str] = []
                # ★ 3.41.0：**H&R 唯一自动来源 = 收件箱「欢迎短讯」**
                #   （Master 定调：「所有 H&R 规则都从收件箱的欢迎邮件进，外面的是假规则」）
                mail_hr: Dict[str, Any] = {}
                _wv: Dict[str, Any] = {}
                try:
                    _wv = self._collect_ref().site(sid).welcome()
                except Exception as _me:  # noqa: BLE001
                    _wv = {"ok": False, "error": str(_me)}
                # ★ 3.39.0：按**框架**选解析器（同类站一套逻辑；未知 → 通用关键词）
                _fw = self._framework_of(dom)
                if _fw in ("", "unknown"):
                    # ★ 3.39.1：框架未知 → 现场识别一次（走采集层 + PV 闸门；识别一次能用 30 天）
                    #   否则「未知框架」站会一直用通用解析器 → 明明有 H&R 也读不出来。
                    try:
                        _cap = self._site_cap(sid, probe=True)
                        _fw2 = str(getattr(_cap, "framework", "") or "").strip().lower()
                        if _fw2 and _fw2 != "unknown":
                            _fw = _fw2
                            self._log(f"站点规则:{dom} 现场识别框架 = {_fw}")
                    except Exception as _fw_err:  # noqa: BLE001
                        self._log(f"站点规则:{dom} 框架识别失败:{_fw_err}", "warning")
                _parser = parser_for_framework(_fw)
                # ★ 3.41.2：框架是 custom/unknown（如 GitBook wiki）时，通用解析器可能读不出条款 →
                #   兜底再试 NexusPHP 解析器（PT 站最通用的写法）；两者都读不到才算没有。
                _parser_chain: List[Any] = [_parser]
                if str(_fw or "").strip().lower() not in ("nexusphp",):
                    try:
                        _np = parser_for_framework("nexusphp")
                        if _np is not None and _np is not _parser:
                            _parser_chain.append(_np)
                    except Exception:  # noqa: BLE001
                        pass
                item["framework"] = _fw
                # ★ 3.41.0：**只走欢迎短讯给出的「规则」地址**——「外面的是假规则」。不再默认抓
                #   myhr.php / rules.php；`paths` 参数可手动覆盖地址。
                _hr_cands: List[Dict[str, Any]] = []
                _rule_urls: List[str] = []
                _rule_meta: Dict[str, Any] = {}
                # ★ 3.41.0：**地址一次捞到就存下来**（省 PV：以后直接读存量地址，不再翻收件箱）
                _saved = str((store.get(dom) or {}).get("rule_url") or "").strip()
                _saved_urls = self._clean_rule_urls(re.split(r"[,\s]+", _saved)) if _saved else []
                if _want_override:
                    _rule_urls = list(want)
                    item["rule_src"] = "paths"
                    # ★ 3.41.2：手动给的地址**也存下来**（Master：把地址存下来不就好了）→ 以后当存量用
                    _rule_meta = {
                        "rule_url": " ".join(_rule_urls)[:400],
                        "rule_label": "手动指定",
                        "rule_src": "saved",
                        "rule_mail_id": "",
                    }
                elif _saved_urls:
                    _rule_urls = _saved_urls[:3]
                    item["rule_src"] = "saved"
                    item["rule_url"] = " ".join(_rule_urls)
                    _wv = {"ok": False, "error": "已存地址"}
                    if " ".join(_rule_urls) != _saved:
                        _rule_meta = {"rule_url": " ".join(_rule_urls)[:400]}
                # 没有（可用的）存量地址 → 现捞一次（收件箱欢迎短讯里的「规则」地址）并落库
                if not _rule_urls:
                    if _wv.get("ok"):
                        item["welcome"] = {"id": _wv.get("id"), "subject": _wv.get("subject")}
                        _targets = self._pick_rule_links(_wv.get("links") or [])
                        _rule_urls = [u for _l, u in _targets]
                        item["welcome"]["rule_links"] = [{"label": _l, "url": _u} for _l, _u in _targets]
                        if _targets:
                            _rule_meta = {
                                "rule_url": " ".join(_rule_urls)[:400],
                                "rule_label": str(_targets[0][0])[:60],
                                "rule_src": "welcome",
                                "rule_mail_id": str(_wv.get("id") or ""),
                                "rule_mail_subject": str(_wv.get("subject") or "")[:80],
                            }
                            item["rule_src"] = "welcome"
                        else:
                            # 少数站把条款直接写在信里 → 正文兜底
                            _mres = parse_hr_from_mail(str(_wv.get("body") or ""), _fw)
                            if _mres.get("hr") is not None:
                                _hr_cands.append({"from": "欢迎短讯正文", **self._hr_facts(_mres)})
                                item["welcome"]["hr_from_body"] = _mres.get("hr")
                    else:
                        item["welcome"] = {"ok": False, "error": str(_wv.get("error") or "")[:60]}
                for path in _rule_urls:
                    if not self._pv_allow(sid, "rules", 1):
                        break
                    html = ""
                    try:
                        if str(path).lower().startswith("http"):
                            _fr = self._collect_ref().site(sid).url(str(path), kind="official")
                            html = _fr.text if getattr(_fr, "ok", False) else ""
                        else:
                            html = self._rules_fetch(site, path)
                    except Exception as _fe:  # noqa: BLE001
                        self._log(f"站点规则:{dom} 规则页抓取失败:{str(_fe)[:60]}", "warning")
                    self._pv_spend(sid, "rules", 1)
                    if not html:
                        continue
                    pages.append(path)
                    got = {}
                    for _pi, _pp in enumerate(_parser_chain):
                        _g = _pp(html) or {}
                        if _g.get("hr") is not None:
                            got = _g
                            if _pi:
                                item["hr_parser"] = "nexusphp(兜底)"
                            break
                        if not got or len(_g) > len(got):
                            got = _g
                    # H&R：**只有从欢迎短讯指到的地址**来的才算数（source=welcome）
                    if got.get("hr") is not None:
                        _hr_cands.append({"from": str(path), **self._hr_facts(got)})
                    # 非 H&R 事实（名额/考核）照常采
                    if got.get("exam_avg_hours") is not None and parsed.get("exam_avg_hours") is None:
                        parsed["exam_avg_hours"] = got["exam_avg_hours"]
                        parsed["exam_evidence"] = f"{path}: {got.get('exam_evidence', '')}"
                    if got.get("seed_cap") is not None and parsed.get("seed_cap") is None:
                        parsed["seed_cap"] = got["seed_cap"]
                # 多个候选页 → 优先「带保种时长」的那条（其余只保 hr）
                if _hr_cands:
                    _best = next((c for c in _hr_cands if c.get("seed_hours") is not None), _hr_cands[0])
                    mail_hr = {k: v for k, v in _best.items() if k != "from"}
                    item["hr_source_page"] = _best.get("from")
                elif pages:
                    # ★ 3.41.2（Master）：「规则里面没有关键字就是没有」——规则页**读到了**但没有任何
                    #   H&R 关键字 → 明确判定「无 H&R」，不再留一个含糊的「未知」。
                    mail_hr = {
                        "hr": False, "confidence": "low", "source": "welcome", "hr_src": "welcome",
                        "evidence": f"{pages[0]}: 规则页未出现 H&R 关键字（按「无关键字即无」判定）",
                    }
                    item["hr_source_page"] = f"{pages[0]}（未提及 H&R）"
                item["pages"] = pages
                item["parsed"] = parsed
                if persist and _rule_meta:
                    try:
                        store.put(dom, _rule_meta)      # ★ 地址落库（durable）
                    except Exception as _qe:  # noqa: BLE001
                        self._log(f"站点规则:{dom} 规则地址落库失败:{_qe}", "warning")
                _stored: Dict[str, Any] = {}
                _cur_src = str((store.get(dom) or {}).get("source") or "")
                _site_manual = _cur_src == "manual"
                if persist and mail_hr:
                    # ★ 3.41.2：欢迎链路的结论是**每轮重新推导**的 → 覆盖式写入；
                    #   只有「手填」才是不许动的最高权威（踩过：welcome 被当权威后，旧误判写不回去）
                    _payload = dict(mail_hr, name=name, site_id=sid)
                    rec = store.merge_probe(dom, _payload) if _site_manual else store.put(dom, _payload)
                    _stored.update({
                        k: rec.get(k)
                        for k in ("hr", "seed_hours", "seed_need_hours", "seed_cap", "source")
                    })
                if persist and (
                    parsed.get("seed_cap") is not None
                    or parsed.get("exam_avg_hours") is not None
                ):
                    _payload2 = dict(parsed, name=name, site_id=sid)
                    rec = store.merge_probe(dom, _payload2) if _site_manual else store.put(dom, _payload2)
                    _stored.setdefault("source", rec.get("source"))
                    _stored["seed_cap"] = rec.get("seed_cap")
                if not persist:
                    pass
                elif _stored:
                    item["stored"] = _stored
                else:
                    store.ensure_builtin(dom, name)
                eff, src = self._crossseed_seed_hours_detail(dom)
                item["effective_hours"] = eff
                item["hours_src"] = src
                results.append(item)
                if idx + 1 < len(sites):
                    time.sleep(random.uniform(*RULES_PROBE_DELAY))
            # ★ 3.41.0：一次性作废「公开页 / 内置表」推出来的 H&R（Master 定调）
            try:
                if not bool(self.get_data("hr_trust_migrated_3410")):
                    _n = store.retire_untrusted_hr()
                    self.save_data(key="hr_trust_migrated_3410", value=True)
                    self._log(
                        f"站点规则:H&R 只认「手填 + 收件箱欢迎短讯」，已作废外部来源 {_n} 条（生效时长回落默认）"
                    )
            except Exception as _re:  # noqa: BLE001
                self._log(f"站点规则:作废外部 H&R 失败:{_re}", "warning")
            ok_n = sum(1 for r in results if r.get("stored") or r.get("parsed"))
            self._log(
                f"站点规则:探测完成 {ok_n}/{len(results)} 站有结果"
                f"（H&R 只走收件箱欢迎短讯的规则地址；paths={paths or '自动'}）"
            )
            return Response(success=True, message=f"已探测 {len(results)} 个站点，{ok_n} 个有结果并入库", data={
                "results": results,
                "rules": self._rules_view(),
            })
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=f"探测失败: {err}")

    def _rules_view(self) -> List[Dict[str, Any]]:
        """规则库视图：**每个站点一行**（按域名别名合并，如 ``btschool.club`` ≡ ``pt.btschool.club``）。

        行内含：有无 H&R、生效保种时长与来源、做种上限、证据片段、是否已入库。
        """
        def _norm(d: str) -> str:
            return re.sub(r"^https?://", "", str(d or "").strip().lower()).strip("/")

        store = self._site_rules()
        manual = (getattr(self, "_cs_cfg", {}) or {}).get("site_hours") or {}
        if not isinstance(manual, dict):
            manual = {}
        # 站点列表（MP 配置）→ 展示用域名/站点名
        site_rows: List[Dict[str, Any]] = []
        try:
            for r in (self._list_sites() or []):
                d = _norm(r.get("domain"))
                if d:
                    site_rows.append({"domain": d, "name": str(r.get("name") or "")})
        except Exception:  # noqa: BLE001
            pass

        def _alias(a: str, b: str) -> bool:
            a, b = _norm(a), _norm(b)
            if not a or not b:
                return False
            return a == b or a.endswith("." + b) or b.endswith("." + a)

        groups: List[Dict[str, Any]] = []

        def _group_for(dom: str) -> Dict[str, Any]:
            for g in groups:
                if _alias(g["domain"], dom):
                    return g
            g = {"domain": _norm(dom), "aliases": [], "rec": {}, "site_name": "", "manual": None}
            groups.append(g)
            return g

        # 1) 规则库（探测/内置已入库的）
        for dom, rec in store.items().items():
            g = _group_for(dom)
            g["aliases"].append(_norm(dom))
            if (rec.get("seed_hours") is not None) or (not g["rec"]):
                g["rec"] = dict(rec)
            if rec.get("name"):
                g["site_name"] = str(rec.get("name"))
        # 2) MP 站点列表（未入库的也展示，方便一眼看出缺哪站）
        for row in site_rows:
            g = _group_for(row["domain"])
            g["aliases"].append(row["domain"])
            g["display_domain"] = row["domain"]
            if row["name"]:
                g["site_name"] = row["name"]
        # 3) 手填覆盖
        for dom, hrs in (manual or {}).items():
            g = _group_for(dom)
            g["aliases"].append(_norm(dom))
            g["manual"] = hrs
        # 4) 内置已知（不在列表也不在库里的也展示）
        for dom, b in BUILTIN_RULES.items():
            if not any(_alias(g["domain"], dom) for g in groups):
                g = _group_for(dom)
                g["aliases"].append(dom)
                g["rec"] = dict(b or {})

        out: List[Dict[str, Any]] = []
        for g in groups:
            disp = str(g.get("display_domain") or g["domain"])
            eff, src = self._crossseed_seed_hours_detail(disp)
            row = dict(g["rec"] or {})
            row["domain"] = disp
            row["site_name"] = g["site_name"] or row.get("name") or disp
            row["effective_hours"] = eff
            row["hours_src"] = src
            # ★ 3.39.0：来源可见；★ 3.41.0：H&R 只认「手填 / 欢迎短讯」，其余标 retired
            _fw = str(row.get("framework") or self._framework_of(disp) or "unknown")
            row["framework"] = _fw
            if g.get("manual") is not None:
                row["layer"] = "manual"
            else:
                _src = str(row.get("source") or "none")
                _retired = (row.get("hr_src") == "retired") or bool(row.get("seed_hours_retired"))
                row["layer"] = "retired" if (_retired and _src not in ("manual", "welcome")) else _src
            row["hr_trusted"] = str(row.get("source") or "") in ("manual", "welcome")
            row["hr_source"] = str(row.get("source") or "")
            # ★ 11.7.0：逐种 H&R 站可见（无站点级 H&R，H&R 由发布者逐种开关；补源禁用）
            try:
                row["per_torrent_hr"] = bool(store.per_torrent_hr_of(disp))
            except Exception:  # noqa: BLE001
                row["per_torrent_hr"] = False
            # ★ 3.41.0：规则地址（从收件箱欢迎短讯捞到并落库）可见
            row["rule_url"] = str(row.get("rule_url") or "")
            row["rule_label"] = str(row.get("rule_label") or "")
            row["rule_src"] = str(row.get("rule_src") or "")
            try:
                row["framework_default"] = framework_note(_fw) or ""
            except Exception:  # noqa: BLE001
                row["framework_default"] = ""
            if g.get("manual") is not None:
                row["manual_hours"] = g["manual"]
            # ★ 15.6.0：站点级完成度阈值（覆盖全局；null/空 = 跟全局）
            try:
                _cr = (store.get(disp) or {}).get("complete_ratio")
                row["complete_ratio"] = None if _cr in (None, "") else float(_cr)
            except Exception:  # noqa: BLE001
                row["complete_ratio"] = None
            row["in_library"] = bool(g["rec"])
            if row.get("seed_hours") is None and row.get("seed_hours_seen") is not None:
                row["evidence_hours"] = row.get("seed_hours_seen")
            out.append(row)
        out.sort(key=lambda r: (str(r.get("site_name") or r.get("domain") or "")))
        return out

    def get_site_rules(self, action: str = "", site: str = "", hours: str = "", hr: str = "",
                       ratio: str = "") -> Response:
        """站点规则库读写。

        - ``GET /rules``：列表（含生效保种时长与来源）；
        - ``GET /rules?action=refresh``：按 MP 配置 + 内置表补全（**不触网**）；
        - ``GET /rules?action=probe&site=<id|domain>``：抓页面探测（1~2 请求/站）；
        - ``GET /rules?action=set&site=<domain>&hours=<n>``：手填覆盖（写进「站点保种时长」）；
        - ``GET /rules?action=set_ratio&site=<domain>&ratio=<0~1>``：★ 15.6.0 站点级**完成度阈值**
          （空 / 1 = 清掉覆盖，回全局默认）。
        """
        try:
            act = str(action or "").strip().lower()
            store = self._site_rules()
            if act in ("set_ratio", "ratio"):
                dom = str(site or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")
                if not dom:
                    return Response(success=False, message="缺少 site(域名)")
                _rv = str(ratio or "").strip()
                if _rv == "":
                    store.put(dom, {"complete_ratio": None})
                    return Response(success=True, message=f"{dom} 完成度阈值已清掉（回全局默认）",
                                    data={"rules": self._rules_view()})
                try:
                    rv = float(_rv)
                except (TypeError, ValueError):
                    return Response(success=False, message="ratio 必须是数字(0~1)")
                rv = min(1.0, max(0.0, rv))
                store.put(dom, {"complete_ratio": rv})
                return Response(success=True,
                                message=f"{dom} 完成度阈值已设为 {rv:g}（下载进度 ≥ 该值才计 H&R）",
                                data={"rules": self._rules_view()})
            if act == "set":
                dom = str(site or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")
                if not dom:
                    return Response(success=False, message="缺少 site(域名)")
                try:
                    hv = float(hours)
                except (TypeError, ValueError):
                    return Response(success=False, message="hours 必须是数字")
                manual = dict((getattr(self, "_cs_cfg", {}) or {}).get("site_hours") or {})
                manual[dom] = max(0.0, hv)
                self._cs_cfg["site_hours"] = manual
                self.save_data(key="crossseed_cfg", value=dict(self._cs_cfg))
                return Response(success=True, message=f"{dom} 保种时长已设为 {hv:g}h", data={"rules": self._rules_view()})
            if act in ("hr", "nohr"):
                dom = str(site or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")
                if not dom:
                    return Response(success=False, message="缺少 site(域名)")
                val = str(hr or "").strip().lower()
                if val in ("0", "false", "no", "none", "off"):
                    store.put(dom, {
                        "hr": False, "seed_hours": 0.0, "source": "manual", "confidence": "high",
                        "evidence": "手填：该站无 H&R，不做 H&R 保种保护",
                    })
                    return Response(success=True, message=f"{dom} 已标记为「无 H&R」(不做保护)", data={"rules": self._rules_view()})
                if val in ("1", "true", "yes", "on"):
                    prev = dict(store.items().get(dom) or {})
                    hours = prev.get("seed_hours")
                    if not hours:
                        hours = self._crossseed_seed_hours(dom) or 24.0
                    store.put(dom, {
                        "hr": True, "seed_hours": float(hours), "source": "manual", "confidence": "high",
                        "evidence": "手填：该站有 H&R（按此保护）",
                    })
                    return Response(
                        success=True,
                        message=f"{dom} 已标记为「有 H&R」（手动，按 {float(hours):g}h 保护；如需改时长直接编辑「保种(h)」）",
                        data={"rules": self._rules_view()},
                    )
                # 其余（unknown/空/其它）= 取消手填，交还探测
                store.clear(dom)
                store.ensure_builtin(dom)
                return Response(success=True, message=f"{dom} 已恢复为探测/内置判定", data={"rules": self._rules_view()})
            if act in ("refresh", "sync"):
                for dom, nm in (({str(r.get("domain") or "").strip().lower(): str(r.get("name") or "") for r in (self._list_sites() or [])})).items():
                    if dom:
                        store.ensure_builtin(dom, nm)
                return Response(success=True, message="已按 MP 配置 + 内置表补全规则库", data={"rules": self._rules_view()})
            if act in ("probe", "fetch"):
                sid = 0
                dom = str(site or "").strip()
                if dom:
                    if dom.isdigit():
                        sid = int(dom)
                    else:
                        sid = self._site_id_by_domain(dom)
                        if not sid:
                            # 别名兜底：MP 里存 btschool.club，用户可能写 pt.btschool.club
                            _d = re.sub(r"^https?://", "", dom.strip().lower()).strip("/")
                            for _row in (self._list_sites() or []):
                                _rd = re.sub(r"^https?://", "", str(_row.get("domain") or "").strip().lower()).strip("/")
                                if _rd and (
                                    _rd == _d or _rd.endswith("." + _d) or _d.endswith("." + _rd)
                                ):
                                    sid = int(_row.get("id") or 0)
                                    break
                        if not sid:
                            return Response(success=False, message=f"未找到站点 {dom}")
                return self.probe_site_rules(site_id=sid, persist=True)
            if act == "clear":
                n = store.clear(str(site or ""))
                return Response(success=True, message=f"已清空规则库 {n} 条", data={"rules": self._rules_view()})
            _rp_info: Dict[str, Any] = {}
            try:
                from .. import rulepack as _rp_mod

                _rp_info = {
                    "ok": bool(_rp_mod.pack_ok()),
                    "file": str(getattr(_rp_mod, "PACK_PATH", "")),
                    "frameworks": _rp_mod.framework_names(),
                    "domains": len(_rp_mod.builtin_domains() or {}),
                }
            except Exception:  # noqa: BLE001
                _rp_info = {}
            return Response(success=True, message="OK", data={"rules": self._rules_view(), "rulepack": _rp_info})
        except Exception as err:  # noqa: BLE001
            return Response(success=False, message=str(err))

    def probe_site_formula(self, site_id: int, persist: bool = False) -> Response:
        """诊断:抓取站点 mybonus.php 并解析魔力公式与参数。

        Args:
            site_id: 站点 ID。
            persist: 是否同时把结果写入站点公式预设缓存(供内核命中)。
        """
        site = self._get_site(site_id)
        if not site:
            return Response(success=False, message="站点不存在")
        try:
            cap = fetch_site_formula(site)
            if persist and cap.ok:
                _dom = (getattr(site, "domain", "") or "").strip().lower()
                self._register_formula_params(_dom, cap, getattr(site, "name", "") or "")
                if _dom:
                    self._cache_formula().set(_dom, cap, SITE_FORMULA_STALE_MAX)
        except Exception as err:
            return Response(success=False, message=f"抓取失败: {err}")
        self._log(
            f"公式探测:site={site_id} ({getattr(site, 'domain', '')}) {cap.note} "
            f"ok={cap.ok} params={cap.params} extra={cap.extra} persist={persist}"
        )
        data = {"site_id": site_id, "domain": getattr(site, "domain", ""), "persisted": bool(persist and cap.ok)}
        data.update(cap.as_dict())
        return Response(success=True, data=data)


# ===========================================================================
# ★ 16.0.0「站点已删除」（site deleted）：识别 + 牵连面 + 行内处置
#
# 模块级函数（而非 self._xxx）→ 不触发 tools/check_self_calls.py 的「禁止新增
# 跨文件 self._ 互调」棘轮（与 15.8.9 的 common.site_guard 同一手法）。
# 真值源：魔流台账 mf_site（host._agent_db_site_rows()）× MoviePilot 站点表
#        （common.site_guard(host).mp_sites()，60s 记忆化）。
# 红线：处置只做 pause / resume / **摘种**（delete_file=False），绝不删文件。
# ===========================================================================


def dom_norm(domain: Any) -> str:
    """域名归一（小写、去协议、去路径/尾斜杠）。"""
    s = str(domain or "").strip().lower()
    s = re.sub(r"^https?://", "", s).split("/")[0].strip().strip(".")
    return s


def _as_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def site_seed_stats(host: Any, name: str) -> Dict[str, Any]:
    """按标签前缀 ``魔流-<站名>-`` 统计 qB 里的种子（**只数不写**）。"""
    out: Dict[str, Any] = {"count": 0, "size_gb": 0.0, "paused": 0, "running": 0, "reuse": 0}
    name = str(name or "").strip()
    if not name:
        return out
    pref = f"魔流-{name}-"
    try:
        snap = host._tag_all_torrents() or {}
    except Exception:  # noqa: BLE001
        snap = {}
    for t in snap.values():
        tags = [str(x) for x in (getattr(t, "tags", None) or [])]
        if not any(x.startswith(pref) for x in tags):
            continue
        out["count"] += 1
        try:
            out["size_gb"] += float(getattr(t, "size", 0) or 0) / (1024 ** 3)
        except (TypeError, ValueError):
            pass
        st = str(getattr(t, "state", "") or "").lower()
        if st.startswith("paused"):
            out["paused"] += 1
        else:
            out["running"] += 1
        if any(x == MARK_REUSE for x in tags):
            out["reuse"] += 1
    out["size_gb"] = round(out["size_gb"], 1)
    return out


def site_ledger_counts(host: Any, site_id: Any, iyuu_sid: Any) -> Dict[str, int]:
    """该站在魔流账本里的行数（``mf_seed`` 按台账 ``site_id``、``mf_reseed`` 按 ``iyuu_sid``）。只读。"""
    sid = _as_int(site_id)
    iid = _as_int(iyuu_sid)
    n_seed = 0
    n_reseed = 0
    if sid:
        for r in (host._agent_db_rows("SeedRow") or []):
            if _as_int(getattr(r, "site_id", 0)) == sid:
                n_seed += 1
    if iid:
        for r in (host._agent_db_rows("ReseedRow") or []):
            if _as_int(getattr(r, "site_id", 0)) == iid:
                n_reseed += 1
    return {"seed_rows": n_seed, "reseed_rows": n_reseed}


def site_references(host: Any) -> Dict[str, Dict[str, Any]]:
    """★ 17.5.0：**所有**站点引用的汇总（只读）——「已删站」真值源 = 本函数 − MP 站点表。

    为什么需要它：站点在 MP 里被删掉之后，引用**比 ``mf_site`` 行活得久** ——
    账单（``hr_bills.json``）、跨站来源份、补种记录、任务配置都会继续引用这个域名。
    只认 ``mf_site`` 行会形成盲区（现场 2026-10-15：hdfans.org 的台账行早已不在，
    账单还剩 46 条，而旧判据报「0 个已删站」；更糟的是**删掉那一行会让它彻底隐形**）。

    引用来源（逐项记进 ``refs``）：
    ``mf_site``(台账行) / ``bills``(账单) / ``mf_seed`` / ``mf_reseed`` / ``mf_crossseed`` / ``task``。

    键 = 归一化域名；没有域名的残留（台账行已删、只剩按 id 的账本行）用 ``site:<id>`` /
    ``iyuu:<sid>`` 兜底建键 —— ★ **只在内存里建键，绝不建台账行**（Master 2026-10-15 拍板）。
    """
    out: Dict[str, Dict[str, Any]] = {}

    def _slot(dom: Any = "", sid: Any = None, iyuu: Any = None) -> Dict[str, Any]:
        d = dom_norm(dom)
        sid_i = _as_int(sid)
        iyuu_i = _as_int(iyuu)
        key = d or (f"site:{sid_i}" if sid_i else (f"iyuu:{iyuu_i}" if iyuu_i else ""))
        if not key:
            return {}
        ent = out.get(key)
        if ent is None:
            ent = {"key": key, "domain": d or "", "name": "", "site_id": None,
                   "mp_site_id": None, "iyuu_sid": None, "has_row": False,
                   "status": "", "deleted_at": None, "refs": [], "bills": 0}
            out[key] = ent
        # ★ 台账 site_id / iyuu_sid 必须落进槽里：``deleted_sites_rows`` 要用它数 mf_seed 行
        #   （漏了会让「按域名建键」的正常站算成 0 行 —— 17.5.0 回归抓到）
        if sid_i and not ent["site_id"]:
            ent["site_id"] = sid_i
        if iyuu_i and not ent["iyuu_sid"]:
            ent["iyuu_sid"] = iyuu_i
        return ent

    def _ref(ent: Dict[str, Any], kind: str) -> None:
        if ent and kind not in ent["refs"]:
            ent["refs"].append(kind)

    by_site_id: Dict[int, str] = {}
    by_mp_id: Dict[int, str] = {}
    by_iyuu: Dict[int, str] = {}
    # 1) 台账行（唯一带生命周期状态的来源）
    for r in (host._agent_db_site_rows() or []):
        if not isinstance(r, dict):
            continue
        sid = _as_int(r.get("site_id"))
        ent = _slot(r.get("domain"), sid=sid, iyuu=r.get("iyuu_sid"))
        if not ent:
            continue
        _ref(ent, "mf_site")
        ent["has_row"] = True
        ent["name"] = str(r.get("name") or "").strip() or ent["name"]
        ent["mp_site_id"] = _as_int(r.get("mp_site_id")) or ent["mp_site_id"]
        ent["iyuu_sid"] = _as_int(r.get("iyuu_sid")) or ent["iyuu_sid"]
        ent["status"] = str(r.get("status") or "").strip()
        ent["deleted_at"] = r.get("deleted_at") or ent["deleted_at"]
        if sid:
            by_site_id[sid] = ent["key"]
        if ent["mp_site_id"]:
            by_mp_id[ent["mp_site_id"]] = ent["key"]
        if ent["iyuu_sid"]:
            by_iyuu[ent["iyuu_sid"]] = ent["key"]
    # 2) 账单（★ 残留寿命最长的一层）
    try:
        _bills = host._hrbills_store().all() or {}
    except Exception:  # noqa: BLE001
        _bills = {}
    for b in ((_bills or {}).values() if isinstance(_bills, dict) else []):
        if not isinstance(b, dict) or not dom_norm(b.get("site")):
            continue
        ent = _slot(b.get("site"))
        if not ent:
            continue
        _ref(ent, "bills")
        ent["bills"] += 1
    # 3) 账本残留（台账行已经没了的那部分）
    for r in (host._agent_db_rows("SeedRow") or []):
        sid = _as_int(getattr(r, "site_id", 0))
        if not sid:
            continue
        key = by_site_id.get(sid)
        ent = out.get(key) if key else None
        if ent is None:
            ent = _slot(sid=sid)
        _ref(ent, "mf_seed")
    for r in (host._agent_db_rows("ReseedRow") or []):
        iid = _as_int(getattr(r, "site_id", 0))
        if not iid:
            continue
        key = by_iyuu.get(iid)
        ent = out.get(key) if key else None
        if ent is None:
            ent = _slot(iyuu=iid)
        _ref(ent, "mf_reseed")
    for r in (host._agent_db_rows("CrossSeedRow") or []):
        if not dom_norm(getattr(r, "site_b_domain", None)):
            continue
        _ref(_slot(getattr(r, "site_b_domain", None)), "mf_crossseed")
    # 4) 任务配置（按 mp_site_id）
    for tid, t in ((getattr(host, "_task_configs", None) or {}).items()):
        sid = _as_int(getattr(t, "site_id", 0))
        if not sid:
            continue
        key = by_mp_id.get(sid)
        ent = out.get(key) if key else None
        if ent is None:
            ent = _slot(sid=sid)
        _ref(ent, "task")
    return out


def site_deleted_domains(host: Any, mp: Any = None) -> Dict[str, Dict[str, Any]]:
    """★ 17.5.0：**已删站真值源**（key = 归一化域名 / ``site:<id>``；只读）。

    判据 = 「所有站点引用」（``site_references``）− MP 站点表，含**域名兜底**：

      * ``mp_site_id`` 在 MP 里查不到，但**同域名**还在 MP 里 → **不算删**（MP 里删站后重加
        同名站会拿到新 id；旧 id 查不到 ≠ 站点没了 —— 17.5.0 修的误报根因）；
      * 连域名也查不到 → ``mp_deleted``；
      * 没有 ``mp_site_id``（只有域名）且域名不在 MP → ``domain_missing``；
      * 台账行已不在、只剩账单/账本残留 → ``residue_no_row``（旧判据完全看不见这一类）；
      * **别名兜底**：残留域名是某个**活站**域名的子域（``pt.soulvoice.club`` ⊂ 活站
        ``soulvoice.club``）→ 算活站，不算删（同一个 tracker 换了域名而已）；
      * 域名与 id 都认不出（只剩按 id 的账本行）→ **不硬判**，不进清单。

    报表 ``reportview``、健康自检 H8、通知 ``notify`` 三处**共用这一份**，不再各算各的。
    """
    mp = mp if mp is not None else site_guard(host).mp_sites()
    if not mp:
        return {}
    try:
        mp_ids = {_as_int(k) for k in (mp or {}).keys()}
        mp_domains = {dom_norm(v.get("domain")) for v in mp.values()
                      if isinstance(v, dict) and dom_norm(v.get("domain"))}
    except Exception:  # noqa: BLE001
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for key, ent in site_references(host).items():
        mpsid = _as_int(ent.get("mp_site_id"))
        dom = dom_norm(ent.get("domain"))
        if mpsid and mpsid in mp_ids:
            continue
        if dom and dom in mp_domains:
            continue
        # ★ 别名兜底：残留域名是某个**活站**域名的子域 → 同一个 tracker 换了域名，算活站。
        #   现场 2026-10-15：账单里有 9 条 ``pt.soulvoice.club``（states 全 pending），
        #   而聆音 ``soulvoice.club`` 活着且在 MP 里；不兜底就会把活站报成「站点已删」、
        #   并把这 9 条账单误判成「无法对账」。**只认子域方向**（残留 ⊂ 活站），
        #   不认父域方向 —— 父域更容易把真正被删的站合并掉。
        if dom and any(dom.endswith("." + d) for d in mp_domains):
            continue
        if not dom and not mpsid:
            # 域名与 mp_site_id 都认不出（只剩按 id 的账本行）→ 不硬判，宁可漏报。
            # ★ 刻意**不做按站名匹配**：无域名无 id 的台账行（如手工行）按名字猜会把
            #   「从来不是 MP 站点」的行永久报成已删 → H8/告警常驻噪音。
            continue
        if not ent.get("has_row"):
            reason = "residue_no_row"
        elif mpsid:
            reason = "mp_deleted"
        else:
            reason = "domain_missing"
        out[key] = {**ent, "reason": reason}
    return out


def deleted_sites_rows(host: Any) -> List[Dict[str, Any]]:
    """★ 站点已被 MoviePilot 删除的**全量清单 + 牵连面**（真值源：``site_deleted_domains``；只读）。

    ★ 17.5.0 判据修正：原来只看 ``mf_site`` 行（台账行一删就彻底看不见 → 盲区），
    现在遍历**所有站点引用**（台账行 ∪ 账单 ∪ mf_seed/mf_reseed/mf_crossseed ∪ 任务），
    ``refs`` 标出被哪些层引用、``bills`` 给出账单条数（=「无法对账的欠账」规模），
    ``has_row`` 区分「有台账行（可标记/可处置）」与「只剩残留（只在清单里可见）」。

    ``reason`` ∈ ``mp_deleted`` / ``domain_missing`` / ``residue_no_row``。
    **MP 站点表读不到时返回空**（判不出不硬判，宁可漏报一轮）。
    牵连面全部「只数不写」：qB 标签种数/体积/暂停数/复用副本数、账本行数、站内任务数。
    """
    mp = site_guard(host).mp_sites()
    if not mp:
        return []
    deleted = site_deleted_domains(host, mp=mp)
    tasks = getattr(host, "_task_configs", None) or {}
    out: List[Dict[str, Any]] = []
    for _key, d in deleted.items():
        mpsid = _as_int(d.get("mp_site_id"))
        name = str(d.get("name") or "").strip() or str(d.get("domain") or "")
        bound: List[str] = []
        if mpsid:
            for tid, t in tasks.items():
                if _as_int(getattr(t, "site_id", 0)) == mpsid:
                    bound.append(str(getattr(t, "id", "") or tid))
        out.append({
            "site_id": d.get("site_id"),
            "name": name,
            "domain": d.get("domain") or "",
            "mp_site_id": d.get("mp_site_id"),
            "iyuu_sid": d.get("iyuu_sid"),
            "reason": d.get("reason"),
            "has_row": bool(d.get("has_row")),
            "status": str(d.get("status") or ""),
            "deleted_at": d.get("deleted_at"),
            "refs": list(d.get("refs") or []),
            "bills": int(d.get("bills") or 0),
            "tasks": bound,
            "seeds": site_seed_stats(host, name),
            "ledger": site_ledger_counts(host, d.get("site_id"), d.get("iyuu_sid")),
        })
    out.sort(key=lambda x: (-int((x.get("seeds") or {}).get("count") or 0),
                            -int(x.get("bills") or 0)))
    return out


def site_deleted_mark(host: Any, dry_run: Any = 0) -> Dict[str, Any]:
    """★ 17.5.0：把「MP 侧已删」落到台账 ``mf_site.status``（**只标记，不删行、不动标量**）。

    ★ 17.5.0：由**常驻** worker ``site_lifecycle``（``features/core.py`` 服务表，默认每 30 分钟一轮）
    调，**不依赖任何任务在跑**。规则：

      * 有台账行且判为已删 → ``status='deleted'`` + ``deleted_at``（幂等：已标记不重盖时间）+ ``reason``；
      * 之前标过 deleted、但 MP 里又有该站 → **清回 NULL**（重加同名站 / 站点恢复 = 无损复活，
        按 ``mp_site_id`` 存的 ``pv_budget`` / 站点规则 / 分类 id 原样还在）;
      * 只剩账单/账本残留、**没有台账行**的 → **不建行**（Master 2026-10-15 拍板），只在清单里可见。

    MP 站点表读不到 → 直接 ``{"ok": False, "skipped": "mp_unavailable"}``：判不出就**一个字都不写**，
    绝不把「读不到 MP」误写成「整排站被删」。
    """
    mp = site_guard(host).mp_sites()
    if not mp:
        return {"ok": False, "skipped": "mp_unavailable", "marked": 0, "cleared": 0}
    deleted = site_deleted_domains(host, mp=mp)
    want: Dict[str, Dict[str, Any]] = {}
    for _key, d in deleted.items():
        dom = dom_norm(d.get("domain"))
        if not dom or not d.get("has_row"):
            continue
        want[dom] = {"status": "deleted", "at": time.time(), "reason": d.get("reason")}
    marked = len(want)
    try:
        cur = dict(slot_callbacks(host, "site_status")[0]() or {})
    except Exception:  # noqa: BLE001
        cur = {}
    cleared = 0
    for dom in list(cur.keys()):
        if dom not in want:
            want[dom] = {"status": "active"}   # 站点又回到 MP → 复活
            cleared += 1
    if _truthy(dry_run):
        return {"ok": True, "dry_run": True, "marked": marked, "cleared": cleared,
                "sites": sorted([d for d, v in want.items() if v.get("status") == "deleted"])}
    if not want:
        return {"ok": True, "marked": 0, "cleared": 0, "sites": []}
    try:
        slot_callbacks(host, "site_status")[1](want)
    except Exception as err:  # noqa: BLE001
        return {"ok": False, "error": str(err), "marked": 0, "cleared": 0}
    return {"ok": True, "marked": marked, "cleared": cleared,
            "sites": sorted([d for d, v in want.items() if v.get("status") == "deleted"])}


def deleted_site_find(host: Any, site_id: Any) -> Optional[Dict[str, Any]]:
    """按台账 ``site_id`` / ``mp_site_id`` / **域名** 在「已删除站点」清单里定位一行。

    ★ 17.5.0：支持域名（只剩账单残留、没有台账行的站也能被定位/展示）。
    """
    sid = _as_int(site_id)
    key = "" if sid else dom_norm(site_id)
    if not sid and not key:
        return None
    for r in deleted_sites_rows(host):
        if sid and (_as_int(r.get("site_id")) == sid or _as_int(r.get("mp_site_id")) == sid):
            return r
        if key and dom_norm(r.get("domain")) == key:
            return r
    return None


def _truthy(v: Any) -> bool:
    return str(v if v is not None else "").strip().lower() in ("1", "true", "yes", "on", "y")


def _gate_preview(host: Any, hashes: Any, allow_asset: bool = False,
                  allow_strip_asset: bool = False) -> Dict[str, Any]:
    """★ 删除闸门**预览**：这些 hash 里哪些会被硬保护拦住、理由分布。

    （与物理删除同口径：``_delete_gate_detail`` + ``_delete_bill_assert``；取不到就按「不拦」算。）
    干跑就能提前看到「哪些删不掉、为什么」，不用真删一轮才知道。

    ``allow_asset`` / ``allow_strip_asset``：★ 与 ``DownloaderAdapter.delete_torrents`` 的
    两个具名通道一一对应（都只跳第 5 类「库内资产」）——预览必须按**同一个通道**算，
    否则干跑说「删得掉」、真删被拦（或反过来）。
    """
    hs = [str(h) for h in (hashes or []) if h]
    out: Dict[str, Any] = {"blocked": 0, "reasons": {}, "would_delete": len(hs)}
    if not hs:
        return out
    why: Dict[str, str] = {}
    try:
        fn = getattr(host, "_delete_gate_detail", None)
        if callable(fn):
            if allow_asset:
                why.update(dict(fn(hs, allow_asset=True) or {}))
            elif allow_strip_asset:
                why.update(dict(fn(hs, allow_strip_asset=True) or {}))
            else:
                why.update(dict(fn(hs) or {}))
    except Exception:  # noqa: BLE001
        pass
    try:
        fn2 = getattr(host, "_delete_bill_assert", None)
        if callable(fn2):
            for k, v in (fn2(hs) or {}).items():
                why.setdefault(k, v)
    except Exception:  # noqa: BLE001
        pass
    reasons: Dict[str, int] = {}
    for _r in why.values():
        reasons[str(_r)] = reasons.get(str(_r), 0) + 1
    out["blocked"] = len(why)
    out["reasons"] = reasons
    out["would_delete"] = len(hs) - len(why)
    return out


def _is_body_like(tags: Any, pref: str, rec: Any) -> bool:
    """本体判定（★ 17.4.0，**只增保护**）：这个种的文件是不是「本体 / 库内资产」。

    三个判据任一命中即算本体（取不到判据就按本体算 = fail-closed，宁可只摘种、不误删文件）：

      1. 魔流自己的身份标签 ``<pref>…-资源``（= ``静默-资源``）—— 16.0.0 起的原生判据；
      2. MP 写的 ``已整理 / 辅种``（``tags.is_asset_tags``）—— 文件已被 MP 搬进媒体库的直接证据；
      3. 账本 ``in_library`` / 身份「资源」（``tags.is_library_asset``）—— 资源库真值。

    为什么补 2、3：16.0.0 只看判据 1，于是「已整理入库、但身份还没转成 ``静默-资源``」的种
    会落进「自己的非资源」档被**连文件删** —— 删掉的正是媒体库里的本体。
    """
    try:
        if any(str(x).startswith(pref) and str(x).endswith("-" + SUB_RESOURCE)
               for x in (tags or [])):
            return True
        if is_asset_tags(tags):
            return True
        if is_library_asset(rec):
            return True
    except Exception:  # noqa: BLE001
        return True
    return False


def deleted_site_act(host: Any, site_id: Any, action: str, reuse_only: Any = 0,
                     dry_run: Any = 1, force_asset: Any = 0) -> Dict[str, Any]:
    """★ 已删除站点的行内操作：``pause`` / ``resume`` / ``remove``。

    ``remove`` 口径（Master 2026-10-15 拍板：站点没了 → 本站的种都不必再挂）：

      * **复用副本**（带 ``魔流-辅种``）→ **只摘种**（``delete_file=False``）：文件是从别处
        复用来的，删文件不可逆且会连坐本体；
      * **本体 / 库内资产**（``_is_body_like``：``静默-资源`` ∪ MP 的 ``已整理/辅种``
        ∪ 账本 ``in_library``）→ **只摘种**（``delete_file=False``）：文件在媒体库里，
        摘种只是不再为本站挂，本体一个字节都不动；
      * **自己的、非本体的种** → **连文件一起删**（``delete_file=True``）。

    ★ 与 16.0.0 的差别**只有第二档**：本体此前是「保留不动（连种都不摘）」，现在改**摘种、
    仍不删文件**。只摘种那一档走 ``delete_torrents(allow_strip_asset=True)`` —— 17.4.0 新增的
    **具名豁免通道**（``deletegate._delete_gate_strip``：只跳过第 5 类「库内资产」，理由是
    本操作不删文件、第 5 类的保护目的不适用；其余四类硬拦照拦），**不复用** ``force_asset`` /
    ``gate_manual``（那条的语义是「手动删库内资产」配 ``delete_file=True``，借它摘种是语义借位）。

    连文件删仍走**唯一删除闸门** + 内置**共享文件护栏**（同批之外还有别的种共用同一份文件
    → 自动降级为只摘种，不会连坐）。``reuse_only=1`` 只跑第一档（最安全）。默认干跑。
    ``force_asset=1`` → ★ **只影响连文件删那一档**：改走「手动删库内资产」专用闸门
    （``allow_library_asset=True``，即 15.8.15 那条**唯一**允许突破「库内资产（已入库，永不删）」
    的口子；其余四类照拦）；只摘种那一档本来就走 ``gate_strip``，不受它影响。
    回执恒含 ``{ok, site_id, action, message, blocked}``（与点播/音乐行内操作同一口径）。
    """
    act = str(action or "").strip().lower()
    base: Dict[str, Any] = {"ok": False, "site_id": _as_int(site_id), "action": act,
                            "message": "", "blocked": False}
    row = deleted_site_find(host, site_id)
    if row is None:
        base["message"] = "未找到该「已删除站点」（站点仍在 / MP 站点表读不到）"
        return base
    name = str(row.get("name") or "")
    pref = f"魔流-{name}-"
    want_reuse = _truthy(reuse_only)
    force = _truthy(force_asset)
    _dk: Dict[str, Any] = {"allow_library_asset": True} if force else {}
    #   ★ 17.4.0：只摘种那一档走**具名通道** gate_strip（只跳第 5 类库内资产，理由=本操作
    #     不删文件）。**任何情况下都不带 allow_library_asset**：那条是「删库内资产」的语义。
    _dk_strip: Dict[str, Any] = {"allow_strip_asset": True}
    try:
        snap = host._tag_all_torrents() or {}
    except Exception:  # noqa: BLE001
        snap = {}
    try:  # 本体判据 3 的真值源（账本 in_library / 身份「资源」）
        _led: Dict[str, Any] = dict((host._tag_state() or {}).items() or {})
    except Exception:  # noqa: BLE001
        _led = {}
    all_h: List[str] = []
    reuse_h: List[str] = []   # 别人辅种的复用副本 → 只摘种
    asset_h: List[str] = []   # 本体/库内资产 → ★ 17.4.0 起：只摘种（文件留在媒体库）
    own_h: List[str] = []     # 自己的非本体 → 连文件删
    for h, t in snap.items():
        tags = [str(x) for x in (getattr(t, "tags", None) or [])]
        if not any(x.startswith(pref) for x in tags):
            continue
        all_h.append(str(h))
        if MARK_REUSE in tags:
            reuse_h.append(str(h))
        elif _is_body_like(tags, pref, _led.get(str(h)) or {}):
            asset_h.append(str(h))
        else:
            own_h.append(str(h))
    strip_h: List[str] = reuse_h + asset_h   # 只摘种（不删文件）那一档
    if not all_h:
        base["ok"] = True
        base["message"] = "该站名下没有符合条件的种"
        base["affected"] = 0
        return base
    dry = _truthy(dry_run) if dry_run is not None else True
    try:
        dl = host._get_downloader()
    except Exception:  # noqa: BLE001
        dl = None

    # ------------------------------------------------ remove：分档处置
    if act in ("remove", "drop"):
        if want_reuse:
            plan = {"strip": len(reuse_h), "strip_reuse": len(reuse_h), "strip_asset": 0,
                    "full": 0, "keep": len(all_h) - len(reuse_h)}
            #   ★ 17.4.0：只摘种 → 预览必须按 gate_strip 算（同通道，否则干跑与真删不一致）。
            gate = _gate_preview(host, reuse_h, allow_strip_asset=True)
            if dry:
                base.update(ok=True, dry_run=True, planned=plan, affected=0, gate=gate,
                            message=(f"干跑：只摘复用副本 {len(reuse_h)} 个（不删文件）"
                                     + (f"；闸门会拦 {gate['blocked']} 个" if gate["blocked"] else "")))
                return base
            if dl is None:
                base["message"] = "下载器不可用"
                return base
            try:
                n1, e1 = ((0, None) if not reuse_h else
                          dl.delete_torrents(hashes=reuse_h, delete_file=False,
                                             reason="站点已删除（复用副本·只摘种）", source="sitedeleted",
                                             **_dk_strip))
            except Exception as e:  # noqa: BLE001
                base["message"] = f"操作失败:{e}"
                return base
            base.update(ok=not e1, blocked=bool(e1), stripped=int(n1 or 0),
                        deleted_with_file=0, kept=len(all_h) - len(reuse_h), gate=gate,
                        affected=int(n1 or 0),
                        message=str(e1) if e1 else f"已摘种 {int(n1 or 0)} 个复用副本（不删文件）")
            return base
        plan = {"strip": len(strip_h), "strip_reuse": len(reuse_h), "strip_asset": len(asset_h),
                "full": len(own_h), "keep": 0}
        #   两条通道各自的预览（与真删同口径）：连文件删那一档按 allow_asset（force 时才放宽），
        #   只摘种那一档固定按 gate_strip。
        gate = _gate_preview(host, own_h, allow_asset=force)
        gate_strip = _gate_preview(host, strip_h, allow_strip_asset=True)
        if dry:
            base.update(ok=True, dry_run=True, planned=plan, affected=0,
                        gate=gate, gate_strip=gate_strip,
                        message=(f"干跑：摘种 {len(strip_h)}（复用副本 {len(reuse_h)} + 本体 {len(asset_h)}，"
                                 f"均不删文件）+ 连文件删 {len(own_h)}（自有非本体）"
                                 + ("（连文件删·库内资产强删）" if force else "")
                                 + (f"；闸门会拦 {gate['blocked'] + gate_strip['blocked']} 个"
                                    if (gate["blocked"] or gate_strip["blocked"]) else "")))
            return base
        if dl is None:
            base["message"] = "下载器不可用"
            return base
        try:
            # ★ 先「连文件删」（共享护栏此时还能看到仍在的辅种副本 → 共用路径的自动降级为只摘种），
            #   再摘种；反过来的话护栏看不见已摘掉的别人，会把共用文件一起干掉。
            #   空批不发调用（少一次下载器往返 / 少一条空日志）。
            n2, e2 = (0, None)
            n1, e1 = (0, None)
            if own_h:
                n2, e2 = dl.delete_torrents(hashes=own_h, delete_file=True,
                                            reason="站点已删除（自有非本体·连文件）", source="sitedeleted",
                                            **_dk)
            if strip_h:
                n1, e1 = dl.delete_torrents(hashes=strip_h, delete_file=False,
                                            reason="站点已删除（复用副本 + 本体·只摘种）", source="sitedeleted",
                                            **_dk_strip)
        except Exception as e:  # noqa: BLE001
            base["message"] = f"操作失败:{e}"
            return base
        errs = [x for x in (e1, e2) if x]
        base.update(ok=not errs, blocked=bool(errs), stripped=int(n1 or 0),
                    deleted_with_file=int(n2 or 0), kept=0, gate=gate, gate_strip=gate_strip,
                    affected=int(n1 or 0) + int(n2 or 0),
                    message=(errs[0] if errs else
                             f"已摘种 {int(n1 or 0)}（复用副本 {len(reuse_h)} + 本体 {len(asset_h)}，"
                             f"均不删文件）+ 连文件删 {int(n2 or 0)}（自有非本体）"))
        return base

    # ------------------------------------------------ pause / resume
    hashes = reuse_h if want_reuse else all_h
    _verb = "暂停" if act == "pause" else ("恢复" if act == "resume" else "")
    if not _verb:
        base["message"] = f"未知动作 {act}（可选 pause/resume/remove）"
        return base
    if not hashes:
        base["ok"] = True
        base["affected"] = 0
        base["message"] = "没有符合条件的种"
        return base
    if dry:
        base.update(ok=True, dry_run=True, planned=len(hashes), affected=0,
                    message=f"干跑：将{_verb} {len(hashes)} 个种")
        return base
    if dl is None:
        base["message"] = "下载器不可用"
        return base
    try:
        n, err = dl.pause_torrents(hashes) if act == "pause" else dl.resume_torrents(hashes)
    except Exception as e:  # noqa: BLE001
        base["message"] = f"操作失败:{e}"
        return base
    base["ok"] = not err
    base["blocked"] = bool(err)
    base["affected"] = int(n or 0)
    base["message"] = str(err) if err else f"已{_verb} {int(n or 0)} 个种"
    return base
