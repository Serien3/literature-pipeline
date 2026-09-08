# MinerU 精准解析 PDF 工具

这个命令行程序使用 MinerU 精准解析 API 上传本地 PDF，并将 MinerU 返回的完整结果 ZIP 解压到本地。程序会保留 Markdown、原 PDF 和图片目录，并自动把 JSON 等辅助产物整理到 `temp/`。

## 安装

需要 Python 3.10 或更高版本。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

在 [MinerU API 管理页面](https://mineru.net/apiManage/token) 创建 Token。程序按以下任一方式获取 Token，优先级：**真实环境变量 > .env 文件 > 报错**。不要把 Token 写进脚本或提交到代码仓库。

**方式一：环境变量**

```bash
export MINERU_TOKEN='你的 Token'
```

**方式二：.env 文件（推荐）**

在运行目录（即执行命令的当前目录）创建 `.env` 文件：

```bash
echo "MINERU_TOKEN='你的 Token'" > .env
```

`.env` 已加入仓库根目录的 `.gitignore`，不会被提交。文件中支持注释、引号等常见格式（由 python-dotenv 解析）。

需要指定其他位置的 .env 文件时，用 `--env-file`（此时不再自动查找运行目录下的 `.env`）：

```bash
.venv/bin/python mineru_convert.py paper.pdf --env-file /path/to/custom.env
```

`.env` 中必须含有 `MINERU_TOKEN` 键，且 `--env-file` 指向的文件必须存在，否则程序会报错退出。

## 使用

转换当前测试论文：

```bash
.venv/bin/python mineru_convert.py svpg.full.pdf -o results
```

结果会保存到 `results/svpg.full/`，目录结构如下：

```text
results/svpg.full/
├── full.md
├── *_origin.pdf
├── images/
└── temp/
    ├── *_content_list.json
    ├── *_content_list_v2.json
    ├── *_model.json
    └── layout.json
```

Markdown、原 PDF 和 `images/` 的名称、内容、位置均不会被整理步骤修改。处理另一篇论文时只需更换 PDF 路径：

整理只应用于以后生成的结果；脚本不会主动修改已经存在的结果目录。使用 `--overwrite` 重新解析时，新结果会采用上述结构。

```bash
.venv/bin/python mineru_convert.py /path/to/paper.pdf -o results
```

扫描版论文需要开启 OCR；中文论文应指定中文：

```bash
.venv/bin/python mineru_convert.py scan.pdf -o results --ocr --language ch
```

其他常用选项：

```text
--env-file custom.env  从指定 .env 文件读取 Token（默认：当前目录下的 .env）
--pages 1-20       只解析指定页
--model pipeline   改用 pipeline 模型（默认 vlm）
--no-formula       关闭公式识别
--no-table         关闭表格识别
--timeout 3600     延长最长等待时间
--overwrite        替换同名 PDF 的已有结果目录
```

查看完整帮助：

```bash
.venv/bin/python mineru_convert.py --help
```

精准解析 API 当前限制单文件不超过 200 MB、200 页。解析为异步任务，程序会等待 MinerU 完成上传、解析和结果下载。
