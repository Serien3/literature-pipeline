# Literature Pipeline

把 Zotero Collection 中的书目元数据与本机 PDF 一次性导入用户自己的 Obsidian vault，并按用户明确选择，通过 MinerU 将 PDF 转成便于 agent 阅读的 Markdown。

本程序的 `sync` 创建论文文件夹、Zotero 原始元数据快照、用于 Obsidian 浏览的 `meta.md`，并以符号链接引入 Zotero 已保存在本机的 PDF，但绝不调用 MinerU。用户随后通过独立的 `convert` 命令在终端界面中明确选择论文，或使用 `--key` 进行非交互调用；只有确认选择后才会上传 PDF 和消耗 MinerU 额度。完整产品规格见 [docs/v2_spec.md](docs/v2_spec.md)。

```text
论文网页 → Zotero Connector → sync → {metadata, PDF links} → convert（TUI/--key）→ {full.md, images, temp}
```

## 安装

支持在 Zotero 所在的 Windows 或 Linux 电脑上运行，需要 Python 3.11 或更新版本。Windows 安装：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Linux 安装：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

MinerU SDK 已是主程序依赖，不需要为 `tools/pdf2md` 另建虚拟环境。

在 Zotero 设置中允许本机其他应用访问，并保持 Zotero 运行。列出个人库中的 Collection：

```powershell
.\.venv\Scripts\literature-pipeline.exe collections
```

PDF 使用文件符号链接。Windows 请先开启“开发者模式”，或使用具备创建符号链接权限的终端；Linux 使用当前文件系统的标准符号链接能力。`doctor` 会实际检查该能力。

## 初始化已有或新的 vault

以下命令只创建 `<vault>\.pipeline\config.toml` 和运行锁，不要求 vault 为空，也不会创建或覆盖 Home、Bases、模板及其他用户文件：

```powershell
.\.venv\Scripts\literature-pipeline.exe init `
  --vault "D:\Research\PaperLibrary" `
  --collection ABCDEFGH
```

可以在初始化时设置以后手工转换所使用的参数：

```powershell
.\.venv\Scripts\literature-pipeline.exe init `
  --vault "D:\Research\PaperLibrary" `
  --collection ABCDEFGH `
  --pdf2md-language ch
```

`--vault` 对所有需要 vault 的命令都是可选项。`init` 省略它时初始化当前目录；其他命令会从当前目录逐级向上寻找最近的 `.pipeline\config.toml`。因此既可以在 vault 根目录运行，也可以进入某篇论文乃至其 `images`、`temp` 子目录后运行。需要操作别处的 vault 时，仍可显式传入 `--vault`，并以显式路径为准。

可选检查配置、vault 可写性及 Zotero Collection：

```powershell
.\.venv\Scripts\literature-pipeline.exe doctor
```

## 导入元数据

每次需要导入新收藏时执行：

```powershell
.\.venv\Scripts\literature-pipeline.exe sync
```

`sync` 会串行、原子地写入元数据，再为本轮新增论文以最多 4 路并发查询并建立
PDF 链接；运行期间会在标准错误流显示阶段和链接进度。最终汇总格式保持稳定。

新论文直接建立在 vault 根目录；`sync` 结束时尚未产生转换结果：

```text
PaperLibrary/
├── .pipeline/
│   ├── config.toml
│   └── writer.lock
├── Attention Is All You Need [ABCD1234]/
│   ├── zotero-item.json
│   ├── meta.md
│   └── Vaswani - Attention Is All You Need [ZXCV5678].pdf -> Zotero 原文件
└── Deep Residual Learning for Image Recognition [EFGH5678]/
    ├── zotero-item.json
    └── meta.md
```

目录名优先使用非空 `shortTitle`，否则使用 `title`，两者都没有时使用 Zotero item key；有标题时末尾始终保留 `[key]`。标题会清理 Windows 禁止字符并限制为 100 个字符，但完整元数据不受影响。目录名只在首次导入时确定，Zotero 后续修改不会触发重命名，旧的纯 key 目录也不会自动迁移。

`zotero-item.json` 完整保存 Zotero `item.data`，是未经字段转换的原始快照。`meta.md` 复制全部元数据，但为兼容 Obsidian Properties 做两项最小调整：

- `creators` 转为保持顺序的姓名字符串列表；完整 creator role 和姓名结构仍在 JSON 中。
- Zotero `tags` 转为 `zoteroTags` 字符串列表，不生成 Obsidian 原生 `tags` 属性；tag 中的空格、大小写、顺序和重复项均保留。

`relations` 及其他字段保持 Zotero 原结构，所以嵌套字段可能仍不能由 Obsidian Properties 完整展示。Zotero 没有返回的字段（例如部分条目没有 `shortTitle`）不会被程序补造。程序也不增加 `paper_id`、状态或其他 Pipeline 属性。

`meta.md` 创建成功后，该条目完全归用户所有。后续 `sync` 只导入新的 Zotero key，不修改两个现有元数据文件。即使 Zotero 条目被修改、移出 Collection 或删除，本地内容也保持不变。用户重命名 vault 根目录下的论文文件夹后，程序仍会读取 `meta.md` 中的原生 `key`，避免重复导入。

已有 `meta.md` 的旧条目不会被自动补建 `zotero-item.json`。如果首次写入恰好在 JSON 创建后中断，下次 `sync` 会扫描 sidecar 中的 key，在原目录中从已有 JSON 快照恢复 `meta.md`，即使 Zotero 标题已经改变也不会另建目录。

`sync` 只为本轮新入库论文自动建立 PDF 链接。为既有论文补建链接，或在 Zotero 重命名/移动 PDF 后修复链接：

```powershell
.\.venv\Scripts\literature-pipeline.exe link-pdfs
```

一个条目有多个 PDF 时会全部链接，不猜测哪个是正文。没有 PDF 属于正常情况；PDF 未下载或符号链接失败不会回滚 `meta.md` 和 JSON，修复环境后重新运行 `link-pdfs` 即可。普通文件和用户目录永不覆盖，Zotero 删除附件也不会触发本地删除。

## PDF 转 Markdown

在 Windows Terminal、PowerShell 或 Linux 终端中直接运行 `convert`，会先检查已有论文，然后打开交互式多选界面：

```powershell
.\.venv\Scripts\literature-pipeline.exe convert
```

Linux 中对应为：

```bash
literature-pipeline convert
```

界面显示全部状态，但只有 `Ready` 可以选择。初始不选择任何论文；使用方向键移动、Space 选择、`a` 全选当前搜索结果中的 Ready 项、`/` 搜索，Enter 进入额度确认，`q` 取消。当前论文的不可转换原因始终显示在详情区。确认退出界面后，所选论文按列表顺序串行转换。

如果只需要查看状态，或需要在脚本和非交互终端中使用，保留纯文本列表模式；这一步不要求 MinerU Token，也不消耗额度：

```powershell
.\.venv\Scripts\literature-pipeline.exe convert `
  --list
```

