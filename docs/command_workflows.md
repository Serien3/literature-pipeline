# `sync`、`link-pdfs` 与 `convert` 的职责和流程

Literature Pipeline 的三个主要业务命令组成一条明确的数据流：

```text
Zotero Collection
       │
       ▼
      sync ─── 新论文元数据入库并首次建立 PDF 链接
       │
       ▼
  Obsidian Vault
       │
       ├── link-pdfs ─── 补建或修复已入库论文的 PDF 链接
       │
       └── convert ───── 读取 Vault 中的 PDF 并调用 MinerU
```

三个命令的职责边界如下：

| 命令 | 数据来源 | 修改内容 | 访问 Zotero | 调用 MinerU |
|---|---|---|---:|---:|
| `sync` | Zotero Collection + Vault | 新建论文元数据和首次 PDF 链接 | 是 | 否 |
| `link-pdfs` | Zotero attachments + Vault | 补建、修复 PDF 链接 | 是 | 否 |
| `convert` | 仅 Vault | 创建 Markdown 转换结果 | 否 | 用户确认后是 |

## 1. `sync`：入库新论文

### 功能

`sync` 发现 Zotero Collection 中尚未进入 Vault 的论文，并完成首次入库：

- 创建论文目录；
- 保存不可变的 `zotero-item.json` 原始数据快照；
- 生成供 Obsidian 使用的 `meta.md`；
- 为本轮新增论文首次建立 PDF 符号链接；
- 不调用 MinerU，也不覆盖已经完成入库的论文。

### 业务流程

```text
取得 Vault 全局写锁
  ↓
读取 Zotero Collection 的全部顶层条目
  ↓
扫描 Vault，建立已有论文 key 索引
  ↓
校验并排除非论文条目、已有 key、重复 key 和冲突 key
  ↓
逐篇原子创建 zotero-item.json 和 meta.md
  ↓
收集本轮新增论文
  ↓
最多 4 路并发读取其 Zotero PDF 附件并建立符号链接
  ↓
输出汇总，释放全局锁
```

### 实现概要

CLI 创建 `Importer(vault, config, Zotero(...))` 并调用 `sync()`：

1. `Zotero.items()` 分页读取目标 Collection。
2. `index_existing()` 将 Vault 中的论文分为完整入库、部分入库和 key 冲突，并用 `set`/`dict` 提供均摊 O(1) 的 key 查询。
3. `atomic_create()` 以只创建、不覆盖的方式发布 JSON 和 Markdown 元数据。
4. 元数据处理完成后，最多使用四个独立 Zotero session 并发执行 `PdfLinker.link_paper()`。
5. 每篇论文读取 child items，筛选所有有效 PDF attachments，读取其本地 file URI 并建立符号链接。

`sync` 只为本轮新增论文建立链接。PDF 缺失或链接失败不会回滚已经成功写入的元数据；同一论文有多个 PDF 时会全部链接，不猜测哪个是正文。

## 2. `link-pdfs`：维护 PDF 链接

### 功能

`link-pdfs` 针对所有已完成入库的论文重新读取 Zotero 当前附件信息，补建或修复 PDF 符号链接。它不创建论文元数据，也不调用 MinerU。

典型使用场景包括：

- `sync` 时 PDF 尚未下载；
- 当时没有创建符号链接的系统权限；
- Zotero 附件文件名或文件位置发生变化；
- 原有符号链接损坏或丢失；
- 后来为论文增加了 PDF 附件。

### 业务流程

```text
取得 Vault 全局写锁
  ↓
扫描所有完整入库论文
  ↓
报告并跳过本地重复 key
  ↓
逐篇读取 Zotero child items
  ↓
筛选所有有效 PDF attachments
  ↓
逐附件读取本地 file URI
  ↓
创建、改名、修复或确认对应符号链接
  ↓
输出汇总，释放全局锁
```

### 实现概要

CLI 创建 `PdfLinker(Zotero(...))` 并调用 `link_existing(vault)`：

