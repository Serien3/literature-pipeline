# Literature Pipeline v1 MVP 规格

## 1. 文档定位

本文定义 Literature Pipeline 当前阶段 v1 MVP 的产品意图、系统边界、输入输出、元数据格式、同步语义和验收标准，供后续详细设计与实现使用。

本文是当前阶段的权威规格。若本文与仓库中的 `SYSTEM_SPEC.md`、`README.md`、既有代码或测试冲突，以本文为准。既有实现只代表历史现状，不构成必须保留的兼容约束。

本文使用以下规范词：

- **必须**：实现不可偏离的要求。
- **不得**：明确禁止的行为。
- **可以**：不改变产品语义的可选实现。

## 2. 产品意图

用户使用 Zotero Connector 从论文网页采集书目信息，但不把 Zotero 作为日常维护论文数据库的工具。用户实际维护的是自己的 Obsidian 论文库，其中每篇论文对应一个文件夹，文件夹中的 `meta.md` 保存该论文的元信息。

Literature Pipeline 只负责完成一次性、幂等的元数据入库，并为 Zotero 已保存在本机的 PDF 建立零复制入口：

```text
论文网页
   ↓ Zotero Connector
Zotero 个人库中的指定 Collection
   ↓ Literature Pipeline（只读 Zotero）
<vault>/<readable-title> [<zotero-item-key>]/{zotero-item.json, meta.md, PDF symlinks}
   ↓
用户在本地 Obsidian 论文库中自行维护
```

本产品不是 Zotero 的替代客户端，也不是双向同步器、PDF 内容管理器或论文处理流水线。

## 3. v1 MVP 的唯一职责

系统必须：

1. 从 Zotero Local API 读取个人库中一个指定 Collection 的顶层条目。
2. 排除 attachment、note 和 annotation 等非顶层书目记录。
3. 识别 Collection 中尚未进入本地论文库的条目。
4. 为每个新条目建立独立文件夹。
5. 将 Zotero API 返回的完整 `data` 对象原样保存在 `zotero-item.json`。
6. 将该对象生成适合 Obsidian 浏览的 `meta.md`；只对 `creators` 和 `tags` 作本规格明确规定的最小投影。
7. 在重复运行时不重复创建同一 Zotero 条目，也不修改已入库的两个元数据文件。
8. 单篇失败时报告错误，并继续处理其他条目；下次运行可以重新尝试尚未成功入库的条目。
9. 读取顶层条目的 PDF child attachments，并为 Zotero 本机文件创建零复制符号链接。
10. 提供显式、幂等的方式，为既有论文补建或修复由本系统管理的 PDF 链接。

除上述职责外，不应为“以后可能需要”预先引入业务能力。

## 4. 明确不属于 v1 的范围

v1 不实现、也不得隐式承担以下职责：

- 下载、复制、选择“主 PDF”、校验内容、冻结或修改 Zotero PDF。
- 删除因 Zotero 附件变化而失效的链接，或管理 `full.md`、图片、阅读笔记等论文材料。
- 调用 MinerU 或任何 PDF 转换服务。
- 自动生成论文精读笔记。
- DOI、arXiv ID 或标题的重复论文检测与合并。
- Zotero 与 Obsidian 的双向同步。
- 用 Zotero 后续内容覆盖或刷新已经入库的 `meta.md`。
- 将本地修改写回 Zotero。
- 对条目实施状态机、任务队列、失败重试状态或版本迁移流程。
- 因条目移出 Collection、在 Zotero 中被删除或修改而删除本地文件。
- 管理用户的阅读状态、主题、项目、个人标签或其他研究工作流字段。
- 规定或管理用户以后放入论文文件夹的其他文件。
- 多 Collection 聚合、子 Collection 递归、团队库或云端 Zotero API。
- 迁移当前旧实现已经产生的 vault、SQLite 状态或旧版 `meta.md`。

PDF 转换和论文精读等能力可以作为相互独立、由用户明确调用的工具存在，但 Literature Pipeline 不得调用它们、跟踪它们或在 `meta.md` 中记录它们的状态。

## 5. 系统边界与运行环境

### 5.1 Zotero 边界

