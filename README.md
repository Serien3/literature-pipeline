# Literature Pipeline

把 Zotero Collection 中的书目元数据一次性导入用户自己的 Obsidian vault。

本程序创建论文文件夹、Zotero 原始元数据快照、用于 Obsidian 浏览的 `meta.md`，并以符号链接引入 Zotero 已保存在本机的 PDF。它不复制或下载 PDF、不转换全文、不生成阅读笔记，也不会在首次入库后继续同步或覆盖元数据。完整产品规格见 [docs/v1_spec.md](docs/v1_spec.md)。

```text
论文网页 → Zotero Connector → 指定 Collection → <vault>/<可读标题> [<zotero-key>]/{metadata, PDF links}
```

## 安装

生产环境为 Zotero 所在的 Windows 电脑，需要 Python 3.11 或更新版本：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

在 Zotero 设置中允许本机其他应用访问，并保持 Zotero 运行。列出个人库中的 Collection：

```powershell
.\.venv\Scripts\literature-pipeline.exe collections
```

PDF 使用 Windows 文件符号链接。请先在 Windows 设置中开启“开发者模式”，或使用具备创建符号链接权限的终端；`doctor` 会实际检查该能力。

## 初始化已有或新的 vault

以下命令只创建 `<vault>\.pipeline\config.toml` 和运行锁，不要求 vault 为空，也不会创建或覆盖 Home、Bases、模板及其他用户文件：

```powershell
.\.venv\Scripts\literature-pipeline.exe init `
  --vault "D:\Research\PaperLibrary" `
  --collection ABCDEFGH
```

可选检查配置、vault 可写性及 Zotero Collection：

```powershell
.\.venv\Scripts\literature-pipeline.exe doctor --vault "D:\Research\PaperLibrary"
```

## 导入元数据

每次需要导入新收藏时执行：

```powershell
.\.venv\Scripts\literature-pipeline.exe sync --vault "D:\Research\PaperLibrary"
```

新论文直接建立在 vault 根目录：

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
.\.venv\Scripts\literature-pipeline.exe link-pdfs --vault "D:\Research\PaperLibrary"
```

一个条目有多个 PDF 时会全部链接，不猜测哪个是正文。没有 PDF 属于正常情况；PDF 未下载或符号链接失败不会回滚 `meta.md` 和 JSON，修复环境后重新运行 `link-pdfs` 即可。普通文件和用户目录永不覆盖，Zotero 删除附件也不会触发本地删除。

符号链接不复制 PDF 内容，可以跨磁盘，但它仍是 Zotero 原文件的另一个入口：通过链接编辑 PDF 会直接修改 Zotero 文件；跨电脑同步 vault 或移动 Zotero 数据目录后链接可能失效。

同步结束会报告：

```text
created=2 skipped=10 conflicts=0 failed=0 pdf_linked=2 pdf_missing=0 pdf_failed=0
```

元数据冲突或失败不会写入 `meta.md`。PDF 链接失败发生在元数据成功之后，不会回滚文件；修正问题后执行 `link-pdfs` 即可。

## 配置

`.pipeline/config.toml` 只有两个字段：

```toml
collection = "ABCDEFGH"
zotero_url = "http://localhost:23119/api/"
```

v1 只支持个人库中的一个 Collection、直接成员和 Zotero Local API，不支持团队库、子 Collection 递归或远程 Zotero API。

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
├── tools/pdf2md/              # 独立的 MinerU 辅助工具
├── CONTRIBUTING.md            # 贡献指南
├── pyproject.toml             # 构建、依赖和工具配置
└── README.md
```

提交修改前请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。独立 PDF 转换工具的安装和用法见 [tools/pdf2md/README.md](tools/pdf2md/README.md)。