1. `index_existing()` 获取所有完整论文和本地 key 冲突。
2. 对每篇无冲突论文调用 `link_paper(folder, item_key)`。
3. `_attachment()` 校验父子关系、附件类型、link mode 和 PDF 类型。
4. `file_uri_path()` 确认 Zotero 返回的是有效本地文件。
5. `ensure_pdf_link()` 根据当前附件创建或修复链接。

受管理链接名称固定为：

```text
<清理后的 filename stem> [<attachment-key>].pdf
```

对于同一个 attachment key：链接不存在时创建，文件名变化时改名，目标变化时原子替换，已经正确时记为 unchanged。普通文件或用户目录绝不覆盖。

当前实现不会主动删除已经不再由 Zotero 返回的旧附件链接。如果新附件使用了不同 attachment key，可能同时留下新旧链接；此时 `convert` 会报告多个链接并拒绝猜测转换对象。

## 3. `convert`：转换 Vault 中的 PDF

### 功能

`convert` 只读取 Vault，不访问 Zotero。它检查本地论文状态，让用户通过 TUI 或 `--key` 明确选择论文，并在确认后调用 MinerU，发布 `full.md`、`images` 和 `temp`。

它转换的是 Vault 当前符号链接指向的 PDF，而不是隐式追踪 Zotero 最新附件。

### 三种入口

- `convert`：打开交互式 TUI，选择并确认后转换。
- `convert --list`：输出纯文本状态列表，不读取 Token、不调用 MinerU。
- `convert --key KEY`：直接授权转换指定 key，可重复传入，不打开 TUI。

### 业务流程

```text
短暂取得 Vault 锁并建立论文索引
  ↓
仅根据本地目录计算转换状态
  ↓
TUI 选择或接收明确的 --key
  ↓
读取 MinerU Token
  ↓
逐篇取得专属转换锁
  ↓
在锁内重新执行本地预检
  ↓
调用 MinerU 并安全发布结果
```

### 本地状态

状态只包括三种：

- `Converted`：论文目录中已经存在普通文件 `full.md`。
- `Ready`：没有输出冲突，并且恰好存在一个有效的受管理 PDF 符号链接，其目标为普通文件。
- `Unavailable`：其他所有情况；详情说明没有链接、多个链接、断链、目标无效、输出名称冲突或本地 key 冲突等具体原因。

只有符合以下格式的符号链接才被视为受管理输入：

```text
<任意名称> [<8 位 attachment key>].pdf
```

普通 PDF 文件及命名不符合规范的符号链接不会成为转换输入。多个受管理链接统一视为 `Unavailable`，程序不会自行选择其中一个。

### 实现概要

CLI 创建不含 Zotero 依赖的 `ConversionService(vault, config)`：

1. `index_existing()` 获取所有完整论文和 key 冲突。
2. `inspect()` 检查 `full.md`、`images`、`temp` 和本地 PDF 符号链接，生成 `ConversionCandidate`。
3. 裸 `convert` 将候选交给 TUI；只有 `Ready` 可选，Token 在用户确认后才读取。
4. `convert_selected()` 校验并去重 key，为每篇论文取得 `PdfConversionLock`，然后重新调用 `inspect()`。
5. 复检仍为 `Ready` 才构造 `ConversionOptions` 并调用 `convert_pdf_into_paper()`；`Converted` 安全跳过，其他状态失败且不调用 MinerU。

转换结果先在临时位置完成和验证，再发布到论文目录。发布过程拒绝结果中的符号链接、移除 MinerU 返回的顶层 PDF 副本、保留输入 PDF 链接，并且不覆盖已有文件或目录。一篇转换失败不会阻止同一命令中的后续论文。

## 4. 设计原则

- `sync` 负责发现和首次入库。
- `link-pdfs` 负责 Zotero 与 Vault 之间的附件链接维护。
- `convert` 负责消费 Vault 当前准备好的 PDF。
- Zotero 数据和附件变化不会由 `convert` 隐式处理。
- MinerU 调用必须建立在明确选择和本地复检成功的基础上。
- 元数据、PDF 链接和转换结果分别维护，任一阶段失败不应破坏其他阶段已经成功产生的内容。
