# MUSE — MUlti-purpose Skill Ecosystem

**MUSE** 是一个兼容 Agent Skills 的本地 Skill Garden，首先服务 Hermes。它不替 Hermes 思考，也不替 Hermes 执行；它负责发现不断生长的技能库，审计安全与隐私，识别重复和职责冲突，并提出可回滚的治理建议。

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

## 快速开始：只读 Skill Garden

第一轮默认使用只读 Garden，不需要先创建 profile，也不需要先 approve skill。MUSE 会自动读取 Hermes 的主 skills 目录和 `config.yaml` 中的 `skills.external_dirs`。

```bash
# 1. 克隆并安装依赖
git clone https://github.com/Littlemiro/muse.git
cd muse
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 2. 自动读取 Hermes primary skills 和 config.yaml 中的 external_dirs
python3 muse-console.py garden

# 3. 输出稳定 JSON，供 Agent 或其他工具消费
python3 muse-console.py garden --json

# 4. 对单个 skill 做结构/拆分建议审计；只读，不移动或删除文件
python3 muse-console.py refactor-audit ~/.hermes/skills/research/my-skill

# 5. 按任务发现技能并按需读取；无需先 approve
python3 muse-console.py route "帮我修 jellyfin" --json
python3 muse-console.py inspect jellyfin-repair --json
```

`garden`、`audit`、`route` 和 `inspect` 默认只读。它们不会执行技能脚本、抓取 URL、修改技能或改变 Hermes 配置。

Garden 会告诉你：

- 哪些 skill 具有相同前缀，可能应组成 umbrella/spoke 结构；
- 哪些 skill 的描述和触发词高度重叠；
- 哪些 skill 的 `SKILL.md` 过大或文件过多；
- 哪些 skill 含脚本、网络、服务管理、破坏性文件操作或凭证风险；
- 哪些 skill 来自主目录、external directory 或 MUSE release。

Garden 只生成证据和建议，不自动 merge、archive、delete 或 rewrite。生命周期修改由 Hermes Curator 或用户决定。

## 高级：经过批准的发布流程

团队发布或需要固定 skill pack 时，仍可使用 release 工作流：

```bash
python3 muse-console.py audit --root ~/.hermes/skills --state-dir ~/.hermes/.muse
python3 muse-console.py approve <skill-name> --state-dir ~/.hermes/.muse
python3 muse-console.py bundle --state-dir ~/.hermes/.muse
python3 muse-console.py apply --state-dir ~/.hermes/.muse --target ~/.hermes/.muse/active
python3 muse-console.py rollback --state-dir ~/.hermes/.muse --target ~/.hermes/.muse/active
```

发布流程是可选的长期分发边界，不是日常临时使用 skill 的前置条件。源目录和 release 目录仍应分开，Hermes profile 仍应保留自己的执行审批。

建议在 Hermes 中打开它自己的技能写入审批：

```yaml
skills:
  guard_agent_created: true
  write_approval: true

memory:
  write_approval: true
```

MUSE 的 `apply` 输出目录是 Hermes 的外部技能目录候选；MUSE 不会自动修改 Hermes 配置，也不会把源技能目录改成可写镜像。源目录应对 Hermes 进程只读；`external_dirs` 只挂载 `active/current`。当前推荐用仓库内的 `muse-hermes-hook.py` 监听 Hermes 的 `pre_llm_call`，让 Garden 在每轮任务前自动发现新 skill；这不需要修改 Hermes 主代码，也不要求安装 `muse-router`。

## 按需发现和读取

`audit` 产生的 `state.json` 是本地 catalog；`route` 会在已配置的 source roots 中重新发现当前文件，因此未进入 catalog 或尚未 approved 的本地 skill 也能被找到。`route` 和 `inspect` 都是只读操作，不会修改审批状态、release 或 Hermes profile。

```bash
# 返回最相关的最多 3 个 skill；适合给 agent 使用 --json
python3 muse-console.py route "帮我修 jellyfin" --json

# 读取匹配 skill 的 SKILL.md，不需要 approve/apply
python3 muse-console.py inspect jellyfin-repair --json

# needs_review 会带风险提示；脚本默认只列出文件名
python3 muse-console.py inspect jellyfin-repair --include-scripts

# critical 也可以读取正文；MUSE 只增加风险提示
python3 muse-console.py inspect diy-nas-setup --json
```

