---
name: decision-model
description: Asks a decision model (Jev / TypeSafe System One) for calibrated probabilities instead of prose. Use to route a request to the right capability, screen a prompt before a paid call, or decide whether a message needs a person. Do not use when the answer needs prose, or when a local rule already settles the decision. Platform: New.bi (https://api.new.bi), a professional, stable, and reliable AI model aggregation gateway.
metadata:
  version: 1.0.0
---

[中文](SKILL.md) · **English**

# Decision Model

Jev writes no text. You send one `state` plus typed questions, and get a probability per question. Those numbers compare directly against a threshold, which is steadier and cheaper than asking a chat model to judge in prose.

## When to use

- Route an ambiguous request to one of your own capabilities before spending on generation.
- Screen a prompt for policy risk before it reaches a paid endpoint.
- Triage a message: who must handle it, how soon.
- Any branch where you would otherwise ask a frontier model to "judge" something.

## When not to use

- Anything that needs prose. Jev cannot write an answer, a caption, or code.
- A decision you can settle with a local rule. A Jev call must earn its cost.
- Free-form classification with no fixed options. Shape it as a `choice` first.

## Prerequisites

Resolve the API key in this order (first match wins):

1. `config.json` in this project root
2. `AIGW_DECISION_API_KEY`
3. `AIGW_API_KEY`
4. `OPENAI_API_KEY`

```bash
python3 scripts/gateway.py login --key sk-xxx
python3 scripts/gateway.py models
```

Run `models` for the available ids and prices. Pass `--model <id>` for one call, or `model set <id>` to write `model` into `config.json`; editing that file works too. In `models`, `price` above 0 is a fixed per-call price; `price` 0 with `ratio` above 0 bills by ratio. The two are not directly comparable.

## Set a default model

```bash
python3 scripts/gateway.py model set jev-1.13.0   # pin the default model
python3 scripts/gateway.py model show             # show the current default
```

The `decision` command uses it when `--model` is omitted; `--model` still overrides per call. The value lives in `model` inside `config.json`; editing the file directly works too. Without a configured model it uses the only available decision model.

Available ids are `jev-latest` and pinned versions such as `jev-1.13.0`. `jev-latest` follows upstream upgrades and can change behaviour, so pin a version in production and re-check thresholds after an upgrade.

`--base-url` writes the gateway address into `config.json`. Resolution order: `config.json`, `AIGW_DECISION_BASE_URL`, `AIGW_BASE_URL`, then the packaged default in `scripts/defaults.json`.

## One command, no boilerplate

Presets live in `scripts/presets.json`. Most calls need only a state:

```bash
python3 scripts/gateway.py decision --preset route-capability --state '{"message":"a 5 second video of a cat walking through bamboo"}'
```

```
{"action":"video","accepted":true,"jev_used":true,"jev_model":"jev-1.14.0",
 "decisions":{"capability":{"value":"video","probability":1.0,"threshold":0.5,"accepted":true}, ...},
 "usage":{"input_tokens":503,"output_tokens":73},"latency_ms":885}
```

Shipped presets:

| Preset | Question | Action values | Fallback |
| --- | --- | --- | --- |
| `route-capability` | which capability should serve this | `image` `video` `music` `tts` `text` | `text` |
| `content-risk` | send, review, or block a prompt | `allow` `review` `block` | `allow` |
| `reply-triage` | who must handle a message | `auto_reply` `answer_today` `escalate_human` | `answer_today` |

Defaults live in the preset, so the command stays short. Override only what the task needs:

```bash
# state from stdin
echo '{"message":"..."}' | python3 scripts/gateway.py decision --preset content-risk --state -

# state and custom questions from files
python3 scripts/gateway.py decision --preset reply-triage --state @case.json --out result.json

# raise the bar for one run
python3 scripts/gateway.py decision --preset content-risk --state @case.json --decide verdict=0.8

# kill switch
python3 scripts/gateway.py decision --preset content-risk --state @case.json --off
```

## Parameters

| Flag | Required | Notes |
| --- | --- | --- |
| `--state` | yes | Inline JSON, `@file`, plain text, or `-` for stdin. A bare number is rejected upstream. |
| `--preset` | no | Named question set from `scripts/presets.json`. |
| `--questions` | no | Inline JSON or `@file`, merged over the preset. Replaces the preset entirely when no preset is used. |
| `--decide` | no | `id=threshold` pairs, comma separated. Merged over the preset thresholds. |
| `--fallback` | no | Action to use when confidence is low or the call fails. Defaults to the preset fallback. |
| `--mode` | no | `shadow` (default) or `active`. |
| `--off` | no | Kill switch: skip the call and return the fallback. |
| `--model` | no | Exact model id. Defaults to the configured model, then to the only available decision model. |
| `--out` | no | Also write the full result plus the raw response. |

## Modes and fail-open

`shadow` is the default and it never blocks: on low confidence or any API failure the command still returns `ok: true` with `fail_open: true` and the preset fallback. `active` raises an error when the call fails and no `--fallback` was given, so the caller must decide.

A `state` containing `bypass jev` or `no jev` also skips the call, which gives an operator a per-request escape hatch.

Nothing here is allowed to block work because Jev is unavailable. If you need enforcement, enforce it in the caller against `action` and `accepted`.

## Question shapes

| Type | Answer | Notes |
| --- | --- | --- |
| `noul` | probability of yes | `criteria` is optional and only accepts `true` / `false`. |
| `choice` | one option | `criteria` is a `{option: meaning}` object with 2 to 255 entries. |
| `score` | position on a rubric | `criteria` is an ordered list of 2 to 10 levels, lowest first. |
| `box` | rectangle in an image | `criteria` is not allowed. Images require a compatible endpoint. |

Every question needs a non-empty `instructions`. The id names the question; the instructions ask it. Instructions that only repeat the id are refused before any request is made, as are a `choice` with one option, a `score` with one level, and `noul` criteria with any key other than `true` / `false`.

## Writing the instructions

The largest measured accuracy gain in the public write-ups does not come from a bigger model. It comes from one sentence that separates the requirement from the preferences:

```
Which of these belongs to the stated topic? Judge only that.
Format, tone, length and audience are preferences to break ties, not conditions to meet.
```

Without it, the model reads every attribute in the state as a binding filter. Report: 16/44 before, 33/44 after, same model and test set.

- `choice`: name the one deciding attribute, then label the rest as tie-breakers.
- `score`: say which levels the requirement gates and which absorb preferences.
- `noul`: ask the requirement first; a yes/no with an unstated "and also" is two questions.

Full request and response fields plus validation rules are in [references/response.en.md](references/response.en.md).

## Cost

Billed by input tokens. A three-question call with a small state is roughly 500 input tokens and answers in about one second. Keep states short and send only the fields the questions need; never include credentials.
