
# 名称解析最终方案（MediaCMN）

## 背景

后端元数据丰富化入口在 [metadata_enricher.py](file:///home/meal/mediacmn/media-server/services/media/metadata_enricher.py) 中，对每个 `FileAsset.full_path` 进行名称解析，提取：

- `title`（用于检索元数据）
- `type`（movie / episode）
- `season` / `episode`（剧集详情定位）
- `year` / `country`（用于提高匹配准确率）

直接将完整路径交给开源 guessit 解析时，会被“路径分段、中文分类目录、网盘/存储前缀、范围目录（101~200）、第X话”等噪声干扰，导致：

- 把“第149话”当作 `alternative_title` 或 `episode_title`，甚至误判为 `movie`
- 把路径前缀 `dav.302.133quark302` 等拆进 season/episode/title
- 对动画/综艺这类“无 SxxExx 标准命名”的剧集识别不稳定

## 结论：采用“高质量预处理 + GuessIt 约束性调用”，不 fork GuessIt

最终选择方案 2 的强化版：

- 不对 GuessIt 源码做二次开发（减少维护成本，避免 LGPL 组件改造带来的合规/升级复杂度）
- 在进入 GuessIt 前，对“输入字符串”做路径级预处理与提示抽取
- 使用 GuessIt 的配置合并能力（`-c/--config` 对应 API 的 `config`），并强制关闭用户家目录配置（避免不同机器结果不一致）

对应实现：

- 解析器实现：[media_parser.py](file:///home/meal/mediacmn/media-server/utils/media_parser.py)
- 元数据入口接入：[metadata_enricher.py](file:///home/meal/mediacmn/media-server/services/media/metadata_enricher.py)
- GuessIt 本项目配置：[options.json](file:///home/meal/mediacmn/media-server/utils/options.json)

## 设计目标

- 高准确率：优先保证 `title/season/episode/type` 稳定正确
- 高效率：纯字符串处理 + 单次 guessit 调用，避免多轮试探
- 可扩展：后续通过“忽略目录名集合/技术词集合/规则正则”快速迭代
- 可复现：关闭用户配置、固定本项目 config 文件

## 解析流程（核心策略）

### 1）是否强制按剧集解析（strict_episode）

规则由 `MediaParser.should_force_episode()` 判定：

- 路径中包含 `SxxExx` / `E123`
- 文件名包含中文模式 `第149话/第12集`
- 路径分段包含 `动画/综艺/剧集/电视剧`

一旦命中，解析器会在调用 GuessIt 时强制 `type=episode`，并启用 `episode_prefer_number`。

### 2）标题提示（expected_title）

从“路径分段”倒序回溯，跳过噪声目录（如 `dav/302/101~200/S01/第1季/1080p` 等），选取最可能的标题段作为 `expected_title`。

这样可以把 GuessIt 的标题判定从“猜”变成“在提示范围内匹配”，显著降低 title 误判。

### 3）预处理：把非标准中文集序转写为 E/S 标记

将：

- `第149话` / `第149集` → `E149`
- `第1季` → `S01`

并清理常见噪声：`101~200`、`(高清SDR)`、`2Audios` 等。

### 4）GuessIt 调用方式（保证一致性）

固定参数：

- `no_user_config=True`：不读取 `~/.config/guessit`，避免环境差异
- `name_only=True`：把 `/` 和 `\` 当作普通分隔符，降低“路径结构误导”
- `single_value=True`：避免 season/episode 被解析成 list 影响下游
- `config=[<项目内 options.json>]`：加载本项目特化配置

并按需追加：

- `type=episode`（当 strict_episode 为 True）
- `expected_title=[<title_hint>]`（当可提取到 title_hint）

## 与元数据丰富化的接口契约

[metadata_enricher.py](file:///home/meal/mediacmn/media-server/services/media/metadata_enricher.py) 只依赖以下字段：

- `title: str | None`
- `type: "movie" | "episode" | None`
- `season: int | None`
- `episode: int | None`
- `year: int | None`
- `country: Any | None`

解析器保证：

- 当 `strict_episode=True`：`type` 必为 `episode`，并尽最大努力补齐 `season/episode`（缺省 season=1）
- 当存在可靠 `title_hint`：优先返回 `title_hint`，避免解析到技术词当 title

## 典型样例（预期结果）

### 综艺标准命名

输入：

`/dav/302/133quark302/综艺/现在就出发/S01/2023.S01E10.Part2.1080p.WEB-DL.HEVC.DDP.2Audios.mp4`

预期：

- `title=现在就出发`
- `type=episode`
- `season=1`
- `episode=10`
- `part=2`

### 动画“第149话”命名

输入：

`dav.302.133quark302.动画.完美世界.101~200.完美世界 第149话 1080P(高清SDR)_Tacit0924.mp4`

预期：

- `title=完美世界`
- `type=episode`
- `season=1`
- `episode=149`

## 测试

新增 pytest 用例覆盖上述路径（含参数化样例）：

- [test_media_parser.py](file:///home/meal/mediacmn/media-server/tests/test_media_parser.py)

同时为避免 vendored GuessIt 的测试与 site-packages 的 GuessIt 测试发生模块冲突，pytest 配置忽略：

- `media-server/utils/guessit`（只作为源码参考/可能的后续二开基础，不参与本项目测试收集）

配置文件：

- [pytest.ini](file:///home/meal/mediacmn/media-server/pytest.ini)

## 失败案例分析与优化方向

以下分析基于最新一次评估输出的失败样本文件：[media_parser_eval_results.jsonl](file:///home/meal/mediacmn/media-server/tests/data/media_parser_eval_results.jsonl)。样例中 `expected` 为人工标注的“理想解析结果”，`got` 为当前 `MediaParser.parse()` 的实际输出，`failed_fields` 列出不一致的字段。

需要注意：

- 评估脚本中 `expected.type` 使用 tv/anime/variety 来标识内容类别，而解析器内部只区分 movie/episode，因此所有条目的 `type` 在评估时都会被判为失败。这是评估约定与解析器契约不一致导致的统计问题，本节更关注 `title`/`season`/`episode`/`year` 等实际影响元数据抓取的字段。

### 一、中文剧集目录 + 年份括号（title/year 差异）

典型失败样例：

- `/dav/302/133quark302/电视剧/华语/万灵渡 (2025)/S01E08.mp4`
  - expected：`title=万灵渡`, `year=2025`
  - got：`title=万灵渡  2025 `, `year=None`
- `/dav/302/133quark302/电视剧/华语/天地剑心(2025)/03 4K.mkv`
  - expected：`title=天地剑心`, `year=2025`
  - got：`title=天地剑心 2025 `, `year=None`
- `/dav/302/133quark302/电视剧/华语/少年白马醉春风（2024）/07 4K.mkv`
  - expected：`title=少年白马醉春风`, `year=2024`
  - got：`title=少年白马醉春风（2024）`, `year=None`

问题归纳：

- 中文目录通常采用 `剧名 (年份)`、`剧名（年份）` 形式，当前 `title_hint` 直接取整段目录名，未剥离年份括号。
- `year` 只从 GuessIt 结果中读取，而 GuessIt 在这种场景下有时不会单独拆出年份字段，导致 `year=None`。

优化方案：

1. 在 `_extract_title_hint()` 中，对候选目录名做一次“剧名 + 年份”拆分：
   - 正则匹配 `(?P<title>[\u4e00-\u9fffA-Za-z0-9··\s]+)[\(（](?P<year>(19|20)\d{2})[\)）]`
   - 如命中：
     - `title_hint` 使用捕获的 `title`
     - 额外返回 `year_hint`（或在实例中缓存一个 `_year_hint_from_path`）
2. 在 `parse()` 逻辑中：
   - 如果 GuessIt 未给出 `year`，而路径解析出了 `year_hint`，则将 `info["year"] = year_hint`
   - 同时确保 `title` 使用不含年份的纯剧名，避免“万灵渡 2025”参与后续 TMDB/豆瓣检索。

预期收益：

- 修复所有“目录名带年份括号”的 year 缺失问题，同时让 title 更干净，有利于外部元数据匹配。

### 二、绝对集序目录（斗罗大陆 1-255【4K】）导致标题偏移

典型失败样例：

- `/dav/302/133quark302/动画/斗罗大陆1【4K】全253集/1-255【4K】/斗罗大陆S01E141.mp4`
  - expected：`title=斗罗大陆`, `season=1`, `episode=141`
  - got：`title=1 255【4K】`, `episode_title=斗罗大陆S01E141`

问题归纳：

- 路径中存在类似 `1-255【4K】` 的“绝对集数范围 + 清晰度”目录，当前 `_extract_title_hint()` 在倒序回溯时将其当作潜在标题。
- `clean_name` 仍保留了 `斗罗大陆S01E141`，但因为 `title_hint` 被错误选择为 `1-255【4K】`，GuessIt 最终将范围目录当成标题。

优化方案：

1. 扩展 `_is_ignorable_segment()`：
   - 已处理 `\d+~\d+`，补充对 `\d+-\d+`、`1-255【4K】` 这类模式的识别：
     - 忽略形如 `\d+[\-~]\d+` 的范围片段
     - 忽略形如 `\d+[\-~]\d+.*?【\d+p?】` 的组合片段
2. 在 `_extract_title_hint()` 中：
   - 对包含大量数字且缺乏中文词汇的目录，优先判定为“技术/范围目录”，直接跳过
   - 继续向上回溯到 `斗罗大陆1【4K】全253集`，再依据“最长中文片段”规则拆出剧名 `斗罗大陆`

预期收益：

- 避免使用“集数范围目录”作为标题提示，确保系列名称来自更上层的主目录，从而修复 `title` 错误。

### 三、系列 + 子标题（唐朝诡事录之西行）被截断为父标题

典型失败样例：

- `/dav/302/133quark302/电视剧/华语/唐朝诡事录/唐朝诡事录之西行S02/4K/22 4K.mkv`
  - expected：`title=唐朝诡事录之西行`, `season=2`
  - got：`title=4K`, `season=1`

同类失败样例：

- `/dav/302/133quark302/电视剧/华语/大生意人（2025）/4K SDR/03 4K.mkv`
  - expected：`title=大生意人`, `year=2025`
  - got：`title=4K SDR`, `year=2025`
- `/dav/302/133quark302/电视剧/华语/入青云[60帧率版本][全36集][国语配音+中文字幕].Love.in.the.Clouds.S01.2025.2160p.WEB-DL.H265.60fps(1).AAC-BlackTV/Love.in.the.Clouds.S01E03.2025.2160p.WEB-DL.H265.60fps.AAC-BlackTV.mkv`
  - expected：`title=入青云`, `year=2025`, `season=1`, `episode=3`
  - got：`title=帧率版本`, `year=2025`, `season=1`, `episode=3`
- `/dav/302/133quark302/电视剧/华语/掌心.2160p.60fps.电影港 地址发布页 www.dygang.me 收藏不迷路/掌心.S01E01.2160p.60fps.WEB-DL.H265.AAC.mkv`
  - expected：`title=掌心`, `season=1`, `episode=1`
  - got：`title=地址发布页`, `season=1`, `episode=1`

问题归纳：

- `_extract_title_hint()` 倒序回溯目录时，如果遇到 `4K` / `4K SDR` 这类“纯技术词目录”，会被误选为标题提示，导致 title 被质量目录污染。
- 对于 `剧名[标签1][标签2]...` 这类目录，当前按“最长中文片段”抽取会把 `帧率版本/国语配音` 等标签当成 title_hint。
- 对于 `剧名.2160p.60fps...站点宣传词` 这类目录，当前按“最长中文片段”抽取会把 `地址发布页/收藏不迷路` 等宣传词当成 title_hint。

优化方案：

1. 在 `_extract_title_hint()` 里增强对子目录的处理：
   - 对包含“之”字的中文段（如 `唐朝诡事录之西行S02`），优先提取“之”后整段作为更精细的标题候选。
   - 清理 `Sxx` 等季标记后，保留 `唐朝诡事录之西行` 作为候选 title_hint。
2. 扩展 `_is_ignorable_segment()` 的“技术目录过滤”能力：
   - 对目录分词后（如 `4K SDR` → `4k` + `sdr`），若全部命中技术词集合（分辨率/编码/音频/动态范围等），直接忽略该目录，继续向上回溯到真正的剧名目录（如 `大生意人（2025）`）。
3. 在 `_extract_title_hint()` 中增加“方括号/书名号标签剥离”规则：
   - 如果目录名包含 `[` 或 `【`，优先取第一个括号前的头部片段作为剧名候选（如 `入青云[60帧率版本]...` → `入青云`）。
4. 在 `_extract_title_hint()` 中增加“点分隔技术段剥离”规则：
   - 如果目录名包含 `.` 且命中 `2160p/1080p/fps` 等技术标记或宣传词，优先取第一个点之前的头部片段作为剧名候选（如 `掌心.2160p...地址发布页...` → `掌心`）。

预期收益：

- 修复“系列 + 副标题”这类结构中子标题丢失的问题，使 `唐朝诡事录之西行`、`汪汪队之小砾与工程家族` 等可以被稳定识别。

### 四、子系列与主系列的归一策略（汪汪队立大功）

典型失败样例：

- `/dav/302/133quark302/电视剧/华语/汪汪队1-10季/.../汪汪队立大功第十季 第13集.mp4`
  - expected：`title=汪汪队立大功`
  - got：`title=第10季 26集`, `episode_title=汪汪队立大功第十季`
- `/dav/302/133quark302/电视剧/华语/汪汪队1-10季/4. 国语小砾与工程家族.../汪汪队之小砾与工程家族 第17集 ...mp4`
  - expected：`title=汪汪队立大功`
  - got：`title=4  国语小砾与工程家族 26集 1080P 配套音频`, `episode_title=汪汪队之小砾与工程家族`

问题归纳：

- 手工标注选择了“IP 级主标题”（汪汪队立大功）作为归一化 title，而当前解析器倾向从“最近的父目录/文件名”中提取更细的中文标题（如 `汪汪队之小砾与工程家族`）。
- 在绝大多数元数据抓取场景中，使用“主标题”更利于对齐 TMDB/豆瓣条目，但对子系列信息的保留也有价值。

优化方案：

1. 引入“主标题归一规则”（可配置）：
   - 在解析阶段增加一个“同义/子系列到主系列”的映射表，例如：
     - `汪汪队之小砾与工程家族` → `汪汪队立大功`
   - 解析器内部：
     - `info["title"]` 使用归一后的主标题
     - 将原始细分标题塞入 `info["episode_title"]` 或 `aliases` 中，供上层展示或调试
2. 由于此类归一化需求具有一定业务定制性，推荐以 JSON/配置文件形式维护，而不是写死在代码里。

预期收益：

- 让评估中的 `title` 字段能够与人工标注达成一致，同时保持子系列信息不丢失，兼顾检索与展示。

### 五、year/season 的边界问题（EP07.2025 等）

典型失败样例：

- `/dav/302/133quark302/电视剧/华语/似锦.2025.EP01-40.4K.../Sijin.2025.EP07.4K...mkv`
  - expected：`year=2025`, `season=1`
  - got：`year=2025`, `season=2025`

问题归纳：

- GuessIt 在遇到 `2025.EP07` 时，可能将年份错误地映射为 season；当前解析器没有对“明显不合理的 season 数值”做保护。

优化方案：

1. 在 `parse()` 后处理阶段增加 season 合法性检查：
   - 若 `season >= 1900` 且 `year` 存在，则认为 season 被年份污染：
     - 优先使用路径级 season_hint（如从 `S01`、`第1季` 等提取）
     - 若无可用 season_hint，则降级为 `season=1`
2. 针对 year：
   - 保持 `year` 为 4 位数字且在合理年代区间内（已有 `_guessit_options` 配合 GuessIt 完成大部分工作）

预期收益：

- 修正因年份误填入 season 造成的季号错误，提升 `season` 字段的可靠性。

### 六、评估与解析器契约的对齐建议

- 评估数据集中的 `type` 字段采用 tv/anime/variety 的细粒度类别，而解析器设计只关心 movie/episode：
  - 建议在评估脚本中，将 tv/anime/variety 统一映射为 episode 再参与 `type` 比较，避免统计上“必然失败”。
  - 或者在 future 版本中新增一个 `media_kind` 字段（tv/anime/variety/movie），由上层根据路径/存储来源推导，而保持 GuessIt 输出的 `type` 不变。

总结：

- 以上优化大部分可以通过增强 `_extract_title_hint()`、`_is_ignorable_segment()` 与 `parse()` 的事后修正逻辑实现，保持对 GuessIt 的单次调用模型不变。
- 实施后应重新运行评估脚本，重点关注 `title/season/year` 的字段准确率变化，以及 `media_parser_eval_results.jsonl` 中失败样本数量的变化趋势。
