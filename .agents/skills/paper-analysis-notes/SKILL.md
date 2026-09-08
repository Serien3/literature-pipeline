---
name: paper-analysis-notes
description: "Read and deeply analyze an academic paper into a durable Markdown paper-analysis-tree note. Use for 论文精读、论文解析、文献阅读笔记, or requests to reconstruct a paper's own background narrative, incremental target gap, insight, contributions, method, evidence, and limitations instead of merely summarizing it."
---

# Paper Analysis Notes

产出一份可独立阅读的 Markdown 论文笔记。笔记仿照“论文解析树”的信息结构，不是死板地按论文段落顺序做摘要。

本文件规定分析过程和交付检查；[笔记模板](references/note-template.md) 规定成文结构、核心标签和章节分工。分析时需厘清的关系不必逐项变成正文中的独立字段。

把**因果主线**作为全文锚点：

> Task and application → Background（前人推进后的知识边界）→ Technical challenges 与 Research gap（本文要推进的增量问题） → Key insight / motivation → Contributions 与 Pipeline modules → Experiments（验证证据）→ Limitation（限制成因与适用边界）

## 1. 确认材料与产物

- 以用户指定的论文版本、输出路径、语言和详略度为准。
- 未指定语言时，沿用用户的主要语言；专业术语首次出现时保留论文原文。
- 未指定路径时，本地论文写到同目录的 `<paper-stem>-reading-note.md`；远程论文写到当前工作目录。目标文件已存在时先读取并增量更新，保留无法确认是否可删的人工内容。
- 记录实际阅读的版本和材料范围。通常论文阅读材料已经被转化为易读取的 Markdown 文档，这就是论文的原文完整版本。

完成条件：论文身份、版本、可用材料、输出路径均已确定。

## 2. 建立证据账本

通读全文后再写总览。先在工作草稿中为以下信息收集定位：章节、图、表、公式或附录。

- Task、输入、输出、应用场景与评价目标。
- Background 中与作者工作直接相关的问题演进：前人面对什么问题、用什么思路解决、解决到什么程度，以及留下或新产生了什么问题。
- 本文每个目标 Technical challenge 及其“Previous method → Failure cases / limitation → Technical reason”，并明确对应的 Research gap。分析必须具体到机制，不以“性能不足”代替原因。
- Key insight / motivation。说明可迁移的解决原则及其动机，区别于某个 Pipeline module 的实现名称。
- 每项 Contribution 的 Problem addressed、Approach、Advantage，以及在 Method 和 Experiments 中的落点。
- Method 总流程与每个 Pipeline module 的 Motivation、做法、输入输出、依赖、为什么能 work 和 Technical advantage。
- Comparison experiments、Ablation studies 及其他关键证据的设置、对照、指标、数值和适用范围。
- Limitation：作者明确承认的限制，以及能够由假设、方法或实验覆盖范围直接推出的限制。

草稿按上述术语组织分析，各条目使用稳定、具体的名称，并以名称关联证据。无需建立额外的字母编号或索引；正文标题的呈现方式见模板。

完成条件：待写入笔记的信息已在分析中区分为“论文支持”“解析推断”“不适用”或“材料未交代”，且每个关键结论都有论文内定位；这些分类用于检查，不要求逐项作为正文标签。

## 3. 重建知识边界并筛选本文问题

站在人类已知的知识边界上看这个工作，对于他提出的 research gap/question：这通常不是一个完全老的问题——相关的东西是什么，前人对这个 challenge 解决到了什么程度，这个工作试图解决哪些不一样增量的问题？**回答这些问题是为了明确背景基线、建立知识边界，准确理解本文要解决的 gap/question，而不是建立完整的领域知识图谱**。

这一步的价值在于我们与作者思维逻辑的对齐，作者的科研 Roadmap 一般为：定位到作者所在的 task -> 引出本 task 中与本工作相关的 technical challenge -> 领域背景，从问题到解决到新问题 -> 已有方法已经解决了 challenge 的一部分，但在某个重要维度上还没有解决好，这就是本文的目标 gap/question -> 我们的方法

这里的**知识边界**专指作者在本文 Background / Introduction / Related Work 中呈现的、本文工作出现之前的背景状态。依据作者对前序工作的概括重建以下演进：

1. 最初的问题是什么，代表性路线实际解决了哪一部分？
2. 它把能力推进到了什么程度，又留下了什么 residual issue，或因该解法引入了什么新问题？
3. 后续或并行路线分别解决了什么，与此前进展是什么关系，直到本文出场前已经能够做到什么、仍不能稳定做到什么？
4. 哪些未决问题只是 Background 中的领域背景或开放问题，哪些才构成本文明确试图推进的 Research gap？

将这一结果表述为“据本文叙述的知识边界”，不宣称它是穷尽所有工作的领域综述。Background 完整保留理解本文的 research gap/question 所需的问题演进，以能完成思维对齐为准；精简无关历史和重复表述，不按固定字数压缩。默认不检索或展开阅读外部前序文献；只有用户明确要求核查相关工作或了解当前领域进展时，才把外部调研作为独立补充，不挤占本文分析。