- v1 读取 Zotero 个人库中的一个指定 Collection。
- v1 只处理该 Collection 的直接成员，不递归处理子 Collection。
- v1 只使用 Zotero Local API，不直接读取 Zotero SQLite 数据库。
- v1 对 Zotero 只读，不申请或使用写权限。
- PDF 路径只通过 Local API 的 attachment child endpoint 和 `/file/view/url` 获取；不得猜测 data directory，也不得读取 Zotero SQLite。
- Zotero API 地址必须指向本机回环地址，不得接受远程主机或在 URL 中携带凭据。
- Zotero Connector 如何从网页提取数据属于 Zotero 的职责，不属于本系统。

### 5.2 Obsidian 边界

- 本地论文库可以是一个已有的 Obsidian vault；Pipeline 不拥有整个 vault。
- Pipeline 只在 vault 根目录下创建新论文文件夹及其中的两个元数据文件和 PDF 符号链接。
- Pipeline 不得覆盖 vault 中已有的首页、Bases、插件配置、模板或其他用户文件。
- Obsidian 只是用户浏览和维护 Markdown 的界面，Pipeline 不依赖 Obsidian 进程运行。

### 5.3 平台

目标生产环境是 Zotero 所在的同一台 Windows 电脑。其他平台可以用于开发和自动测试，但不构成 v1 的生产兼容承诺。

## 6. 本地目录契约

每篇论文的文件夹直接位于 vault 根目录。新条目的规范目录使用可读标题并保留 Zotero item key：

```text
<vault>/
└── Example Paper [ABCD1234]/
    ├── zotero-item.json
    ├── meta.md
    └── Original Filename [ZXCV5678].pdf -> <Zotero managed PDF>
```

其中 `ABCD1234` 是 Zotero 顶层条目 `data.key` 的原值。可读标题按以下确定性规则生成：

1. 优先使用非空字符串 `shortTitle`，否则使用非空字符串 `title`；两者均缺失或为空时，目录名退回纯 item key。
2. 字段存在但不是字符串时，该条目失败，不猜测或强制转换。
3. 保留 Unicode；不转拼音、不生成 ASCII slug，也不加入作者、年份或期刊。
4. ASCII 控制字符及 Windows 禁止字符 `< > : " / \ | ? *` 的连续片段替换为 ` - `，连续空白合并为一个空格，并清除首尾空格、句点和连字符。
5. 清理后的可读标题最多保留前 100 个 Unicode 字符，截断后再次清理尾部；若结果为空则退回纯 item key。
6. 有可读标题时，最终格式固定为 `<可读标题> [<item-key>]`。key 后缀保证同名或截断后同名条目仍有不同目录。

目录名只在首次入库时决定。系统不得因 Zotero 后续的标题、作者、年份、DOI 或其他书目信息变化而重命名目录，也不得自动迁移旧版纯 key 目录。用户可以自行重命名已完成的论文目录。

PDF 链接名固定为 `<清理后的原文件名 stem> [<attachment-key>].pdf`。stem 沿用 Windows 字符清理规则并最多保留 100 个 Unicode 字符；为空时使用 `PDF`。attachment key 后缀是 Pipeline 管理链接的保留命名空间，并保证多个同名附件不冲突。

用户可以在论文文件夹中自行添加任意文件。Pipeline 不得修改这些文件；仅可识别和修复文件名带对应 attachment key 的符号链接。普通文件、目录和其他符号链接均不得覆盖。

实现可以在 vault 的 `.pipeline/` 中使用配置文件和仅在运行期间有效的文件锁，但这些只是程序运行设施，不得成为论文业务数据的事实来源。v1 不得使用 SQLite 或其他持久任务数据库保存入库状态。

## 7. Zotero 元数据模型

### 7.1 Schema 来源

系统不自行定义一套书目字段白名单。

Zotero 官方 schema 按 `itemType` 定义合法字段集合。不同 item type 可以具有不同字段；同一 item type 中未能从网页提取的字段通常由 Zotero 表示为空字符串、空数组或空对象。

入库时，条目响应中的 `data` 对象是唯一的元数据输入和字段 schema。实现不得根据当前已知字段列表筛选该对象，也不得要求修改代码才能接纳 Zotero 将来新增的字段。

