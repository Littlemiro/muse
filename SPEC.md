# MUSE Skill 格式规范

## 目录结构

每个 skill 是一个独立目录：

```
<category>/<skill-name>/
├── SKILL.md               # 主文件（必需）
├── references/            # 附加文档（可选）
├── templates/             # 模板文件（可选）
├── scripts/               # 可执行脚本（可选）
├── assets/                # 资源文件（可选）
└── examples/              # 示例文件（可选）
```

## SKILL.md Frontmatter 标准

### 必需字段

| 字段 | 说明 | 约束 |
|------|------|------|
| `name` | 技能名称 | 字符串，唯一标识 |
| `description` | 简短描述 | 字符串，≤1024 字符 |

### 推荐字段

```yaml
---
name: my-skill
description: Brief description of what this skill does
version: 1.0.0
author: Your Name / Organization
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, automation]
    category: devops
trigger_keywords: [my, trigger, words]
---
```

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `version` | 版本号 | `0.1.0` |
| `author` | 作者/维护者 | `Hermes Agent` |
| `license` | 开源协议 | `MIT` |
| `platforms` | 支持平台 | `[linux, macos, windows]` |
| `metadata.hermes.tags` | 标签列表 | 从分类+描述推断 |
| `metadata.hermes.category` | 分类目录 | 从路径推断 |
| `trigger_keywords` | 触发关键词 | 从名称+分类+描述推断 |
| `metadata.hermes.related_skills` | 相关技能（同分类+标签重叠） | 自动推断 |

### 验证器要求

1. `SKILL.md` 必须存在
2. 文件以 `---` 开头（第一个字节）
3. 有 `---\n...\n---` 格式的 YAML frontmatter
4. frontmatter 包含 `name` 字段（非空）
5. frontmatter 包含 `description` 字段（非空，≤1024 字符）
6. frontmatter 之后有非空 body

## 渐进式加载

| 级别 | 可见性 | 何时加载 |
|------|--------|---------|
| Level 1 | 名称 + 描述 | 始终可见（在 MCP prompts/list 中） |
| Level 2 | 完整 SKILL.md | 调用 prompts/get 时加载 |
| Level 3 | references/ templates/ scripts/ assets/ | 技能执行时按需加载 |

## 外部技能目录

对于 Hermes Agent，可以通过 `config.yaml` 加载外部技能目录：

```yaml
skills:
  external_dirs:
    - path: /path/to/your/skills
```