一个候选问题只有同时满足以下条件，才能列为本文目标 Technical challenge：

- 在本文出场前的知识边界上仍未解决，或由最新进展新产生；
- 作者明确将其设为本文要处理的 Research gap，而非只用于介绍领域历史；
- 至少一项 Contribution 或一个 Pipeline module 有意改变相关机制来处理它。

前人已经解决的问题归入 Background；仍然开放但本文没有给出对应 Contribution 或 Pipeline module 的问题归入“范围外开放问题”，不得写入本文 Technical challenges 清单。

完成条件：Introduction 中出现的每个相关问题都已区分为“Background 中前人已解决/部分解决的问题”“本文目标 Technical challenge”或“本文范围外开放问题”；读者能沿相关路线理解已解决程度、残留问题和 Research gap，且不存在从 Background 直接跳到 Contribution 的无依据归因。

## 4. 重建因果主线

先回答下列关系，再组织文字：

1. 相关路线如何通过承接或并行进展，把领域推进到本文面对的知识边界？
2. 每个目标 Technical challenge 对应什么 Research gap，Previous method 的哪个机制导致了什么可观察失败？
3. Key insight / motivation 如何改变解决问题的视角？它与具体实现有什么区别？
4. 每项 Contribution 解决哪些 Technical challenges，由哪些 Pipeline modules 实现？
5. 每个 Pipeline module 为什么在论文假设下能 work，而不只是“作者这样设计”？
6. Experiments 中哪些实验分别支持总体效果、单项 Contribution 和 design choice？证据实际能支持到什么强度？
7. Limitation 中哪些限制影响结论外推，它们由什么条件或机制产生？

这些关系允许一对多和多对一映射。无法闭合的关系应作为“论文未证明”或局限保留，而不是补写成事实。

完成条件：每项核心 Contribution 都能追溯到相关 Background 和目标 Technical challenge，并说明其解决思路、实现它的 Pipeline modules 及验证证据；孤立的 Technical challenge、未验证的 Advantage 和证据缺口均已显式标记。

## 5. 写入解析树笔记

写作前读取并遵循 [references/note-template.md](references/note-template.md)。保留其中五个一级分析章节及其顺序；根据论文实际数量增删 Technical challenge、Contribution、Pipeline module 和实验等重复分支。

- 按模板中的章节分工逐层展开。Abstract 是完成全文分析后的执行摘要，不是对原摘要逐句翻译；同一概念跨章节出现时，应增加新的解释层次。
- 保留核心标签，标签下可使用完整自然段。输入输出、对应关系和证据定位放入相关解释，避免为辅助信息层层添加字段。
- Method 的关键公式同时解释符号、计算过程和直觉作用；Experiments 保留关键绝对值、差值、单位和不确定性；Limitation 区分作者报告与解析推断。

优先释义并提供论文内定位，短引文只在原措辞不可替代时使用。默认材料边界是当前论文及其附带材料；用户明确要求的外部背景另标“外部补充”，不得混入论文自身主张。若论文不是典型的 pipeline 方法论文，将 Pipeline module 对应为理论环节、论证环节或实证研究环节，并明确这一适配。

完成条件：所有保留节点都有实质内容或明确的缺失说明；文档中没有模板提示语、空占位符或无法追溯的确定性断言。

## 6. 一致性审计并交付

完整笔记或实质性重写完成后，将交付前审计交给一个独立上下文的 subagent。提供用户阅读要求、模板、笔记及论文的路径，不附主 agent 的自评或预设结论。仅轻微措辞或格式修改可由主 agent 核对。

Subagent 对照原文与实际图像审阅，重点检查：

- Background 是否讲清已有进展与 Research gap；Technical challenges 和 Contributions 是否属于本文增量，Key insight / motivation 是否与具体实现区分。
- Method 是否解释各 Pipeline module 的输入输出、做法、为什么能 work 和 Technical advantage，并与所解决的问题衔接。
- Experiments 的数值、条件和图中例外是否支持结论，缺失的 Ablation studies 是否注明；Limitation 是否解释成因，论文陈述、解析推断与材料缺口是否清楚区分。
- 五章内容是否符合模板、术语是否一致，思维对齐与解释是否完整；是否存在无增量的重复、过度符号化或损害语言自然的机械填项。

Subagent 只返回有依据、影响准确性或理解的问题，逐项给出笔记位置、依据和修改建议；无问题则明确通过。主 agent 核实并修订，通常一轮即可；重要问题仍未解决时，仅复核相关部分。

完成条件：审阅发现的重要问题已修正，无法确认的内容已明确标注，笔记可独立阅读。Subagent 不可用时由主 agent 按同样要求审计，并在交付时如实说明。

最终回复给出 Markdown 文件链接和最重要的材料缺口；不在回复中重复整份笔记。