### 7.2 原始快照：`zotero-item.json`

`zotero-item.json` 是 Zotero 元数据的唯一无损原始快照：

- 文件内容必须是 Zotero 条目响应中的完整 `item.data` 对象，不包含 API 响应的外层包装。
- 所有键和值都必须保留，包括未知字段、空字符串、空数组、空对象、`false` 和 `null`。
- 对象、数组、顺序和 JSON 基本类型必须保持；不得筛选、重命名、补充、规范化或推测字段。
- “未经修改”指反序列化后的 JSON 值与输入 `item.data` 严格等价；不要求保留 API 响应原有的空白排版。

因此 creator role、姓名原结构、tag 对象及 `relations` 等嵌套结构都在此文件中完整保留。

### 7.3 Obsidian 投影：`meta.md`

`meta.md` 的 YAML frontmatter 以尽可能无损复制 `item.data` 为目标，只允许以下两项变换：

1. `creators` 保持原顺序，但每个 creator 对象转换成一个显示姓名字符串。机构作者优先使用非空 `name`；个人作者按 `firstName`、`lastName` 拼接。`creatorType` 和姓名原结构仅在 `zotero-item.json` 中保留。
2. Zotero `tags` 改名为 `zoteroTags`，其值为保持原顺序的 tag 名字符串列表。大小写、空格和重复项必须保留。不得生成 Obsidian 原生 `tags` 属性。

除此之外：

- 所有字段及空值都必须保留，字段名和大小写不得改变。
- `collections` 和 `relations` 必须保持 Zotero 原结构；即使 Obsidian Properties 不能完整展示嵌套 `relations`，也不作额外转换。
- 不得合成 Zotero 没有返回的稀疏字段。例如，有 `shortTitle` 就原样写入，没有就不得创建。
- 字符串、数字、布尔值、空值、数组和对象的类型必须保持。YAML 序列化不得把字符串误解成日期、数字或布尔值。
- 若输入结构无法按上述规则明确转换，必须令该条目失败，不得猜测或发布部分结果。
- 若 Zotero 将来同时返回 `tags` 与 `zoteroTags`，因字段名冲突必须令该条目失败。

`meta.md` 是便于 Obsidian 浏览的视图；需要完整 Zotero 结构时，以同目录的 `zotero-item.json` 为准。

### 7.4 禁止添加 Pipeline 字段

Pipeline 不得向 `meta.md` 添加 Zotero `data` 之外的属性，包括但不限于：

- `type`
- `paper_id`
- `imported_at` 或 `added`
- `metadata_source`
- `reading_status`
- `topics`
- `projects`
- 本地自定义 `tags`
- `source_status`
- `metadata_status`
- `pdf_status`
- `conversion_status`
- `error`
- PDF、全文或阅读笔记链接
- `pipeline` 对象或 `lp_*` 前缀字段

如果 Zotero `data` 自身包含同名字段，则该 Zotero 字段仍应按原样保存；这里禁止的是 Pipeline 自行添加字段。

### 7.5 正文

新建 `meta.md` 时，YAML frontmatter 之外不添加材料导航、备注模板、标题或其他正文。frontmatter 结束后可以只有一个换行。

示意如下；实际字段完全以 Zotero 返回的 `data` 为准：

```yaml
---
key: "ABCD1234"
version: 42
itemType: "journalArticle"
title: "Example Paper"
creators:
  - "John Smith"
abstractNote: ""
publicationTitle: "Example Journal"
volume: ""
issue: ""
pages: ""
date: "2025"
DOI: "10.1000/example"
zoteroTags: []
collections:
  - "ZXCV5678"
relations: {}
dateAdded: "2026-09-08T10:00:00Z"
dateModified: "2026-09-08T10:00:00Z"
---
```

## 8. 入库与幂等语义

### 8.1 新条目

对尚未入库的 Zotero item key，系统必须：

1. 验证它是指定 Collection 返回的顶层书目条目。
2. 获取并验证 `data` 是对象，且包含合法的 `key` 和 `itemType`。
3. 在写文件前完成 JSON 序列化、Obsidian 投影和 YAML 序列化的全部验证。
4. 按第 6 节规则确定新目录名，先安全创建保存完整 `data` 的 `zotero-item.json`，再安全创建 `meta.md`。
5. 只有 `meta.md` 完整发布后，才视为本次入库成功。

