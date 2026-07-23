# MUSE Skill 格式规范与 Hermes 扩展

MUSE 不替代 [Agent Skills](https://agentskills.io/) 的基础格式。`SKILL.md` 应保持跨 Agent 可读；MUSE 的分类、风险、来源、测试和审批信息属于本地治理元数据，不应成为其他 Agent 使用技能的硬依赖。

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

推荐把 MUSE 专属字段放在 `metadata.muse`，或放在技能目录旁的本地治理文件中：

```yaml
metadata:
  muse:
    primary_category: devops_infrastructure
    tags: [automation, local-file]
    risk_level: medium
    destructive: false
    requires_auth: false
    requires_network: false
    maturity: experimental
    maintenance: active
```

这些字段是声明，不是权限。真正的批准状态、来源 hash 和 release 历史由本地 `muse-console.py` 状态目录保存，不能由技能正文自行声明为 trusted。

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

对于 Hermes Agent，可以通过 `config.yaml` 加载 MUSE 的 approved export：

```yaml
skills:
  external_dirs:
    - /path/to/.hermes/.muse/active/current
```

MUSE 不会自动修改 Hermes 配置。使用 `python3 muse-console.py config --target <activation-root>` 获取配置片段。

Hermes 的本地 `skills/` 优先于 `external_dirs`。要让 approved export 真正成为生效版本，应使用本地技能目录为空的 profile，或确保 source 不在该 profile 的 primary skills 目录中。
