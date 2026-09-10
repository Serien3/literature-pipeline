# Literature Pipeline v2 规格

## 1. 文档定位

本文定义 Literature Pipeline v2 的产品意图、系统边界、输入输出、同步语义、PDF 转 Markdown 契约和验收标准，是当前实现的权威规格。README、代码或测试与本文冲突时，以本文为准。

本文使用以下规范词：

- **必须**：实现不可偏离的要求。
- **不得**：明确禁止的行为。
- **可以**：不改变产品语义的可选实现。

## 2. 产品意图

用户通过 Zotero Connector 收集论文，在自己的 Obsidian vault 中长期维护论文材料。Literature Pipeline 负责把一个 Zotero Collection 中尚未入库的论文一次性转移到 vault：保存无损元数据快照、建立本机 PDF 的零复制入口。PDF 转 Markdown 是与同步解耦的显式操作；只有用户选择具体论文 key 后，系统才把唯一 PDF 交给 MinerU。

```text
Zotero 个人库中的指定 Collection
   ↓ sync（只读 Zotero，不调用 MinerU）
<vault>/<readable-title> [<item-key>]/
   ├── zotero-item.json
   ├── meta.md
   └── <filename> [<attachment-key>].pdf -> Zotero managed PDF
   ↓ convert --key <item-key>（显式选择）
   ├── full.md
   ├── images/
   └── temp/
```

本产品不是 Zotero 双向同步器、PDF 主附件猜测器、后台任务队列或论文精读笔记生成器。

## 3. 系统职责与非目标

系统必须：

1. 从 Zotero Local API 读取个人库中一个指定 Collection 的直接成员。
2. 排除 attachment、note 和 annotation 等非顶层书目记录。
3. 为尚未入库的 item key 创建论文目录，保存完整 `item.data` 到 `zotero-item.json`，并生成仅作最小投影的 `meta.md`。
4. 重复运行时不修改已经完成的元数据文件。
5. 为本轮新论文建立所有本机 PDF child attachment 的符号链接。
6. 提供 `link-pdfs`，为已有论文补建或修复受管理的 PDF 符号链接。
7. 列出已入库论文的转换就绪状态，不消耗 MinerU 额度。
8. 只转换用户通过 item key 明确选择的一个或多个已入库论文。
9. 隔离单篇失败，继续处理批次中的其他论文，并用汇总及退出码如实报告结果。

系统不得：

- 写入 Zotero、直接读取 Zotero SQLite，或猜测 Zotero data directory。
- 复制、下载、冻结或修改作为输入的 Zotero PDF。
- 在多个 PDF 中猜测哪个是正文。
- 更新、重排或覆盖已有 `meta.md` 与 `zotero-item.json`。
- 由 `sync` 隐式触发任何 MinerU 请求，或在没有明确 key 的情况下批量转换。
- 保存转换状态表、建立后台队列或自动重试失败转换。
- 自动覆盖或合并用户已有的 `full.md`、`images/`、`temp/` 或其他文件。
- 自动生成精读笔记、合并重复论文或管理阅读状态。
- 因条目离开 Collection 或在 Zotero 中删除而删除本地材料。

## 4. 运行环境与外部边界

- 目标生产环境是 Zotero 所在的 Windows 电脑；Python 必须为 3.11 或更新版本。
- Zotero API 地址必须是本机回环 HTTP 地址，不得包含凭据。
- Zotero 访问只读；PDF 路径只通过 attachment child endpoint 与 `/file/view/url` 获得。
- PDF 转换使用 MinerU 精准解析服务，会把论文 PDF 上传到外部服务。每次转换必须由用户显式提供论文 key。
- MinerU SDK 与 dotenv 是 Literature Pipeline 的正式安装依赖，不使用工具目录专属虚拟环境。
- Obsidian 仅用于浏览和维护文件；Pipeline 不依赖 Obsidian 进程。

## 5. 配置与 Token

配置位于 `<vault>/.pipeline/config.toml`：

```toml
collection = "ABCDEFGH"
zotero_url = "http://localhost:23119/api/"

[pdf2md]
model = "vlm"
language = "en"
ocr = false
timeout = 1800
```

约束如下：

