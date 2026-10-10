# -*- coding: utf-8 -*-
"""魔流 · manualinject —— 手工 / 临时投放通道（公共模块，15.8.14）。

给「临时需求 / 测试需求」一条**一等公民**入口：走插件写端点，而不是脚本直连 qB。

为什么需要它（2026-10-10 事故复盘，见 ``docs/DESIGN-CURRENT.md`` §8）：
    手工加种走工作区脚本直连 qB，打出的 ``魔流-手动`` 是**零生产代码认得**的孤儿标签
    —— 不在账本、不在任何任务 → 归流不收（``_magicize_scope`` 只认前缀）、
    静默池不定罪、清理不管 → 两颗音乐种满速上传 3.76 MB/s、累计 277 GiB 无人问。

本通道把「手工加种」收编进插件，四件事一起做（缺一不可）：
  ① **去重**：落种前过全局 dup 闸门（``DupGateMixin``），与各任务共享「同一资源只下一次」；
  ② **身份**：落种即打 ``魔流-<站>-静默-<子>``（可识别身份，**不是**孤儿标签）；
  ③ **账本**：写 ``SeedLedgerStore``（``site`` 记来源 / ``state=静默`` / ``sub`` 记身份）
     → 归流、静默审计、删除闸门、站点报表都看得见它；
  ④ **退场**：:meth:`ManualInjectMixin._inject_release` 显式回收（默认只暂停，
     ``mode=delete`` 才删种 + 销账）。

口径（两个缺省值都是刻意的）：
  · ``site`` 缺省 ``手工`` —— **不是真实站点**，只是「这颗种从哪来」的溯源标记，
    站点报表里单列一个 ``手工`` 桶；要归到某个真实站（例如辅种）就显式传 ``site=<站名>``。
  · ``sub`` 缺省 ``资源`` —— 资源份受身份保护，**在途不会被静默池「入池即判」删**
    （``_silent_drop_incomplete_now`` 放行清单①）；下完后作为库内资产留在盘上，
    直到显式退场。要「交给静默-普通 自动清理」传 ``sub=普通``（注意：没下完的普通份
    会在入池那一刻被判删，只适合「不关心是否下得完」的种）。
  · 库内资产按插件铁律**永不删**：要删本通道的投放，必须 ``mode=delete`` + ``force=1``，
    此时本模块先把**本通道自己**的记录降到 ``普通`` 再走唯一删种闸门
    （``DownloaderAdapter.delete_torrents``）；非本通道的种一律拒绝。

端点（见 ``features/agentapi.py``）：``POST /agent/inject``、``POST /agent/inject/release``。
"""

from typing import Any, Dict, List, Optional

from .downloader_ops import _magnet_infohash
from .fingerprint import fingerprint as _torrent_fingerprint, info_hash as _torrent_info_hash
from .tags import STATE_SILENT, SUB_PLAIN, SUB_RESOURCE, tag_for

__all__ = [
    "MANUAL_SITE",
    "MANUAL_TASK_ID",
    "ManualInjectMixin",
]

MANUAL_SITE = "手工"           # 缺省来源标记（不是真实站点，只是溯源桶）
MANUAL_TASK_ID = "__manual__"  # dup 闸门里的占用方 id（独立命名空间，不占任何任务）
_B64_PREFIX = "data:application/x-bittorrent;base64,"
_TRUTHY = ("1", "true", "yes", "y", "on")


def _truthy(value: Any) -> bool:
    """命令行风格的真值（``1/true/yes/y/on``）。"""
    return str(value or "").strip().lower() in _TRUTHY


