---
name: paper-pdf-to-md
description: 调用 MinerU 转换脚本，将论文仓库中的 PDF 转换为以 Markdown 为核心、包含图片和辅助文件的完整版本，保存在该论文文件夹内。用于论文 PDF 转 Markdown、PDF 转换或论文入库时的格式转换。
---

# 论文 PDF 转 Markdown

调用本 skill 自带的 [scripts/mineru_convert.py](scripts/mineru_convert.py) 完成转换。整个 skill 文件夹可整体迁移，无需依赖原项目目录。

## 仓库约定

用户已在论文仓库根目录准备好虚拟环境（默认 `.venv/`，含 [scripts/requirements.txt](scripts/requirements.txt) 中的依赖）和 `.env`（含 `MINERU_TOKEN`）。输入 PDF 位于根目录的 `<literature>/` 文件夹内，转换结果也保存在该文件夹内。

## 执行

1. 确定论文仓库根目录及用户指定的 PDF。从仓库根目录运行，使用已有虚拟环境的 Python；虚拟环境名称不同时使用实际路径。根据当前 `SKILL.md` 的实际位置定位同目录下的 `scripts/mineru_convert.py`，使用脚本的绝对路径，不把 skill 目录当作论文仓库根目录。
   Windows 使用实际虚拟环境的 `Scripts/python.exe`。若论文由 literature-pipeline 入库，PDF 在 vault 的 `papers/<paper_id>/` 下，令牌配置在 vault 的 `.pipeline/.env`；虚拟环境可以位于代码项目中，不要求在 vault 内新建。
2. 执行以下命令，将示例路径替换为实际路径，保留路径引号：

   ```bash
   .venv/bin/python "<skill绝对路径>/scripts/mineru_convert.py" \
     "<literature>/<文件名>.pdf" \
     --env-file ".env" \
     -o "<literature>"
   ```

   脚本会上传 PDF 至 MinerU，等待解析完成并下载结果。默认转换全文；扫描版加 `--ocr`，中文论文加 `--language ch`。让脚本读取 `.env`，无需输出其中的凭据。
3. `-o` 是直接保存结果的目录；省略时默认使用输入 PDF 所在目录。结果结构为：

   ```text
   <literature>/
   ├── <文件名>.pdf
   ├── meta.md
   ├── full.md
   ├── images/
   └── temp/
   ```

   已有 `meta.md` 始终保留，包括使用 `--overwrite` 重新转换时；脚本仅在没有元数据文件时创建最小记录。失败时报告脚本错误，不自动反复提交。
4. 等待命令成功退出，确认结果目录中的 Markdown 存在且非空，向用户返回实际 Markdown 文件链接。