- `ocr` 必须是布尔值。
- `model` 必须是 `vlm` 或 `pipeline`。
- `language` 必须是非空字符串。
- `timeout` 必须是大于零的整数秒。
- 公式和表格识别保持开启；集成转换不暴露页码范围。

旧配置缺少 `[pdf2md]` 时必须采用上述默认转换参数。兼容读取旧的布尔 `pdf2md.enabled` 时必须忽略其值；该字段不得触发转换。

Token 不得写入 `config.toml`。`convert --key` 优先读取进程环境变量 `MINERU_TOKEN`；环境变量不存在时读取 `<vault>/.pipeline/.env`。真实环境变量存在但为空时必须报错，不得退回文件。Token 文件不得是符号链接，日志不得输出 Token。

`sync` 与 `convert --list` 不得读取或要求 Token。`convert --key` 必须在查询论文附件或调用 MinerU 前验证 Token。`doctor` 可以报告 Token 是否就绪，但 Token 缺失不得令只使用同步功能的 vault 检查失败。

## 6. 元数据与目录契约

每篇论文目录直接位于 vault 根目录。目录名规则为：优先非空 `shortTitle`，其次非空 `title`，否则 item key；保留 Unicode，将 Windows 禁止字符替换为 ` - `，合并空白，清理首尾空格、句点和连字符，并把可读部分限制为 100 个 Unicode 字符。有标题时格式为 `<title> [<item-key>]`。

`zotero-item.json` 必须保存完整 `item.data` JSON 值，不筛选、补充、重命名或规范化字段，并保留空值、未知字段与嵌套结构。

`meta.md` 必须把同一对象写成 YAML frontmatter，只允许两项投影：

1. `creators` 按原顺序变成显示姓名字符串列表；机构使用 `name`，个人拼接 `firstName` 与 `lastName`。
2. Zotero `tags` 改名为 `zoteroTags` 字符串列表，保留顺序、大小写、空格和重复项。

不得向 `meta.md` 添加 Pipeline 状态、时间、PDF 或转换字段。完整结构以 `zotero-item.json` 为准。

PDF 符号链接名固定为 `<清理后的 filename stem> [<attachment-key>].pdf`。Pipeline 不复制 PDF；链接可以跨卷，但通过链接修改 PDF 等同于修改 Zotero 原文件。

用户拥有论文目录。除首次创建本规格列出的文件、受管理 PDF 符号链接及本轮转换结果外，Pipeline 不得修改其他内容。

## 7. 入库与幂等

`sync` 必须先分页取得 Collection 的完整一致快照，再扫描 vault 直接子目录中的 `meta.md` 和 sidecar-only `zotero-item.json` 建立 key 索引。

新条目的顺序是：

1. 验证条目与全部序列化结果。
2. 计算稳定目录名。
3. create-only、原子发布 `zotero-item.json`。
4. create-only、原子发布 `meta.md`。
5. 只有 `meta.md` 发布后才计为 `created`。
6. 读取并链接 PDF child attachments。
7. 在汇总后列出本轮新增的 item key，供用户选择后续转换对象。

若只有合法 sidecar 而没有 `meta.md`，必须从 sidecar 快照恢复，不得改用较新的 Zotero 数据。`meta.md` 一旦存在即表示已入库；后续 `sync` 直接跳过，不更新元数据、不补建 sidecar，也不检查转换结果。

用户重命名论文目录后，只要 `meta.md` 中保留原生 key，仍必须识别为已入库。多个本地文件声明相同 key 时报告冲突且不自动处理。目标目录或元数据路径为符号链接时拒绝写入。

## 8. PDF 符号链接

- 只处理文件型 attachment，且 MIME 为 `application/pdf` 或 filename 以 `.pdf` 结尾。
- `sync` 为本轮新论文链接全部 PDF，不以转换的唯一 PDF 限制改变链接行为。
- 无 PDF 是正常结果。
- 附件未下载、URI 无效、权限不足或名称冲突不得回滚元数据，也不得阻止其他附件。
- `link-pdfs` 可扫描全部完成论文，幂等创建、重命名或修复按 attachment key 识别的符号链接。
- 普通文件、目录、多个同 key 链接或其他符号链接不得覆盖。Zotero 删除附件后不得自动删除本地链接。

