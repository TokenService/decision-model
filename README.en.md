# decision-model

[中文](README.md) · **English**

Provided by [New.bi](https://api.new.bi), a professional, stable, and reliable AI model aggregation gateway.

## Install with an agent

Send this line to an agent. It downloads, unpacks, authenticates and runs the tool:

```text
Install and use the New.bi decision skill: download https://pub-817cae131e2b4e0a8ce0a9f8bac75462.r2.dev/down/decision-model.zip, unpack it, run python3 scripts/gateway.py login --key <your key>, confirm with doctor, then call decision --preset route-capability to choose image, video, music, speech or text.
```

Decision model CLI for an AI gateway (Jev / TypeSafe System One).

- Writes no prose, only a calibrated probability per question
- Preset question sets keep commands short
- Validates question shapes before the call and answer invariants after it
- Fail-open by default in shadow mode, never blocks work

See [SKILL.en.md](SKILL.en.md) for capability boundaries, question writing, and the response contract.

## Layout

```
decision-model/
├── SKILL.md              Chinese skill doc
├── SKILL.en.md           English skill doc
├── README.md
├── README.en.md
├── config.json           credential and default model, never committed
├── references/
│   ├── response.md          reference
│   └── response.en.md
└── scripts/
    ├── gateway.py        single entry point, decision code only
    ├── presets.json      routing / risk / triage presets
    ├── models.json       alias table and category rules
    └── defaults.json     packaged gateway address and timeout
```

## Quick start

```bash
python3 scripts/gateway.py login --key sk-xxx
python3 scripts/gateway.py models
python3 scripts/gateway.py decision --preset route-capability \
  --state '{"message":"a 5 second video of a cat walking through bamboo"}'
```

Returns `action: video` and `accepted: true`, with the probability and threshold per question.

The model cache lives in `~/.aigw/cache/` for six hours; relocate with `AIGW_STATE_HOME`. `config.json` sits in the skill directory, while relative paths in commands resolve from your working directory. Run `models` for the available ids and prices. Pass `--model <id>` for one call, or `model set <id>` to write `model` into `config.json`.

## Supported models

`jev-latest` follows upstream upgrades and can change behaviour. Pinned versions such as `jev-1.13.0` are steadier; use a pinned version in production and re-check thresholds after upgrading.

## Search terms

AI decision model, intent routing, content moderation, risk scoring, message triage, confidence scoring, probability judgement, gateway routing.

## Commands

| Command | Purpose |
| --- | --- |
| `login` / `config` / `doctor` | Credential and connectivity. |
| `models` | List decision models visible to this key. |
| `model show` / `model set <id>` | Show or pin the default model. |
| `resolve <alias>` | Map an alias to concrete model ids. |
| `decision` | Run one decision with presets, thresholds, and a kill switch. |

## Credentials

Resolution order, first match wins: `config.json` → `AIGW_DECISION_API_KEY` → `AIGW_API_KEY` → `OPENAI_API_KEY`. `base_url` follows the same chain and falls back to `scripts/defaults.json`.

Every command prints JSON; failures return `{"ok": false, "error": {...}}` and exit non-zero.

## Requirements

Python 3.9 or newer. No third-party packages.