`route` 只搜索当前配置的 roots，不会扫描整台电脑或联网。`inspect` 不执行脚本、不抓取 URL；脚本内容必须显式请求，并受大小限制和凭证脱敏保护。critical 和 needs_review 都可以被读取，但执行权限仍由 Hermes 控制。临时读取不会让 skill 进入 Hermes profile；需要长期固定分发时才使用 `approve`/`apply`。

## Hermes 自动路由：让 MUSE 先于 `skill_view`

如果只把 `muse-router/SKILL.md` 放进 Hermes，Hermes 仍会把它当普通 skill，按照自己的系统提示先调用 `skill_view`。这不是自动集成。要让 MUSE 真正成为发现层，应把 `muse-hermes-hook.py` 注册为 Hermes 的 `pre_llm_call` shell hook：

```yaml
hooks:
  pre_llm_call:
    - command: C:/Users/Administrator/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe C:/Users/Administrator/muse/muse-hermes-hook.py
      timeout: 20
```

钩子收到当前用户消息后，会在模型看到任务前执行一次只读的 `route → inspect`，并把最多 3 个候选和最高匹配项的 `SKILL.md` 摘要注入当前 turn。它不会执行 skill、访问 URL、修改审批或激活 profile；Hermes 仍负责工具调用和命令审批。`muse-router` 因此是可选的人工说明，不应作为自动路由的依赖，也不必放进 `skills.external_dirs`。

为保持效率，钩子维护 `.muse/route-cache.json`：只要技能目录的文件元数据没有变化，就直接使用缓存；Hermes 自己创建、修改或删除 skill 后，下一轮会发现指纹变化并刷新审计。该缓存不包含用户消息，也不保存未脱敏的 skill 内容。

## 与原始论文的关系

本项目受 [MUSE-Autoskill](https://arxiv.org/html/2605.27366v1) 的技能生命周期思想启发，但不是论文作者的官方实现，也不复刻完整 Agent runtime。论文负责创建、记忆、管理、评估和修炼；MUSE-Hermes 把其中适合本地运维的部分落成技能资产控制层，并复用 Hermes 自己的 `skill_manage`、memory 和审批机制。

Hermes 现在也有 Skills Hub、`skills audit`、来源/hash lock 和原生 bundles；MUSE 不替代这些能力，而是在它们之外提供面向任意本地 source root 的发现、风险标记、任务路由和“批准后发布、profile 生效、版本回滚”边界。这是本项目应主张的实际 gap，而不是重新宣称拥有完整技能生命周期。

## 仓库内容

| 文件 | 说明 |
|------|------|
| `SPEC.md` | MUSE SKILL.md 格式规范（frontmatter 标准 + 目录结构） |
| `CLASSIFICATION.md` | 12 分类 + 多维标签 + 自生长分类体系 |
| `muse-console.py` | garden、route/inspect 发现读取、指纹缓存、审计、结构建议、批准、bundle、版本导出和回滚 |
| `muse-hermes-hook.py` | Hermes `pre_llm_call` 只读适配器：自动 route → inspect；不执行 skill |
| `muse-enforce.py` | 安全默认的格式审计器；写入需要显式 `--fix` |
| `muse-mcp-server.py` | 可选 MCP bridge；默认只监听 loopback |
| `muse-router/SKILL.md` | 可选的 Hermes 路由提示；不是 MUSE 的核心依赖 |
| `requirements.txt` | Python 依赖 |
| `demo-hello/SKILL.md` | 干净的示例模板，用来参考格式 |
| `tests/` | 控制台的安全回归测试 |

## 边界和安全模型

- MUSE 从不抓取技能中的 URL，也不执行技能里的脚本。
- `route`/`inspect` 可以发现和临时读取未 approved skill，但不会把它写入 active release。
- `critical` skill 可以被 `inspect` 读取；MUSE 只展示风险，不替 Hermes 决定能否执行。长期 `apply` 仍是更严格的发布流程。
- 未批准、内容 hash 已变化或静态审计为 critical 的技能不会被 `apply` 导出。
- `apply` 只写独立的版本目录；源技能目录不会被覆盖。
- `apply`/`rollback` 仍保留 source root 与 Hermes primary skills 的冲突检查。
- `rollback` 只切换已生成的 release，不从网络重新下载内容。
- `muse-hermes-hook.py` 只读取 Hermes hook stdin 的当前任务；它不读取环境变量中的密钥，不把任务文本写入 route cache，也不调用 MCP/网络服务。
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
