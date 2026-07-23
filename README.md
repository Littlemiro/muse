# MUSE — MUlti-purpose Skill Ecosystem

**MUSE** 是一个兼容 Agent Skills 的本地技能资产治理层，首先服务 Hermes。它不替 Hermes 思考，也不替 Hermes 学习；它负责让技能变得可发现、可审计、可批准、可组合、可回滚。

```
┌──────────────────────────────────────────────────┐
│  MUSE 框架                                        │
│                                                   │
│  muse-console.py    ← Hermes 技能资产控制台         │
│  CLASSIFICATION.md  ← 分类、标签和风险元数据        │
│  SPEC.md            ← Agent Skills 兼容扩展         │
│  muse-enforce.py    ← 安全默认的格式审计器          │
│  muse-mcp-server.py ← 可选的本地只读 MCP 桥         │
│  demo-hello/        ← 示例技能                      │
└──────────────────────────────────────────────────┘
```

## 快速开始：Hermes 本地控制台

推荐让 MUSE 管理一个“本地技能目录为空、只挂载 approved export”的 Hermes profile。Hermes 的本地 `skills/` 优先于 `external_dirs`；如果直接扫描并导出到默认 profile，旧本地技能会遮蔽 MUSE release，`apply`/`rollback` 会主动拒绝这种配置。

```bash
# 1. 克隆
git clone https://github.com/Littlemiro/muse.git
cd muse

# 2. 创建一个不预置本地技能的 Hermes profile
hermes profile create muse --no-skills

# 3. 先只读审计原 profile 的技能，不会改源文件
python3 muse-console.py audit --root ~/.hermes/skills --state-dir ~/.hermes/.muse

# 4. 查看技能并批准一个没有变化的版本
python3 muse-console.py list --state-dir ~/.hermes/.muse
python3 muse-console.py approve <skill-name> --state-dir ~/.hermes/.muse

# 5. 按分类生成 bundle；必须写入目标 profile 的 bundle 目录
python3 muse-console.py bundle --state-dir ~/.hermes/.muse \
  --output-dir ~/.hermes/profiles/muse/skill-bundles

# 6. 导出批准的技能到独立目录；源技能不会被覆盖
python3 muse-console.py apply --state-dir ~/.hermes/.muse \
  --target ~/.hermes/.muse/active \
  --consumer-home ~/.hermes/profiles/muse

# 7. 打印目标 profile 的 config.yaml 片段，手动加入 external_dirs
python3 muse-console.py config --target ~/.hermes/.muse/active

# 8. 需要时回滚到上一版批准集合
python3 muse-console.py rollback --state-dir ~/.hermes/.muse \
  --target ~/.hermes/.muse/active \
  --consumer-home ~/.hermes/profiles/muse

# 9. 使用这个 profile
muse chat
```

建议先在独立 Hermes profile 中使用，并打开 Hermes 自己的技能写入审批：

```yaml
skills:
  guard_agent_created: true
  write_approval: true

memory:
  write_approval: true
```

MUSE 的 `apply` 输出目录是 Hermes 的外部技能目录候选；MUSE 不会自动修改 Hermes 配置，也不会把源技能目录改成可写镜像。源目录应对 Hermes 进程只读；`external_dirs` 只挂载 `active/current`。

## 与原始论文的关系

本项目受 [MUSE-Autoskill](https://arxiv.org/html/2605.27366v1) 的技能生命周期思想启发，但不是论文作者的官方实现，也不复刻完整 Agent runtime。论文负责创建、记忆、管理、评估和修炼；MUSE-Hermes 把其中适合本地运维的部分落成技能资产控制层，并复用 Hermes 自己的 `skill_manage`、memory 和审批机制。

Hermes 现在也有 Skills Hub、`skills audit`、来源/hash lock 和原生 bundles；MUSE 不替代这些能力，而是在它们之外提供面向任意本地 source root 的“批准后发布、profile 生效、版本回滚”边界。这是本项目应主张的实际 gap，而不是重新宣称拥有完整技能生命周期。

## 仓库内容

| 文件 | 说明 |
|------|------|
| `SPEC.md` | MUSE SKILL.md 格式规范（frontmatter 标准 + 目录结构） |
| `CLASSIFICATION.md` | 12 分类 + 多维标签 + 自生长分类体系 |
| `muse-console.py` | 发现、审计、批准、bundle、版本导出和回滚 |
| `muse-enforce.py` | 安全默认的格式审计器；写入需要显式 `--fix` |
| `muse-mcp-server.py` | 可选 MCP bridge；默认只监听 loopback |
| `requirements.txt` | Python 依赖 |
| `demo-hello/SKILL.md` | 干净的示例模板，用来参考格式 |
| `tests/` | 控制台的安全回归测试 |

## 边界和安全模型

- MUSE 从不抓取技能中的 URL，也不执行技能里的脚本。
- 未批准、内容 hash 已变化或静态审计为 critical 的技能不会被 `apply` 导出。
- `apply` 只写独立的版本目录；源技能目录不会被覆盖。
- `rollback` 只切换已生成的 release，不从网络重新下载内容。
- MCP bridge 默认绑定 `127.0.0.1`；远程绑定必须显式 `--allow-insecure-remote`，并应放在外部认证代理之后。
- 详细威胁模型见 [SECURITY.md](SECURITY.md)。

## 可选：MCP 和 systemd

Hermes 的 MCP 文档把 Hermes 定位为 MCP client；MUSE 的 bridge 是可选的本地只读适配器，不是 Hermes 必需依赖：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 muse-mcp-server.py --skills-dir ~/.hermes/.muse/active/current
```

不传 `--skills-dir` 时，bridge 也只读取这个 approved export；未批准目录必须显式加 `--allow-unapproved-source`。默认 MCP endpoint 为 `http://127.0.0.1:8768/mcp/`。

`deploy/` 下的 systemd 文件是模板。启用前请创建专用 `muse` 用户，并让它只读 `/opt/muse`、只写 `/var/lib/muse`；同步 timer 现在只做本地审计，不再自动 `git pull`。远程 HTTP 访问必须自行配置认证、TLS 和网络访问控制。

## License

MIT
