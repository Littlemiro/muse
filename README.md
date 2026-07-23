# MUSE — MUlti-purpose Skill Ecosystem

**MUSE** 是一个开放的技能格式标准和工具链，面向 AI Agent（Hermes、Claude Desktop、Codex、Cursor、Reasonix 等），让技能可以在不同 Agent 之间共享、搜索、分类和使用。

```
┌──────────────────────────────────────────────────┐
│  MUSE 框架                                        │
│                                                   │
│  CLASSIFICATION.md  ← 12类 + 多维标签 + 自生长     │
│  SPEC.md            ← SKILL.md 格式规范            │
│  muse-enforce.py    ← 格式校验器                   │
│  muse-mcp-server.py ← MCP 接口服务端               │
│  demo-hello/        ← 示例模板                     │
│  deploy/            ← systemd 部署                 │
└──────────────────────────────────────────────────┘
```

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/Littlemiro/muse.git
cd muse

# 2. 把你的 skill 放到一个目录（比如 ./my-skills/）
# 每个 skill 格式：my-skills/<category>/<name>/SKILL.md

# 3. 用 muse-enforce 校验格式
python3 muse-enforce.py ./my-skills/

# 4. 用 MCP Bridge 暴露给任意 MCP 客户端
pip install -r requirements.txt
python3 muse-mcp-server.py --skills-dir ./my-skills/

# 5. 在 Claude Desktop / Codex / Cursor 中连接
# MCP endpoint: http://localhost:8768/mcp/
```

## 仓库内容

| 文件 | 说明 |
|------|------|
| `SPEC.md` | MUSE SKILL.md 格式规范（frontmatter 标准 + 目录结构） |
| `CLASSIFICATION.md` | 12 分类 + 多维标签 + 自生长分类体系 |
| `muse-enforce.py` | 格式校验器：扫描 SKILL.md 目录，修复 frontmatter 问题 |
| `muse-mcp-server.py` | MCP bridge：将技能目录暴露为 MCP Prompts |
| `requirements.txt` | Python 依赖 |
| `demo-hello/SKILL.md` | 干净的示例模板，用来参考格式 |
| `deploy/` | systemd 服务文件 + daily sync timer |

## License

MIT
