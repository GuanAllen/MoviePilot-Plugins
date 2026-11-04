# -*- coding: utf-8 -*-
"""魔流 · api —— 工作台 API 路由表（146 条，按域分组）。

（由原 `__init__.py` 拆分为 mixin；19.10.29 由 1008 行单段字面量改为分组表。）

这里是**唯一的路由真值源**：`_ROUTES` 每条 `(path, handler, methods, summary)`，
`get_api` 只负责把 handler 名绑成实例方法、补上统一的 ``auth``。改路由只动表，
不用在 1000 行里找位置；``tools/check_api_routes.py`` 静态校验四条不变量
（无重复 path+method、handler 都存在、通配不遮蔽字面量、条数与表一致）。

``methods`` 用逗号分隔的字符串（``"GET"`` / ``"GET,POST"``）：146 条里只有 5 条
是多方法，为它们给每条都补元组括号不值得。

``/agent*`` 路由不在这里 —— 由 ``AgentApiMixin.get_api`` 追加，登记表在
``agentapi._agent_endpoints()``。
"""

from typing import Any, Dict, List

#: 插件 API 一律走 MP 的 bear 鉴权（146 条全一样，故不再逐条写）。
_AUTH = "bear"


_ROUTES = (
    # ── 概览 / 状态（6 条）
    ("/pool", "pool_info", "GET", "池盘空间（按目录分池：总量/已用/80% 阈值下的可占体积）"),
    ("/status", "get_status", "GET", "获取魔流总览"),
    ("/health", "get_health", "GET", "健康自检:任务失败/卡死·时魔下滑·磁盘贴上限(按严重度排序)"),
    ("/health/scan", "health_scan", "GET", "挂种健康度自检(只读):逐文件核盘找空转/缺文件的种 + 其中欠 H&R 的风险"),
    ("/recon", "get_recon", "GET", "站点对账:本地实挂 vs 站点认账 vs 台账(找出挂着但站点不认的种)"),
    ("/features", "features_overview", "GET", "功能注册表（契约③）：登记项 + 开启状态"),

    # ── 任务（增删改查 / 预览 / 优化 / 种子级操作 / 交棒）（22 条）
    ("/tasks", "create_task", "POST", "创建魔流任务"),
    ("/tasks/{task_id}", "get_task_detail", "GET", "获取魔流任务详情"),
    ("/tasks/{task_id}", "update_task", "PUT", "更新魔流任务"),
    ("/tasks/{task_id}", "delete_task", "DELETE", "删除魔流任务"),
    ("/tasks/{task_id}/state", "update_task_state", "POST", "启用或暂停魔流任务"),
    ("/tasks/{task_id}/run", "run_task", "POST", "立即执行一轮魔力优化"),
    ("/tasks/{task_id}/bonus", "get_task_bonus", "GET", "获取任务做种魔力明细"),
    ("/tasks/{task_id}/candidates", "get_task_candidates", "GET", "获取站点候选种子及魔力评分"),
    ("/tasks/{task_id}/backfill-pages", "backfill_torrent_pages", "POST", "回填存量托管种子的详情页链接(供促销核对)"),
    ("/backfill-pages", "backfill_batch", "POST", "对所有任务批量回填详情页链接"),
    ("/tasks/{task_id}/preview", "preview_cleanup", "POST", "预览一轮删种名单"),
    ("/tasks/{task_id}/optimize", "optimize_plan", "GET", "★ 组合优化器:容量预算下最优「保/删」组合(0/1 背包;含前沿+阈值对比;只算不删)"),
    ("/tasks/{task_id}/operations", "get_operations", "GET", "获取任务操作记录"),
    ("/tasks/{task_id}/torrents/{hash}/protect", "protect_torrent", "POST", "手动保留种子"),
    ("/tasks/{task_id}/torrents/{hash}/unprotect", "unprotect_torrent", "POST", "取消保留种子"),
    ("/tasks/{task_id}/torrents/{hash}/delete", "manual_delete_torrent", "POST", "手动删除种子"),
    ("/tasks/{task_id}/torrents/{hash}/pause", "pause_torrent", "POST", "暂停种子"),
    ("/tasks/{task_id}/torrents/{hash}/resume", "resume_torrent", "POST", "恢复做种"),
    ("/tasks/{task_id}/torrents/{hash}/recheck", "recheck_torrent", "POST", "强制校验种子"),
    ("/tasks/{task_id}/torrents/batch", "batch_torrents", "POST", "批量操作托管种子"),
    ("/tasks/{task_id}/handover", "get_task_handover", "GET", "删除任务前：预览名下种子可交棒给谁 / 有多少"),
    ("/tasks/{task_id}/handover", "post_task_handover", "POST", "把任务名下种子交棒给其它任务 / 退回静默池"),

    # ── 操作记录（1 条）
    ("/operations", "get_all_operations", "GET", "获取全部任务的操作记录（主页全局视图）"),

    # ── 标签 / 资产（6 条）
    ("/site/seeds", "get_site_seeds", "GET", "站点级种子报表（逐条种子状态：分类/保护/账单/qB）"),
    ("/tags", "get_tag_model", "GET", "标签模型：状态账本/文件组/分拣规则"),
    ("/tags/set", "set_tag_state", "POST", "手动设置种子状态（改标签 + 写账本）"),
    ("/assets", "assets_library", "GET", "库内资产列表（★ 资产粒度：一条=一份资源；name=资源名；members=本体+各站辅种；block=被哪道闸拦住）"),
    ("/assets/act", "assets_act", "POST", "★库内资源管理动作（protect/unprotect/subscribe/unsubscribe/organize/scrape）"),
    ("/assets/delete", "assets_delete", "POST", "删除库内资产（★ 按资源整组：删种+连带所有辅种+文件；只破「库内资产」一道闸；默认干跑）"),

    # ── H&R 账单 / 站点规则（3 条）
    ("/hr/bills", "get_hr_bills", "GET", "H&R 账单按站分组（欠债/状态分布/need_left/in_qb/missing/per_torrent_hr/规则来源）"),
    ("/rules", "get_site_rules", "GET", "站点规则库(H&R/保种时长/做种上限)"),
    ("/rules/probe", "probe_site_rules", "POST", "逐站拉取站点规则并入库"),

    # ── 站点运维（认领 / 静默池 / 签到 / 考核 / RSS / 凭据 / 补源）（19 条）
    ("/exam", "get_exam_state", "GET", "新手考核汇总 + 一键起任务预演(已通过的默认不返回)"),
    ("/exam/act", "exam_act", "POST", "新手考核:一键起任务(需 confirm=true)"),
    ("/signin", "get_signin_state", "GET", "站点签到/登录:今日状态 + 近 7 天记录(借鉴「站点自动签到」插件)"),
    ("/signin/run", "run_signin", "POST", "站点签到/登录:立即执行一次(kind=sign|login)"),
    ("/silent/pool", "silent_pool", "GET", "静默池全局视图（概览/按站/条目/记录，只读）"),
    ("/silent/enforce", "silent_enforce", "GET", "静默不变量收敛:账本/标签静默但 qB 没停的种补 pause（默认干跑；confirm=1 才写）"),
    ("/claim", "get_claim_state", "GET", "认领:状态(能力/可认领/已认领/账本/记录)"),
    ("/claim/run", "run_claim", "POST", "认领:跑一轮(默认干跑;write=1&confirm=1 才真写)"),
    ("/claim/do", "claim_do", "POST", "认领:手动认领单条(需 confirm=1)"),
    ("/claim/abandon", "claim_abandon", "POST", "认领:放弃认领(需 confirm=1;无接口模板则不执行)"),
    ("/claim/restore", "claim_restore", "POST", "认领:从站点认领页重建本地账本(只写本地;confirm=1 才写,缺省预览)"),
    ("/claim/host", "claim_host_enforce", "GET,POST", "认领职务:名单内贴「认领」并做种/名单外还原(默认干跑;confirm=1 才写)"),
    ("/rss", "get_rss_state", "GET", "RSS:读取各站订阅条目(需先保存 passkey)"),
    ("/rss/config", "get_rss_config", "GET", "RSS:站点 passkey 配置状态(脱敏)"),
    ("/rss/passkey", "save_rss_passkey", "POST", "RSS:保存/清除某站 passkey"),
    ("/creds", "get_creds", "GET", "凭据中心:passkey / apikey / rss 状态(脱敏)"),
    ("/creds/save", "save_cred", "POST", "凭据中心:保存/清除某站某字段"),
    ("/creds/sync", "sync_creds_to_mp", "POST", "凭据中心:一键写入 MP 站点 rss/apikey(需 confirm=1)"),
    ("/rescue", "rescue", "GET,POST", "死种补源：停滞欠 H&R 的种从他站无 H&R 站补下同 Release(action=scan 只读预览 / apply 执行需 confirm=1)"),

    # ── 站点诊断（能力 / 魔力公式）（1 条）
    ("/sites/{site_id}/bonus-formula", "probe_site_formula", "GET", "抓取站点魔力公式与参数(诊断)"),

    # ── PV 配额 / 实时 / 趋势 / 事件（7 条）
    ("/pv", "get_pv_ledger", "GET", "站点 PV 账本:每站每天耗了多少配额(可查历史)"),
    ("/pv/budget", "set_pv_budget", "POST", "设置站点 PV 日预算(0=不限)"),
    ("/live", "get_live_state", "GET", "站点实时数据 + 流量监控(直连站点,非 MP 6h 快照)"),
    ("/events", "get_events", "GET", "结构化事件流(journal 读模型+本地补充;支持 since/limit/kind/task_id/level)"),
    ("/trend", "get_trend", "GET", "趋势观测:每小时采样(站点/任务口径时魔·做种数·体积)最近 7 天"),
    ("/trend/daily", "get_trend_daily", "GET", "长期趋势:日报采样(持久化 180 天;站点/任务口径时魔·做种数·体积·限免数)"),
    ("/trend/why", "explain_trend", "GET", "趋势归因:时魔变化拆成种子数/单种魔力/残差 + 结论 + 证据 + 建议(只读)"),
    ("/pushes", "pushes", "GET", "推送审计:每次加种一条(成功+失败,含站端/下载器原始报错);支持 limit/ok/task_id 过滤"),

    # ── 设置（插件配置 / 下载器 / 任务模板）（6 条）
    ("/settings", "update_settings", "POST", "更新魔流插件设置"),
    ("/downloader/prefs", "get_downloader_prefs", "GET", "读取下载器全局参数"),
    ("/downloader/prefs", "update_downloader_prefs", "POST", "写入下载器全局参数"),
    ("/downloader/paths", "update_downloader_paths", "POST", "写入下载器全局目录"),
    ("/defaults", "get_defaults", "GET", "读取默认任务模板"),
    ("/defaults", "update_defaults", "POST", "保存默认任务模板"),

    # ── 刷流取种 / 辅种 / 套牌 / 推荐 / 点播 / 评分 / 元数据兜底（27 条）
    ("/crossseed", "get_crossseed", "GET", "跨站免费取种:取种台账（在飞）+ 启用任务（**只读**；写操作走 POST）"),
    ("/crossseed", "post_crossseed", "POST", "跨站免费取种:写操作(action=clear/drop/unban/guard)"),
    ("/deck", "deck_info", "GET", "满魔套牌存档（mf_deck，§5.2）：按套牌汇总（site_id 可过滤）"),
    ("/deck/sync", "deck_sync", "POST", "把当前在岗套牌写回存档（task_id 可空=全部 bonus 任务；连续 N 轮不变→满魔冻结）"),
    ("/deck/apply", "deck_apply", "POST", "复用期：按存档把本机在种的牌重新纳管（零下载；apply=false 只预览）"),
    ("/deck/delete", "deck_delete", "POST", "删掉一套牌存档（deck_id）"),
    ("/ondemand", "on_demand", "POST", "点播（§1 权威来源 1）：片名/豆瓣·TMDB·IMDB 链接 → 选源（单价优先：免费 < 三折 < 五折 < 全额，同价比做种数与体积）→ 下载 → 直接转「资源」"),
    ("/ondemand/batch", "on_demand_batch", "POST", "点播多选：一次落多条候选（picks=候选链接，换行/逗号分隔；不重搜、逐条独立成败）"),
    ("/ondemand/items", "ondemand_items", "GET", "点播清单（只读）：进行中（含下载进度/速度/ETA）+ 已完成历史（结果现况回查）"),
    ("/ondemand/act", "ondemand_act", "POST", "点播行内操作（进行中）：pause 暂停 / resume 继续 / remove 移除（走唯一删除闸门，欠 H&R 硬拦）"),
    ("/ondemand/repair", "ondemand_repair", "POST", "点播补整理：把「已转资源·未入库」的历史行重跑 MP 整理（force=1 忽略退避与次数上限）"),
    ("/douban_service", "get_douban_service", "GET", "豆瓣评分服务:库容量 + 后台慢爬进度（**只读**；写操作走 POST）"),
    ("/douban_service", "post_douban_service", "POST", "豆瓣评分服务:写操作(action=start|stop|reset|enrich_<子动作>)"),
    ("/fallback", "get_fallback_state", "GET", "元数据兜底:配置 + 最近一次结果"),
    ("/fallback/run", "run_fallback", "POST", "元数据兜底:立即扫描(dry_run=true 仅演练)"),
    ("/iyuu/sites", "get_iyuu_sites", "GET", "列出 MoviePilot 已配置站点 + 当前 IYUU 设置(供密钥表)"),
    ("/iyuu/test", "test_iyuu", "GET", "测试 IYUU Token 连通性"),
    ("/reseed", "get_reseed", "GET", "全站辅种:状态(站点/配额/云端缓存/账本)"),
    ("/reseed", "update_reseed", "POST", "全站辅种:配置(开关/干跑/站点白名单/限量)"),
    ("/reseed/probe", "reseed_probe", "GET", "全站辅种:逐站下载链诊断(模板/口令/cookie)"),
    ("/reseed/run", "run_reseed", "POST", "全站辅种:立刻跑一轮(dry=true 只算不挂;catalog=N 顺带爬目录)"),
    ("/reseed/catalog", "run_reseed_catalog", "POST",
     "全站辅种:爬种子目录缓存(HDDolby 分区枚举;calls=次数 默认24;reset=1 游标归零;与取种共用小时配额)"),
    ("/recommend", "get_recommend_list", "GET", "列出推荐甄别结果"),
    ("/recommend/{hash}/confirm", "confirm_recommend", "POST", "确认推荐(自动整理入库)"),
    ("/recommend/{hash}/dismiss", "dismiss_recommend", "POST", "忽略推荐并删除"),
    ("/recommend/{hash}/import", "import_recommend", "POST", "手动整理入库"),
    ("/recommend/{hash}/subscribe", "subscribe_recommend", "POST", "★手动给该单集订阅整季（MP 抓齐其余集；不自动订阅）"),
    ("/recommend/{hash}/unsubscribe", "unsubscribe_recommend", "POST", "★退订该记录的整季订阅并复位（不动种子）"),
    ("/recommend/batch_import", "import_recommend_batch", "POST", "批量整理入库(hashes=… 或 all=1)"),

    # ── 云盘归档（6 条）
    ("/cloud", "get_cloud_state", "GET", "云盘归档:配置 + 最近计划/结果 + 归档记录"),
    ("/cloud/test", "test_cloud", "GET", "云盘归档:连通性自检(OpenList 存储/挂载)"),
    ("/cloud/plan", "plan_cloud", "POST", "云盘归档:生成归档计划(只读,不写不删)"),
    ("/cloud/upload", "upload_cloud", "POST", "云盘归档:上传单个文件(dry_run=true 仅演练)"),
    ("/cloud/run", "run_cloud", "POST", "云盘归档:跑一轮(默认 dry_run,不删本地)"),
    ("/cloud/clear", "clear_cloud", "POST", "云盘归档:清空归档记录(不动文件)"),

    # ── 事件通知（2 条）
    ("/notify", "notify_status", "GET", "事件通知:配置 + 最近事件 + 计数(H&R 临期/容量红线/产出骤降/任务失败)"),
    ("/notify/act", "notify_act", "POST", "通知动作:发测试 / 立即扫描 / 清历史"),

    # ── 后台任务队列（2 条）
    ("/jobs", "jobs_list", "GET", "★后台任务队列（进度 + 结果；任务跑在插件进程里，关页面不中断）"),
    ("/jobs/clear", "jobs_clear", "POST", "清理已完成的后台任务记录（在跑的不动）"),

    # ── 诊断（只读 / 干跑为主，写操作需 confirm）（35 条）
    ("/debug/sitecap", "debug_site_caps", "GET", "站点类型/能力识别结果(probe=true 时联网探测)"),
    ("/debug/mpsearch", "debug_mp_search", "GET", "诊断:调 MP 自带搜索看签名兼容性/免费且有源命中(1 PV/站)"),
    ("/debug/np-main", "debug_np_main", "GET", "临时诊断:browse/debug 通道抓同一页的内容与自解析对比"),
    ("/debug/cache", "debug_cache", "GET", "诊断:查看/丢弃站点抓取缓存(drop=<key> 强制下轮重抓)"),
    ("/debug/siteua", "debug_siteua", "GET", "诊断:只改站点 UA 字段(写)"),
    ("/debug/mtapi", "debug_mtapi", "GET", "诊断:按站点 apikey 调 M-Team API 搜索(只读)"),
    ("/debug/hdpost", "debug_hdpost", "GET", "诊断:按站点 apikey 向 HDDolby API 发 POST JSON(只读搜索)"),
    ("/debug/hdapi", "debug_hdapi", "GET", "诊断:按站点 apikey 调 HDDolby 风格 API(只读)"),
    ("/debug/fetch", "debug_fetch", "GET", "诊断:按站点会话抓一个页面(只读;返回状态/长度/命中词)"),
    ("/debug/retag", "debug_retag", "GET", "诊断:把任务旧标签下的种补上当前标签(只加不减;dry=1 只报告)"),
    ("/debug/crossseed", "debug_crossseed", "GET", "诊断:拿本任务候选当「本站非免费」跑一遍跨站选源(dry-run,add=true 才真下)"),
    ("/debug/store", "debug_store", "GET,POST", "状态存储健康度(action=flush 落盘 / drop-hot 清热层键验证回灌)"),
    ("/debug/torrents", "debug_qb_torrents", "GET", "诊断:列出下载器全部种子并按标签分组(只读)"),
    ("/debug/delete-gate", "debug_delete_gate", "GET", "诊断:查询删除闸门(hashes 逗号分隔 → 返回被硬保护拦截的子集)"),
    ("/debug/traffic", "debug_traffic", "GET", "诊断:未知流量审计（无魔流标签的种 + 单种限速分布）"),
    ("/debug/seedlimit", "debug_seed_limit", "GET,POST", "诊断:解除全部单种上传限速（0 = 不限）"),
    ("/debug/emit-transfer", "debug_emit_transfer", "GET,POST", "诊断:手工投递 TransferComplete 事件(验证库记链路)"),
    ("/debug/file", "debug_read_file", "GET", "诊断:读取容器内文本文件片段(白名单 /app /config /core,只读)"),
    ("/debug/fs", "debug_fs", "GET", "诊断:查看路径是否在库/是否硬链接(只读元数据)"),
    ("/debug/qb", "debug_qb_info", "GET", "诊断:qBittorrent 可用信息一览(字段/属性/跟踪器/全局偏好,只读)"),
    ("/debug/collect", "debug_collect", "GET", "采集模块观测：注册表/最近抓取/配额/worker 注册原因"),
    ("/debug/fetch-page", "debug_fetch_page", "GET", "诊断:用站点 cookie 抓取页面片段(只读)"),
    ("/debug/auth-get", "debug_auth_get", "GET", "诊断:用站点 API Key(非 cookie)发 GET,判定端点认哪种鉴权(只读)"),
    ("/debug/recognize", "debug_recognize", "GET", "诊断:识别种子名(评分/榜单/订阅)"),
    ("/debug/douban", "debug_douban", "GET", "诊断:查豆瓣评分源(独立服务 magicflow-douban,HTTP 客户端)"),
    ("/debug/recommend-run", "debug_recommend_run", "POST", "诊断:立即跑一轮推荐甄别"),
    ("/debug/recommend-reset", "debug_recommend_reset", "POST", "诊断:清空推荐甄别结果"),
    ("/debug/cloud-get", "debug_cloud_get", "GET", "诊断:OpenList /api/fs/get 原始响应"),
    ("/debug/cloud-put", "debug_cloud_put", "GET", "诊断:尝试用 1KB 数据 PUT 到 OpenList(定位上传报错)"),
    ("/debug/events", "debug_events", "GET", "事件流诊断:数量(分 kind/level)/本地缓冲/已知分类"),
    ("/debug/trend", "debug_trend", "GET", "趋势诊断:序列数/点数/最后采样时间"),
    ("/debug/rss_candidates", "debug_rss_candidates", "GET", "逐站测试 RSS 候选(条数/hash 补齐/体积)"),
    ("/debug/claim", "debug_claim", "GET", "认领:诊断(能力探测/可认领/账本/适配器)"),
    ("/debug/candidates", "debug_candidates", "GET", "API 站(馒头)候选列表诊断"),
    ("/debug/api", "debug_api", "GET", "API 通道诊断(profile/list/search/detail/dl/hash)"),
    ("/debug/mteam", "debug_mteam_api", "GET", "馒头 API 通道诊断(profile/search/detail/dl)"),
)


class ApiMixin:
    """api 功能集（原 MagicFlow 方法原样搬入）。"""

    def get_api(self) -> List[Dict[str, Any]]:
        """注册 Vue 工作台使用的魔流任务 API。

        表里存的是**方法名**：`getattr` 拿不到就当场报错，别让一条路由悄悄消失
        （通常是处理函数被改名或搬走了，路由表没跟上）。
        """
        routes: List[Dict[str, Any]] = []
        for path, handler, methods, summary in _ROUTES:
            fn = getattr(self, handler, None)
            if not callable(fn):
                raise RuntimeError(f"路由 {path} 的处理函数 {handler} 不存在")
            routes.append({
                "path": path,
                "endpoint": fn,
                "methods": [m.strip().upper() for m in methods.split(",") if m.strip()],
                "auth": _AUTH,
                "summary": summary,
            })
        return routes
