# OpenCLI 安全 Wrapper：opencli-shop

## 风险

OpenCLI daemon（localhost:19825）暴露了完整的浏览器控制能力，包括：
- 提取 httpOnly cookie（Cookie API）
- 发送 CDP 命令
- eval 任意 JavaScript
- 网络抓包

Hermes 调用 opencli 做购物搜索时，如果指令被诱导或误用，可能提取到淘宝/小红书/闲鱼的登录 cookie。

## 解决方案：受限 Wrapper

创建一个 whitelist-only shell wrapper，只放行搜索/详情命令，并自动打开目标站防超时：

```bash
#!/usr/bin/env bash
# 🤖 opencli-shop — 受限版 OpenCLI 购物助手 wrapper
# 自动打开目标站 + 只允许搜索/详情，禁止 cookie/eval/CDP
set -euo pipefail

PLATFORM="${1:-}"
ACTION="${2:-}"
BROWSER_SESSION="${OPENCLI_BROWSER:-main}"

# 站点 URL 映射
URL_MAP() {
  case "$1" in
    taobao)     echo "https://www.taobao.com" ;;
    xianyu)     echo "https://www.goofish.com" ;;
    xiaohongshu) echo "https://www.xiaohongshu.com" ;;
    *)          echo "" ;;
  esac
}

# 白名单
case "${PLATFORM}_${ACTION}" in
  taobao_search|taobao_detail)                ;;
  xianyu_search|xianyu_detail)                ;;
  xiaohongshu_search|xiaohongshu_note)        ;;
  doctor_)                                    exec opencli doctor ;;
  version_|help_|--_)                         exec opencli "$@" ;;
  *)
    echo "⛔ 危险命令已拦截: ${PLATFORM} ${ACTION}"
    exit 1
    ;;
esac

# 自动打开目标站（确保 browser session 就绪）
SITE=$(URL_MAP "$PLATFORM")
[ -n "$SITE" ] && opencli browser "$BROWSER_SESSION" open "$SITE" > /dev/null 2>&1 && sleep 2

shift 2
exec opencli "${PLATFORM}" "${ACTION}" "$@"
```

## 关键设计

- **白名单匹配**：`${PLATFORM}_${ACTION}` 中的下划线是分隔符，单参数命令（如 `doctor`）变为 `doctor_`，匹配 `doctor_)` 模式
- **自动导航**：搜索前先 `opencli browser open` 目标站 + sleep 2s，防止搜索因 browser session 未就绪而超时
- **路径**：安装到 `/usr/local/bin/opencli-shop`

## 配套修改

对应的 skill（如 shopping-assistant）要把所有 `opencli` 调用改为 `opencli-shop`。
