# decision-model

**中文** · [English](README.en.md)

由 [New.bi](https://api.new.bi) 提供，专业、稳定、可靠的大模型聚合中转平台。

调用决策模型（Jev / TypeSafe System One）的命令行工具，也可以直接当 agent 技能用。

输入一段 state 和几个问题，得到每个问题的概率。它不写文字。

## 开始

```bash
python3 scripts/gateway.py login --key sk-xxx
python3 scripts/gateway.py models
python3 scripts/gateway.py decision --preset route-capability \
  --state '{"message":"a 5 second video of a cat walking through bamboo"}'
```

返回 `action: video`、`accepted: true`，以及每个问题的概率和阈值判定。

模型缓存放在 `~/.aigw/cache/`，保留 6 小时；`AIGW_STATE_HOME` 可以改。`config.json` 在技能目录里，命令里的相对路径按当前工作目录算。用 `models` 查可用模型和价格。单次指定用 `--model <id>`；固定默认用 `model set <id>`，写进 `config.json` 的 `model` 字段。

内置三套预设：`route-capability`（判断该走哪个能力）、`content-risk`（放行、复核还是拦截）、`reply-triage`（自动回复、当天处理还是转人工）。

## 支持的模型

`jev-latest` 跟着上游升级，行为会变；固定版本如 `jev-1.13.0` 更稳，生产上建议用固定版本，升级后重新看阈值。

## 常见搜索词

AI 决策、意图识别、内容审核、风险分级、消息分诊、置信度判断、概率判断、路由决策、B 端风控。

## 命令

| 命令 | 做什么 |
| --- | --- |
| `login` / `config` / `doctor` | 密钥、配置、连通性。 |
| `models` | 列出这个密钥能看到的决策模型。 |
| `model show` / `model set <id>` | 看或设置默认模型。 |
| `resolve <别名>` | 别名换成具体模型 id。 |
| `decision` | 发起一次判断，支持预设、阈值、熔断。 |

默认 `shadow` 模式，调用失败或概率不够时返回兜底值，不会卡住业务。输出都是 JSON。

## 密钥

按顺序找，先用找到的：`config.json` → `AIGW_DECISION_API_KEY` → `AIGW_API_KEY` → `OPENAI_API_KEY`。网关地址同样逐级回退，最后用 `scripts/defaults.json` 里的。

## 文件

```
decision-model/
├── SKILL.md              中文说明
├── SKILL.en.md           英文说明
├── config.json           密钥和默认模型，不进 git
├── references/
│   ├── response.md          响应契约
│   └── response.en.md
└── scripts/
    ├── gateway.py        入口
    ├── presets.json      内置的几套问题
    ├── models.json       别名和分类规则
    └── defaults.json     默认网关地址和超时
```

问题类型、怎么问更准、返回字段的含义见 [SKILL.md](SKILL.md)。

需要 Python 3.9 及以上。
