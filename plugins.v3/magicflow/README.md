# MagicFlow - 魔流插件

根据站点魔力公式自动优化做种，智能删除低魔力产出种子。

## 功能特性

- **魔力公式计算**: 根据站点魔力公式精确计算每个种子的魔力产出效率
- **智能删种**: 按魔力产出从低到高排序，结合多种规则确定删除名单
- **魔力保护**: 支持魔力保护阈值和最低魔力值设置，防止魔力过低
- **多站点支持**: 通过站点适配器支持不同站点的魔力公式
- **刷流兼容**: 保留原有刷流插件的规则（做种时间、分享率、大小限制等）

### 跨站免费取种（3.9.0）

**玩法**：本站某颗「下载量大」的种子如果在**本站不免费**（下载就烧流量、拉低分享率），
改去**任意他站**找「**免费且同一 Release**」的副本下回来，下完再把这批文件**辅种回本站** ——
对本站来说是「零下载纯做种」，白赚上传与魔力。

任务配置「高级」→ **跨站免费取种**：

| 配置项 | 默认 | 说明 |
| --- | --- | --- |
| 启用跨站免费取种 | 关 | 打开后，本站不免费的候选会先尝试跨站取种 |
| 每轮跨站名额 | 3 | 每轮刷流最多发起几个跨站取种（防一次打太多站） |
| 单种大小上限 | 20 GB | 超过此体积不做跨站取种 |
| 最多探测站点数 | 6 | 每个候选最多查几个他站（越大越慢/越耗 PV） |

**判同 Release 的硬标准**：`fingerprint()` **完整特征码**（文件列表 + 根目录名）一致；
根目录名不同一律不自动辅种（在 qB 里会变成两个目录/对不上）。

**免费状态不在 `.torrent` 里**（是站点侧促销），所以只从各站的**免费视图**（`spstate`）取候选；
拿到的必是免费种。取种全程走 **PV 闸门 + 缓存**，每站检索结果缓存 6 小时。

**回辅**由插件级单 worker「跨站回辅」（5 分钟一轮）完成：他站下完 → 把本站的 `.torrent`
指向同一批文件添加（暂停 → 校验 → 通过才做种，不匹配自动撤销）。超 24 小时未完成自动丢弃。

查看队列：`GET /crossseed`（`POST /crossseed?action=clear` 清空）。

## 支持的站点