## 9. PDF 转 Markdown

### 9.1 触发范围

`sync` 与 `link-pdfs` 不得触发 MinerU。用户必须先运行 `convert --list` 查看所有已入库论文的状态；此操作不得要求 Token 或消耗 MinerU 额度。

只有 `convert --key <item-key>` 可以触发转换。`--key` 可以重复，从而明确选择多个论文；未提供 `--key` 时不得转换，也不得提供隐式全选。选择范围包括所有已完成入库的历史或新论文。

候选状态至少包括：

- `Ready`：满足全部转换前置条件。
- `Converted`：论文目录已有普通文件 `full.md`。
- `No PDF`：Zotero 中没有有效 PDF attachment。
- `Multiple`：Zotero 中有多个有效 PDF attachments。
- `Unavailable`：唯一 PDF 未下载、当前受管理符号链接缺失、重复、失效或未指向 Zotero 当前文件。
- `Conflict`：本地 key 冲突，或 `full.md`、`images`、`temp` 等输出名称被不兼容内容占用。

每个被选择的 key 必须对应唯一完成论文目录，并且 Zotero 当前返回的有效 PDF child attachment 总数恰好为一个。程序必须读取当前附件 file URI，并确认论文目录中恰好有一个按 attachment key 管理、指向该当前文件的 PDF 符号链接。`convert` 不得自行创建或修复链接；不满足时应提示用户先处理附件或运行 `link-pdfs`。

多个 key 按命令行选择顺序串行、前台执行。程序只在建立本地索引时短暂持有 vault 主写锁；远程转换不得持有主锁。每个转换使用按 item key 区分的细粒度 OS 文件锁，锁只表示活跃进程，不是持久状态。

### 9.2 额度保护预检

调用 MinerU 前，程序必须完成所有可在本地或 Zotero Local API 免费确定的检查：

1. key、完成论文目录和本地 key 唯一性有效。
2. Token 与转换配置有效。
3. Zotero PDF attachment 恰好一个且本机文件存在。
4. 受管理 PDF 符号链接唯一、有效并指向当前附件。
5. 取得该论文转换锁。
6. 论文目录中 `full.md`、`images` 和 `temp` 均未占用。

任一预检失败均不得实例化 MinerU 客户端或上传 PDF。普通文件 `full.md` 已存在时视为 `Converted` 并安全跳过，不提供自动覆盖选项。

### 9.3 MinerU 结果整理

转换必须先在论文目录内的隐藏临时目录保存完整结果，并在发布前：

1. 拒绝结果中的任何符号链接。
2. 删除 MinerU 返回包顶层的所有 `.pdf` 文件；不得修改输入 PDF 或论文目录的 PDF 符号链接。
3. 保留根层 `full.md` 和 `images/`。
4. 把其他 Markdown、JSON 等辅助产物移动到 `temp/`。
5. 验证根层存在普通文件 `full.md`；缺失时转换失败且不发布。

独立 `tools/pdf2md` 入口也必须执行上述 PDF 删除、辅助文件整理与 `full.md` 验证。

### 9.4 直接发布到论文目录

Pipeline 不建立转换结果子目录，而是把暂存结果的根层条目直接发布为论文目录的直接子项：

```text
<paper>/
├── zotero-item.json
├── meta.md
├── <PDF link>.pdf
├── full.md
├── images/
└── temp/
```

发布前必须检查所有目标名称。任一名称已经存在或为符号链接时，整次转换失败，不覆盖、不删除、不合并已有内容。普通可捕获错误应尽力回滚本次已经发布的条目。多条目发布无法获得目录级单操作原子性；进程被强制终止时可以留下部分结果。实现必须最后发布 `full.md`，使它成为直观的完成标志。

### 9.5 失败与显式重试

MinerU 请求、超时、结果验证、名称冲突或文件发布失败均不得修改元数据与 PDF 链接，也不得阻止同一命令中后续选择的论文。出现任一转换失败时，`convert` 必须返回非零；转换结果不得影响 `sync` 的退出码。

系统不自动重试，也不保存转换状态。用户再次明确传入同一 key 才构成新的授权尝试；每次尝试前都必须重新执行额度保护预检。若 `full.md` 已发布，后续选择必须在 MinerU 调用前跳过。

