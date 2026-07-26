# opencli-shop — 受限版 OpenCLI 购物助手 wrapper

位置：`/usr/local/bin/opencli-shop`（Hermes 宿主机，git-bash 环境）

## 用途

在 Hermes 和 OpenCLI 之间加一个安全拦截层，只放行 `taobao`/`xianyu`/`xiaohongshu` 的 `search`/`detail`/`note` 操作，阻止 `eval`/`cookies`/`cdp`/`network` 等可能提取登录态 cookie 的命令。

## 安全规则

白名单通过 `case` 语句实现，只匹配这些组合：

- `taobao_search` / `taobao_detail`
- `xianyu_search` / `xianyu_detail`
- `xiaohongshu_search` / `xiaohongshu_note`
- `doctor` / `version` / `help` / `--`（安全信息命令）

其余全部拦截并输出警告。

## 自动导航

搜索前自动打开目标站点（`browser open`），确保 browser session 就绪，避免直接搜索超时。站点映射：
- `taobao` → `https://www.taobao.com`
- `xianyu` → `https://www.goofish.com`
- `xiaohongshu` → `https://www.xiaohongshu.com`

浏览器 session 默认用 `main`，可通过环境变量 `OPENCLI_BROWSER` 覆盖。

## 更新

2026-07-16：初始创建，白名单 + 自动导航。
2026-07-16：修复 `doctor` 命令匹配（空 ACTION 时的 case 模式）。
2026-07-16：添加 `version`/`help`/`--` 白名单。

## 配合的 skill 更新

`shopping-assistant` skill 所有 38 处 `opencli` 已替换为 `opencli-shop`。添加新购物平台时需同时更新：
1. `opencli-shop` 的白名单 case 表
2. `URL_MAP()` 的站点映射
3. `shopping-assistant` skill 调用名
