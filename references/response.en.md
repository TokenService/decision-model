# Endpoints and response contract

## Response contract

```
POST /v1/systemone
{ "model": "jev-1.13.0", "state": {...}, "questions": {...} }
```

```json
{"model":"jev-1.14.0",
 "answers":{"capability":{"type":"choice","choice":"video","confidence":1.0,
                          "probabilities":{"image":0.0,"video":1.0,"music":0.0,"tts":0.0,"text":0.0}},
            "risk_level":{"type":"score","score":1.86,"confidence":0.87,
                          "legend":{"0":"...","1":"...","2":"..."},
                          "probabilities":{"0":0.0,"1":0.13,"2":0.87}}},
 "usage":{"input_tokens":530,"output_tokens":60}}
```

The reply is validated before use. These are refused and treated as fail-open:

- `answers` missing, or a question answered with the wrong type;
- `choice` probabilities that do not cover exactly the offered options, or do not sum to 1;
- a `choice` that is not the highest-probability option;
- a `score` outside the rubric.

The `model` field is the resolved version and can differ from the request, so thresholds tuned on one alias should be re-checked when it moves.