两个文件必须使用 UTF-8。文件发布必须避免留下被误认为成功结果的半写文件；实现应采用同目录临时文件与原子发布，或提供等价保证。如果进程在发布 sidecar 后、发布 `meta.md` 前中断，下次同步必须使用已有 `zotero-item.json` 中的快照恢复 `meta.md`，不得改用 Zotero 中可能已经变化的数据，也不得覆盖已有 sidecar。

### 8.2 已入库条目

`meta.md` 一旦成功创建，该条目即视为已入库，两个元数据文件均归本地论文库和用户所有。后续 `sync`：

- 不得更新其中任何 Zotero 字段。
- 不得补写后来出现的新字段。
- 不得同步 Zotero 中的修改。
- 不得重新格式化 YAML。
- 不得修改正文。
- 不得因为文件无法解析而覆盖或重建它。
- 不得更新或补建 `zotero-item.json`。

历史论文文件夹若已有 `meta.md` 但没有 `zotero-item.json`，仍直接跳过；v1 不执行 sidecar 回填或迁移。

因此 v1 是 **import-once**，不是持续 metadata sync。

### 8.3 已入库识别

v1 不使用数据库记录导入状态。实现必须使用普通文件确定条目是否已经入库：

- 为避免用户重命名论文文件夹后重复导入，实现还应扫描 vault 直接子目录中的 `meta.md`，读取其中 Zotero 原生 `key` 建立现有 key 索引；v1 不递归扫描更深目录。
- 对没有 `meta.md` 但有 `zotero-item.json` 的直接子目录，还必须读取 sidecar 中的原生 `key` 建立中断条目索引。恢复必须沿用该目录，不得用当前 API 标题重新计算路径。
- 若多个现有 `meta.md` 声明同一个 key，必须报告冲突并跳过该 key，不得自动合并或删除。
- 若同一个 key 被多个完成文件或 sidecar-only 文件声明，或同时存在于不同的完成与中断目录，必须报告冲突并跳过该 key。
- 若新条目按第 6 节得到的目标目录已经存在但其中没有元数据文件，系统可以在不修改目录内其他文件的前提下完成入库。
- 若该目录已有合法 `zotero-item.json` 而没有 `meta.md`，必须按 8.1 的中断恢复规则完成入库。
- 若目标 `meta.md` 已存在，无论内容是否为空、损坏或与目录名不一致，都不得覆盖。
- 目标目录、`meta.md` 或 `zotero-item.json` 是符号链接时必须拒绝写入并报告错误。

### 8.4 Zotero 后续变化

- 条目移出指定 Collection：不做任何本地修改。
- 条目在 Zotero 中被删除：不做任何本地修改。
- 条目的字段、标签或 Collection 关系在 Zotero 中改变：不做任何本地修改。
- 同一 key 重新进入 Collection：识别为已入库并跳过。
- Zotero 中出现内容相同但 key 不同的条目：视为不同输入，各自创建目录；v1 不判断学术意义上的重复论文。

### 8.5 PDF 链接语义

- `sync` 在两个元数据文件成功发布后，为本轮新完成或从 sidecar 恢复完成的论文尝试建立全部 PDF 链接。
- PDF child 必须是文件型 attachment，且 MIME 为 `application/pdf` 或文件名以 `.pdf` 结尾。不得猜测正文与补充材料的优先级。
- 无 PDF 是正常结果。附件 API、未下载文件、符号链接权限或单个链接冲突不得回滚或阻止元数据入库，也不得阻止其他 PDF。
- 链接必须指向 Local API 返回的现存绝对 `file://` 路径。Pipeline 只创建链接，不通过链接写入源 PDF。
- 对唯一匹配 attachment key 的既有符号链接：目标未变则跳过；名称变化则重命名链接；断链或目标变化则安全替换链接。
- 普通文件、目录、多个同 key 链接或目标名称冲突必须保留并报告。Zotero 删除附件后不得自动删除本地链接。
- 符号链接只是另一路径；用户通过它编辑 PDF 等同于直接编辑 Zotero 原文件。

