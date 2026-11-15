---
name: decision-model
description: 调用决策模型（Jev / TypeSafe System One），对带类型的问题给出 0 到 1 的概率。用于生成前的路由判断、内容风险筛查、消息分诊。 平台：New.bi（https://api.new.bi），专业、稳定、可靠的大模型聚合中转平台。
metadata:
  version: 1.0.0
---

**中文** · [English](SKILL.en.md)

# 决策模型

输入一段 state 和几个问题，模型对每个问题返回概率。它不写文字，也不解释理由。

概率可以直接和阈值比。同样一条判断，让 chat 模型写一句话再解析，格式会飘，也贵。

## 什么时候用

- 请求没说要图片还是视频，先判断一次再调用生成接口，避免试错。
- 生成前筛提示词，命中风险就不发请求，省掉一次生成和可能的退款。
- 消息进来了，判断该自动回复、当天处理，还是转人工。

## 什么时候不用

- 要写文案、代码或解释，它不会写。
- 一条 if 能定的判断，比如请求里带了图片就走图生视频。
- 选项还没定下来的分类，先把选项写出来。

## 准备

密钥按顺序查找，先用找到的：

1. 项目根目录 `config.json` 里的 `api_key`
2. `AIGW_DECISION_API_KEY`
3. `AIGW_API_KEY`
4. `OPENAI_API_KEY`

```bash
python3 scripts/gateway.py login --key sk-xxx
python3 scripts/gateway.py models
```

用 `models` 查可用模型和价格。单次指定用 `--model <id>`；固定默认用 `model set <id>`，它写进项目根目录 `config.json` 的 `model` 字段，也可以直接改这个文件。 `models` 里 `price` 大于 0 是按次固定价，`price` 为 0 且 `ratio` 大于 0 是按倍率计费，两者不能直接比大小。

## 固定默认模型

```bash
python3 scripts/gateway.py model set jev-1.13.0
python3 scripts/gateway.py model show
```

设置后 `decision` 不带 `--model` 就用它，`--model` 仍然可以临时覆盖。值写在项目根目录 `config.json` 的 `model` 字段，手改这个文件也一样。 没设置时用目录里唯一的决策模型。

型号有 `jev-latest` 和固定版本（`jev-1.13.0`）。`jev-latest` 跟着上游升级，行为会变，生产上建议固定版本，升级后重新看一眼阈值。

## 调用

预设写在 `scripts/presets.json`，大多数情况只给 state：

```bash
python3 scripts/gateway.py decision --preset route-capability --state '{"message":"a 5 second video of a cat walking through bamboo"}'
```

返回：

```json
{"action":"video","accepted":true,"jev_used":true,"jev_model":"jev-1.14.0",
 "decisions":{"capability":{"value":"video","probability":1.0,"threshold":0.5,"accepted":true}},
 "usage":{"input_tokens":495,"output_tokens":73},"latency_ms":1259}
```

预设和它们的 action 值：

| 预设 | 问什么 | action 取值 | 兜底 |
| --- | --- | --- | --- |
| `route-capability` | 该走哪个能力 | `image` `video` `music` `tts` `text` | `text` |
| `content-risk` | 放行、复核还是拦截 | `allow` `review` `block` | `allow` |
| `reply-triage` | 该谁处理 | `auto_reply` `answer_today` `escalate_human` | `answer_today` |

阈值和兜底都在预设里，命令才短。只改这次需要的：

```bash
# state 从管道来
echo '{"message":"..."}' | python3 scripts/gateway.py decision --preset content-risk --state -

# state 从文件读，结果另存
python3 scripts/gateway.py decision --preset reply-triage --state @case.json --out result.json

# 这次把阈值抬到 0.8
python3 scripts/gateway.py decision --preset content-risk --state @case.json --decide verdict=0.8

# 跳过调用
python3 scripts/gateway.py decision --preset content-risk --state @case.json --off
```

## 参数

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--state` | 是 | 内联 JSON、`@文件`、纯文本，或 `-` 读标准输入。裸数字上游不认。 |
| `--preset` | 否 | `scripts/presets.json` 里的问题集。 |
| `--questions` | 否 | 内联 JSON 或 `@文件`，按 id 覆盖预设里的问题。不用预设时整套替换。 |
| `--decide` | 否 | `id=阈值`，逗号分隔，覆盖预设阈值。 |
| `--fallback` | 否 | 置信度不够或调用失败时返回的 action。默认用预设里的兜底。 |
| `--mode` | 否 | `shadow`（默认）或 `active`。 |
| `--off` | 否 | 不调用，直接返回兜底。 |
| `--model` | 否 | 指定模型，默认用配置文件里的。 |
| `--out` | 否 | 把完整结果和原始响应写进文件。 |

## 失败时怎么办

默认 `shadow`：调用失败或概率低于阈值，命令照样返回 `ok: true`，带上 `fail_open: true` 和兜底的 action，业务不会卡住。

`active`：调用失败且没给 `--fallback` 时直接报错，由调用方决定。

`state` 里出现 `bypass jev` 或 `no jev` 也会跳过调用，方便临时关掉。

需要强制执行的话，自己看 `action` 和 `accepted` 做判断。

## 问题怎么写

| 类型 | 返回 | 写法 |
| --- | --- | --- |
| `noul` | 是/否的概率 | `criteria` 可省略，写也只认 `true` / `false`。 |
| `choice` | 一个选项 | `criteria` 是 `{选项: 说明}`，2 到 255 项。 |
| `score` | 打分档位 | `criteria` 是从低到高的层级列表，2 到 10 级。 |
| `box` | 图片里的矩形 | 不写 `criteria`，需要支持图片的端点。 |

每个问题要有 `instructions`，id 只是名字。只重复 id 的写法、只有一个选项的 choice、只有一级的 score，都会在发请求前被拒。

## 指令怎么写才准

公开实测里准确率提升最大的一次改动跟换模型无关。在 instructions 里说清哪条是硬要求、哪些只是并列时的取舍，效果最明显：

```
下面哪个属于题目说的主题？只看这一点。
格式、语气、长度、受众都只是取舍项，不是必须满足的条件。
```

不写这句，模型会把 state 里每个属性都当成必须满足的条件。同一模型同一题集，带这句 44 题对 33，不带对 16。

- choice：点明唯一决定性的那一条，其余说明可以放弃。
- score：说清哪几档由要求决定，哪几档用来吸收偏好差异。
- noul：只问一条。带「而且」的是非题其实是两个问题。

请求与响应的完整字段、校验规则见 [references/response.md](references/response.md)。

## 成本

按输入 token 计费。三个问题加一小段 state，大约 500 输入 token，一秒左右返回。state 只放问题需要的字段，别放密钥。
