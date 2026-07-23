# MUSE 技能分类体系

## 设计原则

MUSE 技能具有跨域特征（同一技能可能同时涉及研究、代码、浏览器自动化等），因此不使用单级别硬分类，而是采用**主分类 + 多维标签 + 风险/依赖元数据**体系。

## 一级分类（12 类）

| ID | 名称 | 判断标准 |
|---|---|---|
| `research_knowledge` | 研究与知识管理 | 搜索、文献、知识库、论文、代码考察 |
| `writing_editing` | 写作与文本处理 | 写作、改写、润色、摘要、翻译、人类化 |
| `software_development` | 软件开发 | 编码、调试、重构、代码生成、CLI 编程 |
| `data_science` | 数据与分析 | 数据清洗、统计、可视化、机器学习 |
| `web_browser` | 网页与浏览器 | 浏览器控制、登录态、网页提取、网页自动化 |
| `scraping_extraction` | 抓取与信息抽取 | 网页抓取、反爬、Cookie、结构化提取 |
| `devops_infrastructure` | DevOps 与基础设施 | 部署、监控、Webhook、CI/CD、服务器 |
| `desktop_control` | 桌面与设备控制 | Windows/macOS 桌面、鼠标、键盘、GUI |
| `creative_generation` | 创意与生成 | 图片、视频、音频、像素画、插画 |
| `productivity_automation` | 生产力与工作流 | 日程、提醒、批处理、自动化流程 |
| `integrations_services` | 外部服务集成 | GitHub、Notion、智能家居、第三方 API |
| `specialized_domain` | 专业领域 | 难以归入上述通用类的技能（临时兜底） |

> **注意：** `automation` 不作为一级分类。它更适合作为标签，因为几乎所有类别都可能包含自动化能力。

---

## 多维标签体系

将标签拆分为独立维度，而非扁平列表。

### 能力标签 `capability_tags`

```
search | retrieve | summarize | write | edit | translate |
code | debug | refactor | analyze | visualize |
generate-image | generate-video | generate-audio |
browse | scrape | extract | monitor | deploy |
schedule | control-device
```

### 目标对象 `target_objects`

```
paper | website | browser | repository | database |
markdown | knowledge-base | image | video | audio |
desktop | smart-home | github | rss | webhook | server | cli
```

### 执行方式 `execution_mode`（枚举）

```
pure_prompt | local_file | local_cli | external_api |
browser_session | desktop_gui | mcp | hybrid
```

### 风险元数据

```
risk_level: low | medium | high
destructive: true | false
requires_auth: true | false
requires_network: true | false
requires_user_session: true | false
```

### 维护状态

```
maturity: experimental | usable | stable | deprecated
maintenance: active | uncertain | inactive
```

---

## 分类决策规则

### 基础规则

1. 先判断技能的**主要产出**是什么，而不是看作者或标签。
2. 如果主要产出是知识、论文或研究判断 → `research_knowledge`
3. 如果主要产出是代码或代码变更 → `software_development`
4. 如果主要动作是操控浏览器 → `web_browser`
5. 如果主要动作是抓取和提取网页数据 → `scraping_extraction`
6. 如果主要产出是图片、视频或音频 → `creative_generation`
7. 如果技能会修改外部系统、提交代码、控制设备或发送请求 → 记录 `destructive` 和 `risk_level`
8. 一个技能最多有一个 `primary_category`，但可以有 0–3 个 `secondary_categories`
9. 不要根据单个标签决定分类，应综合 `description`、`tags` 和技能正文。
10. 如果无法判断 → `specialized_domain`，降低 `confidence`，不要强行归类。

### 自生长规则（v1.1）

一级分类不是固定死的，**当 `specialized_domain` 中同一子领域聚到 5 个以上技能时，触发分裂评估**：

1. **检测**：每次新增或重新分类技能时，检查 `specialized_domain` 下的子领域分布
2. **临界质量**：同一子领域（如"游戏"、"宠物"、"金融"）出现 ≥5 个技能，且这些技能无法被现有 11 类合理覆盖
3. **分裂提案**：提出新分类的 ID、名称、判断标准，以及从 `specialized_domain` 迁移的技能清单
4. **表决**：手动确认（目前由维护者拍板，未来可引入社区投票）
5. **执行**：创建新分类，迁移技能，更新所有索引

**这个机制防止两种极端：**
- 12 类永远不变 → 导致 `specialized_domain` 变成垃圾桶
- 每加一个技能就加新类 → 一年后 50 类失去分类意义

**触发式生长**——攒够临界质量才动，既有弹性又不碎。

### 分类输出格式

每个技能输出以下 JSON：

```json
{
  "name": "skill-name",
  "original_category": "原目录名",
  "original_tags": ["tag1", "tag2"],
  "primary_category": "research_knowledge",
  "secondary_categories": ["writing_editing", "data_science"],
  "capability_tags": ["search", "summarize", "analyze"],
  "target_objects": ["paper", "knowledge-base"],
  "operation_type": ["read", "extract"],
  "output_type": ["summary", "knowledge"],
  "execution_mode": "external_api",
  "requires_auth": false,
  "requires_network": true,
  "requires_user_session": false,
  "destructive": false,
  "risk_level": "low",
  "maturity": "usable",
  "maintenance": "active",
  "confidence": 0.85,
  "reason": "技能核心产出是知识管理和文献检索"
}
```

---

## 分类后的产出物

全量分类完成后输出：

1. 全部技能的分类结果 JSON
2. 每个一级分类的数量分布
3. `uncategorized` 或 `specialized_domain` 剩余数量
4. `confidence` < 0.7 的技能清单（待人工复核）
5. 同义标签合并建议
6. 分类冲突和需要人工复核的技能
