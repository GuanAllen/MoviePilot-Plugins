# 魔流「脏数据」清理清单（干跑 · 零写入）

- 生成时间：2026-10-15 19:46　范围：静默池报表里「不在下载器」的账本行

- 判据：qB 实测无此 hash（`魔流-辅种` 在世 1068 个，这 126 个一个都不在）

- 数据来源三本账：`deletions.jsonl`（魔流自己的删种流水）、`mf_reseed`（辅种台账，PG `plugin_magicflow_8512da16`）、`hr_bills.json`（H&R 账单）


## 一句话结论

**这 126 条不是「未下完的种」，是魔流自己删掉的种留下的账本行。** 其中 55 条（A 组）销账最安全；35 条（B 组）文件还在、建议保留；36 条（C 组）本来就没台账行，只差一个报表口径。


## 分组与建议动作

| 组 | 条数 | 站点分布 | H&R | 建议 | 为什么 |
|---|---|---|---|---|---|
| A | 55 | carpt.net 54, duckboobee.org 1 | site_hr/settled 54, unknown/pending 1 | 销账=删掉/失效这 55 条辅种台账行 | 台账写「已挂」，但删种时**连文件一起删了**（`delete_file=true`），保留它只会：① 报表虚报 ② 索引里无意义。删台账行后辅种任务会重试，但文件已不在 → 必然失败（每轮白跑）；**稳妥做法是置为失效并保留历史**，或直接删行。 |
| B | 35 | btschool.club 28, duckboobee.org 2, soulvoice.club 3, carpt.net 1, cspt.top 1 | site_hr/settled 29, unknown/pending 6 | 不动；若你要腾台账，可另案处理 | 删种时**只摘了种、文件保留**（`delete_file=false`）。文件在 → 辅种任务重新发现后**可以重新挂上、魔力能回来**。不建议动台账。 |
| C | 36 | carpt.net 34, btschool.club 1, duckboobee.org 1 | site_hr/settled 35, unknown/pending 1 | 不动（只有 H&R 账单，属正常历史账） | 这 36 条只有 H&R 账单、没有辅种台账行，**没有任何数据要清**；报表口径修好后它们自然从「未下完」消失。 |

## 明细（126 条）


### A · 台账 ok+文件已删 → **建议销账**（保留无意义：辅种重试必失败）