## 9. 同步执行语义

一次同步必须分页读取指定 Collection 的完整顶层条目集合。只有 API 响应结构有效时才处理其中条目；单篇数据或文件写入失败不得阻止其他有效条目入库。

系统提供 `sync` 导入新条目并链接其 PDF，以及显式 `link-pdfs` 为所有已完成论文补建或修复链接。v1 不提供后台轮询。

同一 vault 同时只能有一个写入进程。并发控制可以使用 OS 文件锁，但不得依赖残留锁文件推断任务状态。

## 10. 最小配置与用户接口

详细 CLI 形式由详细设计确定，但 v1 用户接口只需覆盖以下能力：

- 列出 Zotero 个人库的 Collection，便于用户选择目标 key。
- 配置或初始化目标 vault、Collection key 和本机 Zotero API 地址。
- 执行一次入库扫描。
- 为既有论文补建或修复 Zotero PDF 符号链接。
- 只读检查配置、Zotero 连接和目标目录可写性。

不得在 v1 CLI 中提供 PDF 内容下载、主附件选择、转换、覆盖转换、重复合并或业务状态处置命令。

最小配置只应包含入库所需内容，例如：

```toml
collection = "ABCDEFGH"
zotero_url = "http://localhost:23119/api/"
```

不得要求 MinerU token、转换模型、OCR、语言、超时或其他非元数据入库配置。

## 11. 错误、安全与数据保护

- 所有错误必须通过清晰、可操作的信息报告；错误不得写入 `meta.md`。
- 日志不得包含凭据；v1 本身不需要 Zotero 写入凭据或外部服务 token。
- 任意失败不得删除或截断既有 `meta.md`。
- 初始化不得要求空 vault，也不得覆盖已有用户配置和文件。
- Pipeline 不得自动清理未知目录、未知文件或已移出 Collection 的论文。
- PDF 链接发布或修复必须避免覆盖普通文件；只允许替换由 attachment key 命名规则明确识别的符号链接。
- 路径处理必须支持 Windows 路径中的空格和 Unicode。
- `doctor` 必须检查 vault 中创建文件符号链接的能力；Windows 权限不足时提示开启开发者模式。
- 不完整的 API 分页结果不得被解释为本地条目需要删除；v1 在任何情况下本来也不执行删除。

## 12. Obsidian 使用约束

由于 `meta.md` 不含 Pipeline 自定义 `type` 字段，Obsidian Bases 应通过文件位置识别论文记录，例如筛选 vault 直接子目录下名为 `meta.md` 的文件。

`creators` 与 `zoteroTags` 是字符串列表，可由 Obsidian Properties 直接展示。使用 `zoteroTags` 而不是原生 `tags`，是因为 Zotero tag 可以包含空格，而 Obsidian 原生标签有不同的语义与约束。`relations` 等其他 Zotero 字段仍可能包含 Obsidian Properties 不支持的嵌套对象；v1 不继续扩大转换范围，完整结构可在 `zotero-item.json` 中查看。

Bases 视图、公式和展示优化属于用户的 Obsidian 配置，不属于 v1 的元数据入库职责。

PDF 符号链接位于 vault 内，Obsidian 和普通文件工具可将其作为 PDF 打开。链接依赖同一台电脑上的 Zotero 原文件，不承诺在跨设备同步或移动 vault 后仍有效。

## 13. 验收标准

实现至少必须通过以下行为验收：

