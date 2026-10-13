# -*- coding: utf-8 -*-
"""魔流 · AI 决策链 + 计划审批（★ 15.17.0，路线图批次⑤）。

两件事，共用**同一套真值源**（人机同源）：

**A. 决策链（只读）** —— ``GET /agent/decide?hashes=...&task_id=`` 增强：
把一个种子从「身份 → 保护 → 删除闸门 → 评分/策略 → 历史 → 结论」逐步摆出来，每步
``{step, rule, verdict, inputs, source_of_truth, at}``。口径全部**读现有真值源**——
``ledger``（身份/历史） / ``protection._protection_sets``（硬·软保护） /
``deletegate._delete_gate_detail``（物理删除闸门） / ``bonus.py``（时魔 · 策略阈值）。
带 ``task_id`` 时补上任务级口径（软/硬保护 + 阈值评分）；不带则退化为全局链。

**B. 计划审批（可写；默认干跑）** ——
``GET /agent/plan`` 生成计划（**只算不删**），返回 ``plan_id`` = **计划内容哈希**；
``POST /agent/plan/apply`` 必须带 ``plan_id``（``confirm=1`` 才真动手）：
**重新生成计划并比对内容哈希** —— 一致才执行（池内状态变了 → 计划过期 → 拒绝），
执行逐条过物理删除闸门（``downloader_ops.delete_torrents`` 是唯一删种出口）。

> 审批的本质：**人批准的是「他看到的那个计划」**，所以凭据不是时间戳而是**内容哈希**；
> 状态一变哈希就变，旧批准自动作废。这样「AI 出计划 → 人复核 → 执行」全程可复现。

动作（``action``）：
- ``cleanup``：某任务一轮删种名单（同 ``preview_cleanup`` / ``decide_deletions`` 口径）。
- ``optimize``：容量预算下的最优「保/删」组合（同 ``optimize_pool`` 口径，可带 ``budget_gb``）。
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Tuple

#: 支持的计划动作（稳定契约，改 = 破坏外部集成）
PLAN_ACTIONS: Tuple[str, ...] = ("cleanup", "optimize")
#: 计划格式版本（进内容哈希，口径变了旧计划自然作废）
PLAN_FORMAT = 1


class PlanMixin:
    """AI 决策链（``/agent/decide`` 增强）+ 计划审批（``/agent/plan`` / ``/agent/plan/apply``）。"""

    # ================================================================== 决策链
    def _chain_ctx(self, task: Any, task_id: str, snap: Any = None) -> Dict[str, Any]:
        """任务级决策上下文（保护集 / 策略 / 时魔表 / 账本），全部**读**现有真值源。"""
        ctx: Dict[str, Any] = {
            "task_id": str(task_id or ""), "task": task, "snap": snap,
            "manual": set(), "crossseed": set(), "claim": set(),
            "prot": {}, "policy": None, "bonus": {}, "ledger": {},
        }
        for key, fn in (("manual", "_agent_manual_hashes"),
                        ("crossseed", "_agent_crossseed_hashes"),
                        ("claim", "_agent_claim_hashes")):
            try:
                _f = getattr(self, fn, None)
                if callable(_f):
                    ctx[key] = set(_f() or set())
            except Exception:  # noqa: BLE001
                pass
        try:
            ctx["ledger"] = dict((self._tag_state() or {}).items())
        except Exception:  # noqa: BLE001
            ctx["ledger"] = {}
        if task is None:
            return ctx
        try:
            ins = self._cleanup_inputs(task, str(task_id or ""))
        except Exception:  # noqa: BLE001
            ins = None
        if not ins:
            return ctx
        ctx["policy"] = ins.get("policy")
        try:
            ctx["prot"] = self._protection_sets(
                task, list(ins.get("bonus_list") or []), list(ins.get("task_torrents") or []))
        except Exception:  # noqa: BLE001
            ctx["prot"] = {}
        ctx["bonus"] = {str(getattr(b, "hash", "") or "").lower(): b
                        for b in (ins.get("bonus_list") or [])}
        return ctx

    def _chain_steps(self, h: str, t: Any, rec: Dict[str, Any],
                     ctx: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """单个 hash 的**决策链**（有序步骤）。每步都带真值源与判定时间。"""
        now = self._agent_now()
        ctx = ctx or {}
        _h = str(h or "").lower()
        rec = rec or {}
        steps: List[Dict[str, Any]] = []

        # ① 身份（账本真值：站点 / 身份 sub / 是否库内资产 / 下载器状态 / 体积）
        try:
            _size = round(float(getattr(t, "size", 0) or 0) / 1024 / 1024 / 1024, 2) if t is not None else None
        except (TypeError, ValueError):
            _size = None
        sub = str(rec.get("sub") or "")
        steps.append({
            "step": "identity", "rule": "ledger/identity",
            "verdict": sub or "未登记",
            "inputs": {
                "site": str(rec.get("site") or ""),
                "name": str(rec.get("title") or getattr(t, "title", "") or "")[:200],
                "sub": sub or "未登记", "in_library": bool(rec.get("in_library")),
                "state": str(getattr(t, "state", "") or rec.get("state") or "unknown"),
                "size_gb": _size, "exists_in_downloader": t is not None,
            },
            "source_of_truth": "mf_resource / mf_identity（ledger）", "at": now,
        })

        # ② 保护（硬=永不删；软=可换出不可删）—— 唯一真值源 _protection_sets
        prot = ctx.get("prot") or {}
        hard = set(prot.get("hard") or set())
        soft = set(prot.get("soft") or set())
        why = dict(prot.get("why") or {})
        incomplete = set(prot.get("incomplete") or set())
        if _h in hard:
            steps.append({
                "step": "protect", "rule": "protection_sets/hard", "verdict": "block",
                "inputs": {"reason": str(why.get(_h) or "硬保护"),
                           "only_incomplete": _h in incomplete},
                "source_of_truth": "protection._protection_sets（docs/MODULES.md X3）", "at": now,
            })
        elif _h in soft:
            steps.append({
                "step": "protect", "rule": "protection_sets/soft", "verdict": "soft_block",
                "inputs": {"reason": str(why.get(_h) or "软保护（可换出、不可删）")},
                "source_of_truth": "protection._protection_sets（docs/MODULES.md X3）", "at": now,
            })
        # 无任务上下文时退化为「全局保护」（手动保留 / 跨站来源 / 已认领 / 欠 H&R）
        for scope, _set, rule, src in (
            ("manual", set(ctx.get("manual") or set()), "manual_protect", "task_states.json:protected_torrents"),
            ("crossseed_source", set(ctx.get("crossseed") or set()), "crossseed_source", "crossseed_source_hashes()"),
            ("claim", set(ctx.get("claim") or set()), "claim", "claim_protected_hashes()"),
        ):
            if _h in _set and not (_h in hard or _h in soft):
                steps.append({
                    "step": "protect", "rule": f"delete_gate/{rule}", "verdict": "block",
                    "inputs": {"scope": scope}, "source_of_truth": src, "at": now,
                })
        if t is not None and _h not in hard and _h not in soft:
            try:
                owed, need, seeded, src = self._hr_obligation("", t, snap=ctx.get("snap"))
            except Exception:  # noqa: BLE001
                owed, need, seeded, src = False, 0.0, 0.0, "err"
            if owed:
                steps.append({
                    "step": "protect", "rule": "hr/bill", "verdict": "block",
                    "inputs": {"site": str(rec.get("site") or ""),
                               "seeded_h": round(float(seeded or 0.0), 1),
                               "need_h": round(float(need or 0.0), 1), "src": str(src or "")},
                    "source_of_truth": ("hr_bills.json" if str(src) == "hrbill"
                                        else "mf_resource.hrs（ledger）"), "at": now,
                })

        # ③ 物理删除闸门（与执行时**同一口径**；这里只是先讲清楚会不会被拦）
        try:
            _g = self._delete_gate_detail([_h], snap=ctx.get("snap")) or {}
        except Exception:  # noqa: BLE001
            _g = {}
        if _h in _g:
            steps.append({
                "step": "delete_gate", "rule": "deletegate/_delete_gate_detail",
                "verdict": "block", "inputs": {"reason": str(_g.get(_h) or "")},
                "source_of_truth": "features/deletegate.py（删种唯一闸门）", "at": now,
            })

        # ④ 评分 / 策略阈值（任务级；口径 = bonus.py `decide_deletions`）
        pol = ctx.get("policy")
        b = (ctx.get("bonus") or {}).get(_h)
        if pol is not None and b is not None:
            try:
                bph = round(float(getattr(b, "bonus_per_hour", 0.0) or 0.0), 4)
                mbph = round(float(getattr(b, "mature_bonus_per_hour", 0.0) or 0.0), 4)
                thr = getattr(pol, "min_bonus_per_hour", None)
                _below = (thr is not None and bph < float(thr or 0.0))
                steps.append({
                    "step": "score", "rule": "bonus/decide_deletions", "verdict": (
                        "delete_candidate" if _below else "keep"),
                    "inputs": {
                        "size_gb": round(float(getattr(b, "size_gb", 0.0) or 0.0), 2),
                        "seeders": int(getattr(b, "seeders", 0) or 0),
                        "age_weeks": round(float(getattr(b, "age_weeks", 0.0) or 0.0), 2),
                        "bonus_per_hour": bph, "mature_bonus_per_hour": mbph,
                        "is_zero_bonus": bool(getattr(b, "is_zero_bonus", False)),
                        "min_bonus_per_hour": None if thr is None else round(float(thr or 0.0), 4),
                        "max_keep_torrents": getattr(pol, "max_keep_torrents", None),
                    },
                    "source_of_truth": "bonus.py（公式 + 任务策略）", "at": now,
                })
            except Exception:  # noqa: BLE001
                pass

        # ⑤ 历史（账本：删种台账 / 保护记录）—— 只读，不推断
        try:
            dels = [r for r in (self._agent_ledger_rows("deletions") or [])
                    if str(r.get("hash") or "").lower() == _h]
        except Exception:  # noqa: BLE001
            dels = []
        if dels:
            _last = dels[-1]
            steps.append({
                "step": "history", "rule": "ledger/deletions", "verdict": "info",
                "inputs": {"deletions": len(dels),
                           "last_at": str(_last.get("at") or _last.get("ts") or ""),
                           "last_reason": str(_last.get("reason") or ""),
                           "last_source": str(_last.get("source") or "")},
                "source_of_truth": "mf_deletions（ledger）", "at": now,
            })

        # ⑥ 结论
        _blocked = any(s["verdict"] == "block" for s in steps)
        _soft = any(s["verdict"] == "soft_block" for s in steps)
        _cand = any(s["verdict"] == "delete_candidate" for s in steps)
        verdict = "blocked" if _blocked else ("soft_protected" if _soft else
                                              ("delete_candidate" if _cand or t is not None else "unknown"))
        steps.append({
            "step": "verdict", "rule": "chain/final", "verdict": verdict,
            "inputs": {"steps": len(steps), "blocked": _blocked, "soft": _soft},
            "source_of_truth": "本链（只综合上述真值源，不新增判定）", "at": now,
        })
        return steps

    # ================================================================== 计划
    @staticmethod
    def _plan_id(action: str, task_id: str, budget: str, items: List[Dict[str, Any]]) -> str:
        """计划内容哈希（12 位）：动作 + 任务 + 预算 + 逐条 (hash, op, size) 规范序列化。

        任何一条种子的增减 / 体积变化 / 预算变化 → 哈希变 → 旧批准自动作废。
        """
        canon = {
            "v": PLAN_FORMAT, "action": action, "task_id": task_id, "budget_gb": budget,
            "items": sorted([[str(i.get("hash") or "").lower(), str(i.get("op") or ""),
                              round(float(i.get("size_gb") or 0.0), 2)] for i in items]),
        }
        raw = json.dumps(canon, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    def _plan_build(self, action: str, task_id: str,
                    budget_gb: str = "") -> Tuple[Optional[Dict[str, Any]], str]:
        """生成计划（**只算不删**）。返回 ``(plan, "")`` 或 ``(None, 错误信息)``。"""
        from ..bonus import optimize_pool, preview_deletions  # 顶层零相对 import（便于离线小测）
        act = str(action or "").strip().lower()
        tid = str(task_id or "").strip()
        if act not in PLAN_ACTIONS:
            return None, f"action 需为 {'|'.join(PLAN_ACTIONS)}"
        if not tid:
            return None, "task_id 必填"
        task = self._get_task_config(tid)
        if not task:
            return None, "任务不存在"
        ins = self._cleanup_inputs(task, tid)
        if ins is None:
            return None, "下载器不可用"

        warnings: List[str] = []
        items: List[Dict[str, Any]] = []
        totals: Dict[str, Any] = {}
        bud_str = str(budget_gb or "").strip()

        if act == "cleanup":
            prev = preview_deletions(ins["bonus_list"], ins["policy"], ins["protected"])
            rows = list(prev.get("deletion_candidates") or [])
            items = [{
                "hash": str(r.get("hash") or ""), "op": "delete",
                "title": str(r.get("title") or "")[:200],
                "size_gb": round(float(r.get("size_gb") or 0.0), 2),
                "bonus_per_hour": round(float(r.get("bonus_per_hour") or 0.0), 4),
                "age_weeks": round(float(r.get("age_weeks") or 0.0), 2),
                "reason": str(r.get("reason") or ""),
            } for r in rows]
            totals = {"torrents": int(prev.get("total_torrents") or 0),
                      "delete": len(items),
                      "keep": int(prev.get("to_keep_count") or 0),
                      "bonus_before": round(float(prev.get("total_bonus_before") or 0.0), 4),
                      "bonus_after": round(float(prev.get("total_bonus_after") or 0.0), 4),
                      "estimated_bonus_gain": round(float(prev.get("estimated_bonus_gain") or 0.0), 4),
                      "freed_gb": round(sum(float(i["size_gb"] or 0.0) for i in items), 2)}
        else:  # optimize
            budget: Optional[float] = None
            if bud_str:
                try:
                    budget = float(bud_str)
                except (TypeError, ValueError):
                    return None, "budget_gb 需为数字（GB）"
                if budget < 0:
                    return None, "budget_gb 不能为负"
            data = optimize_pool(ins["bonus_list"], budget, ins["policy"], ins["protected"])
            plan_d = dict(data.get("plan") or {})
            rows = list(plan_d.get("delete") or [])
            items = [{
                "hash": str(r.get("hash") or ""), "op": "delete",
                "title": str(r.get("title") or "")[:200],
                "size_gb": round(float(r.get("size_gb") or 0.0), 2),
                "bonus_per_hour": round(float(r.get("bonus_per_hour") or 0.0), 4),
                "age_weeks": round(float(r.get("age_weeks") or 0.0), 2),
                "reason": "组合优化：预算外，时魔效率更低",
            } for r in rows]
            totals = {"delete": len(items), "keep": int(plan_d.get("keep_count") or 0),
                      "budget_gb": data.get("budget_gb"), "budget_source": data.get("budget_source"),
                      "method": str(data.get("method") or ""),
                      "freed_gb": round(float(plan_d.get("freed_gb") or 0.0), 2),
                      "kept_bonus_per_hour": round(float(plan_d.get("kept_bonus_per_hour") or 0.0), 4),
                      "lost_bonus_per_hour": round(float(plan_d.get("lost_bonus_per_hour") or 0.0), 4),
                      "kept_bonus_pct": plan_d.get("kept_bonus_pct")}
            if data.get("infeasible"):
                warnings.append("预算低于强制保留体积：受保护种已超预算，计划为空")
            if str(data.get("budget_source") or "").startswith("auto"):
                bud_str = "auto"
            if str(getattr(task, "task_type", "bonus") or "bonus").lower() == "brush":
                warnings.append("刷流任务（目标=分享率/上传）：时魔最优口径仅供参考")
        if str(getattr(task, "task_type", "bonus") or "bonus").lower() == "brush" and act == "cleanup":
            warnings.append("刷流任务的清理口径是「无上传」，非时魔")

        # 逐条决策链（与 /agent/decide 同一函数 → 人机同源）
        try:
            ctx = self._chain_ctx(task, tid)
        except Exception:  # noqa: BLE001
            ctx = {}
        for it in items:
            _h = str(it.get("hash") or "").lower()
            it["chain"] = self._chain_steps(
                _h, (ctx.get("bonus") or {}).get(_h), (ctx.get("ledger") or {}).get(_h), ctx)

        plan = {
            "plan_id": self._plan_id(act, tid, bud_str if act == "optimize" else "", items),
            "format": PLAN_FORMAT,
            "action": act,
            "task_id": tid,
            "task_name": str(getattr(task, "name", "") or "")[:120],
            "task_type": str(getattr(task, "task_type", "bonus") or "bonus"),
            "site_id": int(getattr(task, "site_id", 0) or 0),
            "budget_gb": (bud_str if act == "optimize" else ""),
            "created_at": self._agent_now(),
            "items": items,
            "totals": totals,
            "warnings": warnings,
            "note": "只算不删。批准执行：POST /agent/plan/apply（带 plan_id + confirm=1）。",
        }
        return plan, ""

    def agent_plan(self, action: str = "", task_id: str = "", budget_gb: str = "") -> Dict[str, Any]:
        """``GET /agent/plan?action=cleanup|optimize&task_id=xxx[&budget_gb=N]`` —— **只算不删**。

        生成一份可复核的计划，返回 ``plan_id``（内容哈希）。给人/给 AI 看的是**同一条链**：
        每条待删项都带 ``chain``（身份 → 保护 → 闸门 → 评分 → 历史 → 结论）。
        """
        t0 = time.time()
        plan, err = self._plan_build(action, task_id, budget_gb)
        if err:
            code = "not_found" if err in ("任务不存在",) else "bad_param"
            return self._agent_err(code, err, t0, field="action" if "action" in err else "task_id")
        return self._agent_ok(plan, t0)

    def agent_plan_apply(self, plan_id: str = "", action: str = "", task_id: str = "",
                         budget_gb: str = "", delete_files: int = -1,
                         confirm: int = 0) -> Dict[str, Any]:
        """``POST /agent/plan/apply`` —— 执行**已批准**的计划（默认干跑）。

        ★ 审批凭据 = **内容哈希**：这里会**重新生成**计划并比对 ``plan_id``，
        不一致 = 池内状态已变 → 拒绝（``plan_stale``），请重新生成再批。
        执行走唯一物理删种出口 ``delete_torrents``（闸门二次校验），默认**不动文件**。
        """
        t0 = time.time()
        pid = str(plan_id or "").strip()
        if not pid:
            return self._agent_err("bad_param", "plan_id 必填（先调 GET /agent/plan）", t0, field="plan_id")
        plan, err = self._plan_build(action, task_id, budget_gb)
        if err:
            code = "not_found" if err in ("任务不存在",) else "bad_param"
            return self._agent_err(code, err, t0, field="task_id")
        if str(plan.get("plan_id")) != pid:
            return self._agent_err(
                "plan_stale", "计划已过期（池内状态已变），请重新生成后再批准", t0,
                data={"expected": pid, "current": str(plan.get("plan_id")),
                      "current_delete_count": len(plan.get("items") or [])})
        hashes = [str(i.get("hash") or "") for i in (plan.get("items") or [])
                  if str(i.get("op")) == "delete" and i.get("hash")]
        task = self._get_task_config(str(task_id or "").strip())
        _df = bool(getattr(task, "delete_files", False)) if int(delete_files) < 0 else bool(delete_files)
        if int(confirm or 0) != 1:
            return self._agent_ok({
                "dry_run": True, "plan_id": pid, "action": plan.get("action"),
                "task_id": plan.get("task_id"), "would_delete": len(hashes),
                "delete_files": _df, "items": plan.get("items"), "totals": plan.get("totals"),
                "note": "干跑：零写入。加 confirm=1 才真执行。",
            }, t0)

        if not hashes:
            return self._agent_ok({"plan_id": pid, "deleted": 0, "blocked": [], "delete_files": _df,
                                   "note": "计划内无可删项（池内已达标）"}, t0)

        # 执行前再对一遍闸门（只汇报，不绕闸门 —— 真删仍由 delete_torrents 内部闸门把关）
        try:
            gated = self._delete_gate_detail(hashes) or {}
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"闸门复核失败（fail-closed，不执行）:{e}", t0,
                                   trace_id=str(e))
        allowed = [h for h in hashes if h not in gated]
        downloader = self._get_downloader(getattr(task, "downloader", None) if task else None)
        if not downloader or not downloader.is_available:
            return self._agent_err("internal", "下载器不可用", t0)
        try:
            n, derr = downloader.delete_torrents(
                hashes=allowed, delete_file=_df,
                reason=f"计划审批/{plan.get('action')} plan={pid}",
                source="plan/apply")
        except Exception as e:  # noqa: BLE001
            return self._agent_err("internal", f"执行失败:{e}", t0, trace_id=str(e))
        blocked = [{"hash": h, "reason": str(gated.get(h) or "")} for h in hashes if h in gated]
        return self._agent_ok({
            "plan_id": pid, "action": plan.get("action"), "task_id": plan.get("task_id"),
            "deleted": int(n or 0), "error": str(derr or ""),
            "delete_files": _df, "blocked": blocked,
            "note": f"已按计划执行：删 {int(n or 0)} 条"
                    + (f"，{len(blocked)} 条被闸门拦下（保护种）" if blocked else ""),
        }, t0)
