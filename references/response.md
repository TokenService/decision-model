# 接口与响应契约

## 接口

```
POST /v1/systemone
{ "model": "jev-1.13.0", "state": {...}, "questions": {...} }
```

```json
{"model":"jev-1.14.0",
 "answers":{"capability":{"type":"choice","choice":"video","confidence":1.0,
                          "probabilities":{"image":0.0,"video":1.0,"music":0.0,"tts":0.0,"text":0.0}}},
 "usage":{"input_tokens":530,"output_tokens":60}}
```

返回的 `model` 是实际运行的版本，可能和请求的不一样。换了版本，之前调好的阈值要重新看一遍。

## 会拒绝的回复

命令先校验再用，以下情况按失败处理：

- 没有 `answers`，或某个问题的类型对不上
- choice 的概率键和选项对不上，或加起来不是 1
- choice 选的不是概率最高的那个
- score 超出层级范围