## 10. CLI 与汇总

所有需要 vault 的命令都必须接受可选的 `--vault PATH`，显式路径优先。`init` 省略该参数时必须使用当前目录，不执行向上发现；`doctor`、`sync`、`link-pdfs` 与 `convert` 省略该参数时，必须从当前目录逐级向文件系统根目录搜索，选择最近一个含 `.pipeline/config.toml` 路径的目录。仅有 `.pipeline` 目录不构成标志；最近标志损坏时必须报告该 vault 的配置错误，不得静默回退到外层 vault。完全找不到标志时，必须在访问 Zotero、读取 Token 或修改文件前报错。自动发现不得改变 `convert` 对 `--list` 或显式 `--key` 的要求。

CLI 必须提供：

- `collections`：列出个人库 Collection。
- `init`：create-only 初始化 vault，并可设置转换参数；不构成上传授权。
- `doctor`：检查配置、vault 写入、PDF 符号链接和 Zotero；可以提示 MinerU Token 是否就绪，但 Token 缺失不令检查失败。
- `sync`：一次性导入新论文、链接 PDF 并列出本轮新增 key，绝不调用 MinerU。
- `link-pdfs`：为已有论文补建或修复 PDF 符号链接，不触发转换。
- `convert --list`：列出转换状态，不要求 Token。
- `convert --key KEY [--key KEY ...]`：转换明确选择的论文，不提供隐式全选。

`sync` 汇总必须至少包含：

```text
created skipped conflicts failed
pdf_linked pdf_missing pdf_failed
```

`convert` 汇总必须至少包含 `selected converted skipped failed`。各命令只根据自身职责决定退出码：`sync` 的元数据或 PDF 链接错误导致非零，`convert` 的选择或转换错误导致非零。用户取消时返回 130。

## 11. 安全与数据保护

- 所有发布必须优先采用同文件系统暂存和 create-only/原子操作。
- 初始化不得覆盖已有配置；同步不得覆盖用户文件。
- 不得跟随论文目录、元数据文件、Token 文件或 MinerU 结果中的符号链接。
- 错误信息必须清晰，但不得泄漏 Token。
- 路径必须支持 Windows 空格与 Unicode。
- 网络、附件或单篇转换错误必须局部隔离；完整 Collection 响应或本地索引无法建立时应在写入前整体失败。

## 12. 验收标准

实现至少必须自动验证：

1. JSON 快照与输入 `item.data` 严格深度等价。
2. YAML 只转换 creators 与 tags，保留空值、未知字段、嵌套结构与字符串类型。
3. 重复同步不修改已入库元数据，用户重命名目录后仍能识别。
4. sidecar-only 中断可从原快照恢复，重复 key 与路径冲突不覆盖。
5. 所有 PDF attachment 都建立符号链接；缺失和冲突不回滚元数据。
6. `sync` 在任何配置下都不读取 Token、不调用 MinerU，并列出本轮新增 key。
7. `convert --list` 无 Token 时仍可列出 Ready、Converted、No PDF、Multiple、Unavailable 和 Conflict 状态。
8. `convert` 没有明确 key 时不能运行；一个或多个明确 key 可选择历史或新论文。
9. 无 PDF、多 PDF、链接无效、输出冲突或重复 key 在 MinerU 客户端创建前失败。
10. 普通 `full.md` 已存在时安全跳过，不重复消耗额度；只有再次明确选择才能重试未完成论文。
11. MinerU 返回的根层 PDF 被删除，额外 Markdown 与辅助文件进入 `temp/`，且缺少 `full.md` 时不发布。
12. `full.md`、`images` 或 `temp` 冲突时不覆盖、不合并，输入 PDF 与符号链接保持不变。
13. 主 vault 锁在远程转换前释放，同一论文转换仍受细粒度锁保护。
14. 多 key 串行处理，单篇转换失败不阻止后续选择，汇总与退出码准确。
15. 自动测试使用临时目录和模拟 Zotero/MinerU，不访问真实库、vault 或外部服务。
16. vault 参数可省略；根目录、论文目录和更深子目录能够发现最近 vault，显式路径优先，`init` 默认当前目录，发现失败时不访问外部服务。