状态包括 `Ready`、`Converted`、`No PDF`、`Multiple`、`Unavailable` 和 `Conflict`。也可以绕过 TUI，明确传入一个或多个 Zotero item key：

```powershell
.\.venv\Scripts\literature-pipeline.exe convert `
  --key ABCD1234 `
  --key EFGH5678
```

不提供隐式“全部转换”：TUI 初始选择为空，必须勾选论文并再次确认；`--key` 本身则构成非交互转换授权。裸 `convert` 在 stdin 或 stdout 不是终端时会报错，并提示改用 `--list` 或 `--key`。历史已入库论文和刚完成 `sync` 的论文采用同一选择方式。

运行转换前，将 Token 写入真实环境变量 `MINERU_TOKEN`，或写入 `<vault>\.pipeline\.env`：

```dotenv
MINERU_TOKEN='你的 Token'
```

真实环境变量优先。Token 不写入 `config.toml`，也不会出现在命令汇总中。`sync`、`convert --list` 以及 TUI 的浏览和取消都不要求 Token；TUI 只有在用户确认选择后才读取 Token。

每个被选择的条目必须满足：

- Zotero 顶层条目恰好有一个 PDF child attachment；
- 该 PDF 已在本机下载；
- 当前论文目录中恰好有一个指向 Zotero 当前文件的受管理符号链接；
- `full.md`、`images/` 和 `temp/` 尚未占用。

程序会在上传前完成上述免费检查，并为论文取得独立转换锁。无 PDF、多个 PDF、链接不可用或输出冲突都不会调用 MinerU。已经有普通文件 `full.md` 的论文视为已转换并跳过。

转换结果先下载到论文目录内的隐藏暂存目录。程序删除 MinerU 返回包顶层附带的 PDF 副本、整理辅助文件并验证普通文件 `full.md` 存在，然后把结果直接展开到论文目录。`full.md`、`images/`、`temp/` 或其他待发布名称只要已经存在，程序就保留原内容并令转换失败，不覆盖或合并。

多个 `--key` 按命令行顺序串行转换；TUI 选择按界面列表顺序串行转换。单篇失败不阻止后续选择。程序不自动重试，只有用户再次通过 TUI 确认或明确传入 key 才会重新检查并尝试。

符号链接不复制 PDF 内容，可以跨磁盘，但它仍是 Zotero 原文件的另一个入口：通过链接编辑 PDF 会直接修改 Zotero 文件；跨电脑同步 vault 或移动 Zotero 数据目录后链接可能失效。

同步结束会报告本轮新增 key、元数据和 PDF 链接：

```text
同步完成：created=2 skipped=10 conflicts=0 failed=0 pdf_linked=2 pdf_missing=0 pdf_failed=0
本轮新增 key：ABCD1234 EFGH5678
```

元数据冲突或失败不会写入 `meta.md`。PDF 链接失败发生在元数据成功之后，不会回滚文件；修正问题后执行 `link-pdfs` 即可。

## 配置

`.pipeline/config.toml` 包含 Zotero 配置和独立转换命令采用的默认参数：

```toml
collection = "ABCDEFGH"
zotero_url = "http://localhost:23119/api/"

[pdf2md]
model = "vlm"
language = "en"
ocr = false
timeout = 1800
```

`model` 只能是 `vlm` 或 `pipeline`；`language`、`ocr` 和 `timeout` 对该 vault 的手工转换统一生效。旧配置缺少 `[pdf2md]` 时采用上述默认值。曾经生成的 `enabled` 字段会被兼容读取但忽略；它不可能让 `sync` 自动上传 PDF。

当前版本只支持个人库中的一个 Collection、直接成员和 Zotero Local API，不支持团队库、子 Collection 递归或远程 Zotero API。

## 开发验证

测试使用临时目录和模拟 Zotero，不修改真实 Zotero 或用户 vault：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

仓库采用常见的 `src` 布局，避免测试时意外导入未安装的源码：

```text
literature-pipeline/
├── src/literature_pipeline/   # 可安装的应用包
├── tests/                     # 自动化测试
├── docs/                      # 产品文档和产品规格
├── tools/pdf2md/              # MinerU 独立兼容入口
├── pyproject.toml             # 构建、依赖和工具配置
└── README.md
```

独立 PDF 转换工具的用法见 [tools/pdf2md/README.md](tools/pdf2md/README.md)。其核心实现与依赖属于主软件；独立入口也会删除 MinerU 返回结果中的 PDF 副本。
