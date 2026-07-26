# MUSE 安全模型

MUSE 是技能资产控制层，不是沙箱，也不是安全扫描器能够替代的执行隔离环境。任何技能最终能做什么，仍取决于 Hermes 当前启用的工具、终端后端、文件权限和网络权限。

## 默认信任边界

技能目录是“不可信输入”。MUSE 的静态审计只能发现明显风险，不能证明自然语言指令、脚本或外部依赖安全。

Hermes 自带的 Skills Hub lock/audit 与 MUSE 审计是互补关系：前者记录 Hub 来源和上游状态，后者控制任意 source root 进入当前 profile 的 release 边界。

`muse-console.py`：

- 不抓取 `SKILL.md` 中的 URL；只记录 URL 以便人工检查。
- 不导入或执行技能脚本。
- 不修改源技能目录。
- 不把完整技能正文写入审批状态；审批绑定技能目录的 content hash。
- 只把 unchanged、approved 且没有 critical findings 的技能导出。
- 将每次导出保存为独立 release，回滚不需要联网。

`garden`、`route` 和 `inspect` 是独立的只读发现路径：它们可以从配置的 source roots 找到尚未 approved 的 skill，但不修改技能、审批、release 或 Hermes 配置。`inspect` 不执行脚本、不访问 URL；默认不输出脚本正文，`--include-scripts` 只读取受大小限制且经过脱敏的普通文件。`critical` 和 `needs_review` skill 可以被读取；MUSE 只展示风险，Hermes 仍负责执行权限。使用 `--cache` 或 Hermes hook 时，MUSE 只额外写入 `.muse/route-cache.json`，内容是文件元数据和已脱敏的审计记录，不包含用户任务文本或未脱敏正文。

## Hermes 自动路由钩子

`muse-hermes-hook.py` 是一个 `pre_llm_call` shell hook 适配器。它从 Hermes 通过 stdin 传入的 JSON 中读取当前任务，在本地执行 `route → inspect`，再通过 stdout 返回一个 JSON `context`。它不读取环境变量中的凭证，不执行 skill 脚本，不抓取 URL，不调用 MCP，也不改变 Hermes 的审批状态。

该钩子会把最高匹配 skill 的正文限制在模型上下文大小以内，并默认省略脚本内容。Hermes 的 hook consent/allowlist 仍然是必要的；不要用 `--accept-hooks` 或 `hooks_auto_accept: true` 来掩盖未经审查的第三方命令。部署后应运行 `hermes hooks doctor`，确认命令路径、超时和 allowlist 均符合预期。

## 建议的 Hermes 配置

在实验 profile 中启用：

```yaml
skills:
  guard_agent_created: true
  write_approval: true

memory:
  write_approval: true
```

如果使用 `skills.external_dirs`，请让源目录对 Hermes 进程只读。MUSE 的 approved export 可以作为单独的 external directory；不要把源仓库和 approved export 指向同一个可写目录。

Hermes 的本地 `~/.hermes/skills` 优先于 `external_dirs`。因此不要用默认 profile 的本地技能目录作为 source，再把 release 挂到同一个 profile 的 `external_dirs`；旧文件会遮蔽 release。推荐使用本地 skills 为空的独立 profile，并把 approved export 作为它唯一的 external directory。`muse-console.py apply/rollback` 会检查这个优先级冲突并拒绝激活；route/inspect 的临时读取不绕过这个长期发布保护。

## 风险等级

- `ready`：没有静态发现；仍需人工理解技能意图。
- `needs_review`：发现脚本、外部链接、风险声明不一致或潜在副作用；读取不受阻断，长期发布时需要额外审阅。
- `critical`：发现凭证样式内容、远程管道执行、越界 symlink、无效结构或其他高风险项；读取不受阻断，但默认不能进入长期 approved release。
- `stale`：已批准技能的内容 hash 发生变化；必须重新审计和批准。

## MCP

MCP bridge 默认只监听 `127.0.0.1`，并且默认只读取 `~/.hermes/.muse/active/current`。桥接其他目录必须显式传入 `--allow-unapproved-source`；这代表调用者已经另行完成审计和批准。远程模式没有内置认证，必须显式传入 `--allow-insecure-remote`，并放在带认证、TLS 和网络访问控制的反向代理后面。不要把它直接暴露到公网或不受信任的局域网。

## 供应链

不要把每日 `git pull` 当成更新策略。更新技能时应固定 Git commit 或 release，审计新 hash，人工批准后再 `apply`。运行 MUSE 本身需要的 Python 依赖也应在部署环境中锁定版本并通过组织自己的包策略验证。

## 报告安全问题

报告时请提供：MUSE 版本、命令、脱敏后的 audit JSON、涉及的 finding code 和复现步骤。不要提交 API key、Cookie、完整 session 日志或未经脱敏的技能正文。