1. **JSON 完整复制**：对多种 Zotero item type，读取生成的 `zotero-item.json` 后必须与输入 `item.data` 严格深度相等。
2. **YAML 最小投影**：解析 `meta.md` 后，仅 `creators` 与 `tags` 按 7.3 转换；其余字段与输入严格深度相等。
3. **空值保留**：空字符串、空数组、空对象、`false` 和 `null` 对应的键均未丢失。
4. **复杂结构留档**：不同 creator role、机构作者、原始 tag 对象及 relations 在 JSON 中无损往返；YAML 中 creator 与 tag 的展示值正确，relations 原样保留。
5. **稀疏字段不合成**：`shortTitle` 等字段有则原样保留，无则不生成。
6. **未知字段前向兼容**：模拟 Zotero 增加未知字段，该字段仍自动写入两个文件（除明确的投影字段外结构不变）。
7. **字符串类型安全**：日期样式、纯数字、`yes`/`no`、DOI、带冒号文本等字符串经 YAML 解析后仍为字符串。
8. **重复执行幂等**：同一 Collection 连续同步两次，第二次不创建副本且两个现有文件字节不变。
9. **本地编辑保护**：用户修改 `meta.md` 或 sidecar 后再次同步，两个文件均不被覆盖。
10. **旧条目不回填**：已有 `meta.md` 而没有 sidecar 时直接跳过，不补建 sidecar。
11. **中断恢复**：只有合法 sidecar 而没有 `meta.md` 时，从 sidecar 快照生成 `meta.md`，不覆盖 sidecar、不采用较新的 API 数据。
12. **重命名后识别**：用户重命名 vault 直接子目录中的论文文件夹但保留含原 `key` 的 `meta.md`，再次同步不重复导入。
13. **可读目录名**：验证 `shortTitle → title → key` 优先级、Unicode 保留、Windows 禁止字符处理、空白处理和 100 字符截断。
14. **目录唯一性**：相同标题或截断后相同标题但 key 不同的条目分别入库，目录名均保留完整 key。
15. **目录稳定性**：Zotero 后续标题变化不触发重命名；旧版纯 key 目录不自动迁移。
16. **重复 key 冲突**：完成文件或 sidecar-only 文件重复声明同一 key 时报告冲突，不改动任何一个文件。
17. **移除无副作用**：条目移出 Collection 或从 Zotero 删除后，本地目录和文件保持不变。
18. **不同 key 独立**：两个 DOI 或标题相同但 Zotero key 不同的条目分别入库。
19. **单篇失败隔离**：一个条目或目标路径失败时，其他合法新条目仍能入库。
20. **原子发布**：写入被中断时，不留下会被误判为完整文件的部分文件。
21. **PDF 全量链接**：一个或多个 PDF child 均创建独立符号链接，不复制文件内容；非 PDF child 被忽略。
22. **PDF 失败隔离**：无 PDF、未下载、路径错误或链接权限失败不回滚元数据；单个附件不阻止其他附件。
23. **PDF 幂等修复**：`link-pdfs` 能处理既有纯 key、可读名和用户重命名目录；重复执行不产生副本，目标或文件名变化时只修复受管理链接。
24. **文件保护**：普通文件、目录和非受管理链接发生命名冲突时保持字节与路径不变；Zotero 删除附件不触发本地删除。
25. **无外围依赖**：入库无需 MinerU、Obsidian 进程、转换 skill 或任务数据库；PDF 链接只依赖 Zotero Local API 和本机符号链接能力。

自动测试必须使用临时目录和模拟 Zotero 响应，不得修改真实 Zotero 库或用户 vault。

## 14. 详细设计必须回答的问题

实现人员可以自由选择内部模块划分，但详细设计必须明确：

1. 如何从 Zotero Local API 稳定、完整地分页读取指定 Collection 的顶层条目。
2. 如何验证 `data.key`、按第 6 节生成 Windows 安全的可读目录名并防止路径逃逸。
3. 如何原样保存 JSON 快照，并实现 `creators`、`tags` 两项 YAML 投影及字符串类型保护。
4. 如何扫描 vault 直接子目录中的完成文件和 sidecar-only 文件建立 key 索引，同时不修改任何用户文件。
5. 如何在进程并发和异常中断时保证不覆盖既有文件、不发布半写文件，并从 sidecar-only 状态恢复。
6. 如何隔离单篇失败并向用户汇总本轮“新建、跳过、冲突、失败”的数量与原因，而不持久化业务状态。
7. 如何保证安装和初始化不会接管或覆盖用户已有的 Obsidian vault。
8. 如何读取、验证所有 PDF child 的本机 file URI，并安全、幂等地创建或修复符号链接而不触碰普通文件。

任何详细设计若需要新增持久状态、派生元数据、后台任务、文件生命周期或自动覆盖行为，必须先修改并重新确认本规格，而不得作为实现细节自行扩展。
