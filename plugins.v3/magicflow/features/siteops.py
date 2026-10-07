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

from ..fetcher import (
    set_site_free_rules,
)
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
)
from ..sitestore import get_site_store


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
            self._sync_free_rules()
            self._log(f"魔流:站点规则自动刷新完成（{n} 站）")
        except Exception as err:  # noqa: BLE001
            self._log(f"站点规则刷新异常:{err}", "warning")
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
        「所有 H&R 规则都从收件箱的欢迎邮件进，外面的是假规则」）。公开页只作促销/名额/考核事实，
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
                    # 非 H&R 事实（促销/名额/考核）照常采
                    for _pk in ("free_over_gb", "free_original", "free_ep1"):
                        if got.get(_pk) is not None and parsed.get(_pk) is None:
                            parsed[_pk] = got[_pk]
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
                    or parsed.get("free_over_gb") is not None
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
            self._sync_free_rules()
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
            row["in_library"] = bool(g["rec"])
            try:
                fr = self._site_rules().free_rules(disp)
                if fr:
                    row.update(fr)
            except Exception:  # noqa: BLE001
                pass
            if row.get("seed_hours") is None and row.get("seed_hours_seen") is not None:
                row["evidence_hours"] = row.get("seed_hours_seen")
            out.append(row)
        out.sort(key=lambda r: (str(r.get("site_name") or r.get("domain") or "")))
        return out

    def _sync_free_rules(self) -> int:
        """把规则库里的「促销规则」注入选种器（体积自动免费等）。

        列表页不显示促销标记的免费种（例：体积 >20GB 自动免费）如果只按 promo 判定，
        会被当成收费种 → 免费任务挡掉 / 跨站任务误判。这里把站点规则同步过去。
        """
        try:
            rules = self._site_rules()
            doms = set()
            try:
                doms |= {str(k) for k in (rules.items() or {}).keys()}
            except Exception:  # noqa: BLE001
                pass
            try:
                doms |= {str(r.get("domain") or "") for r in (self._list_sites() or [])}
            except Exception:  # noqa: BLE001
                pass
            doms |= {str(k) for k in BUILTIN_RULES.keys()}
            manual = (getattr(self, "_cs_cfg", {}) or {}).get("site_hours") or {}
            if isinstance(manual, dict):
                doms |= {str(k) for k in manual.keys()}
            mapping: Dict[str, Dict[str, Any]] = {}
            for d in doms:
                if not d:
                    continue
                fr = rules.free_rules(d)
                if fr:
                    mapping[d] = fr
            set_site_free_rules(mapping)
            if mapping:
                logger.info(f"促销规则同步: {len(mapping)} 站可补判免费 {list(mapping.items())[:3]}")
            return len(mapping)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"促销规则同步失败: {e}")
            return 0

    def get_site_rules(self, action: str = "", site: str = "", hours: str = "", hr: str = "") -> Response:
        """站点规则库读写。

        - ``GET /rules``：列表（含生效保种时长与来源）；
        - ``GET /rules?action=refresh``：按 MP 配置 + 内置表补全（**不触网**）；
        - ``GET /rules?action=probe&site=<id|domain>``：抓页面探测（1~2 请求/站）；
        - ``GET /rules?action=set&site=<domain>&hours=<n>``：手填覆盖（写进「站点保种时长」）。
        """
        try:
            act = str(action or "").strip().lower()
            store = self._site_rules()
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
                self._sync_free_rules()
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
                    self._sync_free_rules()
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
                    self._sync_free_rules()
                    return Response(
                        success=True,
                        message=f"{dom} 已标记为「有 H&R」（手动，按 {float(hours):g}h 保护；如需改时长直接编辑「保种(h)」）",
                        data={"rules": self._rules_view()},
                    )
                # 其余（unknown/空/其它）= 取消手填，交还探测
                store.clear(dom)
                store.ensure_builtin(dom)
                self._sync_free_rules()
                return Response(success=True, message=f"{dom} 已恢复为探测/内置判定", data={"rules": self._rules_view()})
            if act in ("refresh", "sync"):
                for dom, nm in (({str(r.get("domain") or "").strip().lower(): str(r.get("name") or "") for r in (self._list_sites() or [])})).items():
                    if dom:
                        store.ensure_builtin(dom, nm)
                self._sync_free_rules()
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
                self._sync_free_rules()
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