- [HDFans](https://hdfans.org) - NexusPHP 架构

## 魔力公式

### HDFans

```
A = Σ((1 - 10^(-Ti/T0)) × Si × (1 + √2 × 10^(-(Ni-1)/(N0-1))) × Wi)
B = B0 × 2/π × arctan(A/L)

参数:
- Ti: 种子生存时间（周）
- T0: 生存时间参数，固定 5
- Si: 种子大小（GB）
- Ni: 当前做种人数
- N0: 做种人数参数，固定 7
- Wi: 权重（普通=1，零魔=0.2）
- B0: 小时魔力上限，固定 100
- L: 曲线参数，固定 300
```

## 安装

1. 将 `magicflow` 目录放入 `MoviePilot/plugins.v3/` 目录
2. 在 MoviePilot 插件市场启用插件
3. 配置站点和下载器

## 配置说明

### 任务配置

| 配置项 | 说明 |
| --- | --- |
| 站点 | 选择要刷魔力的站点 |
| 下载器 | 选择使用的下载器 |
| 检查间隔 | 魔力检查周期（分钟） |
| 每小时最低魔力产出 | 低于此值的种子将被删除 |
| 最多保留种子数 | 超出此数量的低魔力种子将被删除 |
| 魔力保护阈值 | 魔力高于此值时不删除任何种子 |
| 最低魔力保留值 | 魔力低于此值时停止删种 |

### 兼容刷流规则

| 配置项 | 说明 |
| --- | --- |
| 做种时间 | 低于此做种时间的种子将被删除 |
| 分享率 | 低于此分享率的种子将被删除 |
| 种子大小 | 只保留大小范围内的种子 |
| 做种人数 | 只保留做种人数范围内的种子 |

## 开发

### 铁律：不要在函数体内写相对的懒导入（热重载死锁）

MoviePilot 热重载会先 `clear_modules()` 把 `app.plugins.magicflow*` 从 `sys.modules` 里全部清掉，
再单线程重新导入。如果此时你还有在飞的 worker 线程在函数体内执行 `from .x import y`，
两个线程就会形成**环形导入等待**：

```
重载线程 A：持有 app.plugins.magicflow（父包）→ 等 .sites
worker 线程 B：持有 app.plugins.magicflow.sites → 等父包（sites 里 from ..bonus import ...）
```

CPython 的 `_ModuleLock.has_deadlock()` 会检测到这个环并抛 `_DeadlockError`
（`deadlock detected by _ModuleLock('app.plugins.magicflow.sites')`）——**进程不会挂死**，
但那一次重载会失败：`sync.py` 报「同步本地插件失败」，MP 会把插件的全部服务摘掉
（`移除插件服务(None)`）直到下一次成功加载，期间定时任务不跑、插件 API 路由 404。

**做法**：所有相对的模块导入一律放**模块顶层**（必要时放在文件末尾、相关名字定义之后再导入）；
`import traceback` / `import base64` 这类**标准库**的懒导入无所谓（不涉及插件模块锁）。

### 添加新站点支持

1. 在 `sites/` 目录下创建新的计算器类
2. 继承 `BonusCalculator` 基类
3. 实现 `calc_bonus_per_hour` 方法
4. 实现 `parse_bonus_page` 方法解析站点魔力页面
5. 在 `SITE_CALCULATORS` 字典中注册新站点

```python
from sites import BonusCalculator

class NewSiteBonusCalculator(BonusCalculator):
    site_schema = "UNIT3D"
    site_name = "NewSite"

    def calc_bonus_per_hour(self, size, seeders, leechers, age_weeks, volume_factor, **kwargs):
        # 实现站点魔力公式
        ...
```

## 版本号规则（语义化 · 强制）

格式 `MAJOR.MINOR.PATCH`，例：`1.1.0`。

| 改动类型 | 递增 | 例 |
| --- | --- | --- |
| 新功能 / 新标签页 / 新端点 | **+MINOR** | `1.1.0 → 1.2.0` |
| Bug 修复 / 文案 / 样式小改 | **+PATCH** | `1.1.0 → 1.1.1` |
| 不兼容变更（配置迁移、数据格式变） | **+MAJOR** | `1.1.0 → 2.0.0` |

- **PATCH 不超过 99**：到 99 后下一次改动改为 +MINOR 并把 PATCH 归零，**彻底避免 1.0.999 这类超长号**。
- **一次发版只 bump 一次**：一轮改动（一个功能或一批修复）只在收尾统一改版本号；开发中途验证靠硬刷新（`Ctrl+Shift+R`）或临时手动改 `?v`，**不要每改一点就 bump**（1.0.93~1.0.108 就是单改一个设置弹窗蹭出来的）。
- **必须同步的位置（缺一即市场/缓存错乱）**：
  1. `magicflow/__init__.py` → `__version__`
  2. `magicflow/package.json` → `version`
  3. 市场仓 `moviepilot-plugins-git/package.v3.json` → `version` + `history` 新条目
  4. 市场仓 `plugins.v3/magicflow/{__init__.py, package.json}` → `__version__` / `version`
  5. 本地市场索引 `core/local-plugins/package.v3.json` → `version` + `history`
  6. 本地仓 `core/local-plugins/plugins.v3/magicflow/{__init__.py, package.json}`
  7. 已安装副本 `config/plugins_backup/magicflow/`（由 monitor 自动同步覆盖，通常不用手改）
- **为什么必须 bump**：MoviePilot 插件前端走 `remoteEntry.js?v=<__version__>`，不 bump 客户端继续吃旧 chunk；`__version__` 同时是市场判定「有无更新」的依据。

## 协议

GPL-3.0