| # | infohash(前12) | 站点 | 标题 | H&R | 需/已挂 h | 台账状态 | 最后删种 | 文件 |
|---|---|---|---|---|---|---|---|---|
| 1 | `35968a655c61` | carpt.net | 心动的信号.Heart.Signal.2026.S09.2160p.WEB-DL.60f | site_hr/settled | 24.0/26.7 | ok/已挂 | 2026-10-05 21:41:21 | 连文件删 |
| 2 | `9466a77f5be5` | carpt.net | 巴塞罗那.Barcelona.1994.Criterion.Collection.Blu | site_hr/settled | 24.0/24.5 | ok/已挂 | 2026-10-05 21:41:21 | 连文件删 |
| 3 | `876ff2532810` | carpt.net | Zero.Chill.S01.1080p.NF.WEB-DL.DDP5.1.x264-i | site_hr/settled | 24.0/26.1 | ok/已挂 | 2026-10-05 21:41:21 | 连文件删 |
| 4 | `e1f76e3e6943` | carpt.net | 冬城猎凶.Cold.Hunt.2026.S01.1080p.WEB-DL.60fps.H | site_hr/settled | 24.0/25.8 | ok/已挂 | 2026-10-05 21:41:21 | 连文件删 |
| 5 | `ff2121f89f9b` | carpt.net | [兰香如故].Against.the.Current.2026.S01.1080p.Di | site_hr/settled | 24.0/25.4 | ok/已挂 | 2026-10-05 21:41:21 | 连文件删 |
| 6 | `7117a7df7808` | carpt.net | 狂徒 The Outlaw S01 2026 2160p WEB-DL H.265 HD | site_hr/settled | 24.0/24.0 | ok/已挂 | 2026-10-05 22:49:06 | 连文件删 |
| 7 | `5b425a5f8ce8` | carpt.net | [女警出更 第二季].Women.in.Blue.2026.S02.1080p.Appl | site_hr/settled | 24.0/24.5 | ok/已挂 | 2026-10-05 22:49:06 | 连文件删 |
| 8 | `7acfdc1f75a3` | carpt.net | Les.legendes.de.Tatonka.S02.1080p.AMZN.WEB-D | site_hr/settled | 24.0/24.5 | ok/已挂 | 2026-10-05 22:49:06 | 连文件删 |
| 9 | `52250d87086f` | carpt.net | 法兰西之子.The.Son.Of.Français.1999.2160p.WEB-DL. | site_hr/settled | 24.0/24.0 | ok/已挂 | 2026-10-05 23:04:47 | 连文件删 |
| 10 | `6bf22af0e302` | carpt.net | Scary.Movie.2026.BluRay.1080p.x264.TrueHD.7. | site_hr/settled | 24.0/24.3 | ok/已挂 | 2026-10-05 23:39:17 | 连文件删 |
| 11 | `530acb1e204d` | carpt.net | 蓝白红三部曲之红.Three.Colors-Red.1994.Criterion.Col | site_hr/settled | 24.0/24.2 | ok/已挂 | 2026-10-05 23:44:41 | 连文件删 |
| 12 | `14ddf2cb21af` | carpt.net | 别惹蚂蚁.The.Ant.Bully.2006.EUR.BluRay.1080p.x26 | site_hr/settled | 24.0/27.1 | ok/已挂 | 2026-10-06 03:14:29 | 连文件删 |
| 13 | `dc408856da92` | carpt.net | 异形终结.Screamers.1995.2160p.WEB-DL.H.265.AAC2. | site_hr/settled | 24.0/26.9 | ok/已挂 | 2026-10-06 03:14:29 | 连文件删 |
| 14 | `1adf1487d1d3` | carpt.net | 神探飞机头2.Ace.Ventura.When.Nature.Calls.1995.21 | site_hr/settled | 24.0/27.2 | ok/已挂 | 2026-10-06 03:14:29 | 连文件删 |
| 15 | `078b3e9f7904` | carpt.net | Calabash Brothers Complete 1986-1991 WEB-DL  | site_hr/settled | 24.0/24.3 | ok/已挂 | 2026-10-06 03:14:29 | 连文件删 |
| 16 | `578f246d7bae` | carpt.net | The.Mandalorian.And.Grogu.2026.MULTi.COMPLET | site_hr/settled | 24.0/24.2 | ok/已挂 | 2026-10-06 08:17:04 | 连文件删 |
| 17 | `9bf86722fb9a` | carpt.net | Lucky Jo 1964 (BD25) | site_hr/settled | 24.0/0.7 | ok/已挂 | 2026-10-06 11:07:34 | 连文件删 |
| 18 | `e64607de3f8c` | carpt.net | 遗产.Urma.2019.1080p.NF.WEB-DL.x264.DDP5.1-PTe | site_hr/settled | 24.0/0.1 | ok/已挂 | 2026-10-06 11:07:34 | 连文件删 |
| 19 | `50871effa18e` | carpt.net | DYNASTY.WARRIORS.3.Complete.Edition.Remaster | site_hr/settled | 24.0/31.2 | ok/已挂 | 2026-10-07 00:41:36 | 连文件删 |
| 20 | `ef21df167027` | carpt.net | Un.plan.parfait.2012.1080p.JPN.Blu-ray.AVC.D | site_hr/settled | 24.0/31.7 | ok/已挂 | 2026-10-07 01:33:44 | 连文件删 |
| 21 | `85d914d742c8` | carpt.net | [第二次恋爱才完美 第二季].Love.is.Better.the.Second.Tim | site_hr/settled | 24.0/26.2 | ok/已挂 | 2026-10-07 02:02:04 | 连文件删 |
| 22 | `05e7ce58381a` | carpt.net | [兰香如故].Against.the.Current.2026.S01.Complete | site_hr/settled | 24.0/26.6 | ok/已挂 | 2026-10-07 03:39:02 | 连文件删 |
| 23 | `7a6f7680379c` | carpt.net | Terror.Train.1980.1080p.USA.Blu-ray.AVC.DTS- | site_hr/settled | 24.0/26.4 | ok/已挂 | 2026-10-07 07:12:59 | 连文件删 |
| 24 | `c46c75651f4c` | carpt.net | [国语].富都青年.Abang.Adik.2023.2160p.WEB-DL.H.265 | site_hr/settled | 24.0/26.4 | ok/已挂 | 2026-10-07 09:20:12 | 连文件删 |
| 25 | `e25b19a0032c` | carpt.net | 仙逆剧场版 弑仙之战.Renegade.Immortal.Movie.The.Great | site_hr/settled | 24.0/25.1 | ok/已挂 | 2026-10-07 10:23:14 | 连文件删 |
| 26 | `6de23234d4a0` | carpt.net | 性感野兽.Sexy.Beast.2000.GBR.BluRay.1080p.REMUX. | site_hr/settled | 24.0/28.0 | ok/已挂 | 2026-10-08 01:32:00 | 连文件删 |
| 27 | `9f1977dfab05` | carpt.net | 征途.Spark.of.the.Long.March.2026.S01.2160p.IQ | site_hr/settled | 24.0/28.4 | ok/已挂 | 2026-10-08 05:53:58 | 连文件删 |
| 28 | `162ac6e40a3e` | carpt.net | 一笑倾城.Your.Laugh.Is.Very.Alluring.2016.S01.21 | site_hr/settled | 24.0/25.3 | ok/已挂 | 2026-10-09 21:41:20 | 连文件删 |
| 29 | `22752f6166ca` | carpt.net | Against.the.Current.S01.2160p.TX.WEB-DL.AAC2 | site_hr/settled | 24.0/26.9 | ok/已挂 | 2026-10-09 21:58:29 | 连文件删 |
| 30 | `9fce7342979f` | carpt.net | Against.the.Current.S01.2160p.TX.WEB-DL.AAC2 | site_hr/settled | 24.0/26.7 | ok/已挂 | 2026-10-09 22:36:23 | 连文件删 |
| 31 | `c29c76b702c8` | carpt.net | 一笑倾城.Your.Laugh.Is.Very.Alluring.2016.S01.10 | site_hr/settled | 24.0/27.7 | ok/已挂 | 2026-10-09 23:16:27 | 连文件删 |
| 32 | `736c68f5edfb` | carpt.net | Man.of.Virtue.S01.1080p.NF.WEB-DL.AAC.2.0.H. | site_hr/settled | 24.0/143.7 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 33 | `96fcd9830b18` | carpt.net | Pink.Narcissus.1971.1080p.GBR.Blu-ray.AVC.LP | site_hr/settled | 24.0/181.5 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 34 | `6ecd3e52a9f6` | carpt.net | [狂野时代].Resurrection.2025.2160p.HQ.WEB-DL.HEV | site_hr/settled | 24.0/104.8 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 35 | `1c5dc2a1283b` | carpt.net | Totally.Fucked.Up.1993.COMPLETE.BLURAY-BAKED | site_hr/settled | 24.0/185.2 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 36 | `ed9ae44bb181` | carpt.net | Once.Upon.a.Time.Happily.Never.After.S01.216 | site_hr/settled | 24.0/174.5 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 37 | `880903a19f9e` | carpt.net | 神探飞机头3.Ace.Ventura.Pet.Detective.Jr.2009.108 | site_hr/settled | 24.0/52.7 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 38 | `2d99c424b361` | carpt.net | 希望与荣耀.Hope.And.Glory.1987.2160p.WEB-DL.H.265 | site_hr/settled | 24.0/102.5 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 39 | `f335f91f37d3` | carpt.net | 济公游记.Ji.Gong.You.Ji.1998.S01.WEB-DL.1080p.HE | site_hr/settled | 24.0/162.6 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 40 | `a999d643f7ae` | carpt.net | 查令十字街84号.84.Charing.Cross.Road.1987.2160p.WE | site_hr/settled | 24.0/102.0 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 41 | `aab3b5748e1a` | carpt.net | 佩古拉vs纳瓦罗.mp4 | site_hr/settled | 24.0/177.6 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 42 | `b446dbb6fd4f` | carpt.net | 猎艳狂魔.The.Monster.1994.2160p.WEB-DL.H.265.AAC | site_hr/settled | 24.0/149.4 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 43 | `69a3df09f7b3` | carpt.net | The.Muthers.1976.BluRay.1080p.x264.DTS-HD.MA | site_hr/settled | 24.0/134.8 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 44 | `ffc0fecc0ebb` | carpt.net | [一击3].One.Last.Shot.2026.2160p.iTunes.WEB-DL | site_hr/settled | 24.0/151.8 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 45 | `831a596ad070` | carpt.net | On.Swift.Horses.2024.MULTi.COMPLETE.BLURAY-Z | site_hr/settled | 24.0/172.9 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 46 | `a593329cf379` | carpt.net | Das.Boese.unter.der.Sonne.1982.REMASTERED.MU | site_hr/settled | 24.0/161.8 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 47 | `2692570cc96e` | carpt.net | 巧克力.Chocolate.1988.BluRay.1080p.x264.LPCM.2. | site_hr/settled | 24.0/156.2 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 48 | `41e4c33ad8b5` | carpt.net | The.Quiet.Ones.2014.BluRay.1080p.x264.DTS-HD | site_hr/settled | 24.0/159.9 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 49 | `c7f1f3e69168` | carpt.net | [三流之路].Fight.For.My.Way.2017.S01.Complete.NF | site_hr/settled | 24.0/138.7 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 50 | `55e2660cdf6d` | carpt.net | Thor.2011.UHD.BluRay.2160p.HEVC.TrueHD.Atmos | site_hr/settled | 24.0/135.4 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 51 | `cd7540810575` | carpt.net | Nate.and.Jeremiah.Save.My.House.S01.1080p.HM | site_hr/settled | 24.0/162.3 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 52 | `6f525e1cf664` | carpt.net | [VCB-Studio] Hibike! Euphonium 2 [Ma10p_1080 | site_hr/settled | 24.0/137.2 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 53 | `8de81de156e8` | carpt.net | 神秘窥视.The.Watchers.2024.BluRay.1080p.x265.10b | site_hr/settled | 24.0/134.1 | ok/已挂 | 2026-10-10 05:29:08 | 连文件删 |
| 54 | `51824fc0f44b` | carpt.net | [生命奇观2].Living.Spectacles.2026.S02.Complete. | site_hr/settled | 24.0/27.1 | ok/已挂 | 2026-10-10 10:04:27 | 连文件删 |
| 55 | `28a2a463cb4a` | duckboobee.org | The.Scandal.S01.2160p.NF.WEB-DL.DDP5.1.Atmos | unknown/pending | 24.0/79.8 | ok/已挂 | 2026-10-11 10:55:12 | 连文件删 |

### B · 台账 ok+文件还在 → **建议保留**（重挂能回魔力）

| # | infohash(前12) | 站点 | 标题 | H&R | 需/已挂 h | 台账状态 | 最后删种 | 文件 |
|---|---|---|---|---|---|---|---|---|
| 1 | `c40fd1542e03` | btschool.club | Scary.Movie.2026.BluRay.1080p.x264.TrueHD.7. | site_hr/settled | 20.0/31.7 | ok/已挂 | 2026-10-06 19:03:49 | 只摘种 |
| 2 | `e8c78c563f3a` | btschool.club | Das.Boese.unter.der.Sonne.1982.REMASTERED.MU | site_hr/settled | 20.0/43.9 | ok/已挂 | 2026-10-06 19:03:50 | 只摘种 |
| 3 | `0b297db390ce` | btschool.club | 法兰西之子.The.Son.Of.Français.1999.2160p.WEB-DL. | site_hr/settled | 20.0/42.0 | ok/已挂 | 2026-10-06 19:03:50 | 只摘种 |
| 4 | `1773eb972d05` | btschool.club | Pink.Narcissus.1971.1080p.GBR.Blu-ray.AVC.LP | site_hr/settled | 20.0/64.0 | ok/已挂 | 2026-10-06 19:03:50 | 只摘种 |
| 5 | `0b23a3471fec` | btschool.club | 猎艳狂魔.The.Monster.1994.2160p.WEB-DL.H.265.AAC | site_hr/settled | 20.0/48.2 | ok/已挂 | 2026-10-06 19:03:51 | 只摘种 |
| 6 | `cf68e5f2cb3f` | btschool.club | 异形终结.Screamers.1995.2160p.WEB-DL.H.265.AAC2. | site_hr/settled | 20.0/38.7 | ok/已挂 | 2026-10-06 19:03:51 | 只摘种 |
| 7 | `bf2dd1b6233c` | btschool.club | Nate.and.Jeremiah.Save.My.House.S01.1080p.HM | site_hr/settled | 20.0/44.7 | ok/已挂 | 2026-10-06 19:03:51 | 只摘种 |
| 8 | `c6fe06bb2166` | btschool.club | 蓝白红三部曲之红.Three.Colors-Red.1994.Criterion.Col | site_hr/settled | 20.0/31.3 | ok/已挂 | 2026-10-06 19:03:52 | 只摘种 |
| 9 | `6d775c43f3ad` | btschool.club | DORAEMON_CASTLEOFUNDERSEADEVIL | site_hr/settled | 20.0/23.1 | ok/已挂 | 2026-10-06 19:03:52 | 只摘种 |
| 10 | `1dcdff1ed55b` | btschool.club | 神秘窥视.The.Watchers.2024.BluRay.1080p.x265.10b | site_hr/settled | 20.0/47.7 | ok/已挂 | 2026-10-06 19:03:53 | 只摘种 |
| 11 | `8d108a9954a6` | btschool.club | 心动的信号.Heart.Signal.2026.S09.2160p.WEB-DL.60f | site_hr/settled | 20.0/41.9 | ok/已挂 | 2026-10-06 19:03:55 | 只摘种 |
| 12 | `c9dfbd1879b6` | btschool.club | 佩古拉vs纳瓦罗.mp4 | site_hr/settled | 20.0/60.1 | ok/已挂 | 2026-10-06 19:03:56 | 只摘种 |
| 13 | `1ca094e3a5d1` | btschool.club | 冬城猎凶.Cold.Hunt.2026.S01.1080p.WEB-DL.60fps.H | site_hr/settled | 20.0/42.5 | ok/已挂 | 2026-10-06 19:03:58 | 只摘种 |
| 14 | `b30d86bf5bc9` | btschool.club | Zero.Chill.S01.1080p.NF.WEB-DL.DDP5.1.x264-i | site_hr/settled | 20.0/34.9 | ok/已挂 | 2026-10-06 19:03:58 | 只摘种 |
| 15 | `cfc7bc6eef9b` | btschool.club | 别惹蚂蚁.The.Ant.Bully.2006.EUR.BluRay.1080p.x26 | site_hr/settled | 20.0/39.0 | ok/已挂 | 2026-10-06 19:14:24 | 只摘种 |
| 16 | `e7305cc1732f` | btschool.club | [一击3].One.Last.Shot.2026.2160p.iTunes.WEB-DL | site_hr/settled | 20.0/32.1 | ok/已挂 | 2026-10-06 19:14:24 | 只摘种 |
| 17 | `76cda4ce66e4` | btschool.club | MAO.S01.2026.1080p.Baha.WEB-DL.x264.AAC-ADWe | site_hr/settled | 20.0/42.2 | ok/已挂 | 2026-10-06 19:14:24 | 只摘种 |
| 18 | `5c3fb8daf120` | btschool.club | [VCB-Studio] Hibike! Euphonium 2 [Ma10p_1080 | site_hr/settled | 20.0/53.2 | ok/已挂 | 2026-10-06 19:14:24 | 只摘种 |
| 19 | `69eb2fd3f2ab` | btschool.club | Man.of.Virtue.S01.1080p.NF.WEB-DL.AAC.2.0.H. | site_hr/settled | 20.0/26.4 | ok/已挂 | 2026-10-06 19:14:24 | 只摘种 |
| 20 | `e248b7ccad24` | btschool.club | Toy.Story.4.2019.1080p.BluRay.Remux.AVC.DTS- | site_hr/settled | 20.0/51.8 | ok/已挂 | 2026-10-06 23:11:39 | 只摘种 |
| 21 | `f9bbee4607cb` | btschool.club | A.Piece.of.Your.Mind.S01.1080p.WEB-DL.AAC2.0 | site_hr/settled | 20.0/49.4 | ok/已挂 | 2026-10-06 23:11:39 | 只摘种 |
| 22 | `544e9f3ae419` | btschool.club | On.Swift.Horses.2024.MULTi.COMPLETE.BLURAY-Z | site_hr/settled | 20.0/56.7 | ok/已挂 | 2026-10-06 23:11:39 | 只摘种 |
| 23 | `290451b176f2` | btschool.club | O11CE.New.Generation.S01.2160p.DSNP.WEB-DL.D | site_hr/settled | 20.0/72.1 | ok/已挂 | 2026-10-06 23:11:39 | 只摘种 |
| 24 | `f1960acbfdc6` | btschool.club | The.Quiet.Ones.2014.BluRay.1080p.x264.DTS-HD | site_hr/settled | 20.0/40.6 | ok/已挂 | 2026-10-06 23:11:39 | 只摘种 |
| 25 | `d4c1ddbe50a7` | btschool.club | Thor.2011.UHD.BluRay.2160p.HEVC.TrueHD.Atmos | site_hr/settled | 20.0/46.7 | ok/已挂 | 2026-10-06 23:11:39 | 只摘种 |
| 26 | `5611c96f5dff` | btschool.club | Totally.Fucked.Up.1993.COMPLETE.BLURAY-BAKED | site_hr/settled | 20.0/67.4 | ok/已挂 | 2026-10-06 23:11:40 | 只摘种 |
| 27 | `8f220c3cf788` | btschool.club | 济公游记.Ji.Gong.You.Ji.1998.S01.WEB-DL.1080p.HE | site_hr/settled | 20.0/51.1 | ok/已挂 | 2026-10-06 23:11:40 | 只摘种 |
| 28 | `c8ee61bd1366` | btschool.club | [宿敌恋人].Enemies.with.Benefits.2026.S01.Comple | site_hr/settled | 20.0/61.5 | ok/已挂 | 2026-10-06 23:11:41 | 只摘种 |
| 29 | `86d29ed62c5d` | carpt.net | 大地与阴影.Land.And.Shade.2015.1080p.WEB-DL.H.264 | site_hr/settled | 24.0/26.6 | ok/已挂 | 2026-10-11 03:14:58 | 只摘种 |
| 30 | `753544b4e9d3` | cspt.top | Renegade.Immortal.Battle.of.the.Immortal.Sla | unknown/pending | 24.0/200.0 | ok/已挂 | 2026-10-11 22:38:00 | 只摘种 |
| 31 | `92d65fcb43ef` | duckboobee.org | A.Gentlemans.Dignity.S01.1080p.AMZN.WEB-DL.D | unknown/pending | 24.0/13.9 | ok/已挂 | 2026-10-11 10:55:12 | 只摘种 |
| 32 | `342acea9a373` | duckboobee.org | Thor.2011.UHD.BluRay.2160p.HEVC.TrueHD.Atmos | unknown/pending | 24.0/55.4 | ok/已挂 | 2026-10-11 10:55:12 | 只摘种 |
| 33 | `6a7f19144f6b` | soulvoice.club | UNABOMBER.2026.2160p.NF.WEB-DL.H.265.DDP5.1. | unknown/pending | 24.0/195.5 | ok/已挂 | 2026-10-14 10:22:04 | 只摘种 |
| 34 | `61bf0154ac5f` | soulvoice.club | UNABOMBER.2026.2160p.NF.WEB-DL.H.265.DV.DDP5 | unknown/pending | 24.0/194.8 | ok/已挂 | 2026-10-14 10:22:04 | 只摘种 |
| 35 | `4c1262ff1d77` | soulvoice.club | [东方卫视4K超高清频道 朤月东方·中秋话月夜].SHANGHAI-4K.The.Mid | unknown/pending | 24.0/194.5 | ok/已挂 | 2026-10-14 10:22:04 | 只摘种 |

### C · 无台账行 → **只改口径即可**，无数据可清

| # | infohash(前12) | 站点 | 标题 | H&R | 需/已挂 h | 台账状态 | 最后删种 | 文件 |
|---|---|---|---|---|---|---|---|---|
| 1 | `e1177404d365` | btschool.club | 周杰伦 - 太阳之子 (大陆平装版) (2026) [WAV] | site_hr/settled | 20.0/414.5 | 无行 | 2026-10-06 19:35:18 | 只摘种 |
| 2 | `0ed653dea0b1` | carpt.net | 遮天.Shrouding.The.Heavens.S01.2023.2160p.WEB- | site_hr/settled | 24.0/24.8 | 无行 | 2026-10-06 08:17:04 | 连文件删 |
| 3 | `c9ab73804f1b` | carpt.net | 逆天邪神.Against.the.Gods.S01.2023.2160p.WEB-DL. | site_hr/settled | 24.0/24.9 | 无行 | 2026-10-06 08:17:04 | 连文件删 |
| 4 | `a30cff3b59f3` | carpt.net | [征途].Zheng.Tu.2026.S01.Complete.1080p.WEB-DL | site_hr/settled | 24.0/25.3 | 无行 | 2026-10-06 08:17:04 | 连文件删 |
| 5 | `92ab1cb9d3c1` | carpt.net | Dongbeis.Back.S01.2160p.iQIYI.WEB-DL.AAC2.0. | site_hr/settled | 24.0/25.2 | 无行 | 2026-10-06 08:17:04 | 连文件删 |
| 6 | `6c86d824a1f2` | carpt.net | 东大高武学院.Oriental.Martial.Academy.S01.2026.216 | site_hr/settled | 24.0/25.2 | 无行 | 2026-10-06 08:17:04 | 连文件删 |
| 7 | `0a5f472a5ea6` | carpt.net | Chainsmoker.Cat.S01.1080p.NF.WEB-DL.AAC2.0.H | site_hr/settled | 24.0/25.2 | 无行 | 2026-10-06 12:13:14 | 连文件删 |
| 8 | `a2ab27e3a5bf` | carpt.net | Qie.Ben.Cao.Jie.S01.2160p.TX.WEB-DL.AAC2.0.H | site_hr/settled | 24.0/24.2 | 无行 | 2026-10-06 12:13:14 | 连文件删 |
| 9 | `efeb24c7f83b` | carpt.net | Irreplaceable.S01.2026.2160p.YK.WEB-DL.H.265 | site_hr/settled | 24.0/25.2 | 无行 | 2026-10-06 12:13:14 | 连文件删 |
| 10 | `329182f0c0f8` | carpt.net | 东大高武学院.Oriental.Martial.Academy.S01.2026.216 | site_hr/settled | 24.0/24.1 | 无行 | 2026-10-06 12:13:14 | 连文件删 |
| 11 | `4f1595229928` | carpt.net | [征途].Zheng.Tu.2026.S01.Complete.1080p.WEB-DL | site_hr/settled | 24.0/25.6 | 无行 | 2026-10-06 12:13:14 | 连文件删 |
| 12 | `205ddd93d275` | carpt.net | You.and.I.Are.Polar.Opposites.S01.2026.1080p | site_hr/settled | 24.0/24.9 | 无行 | 2026-10-06 12:13:14 | 连文件删 |
| 13 | `8820251f7fbf` | carpt.net | [为爱正名].Stand.up.for.Love.2026.S01.Complete.2 | site_hr/settled | 24.0/25.3 | 无行 | 2026-10-06 12:13:14 | 连文件删 |
| 14 | `37344a10860d` | carpt.net | BanG.Dream!.YUME∞MITA.S01.2026.1080p.Baha.WE | site_hr/settled | 24.0/25.5 | 无行 | 2026-10-06 12:13:14 | 连文件删 |
| 15 | `62bc10d84346` | carpt.net | [征途].Zheng.Tu.2026.S01.Complete.1080p.WEB-DL | site_hr/settled | 24.0/25.6 | 无行 | 2026-10-06 12:13:14 | 连文件删 |
| 16 | `009b30a6b07b` | carpt.net | [一瓯春].Spring.of.The.Blade.2026.S01.Complete. | site_hr/settled | 24.0/25.2 | 无行 | 2026-10-06 12:13:14 | 连文件删 |
| 17 | `35293394a626` | carpt.net | Dongbeis.Back.S01.2160p.iQIYI.WEB-DL.AAC2.0. | site_hr/settled | 24.0/25.3 | 无行 | 2026-10-06 12:13:14 | 连文件删 |
| 18 | `ca910ebf47c5` | carpt.net | [一瓯春].Spring.of.The.Blade.2026.S01.Complete. | site_hr/settled | 24.0/25.0 | 无行 | 2026-10-06 12:13:14 | 连文件删 |
| 19 | `e433984e53d7` | carpt.net | The.Exiled.Heavy.Knight.Knows.How.to.Game.th | site_hr/settled | 24.0/24.6 | 无行 | 2026-10-06 12:13:14 | 连文件删 |
| 20 | `204a9ee622dd` | carpt.net | [余红旧事].The.Old.Story.of.Yu.Hong.2026.S01.Com | site_hr/settled | 24.0/25.2 | 无行 | 2026-10-06 12:13:14 | 连文件删 |
| 21 | `45570801fa26` | carpt.net | [我不是大师].A.Prophet.2026.S01.Complete.1080p.IQ | site_hr/settled | 24.0/26.2 | 无行 | 2026-10-06 15:11:01 | 连文件删 |
| 22 | `488d0e8299d1` | carpt.net | Fired.Up.S01.1080p.HMAX.WEB-DL.DDP5.1.H.265- | site_hr/settled | 24.0/26.7 | 无行 | 2026-10-06 15:11:01 | 连文件删 |
| 23 | `9dcd8cdc17b0` | carpt.net | 兰香如故.Against.the.Current.2026.S01.1080p.WEB- | site_hr/settled | 24.0/30.2 | 无行 | 2026-10-07 00:07:04 | 连文件删 |
| 24 | `7d13dbba69f4` | carpt.net | 李熊猫.Raised.by.Demons：Panda.Li.S01.2026.2160p | site_hr/settled | 24.0/29.3 | 无行 | 2026-10-07 00:07:04 | 连文件删 |
| 25 | `e67a52040826` | carpt.net | Zheng.Tu.S01.1080p.TX.WEB-DL.AAC2.0.H.264-MW | site_hr/settled | 24.0/29.7 | 无行 | 2026-10-07 00:07:04 | 连文件删 |
| 26 | `1a56a9ad0d91` | carpt.net | [一瓯春].Spring.of.The.Blade.2026.S01.Complete. | site_hr/settled | 24.0/30.0 | 无行 | 2026-10-07 00:07:04 | 连文件删 |
| 27 | `1321c6350264` | carpt.net | [炼气十万年].One.Hundred.Thousand.Years.of.Qi.Ref | site_hr/settled | 24.0/29.9 | 无行 | 2026-10-07 00:07:04 | 连文件删 |
| 28 | `43a5528b598f` | carpt.net | 孩童游戏.Child's.Play.1972.1080p.WEB-DL.H.264.AA | site_hr/settled | 24.0/31.5 | 无行 | 2026-10-07 00:07:04 | 连文件删 |
| 29 | `e6a0ca33d72b` | carpt.net | [希望生长的地方].Where.Hope.Grows.2015.USA.BluRay.1 | site_hr/settled | 24.0/27.9 | 无行 | 2026-10-07 00:07:04 | 连文件删 |
| 30 | `9db8a9061338` | carpt.net | Against.the.Current.S01.1080p.TX.WEB-DL.AAC2 | site_hr/settled | 24.0/28.7 | 无行 | 2026-10-07 00:07:04 | 连文件删 |
| 31 | `2dd1e3227c5b` | carpt.net | Qie.Ben.Cao.Jie.S01.2160p.TX.WEB-DL.AAC2.0.H | site_hr/settled | 24.0/32.4 | 无行 | 2026-10-07 00:07:04 | 连文件删 |
| 32 | `d1933e6aa2a8` | carpt.net | 风华令.Love.Legend.2026.S01.2160p.WEB-DL.H265.A | site_hr/settled | 24.0/26.5 | 无行 | 2026-10-07 00:07:04 | 连文件删 |
| 33 | `aa0907a4d2b2` | carpt.net | 择日飞升.A.Good.Day.to.Ascend.S01.2026.2160p.WEB | site_hr/settled | 24.0/26.6 | 无行 | 2026-10-07 02:45:54 | 连文件删 |
| 34 | `e4aea6d0c3ce` | carpt.net | CCTV-5+.2026-Asian.Games-Women's-Men's.Beach | site_hr/settled | 24.0/26.5 | 无行 | 2026-10-07 02:45:54 | 连文件删 |
| 35 | `f5433cc73d5d` | carpt.net | [好，我们离婚吧].OK.Let's.Get.Divorced.2026.S01.Com | site_hr/settled | 24.0/26.9 | 无行 | 2026-10-07 07:58:58 | 连文件删 |
| 36 | `0fad2d25e6c6` | duckboobee.org | [总台8K超高清频道 2026年中央广播电视总台中秋晚会].CCTV-8K.CMG.Th | unknown/pending | 24.0/149.8 | 无行 | 2026-10-11 10:55:12 | 只摘种 |

## 明确不动的

- `hr_bills.json` 126 条（118 settled + 8 pending）：**全部保留**。settled 是 H&R 已结清的**证据**；8 条 pending 在无 H&R 的站（duckboobee/soulvoice/cspt，rule=unknown），下一轮对账会自己结清/作废。

- qB 里的种、下载器、魔力、删除闸门：**本清单不触碰**。

- 那 2 个真正在下载器里的未完成种（与本次无关）：不动。


## 建议的落地顺序（等你拍板）

1. **口径修正（代码 1 处，不碰数据）**：`features/reportview.py` 静默视图 summary 的「未下完」= **在下载器内且未完成**；改完「未下完」128 → 2。加断言、跑 preflight、构建、部署。

2. **A 组 55 条销账（可选）**：先备份 `mf_reseed`（`pg_dump -t`），再按 hash 批量置失效（保留历史）或删行；干跑先出 count。

3. **B 组 35 条**：不动；如你要，我可以另出一份「重挂候选」清单（文件在、可回魔力）。


## 回滚

- 口径修正：`git revert` 单次提交即回滚。
- 销账：执行前 `pg_dump -t plugin_magicflow_8512da16.mf_reseed` 到文件，回滚即恢复该表。
