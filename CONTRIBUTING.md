# 贡献指南

## 新增风格

按 [`chinese-style-skill-workflow`](.agents/skills/chinese-style-skill-workflow/SKILL.md) 的流程开展资料调查与头脑风暴、提出设计方案、生成五张预览并经人工审核，再实施风格包。五张必须包含封面、三张内容页和结束页；区分历史证据与现代设计转译。以“神似而非形似”为原则，提炼色调、材质、抽象纹理、光泽、留白与艺术气质，不把参考器物上的花卉、龙凤、山水等具象图案直接拼贴进 PPT，除非内容确需讨论该图案。没有确认视觉方向前，不创建正式 Skill。

## Skill 目录

沿用经过验证的汝窑 Skill 结构：

```text
.agents/skills/<skill-id>/
├── SKILL.md
├── agents/openai.yaml
├── assets/README.md         # 风格 Skill
├── assets/examples/         # 按需
└── references/              # 仅在需要出处或模式资料时添加
```

分类记录在 `catalog/styles.json` 与 `catalog/workflows.json`。

资源使用相对路径，不依赖个人目录。索引要列明用途、出处/生成方式、审核和授权状态。示例图用于提炼视觉语言，不能固化成模板。工作流 Skill 应复用上述风格流程，并保留人工审核停点。

## 多语言生成

每个 `SKILL.md` 必须保留与现有 Skill 一致的“多语言生成”一节；仓库语言不得成为输出语言限制。修改该节时同步全部 Skill 与 `DESIGN-PRINCIPLES.md`。

## 版本管理

遵循语义化版本：不兼容改动（Skill ID、目录、调用方式）升主版本，0.x 阶段升次版本；向下兼容的新风格或能力升次版本；修正升修订号。同步更新 `VERSION`、`catalog/`、README 页眉与版本表和 `CHANGELOG.md`。Skill 版本当前与集合版本一致。

## 双语维护

中文与英文发行目录保持 Skill ID、版本、分类、文件结构和二进制资源一致。面向用户的文档须人工本地化；不要仅复制机器翻译。修改后运行 `python3 tooling/validate.py`。

## 贡献许可与权利声明

提交贡献即表示：代码（`install.sh`、`tooling/`）按 MIT 授权，其余内容按 CC BY 4.0 授权；你有权提交这些内容。提交素材时说明生成方式或来源、是否使用过参考图及其授权。