class ManualInjectMixin:
    """手工 / 临时投放 —— 「临时需求」的插件内一等公民入口（15.8.14）。"""

    # ------------------------------------------------------------ 参数归一
    def _inject_site(self, site: Any = "") -> str:
        """归一来源标记：缺省 :data:`MANUAL_SITE`（站点报表里单列一个桶）。"""
        return str(site or "").strip() or MANUAL_SITE

    def _inject_sub(self, sub: Any = "") -> str:
        """归一身份子类：只接受 ``普通``（其余一律 ``资源``，含缺省）。"""
        return SUB_PLAIN if str(sub or "").strip() == SUB_PLAIN else SUB_RESOURCE

    def _inject_content(self, magnet: Any = "", torrent: Any = "", url: Any = "") -> Dict[str, Any]:
        """把三种入参归一成 ``content``，并尽量**提前**算出 infohash / 特征码（给 dup 闸门用）。

        返回 ``{"content","kind","info_hash","fingerprint","dup_ready","error"}``；
        ``content`` 为 None 表示入参不可用（``error`` 说明原因）。三种入参互斥，优先级
        ``torrent`` > ``magnet`` > ``url``（种子字节最精确，磁力链次之）。
        """
        raw_torrent = str(torrent or "").strip()
        if raw_torrent:
            import base64

            b64 = raw_torrent
            if b64.startswith(_B64_PREFIX):
                b64 = b64[len(_B64_PREFIX):]
            if b64.startswith("data:"):
                b64 = b64.split(",", 1)[-1]
            b64 = "".join(b64.split())
            try:
                data = base64.b64decode(b64, validate=False)
            except Exception:  # noqa: BLE001
                return {"content": None, "kind": "torrent", "info_hash": "", "fingerprint": "",
                        "dup_ready": False, "error": "torrent 不是合法 base64"}
            if not data:
                return {"content": None, "kind": "torrent", "info_hash": "", "fingerprint": "",
                        "dup_ready": False, "error": "torrent 解码后为空"}
            try:
                ih = str(_torrent_info_hash(data) or "")
            except Exception:  # noqa: BLE001
                ih = ""
            try:
                fp = str(_torrent_fingerprint(data) or "")
            except Exception:  # noqa: BLE001
                fp = ""
            return {"content": data, "kind": "torrent", "info_hash": ih, "fingerprint": fp,
                    "dup_ready": bool(ih or fp), "error": ""}

        mg = str(magnet or "").strip()
        if mg:
            if not mg.lower().startswith("magnet:?"):
                return {"content": None, "kind": "magnet", "info_hash": "", "fingerprint": "",
                        "dup_ready": False, "error": "magnet 需要以 magnet:? 开头"}
            _ih = str(_magnet_infohash(mg) or "")
            # 磁力链拿不到特征码（要等元数据），但 infohash 键足够预检「同一颗种重复投」
            return {"content": mg, "kind": "magnet", "info_hash": _ih, "fingerprint": "",
                    "dup_ready": bool(_ih), "error": ""}

        u = str(url or "").strip()
        if u:
            if not u.lower().startswith(("http://", "https://")):
                return {"content": None, "kind": "url", "info_hash": "", "fingerprint": "",
                        "dup_ready": False, "error": "url 需要以 http(s):// 开头"}
            # 远端 .torrent 由下载器自己取 → 落种前拿不到 infohash，**无法预检重复**
            return {"content": u, "kind": "url", "info_hash": "", "fingerprint": "",
                    "dup_ready": False, "error": ""}

        return {"content": None, "kind": "", "info_hash": "", "fingerprint": "",
                "dup_ready": False, "error": "必须给 magnet / torrent(base64) / url 三者之一"}

    def _inject_save_path(self, save_path: Any = "") -> str:
        """决定保存目录：入参优先，其次点播默认目录（任务保存目录 / MP 默认）。"""
        p = str(save_path or "").strip()
        if p:
            return p
        for fn in ("_ondemand_default_save_path",):
            try:
                got = getattr(self, fn, None)
                if got is not None:
                    p = str(got() or "").strip()
                    if p:
                        return p
            except Exception:  # noqa: BLE001
                continue
        return ""

    def _inject_prepare(self, magnet: Any = "", torrent: Any = "", url: Any = "",
                        save_path: Any = "", site: Any = "", sub: Any = "",
                        category: Any = "") -> Dict[str, Any]:
        """归一化一次投放的全部入参（干跑 / 真投放**共用真值源**），不做任何副作用。

        返回键：``ok/error/content/kind/info_hash/fingerprint/dup_keys/tag/site/sub/
        save_path/category``；``dup_keys`` 为空 = 该入参无法预检重复（例如 url）。
        """
        c = self._inject_content(magnet=magnet, torrent=torrent, url=url)
        out: Dict[str, Any] = {
            "ok": False, "error": str(c.get("error") or ""), "kind": str(c.get("kind") or ""),
            "info_hash": str(c.get("info_hash") or ""), "fingerprint": str(c.get("fingerprint") or ""),
            "dup_ready": bool(c.get("dup_ready")), "dup_keys": [], "tag": "",
            "site": self._inject_site(site), "sub": self._inject_sub(sub),
            "save_path": "", "category": str(category or "").strip(),
        }
        if c.get("content") is None:
            return out
        out["content"] = c["content"]
        out["tag"] = tag_for(out["site"], STATE_SILENT, out["sub"])
        out["save_path"] = self._inject_save_path(save_path)
        if not out["save_path"]:
            out["error"] = "没有可用的保存目录：传 save_path，或先在「设置 → 下载目录」填任务保存目录"
            return out
        try:
            out["dup_keys"] = list(self._dup_keys(info_hash=out["info_hash"] or None,
                                                fingerprint=out["fingerprint"] or None) or [])
        except Exception:  # noqa: BLE001
            out["dup_keys"] = []
        out["ok"] = True
        return out

    # ------------------------------------------------------------ 干跑
    def _inject_plan(self, magnet: Any = "", torrent: Any = "", url: Any = "",
                     save_path: Any = "", site: Any = "", sub: Any = "",
                     category: Any = "") -> Dict[str, Any]:
        """干跑：算身份标签 / 保存目录 + 查全局 dup 占用；**不落种、不写账本、不占闸门**。

        返回 ``_inject_prepare`` 的全部键，另加 ``conflict``（别的任务在 TTL 内占用/下过的键）
        与 ``conflict_states``（``inflight``/``done``）。
        """
        p = self._inject_prepare(magnet=magnet, torrent=torrent, url=url, save_path=save_path,
                                 site=site, sub=sub, category=category)
        if not p.get("ok"):
            return p
        try:
            states = dict(self._dup_conflict_states(MANUAL_TASK_ID, keys=p["dup_keys"]) or {})
        except Exception:  # noqa: BLE001
            states = {}
        p["conflict_states"] = states
        p["conflict"] = sorted(states.keys())
        p["would_add"] = not states
        if p["dup_ready"]:
            p["note"] = ""
        elif p["dup_keys"]:
            p["note"] = "只能按 infohash 预检（magnet 无特征码，内层特征对不住）"
        else:
            p["note"] = "入参无法预检重复（url 类），落种后才由账本/闸门兜住"
        return p

    # ------------------------------------------------------------ 真投放
    def _inject_apply(self, magnet: Any = "", torrent: Any = "", url: Any = "",
                      save_path: Any = "", site: Any = "", sub: Any = "",
                      category: Any = "") -> Dict[str, Any]:
        """真投放：占据闸门 → 落种（带身份标签）→ 写账本；任一步失败即释放占用。

        身份 = ``魔流-<site>-静默-<sub>``（缺省 ``手工`` / ``资源``），账本行 = 同站 + 同子类。
        """
        p = self._inject_prepare(magnet=magnet, torrent=torrent, url=url, save_path=save_path,
                                 site=site, sub=sub, category=category)
        if not p.get("ok"):
            return p
        keys = list(p["dup_keys"] or [])
        if keys:
            try:
                conflict = list(self._dup_claim(MANUAL_TASK_ID, keys=keys) or [])
            except Exception:  # noqa: BLE001
                conflict = []
            if conflict:
                p["ok"] = False
                p["conflict"] = conflict
                p["error"] = "重复资源：已被其它任务在 TTL 内占用/下过（先用 release 退场再投）"
                return p
        dl = None
        try:
            dl = self._get_downloader()
        except Exception:  # noqa: BLE001
            dl = None
        if dl is None or not getattr(dl, "is_available", False):
            if keys:
                self._dup_release(MANUAL_TASK_ID, keys=keys)
            p["ok"] = False
            p["error"] = "下载器不可用"
            return p
        try:
            hs, err = dl.add_torrent(content=p["content"], download_dir=p["save_path"],
                                     tag=p["tag"], category=p["category"])
        except Exception as e:  # noqa: BLE001
            if keys:
                self._dup_release(MANUAL_TASK_ID, keys=keys)
            p["ok"] = False
            p["error"] = f"添加失败: {e}"
            return p
        if not hs:
            if keys:
                self._dup_release(MANUAL_TASK_ID, keys=keys)
            p["ok"] = False
            p["error"] = f"添加失败: {err or '未知'}"
            return p
        h = str(hs[0] if isinstance(hs, (list, tuple)) else hs).strip().lower()
        if keys:
            self._dup_finish(MANUAL_TASK_ID, keys=keys)
        warn = ""
        try:
            self._tag_state().put(h, {"site": p["site"], "state": STATE_SILENT, "sub": p["sub"]})
        except Exception as e:  # noqa: BLE001
            warn = f"账本写入失败（种子已落，标签仍在）: {e}"
        p.update({"ok": True, "hash": h, "added": True, "warning": warn,
                  "message": f"已投放 {h[:12]}：{p['tag']}"})
        return p

    # ------------------------------------------------------------ 退场
    def _inject_release(self, hashes: Any = "", mode: Any = "pause", site: Any = "",
                        delete_files: Any = "", force: Any = "", apply: Any = "") -> Dict[str, Any]:
        """退场：回收**本通道**（账本 ``site`` == ``手工``，可传 ``site`` 覆盖）投放的种。

        - ``mode=pause``（缺省）：只暂停（停止做种/下载），账本与标签都留着 → 可再 resume；
        - ``mode=delete``：删种；``delete_files=1`` 连文件一起删；
          ★ 资源份按插件铁律是「库内资产·永不删」→ 需要 ``force=1`` 时本模块**先**把本通道
            自己的记录降到 ``普通`` 再走唯一删种闸门（``delete_torrents``，内含 H&R /
            跨站来源 / 已认领 / 手动保留 硬拦）；闸门仍拦下的会被如实报出，不硬闯。
        - ``apply`` 缺省假 = 干跑（只报打算做什么）。

        ★ 归属是**硬条件**（账本 ``site`` 必须等于 ``site`` 参数，缺省 ``手工``）：``force=1`` 只解锁
        「本通道自己这条记录 资源→普通」的降级，**绝不放宽归属** —— 别人的种传 ``force`` 也一律拒收。
        """
        hs: List[str] = []
        for chunk in str(hashes or "").replace(",", " ").replace("\n", " ").split():
            h = chunk.strip().lower()
            if len(h) == 40 and h not in hs:
                hs.append(h)
        rep: Dict[str, Any] = {"apply": _truthy(apply), "mode": str(mode or "pause").strip().lower(),
                              "site": self._inject_site(site), "force": _truthy(force),
                              "delete_files": _truthy(delete_files),
                              "asked": len(hs), "owned": 0, "refused": [], "paused": 0,
                              "deleted": 0, "downgraded": [], "still_live": [],
                              "still_protected": {}, "failed": [], "items": []}
        if rep["mode"] not in ("pause", "delete"):
            rep["error"] = "mode 只支持 pause / delete"
            return rep
        if not hs:
            rep["error"] = "hashes 为空（需要逗号/空格分隔的 infohash）"
            return rep
        try:
            store = self._tag_state()
        except Exception as e:  # noqa: BLE001
            rep["error"] = f"账本不可用: {e}"
            return rep
        by_mode: Dict[str, List[str]] = {"pause": [], "delete": []}
        for h in hs:
            rec = dict(store.get(h) or {})
            own = str(rec.get("site") or "") == rep["site"] and bool(rec)  # ★ 归属是硬条件：force 只解锁「资源→普通」降级，绝不放宽归属
            if not own:
                rep["refused"].append({"hash": h, "why": f"不是本通道（site={rec.get('site') or '∅'}）的投放"})
                continue
            if not rec:
                rep["refused"].append({"hash": h, "why": "账本里没有这个种（force 也不认未知种）"})
                continue
            rep["owned"] += 1
            by_mode[rep["mode"]].append(h)
            rep["items"].append({"hash": h, "site": rec.get("site"), "sub": rec.get("sub"),
                                 "state": rec.get("state"), "force": bool(rep["force"])})
        if not (by_mode["pause"] or by_mode["delete"]):
            rep["ok"] = True
            rep["message"] = "没有可退场的投放"
            return rep
        if not rep["apply"]:
            rep["ok"] = True
            rep["would"] = {"pause": by_mode["pause"], "delete": by_mode["delete"]}
            rep["message"] = (f"干跑：将暂停 {len(by_mode['pause'])} 个 / 删除 {len(by_mode['delete'])} 个"
                              "（apply=1 才动手）")
            return rep
        dl = None
        try:
            dl = self._get_downloader()
        except Exception:  # noqa: BLE001
            dl = None
        if dl is None or not getattr(dl, "is_available", False):
            rep["error"] = "下载器不可用"
            return rep
        if by_mode["pause"]:
            try:
                n, err = dl.pause_torrents(by_mode["pause"])
                rep["paused"] = int(n or 0)
                if err:
                    rep["failed"].append({"mode": "pause", "error": str(err)})
            except Exception as e:  # noqa: BLE001
                rep["failed"].append({"mode": "pause", "error": str(e)})
        if by_mode["delete"]:
            todo = list(by_mode["delete"])
            # ★ 库内资产（身份=资源）永不删：本通道自己的记录先降级到「普通」，再走唯一删种闸门
            if rep["force"]:
                for h in todo:
                    rec = dict(store.get(h) or {})
                    if str(rec.get("sub") or "") == SUB_RESOURCE:
                        try:
                            store.put(h, {"sub": SUB_PLAIN})
                            rep["downgraded"].append(h)
                        except Exception as e:  # noqa: BLE001
                            rep["failed"].append({"hash": h, "mode": "downgrade", "error": str(e)})
            try:
                n, err = dl.delete_torrents(todo, delete_file=bool(rep["delete_files"]),
                                            reason="手工投放退场（manualinject）",
                                            source="manualinject.release")
                rep["deleted"] = int(n or 0)
                if err:
                    rep["failed"].append({"mode": "delete", "error": str(err)})
            except Exception as e:  # noqa: BLE001
                rep["failed"].append({"mode": "delete", "error": str(e)})
            live = set()
            try:
                live = {str(k).strip().lower() for k in (dl.get_all_torrents_index() or {})}
            except Exception:  # noqa: BLE001
                live = set()
            for h in todo:  # 真删掉的才销账；没删掉的保留账本行（仍可再试）
                if h in live:
                    rep["still_live"].append(h)
                    continue
                try:
                    store.drop(h)
                except Exception as e:  # noqa: BLE001
                    rep["failed"].append({"hash": h, "mode": "drop", "error": str(e)})
            try:
                rep["still_protected"] = dict(self._delete_gate_detail(rep["still_live"]) or {})
            except Exception:  # noqa: BLE001
                rep["still_protected"] = {}
        rep["ok"] = not rep["failed"]
        rep["message"] = (f"退场完成：暂停 {rep['paused']} / 删除 {rep['deleted']}"
                          f"（拒收 {len(rep['refused'])}）")
        return rep
