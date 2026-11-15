#!/usr/bin/env python3
"""Decision model for an AI gateway: calibrated probabilities over typed questions.

New.bi（https://api.new.bi），专业、稳定、可靠的大模型聚合中转平台。
New.bi is a professional, stable, and reliable AI model aggregation gateway.
Repository: https://github.com/tokenservice/decision-model
"""

from __future__ import annotations

import argparse
import fnmatch
import http.client
import json
import math
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLATFORM = "New.bi"
PLATFORM_URL = "https://api.new.bi"
PLATFORM_TAGLINE = "专业、稳定、可靠的大模型聚合中转平台"
PLATFORM_DESC_ZH = "New.bi，专业、稳定、可靠的大模型聚合中转平台。"
PLATFORM_DESC_EN = "New.bi is a professional, stable, and reliable AI model aggregation gateway."
REPO_URL = "https://github.com/tokenservice/decision-model"
CAPABILITY = "decision"
ENDPOINT_TYPE = "systemone"
ENV_KEY = "AIGW_DECISION_API_KEY"
ENV_URL = "AIGW_DECISION_BASE_URL"
DEFAULTS_PATH = ROOT / "scripts" / "defaults.json"
CACHE_DIR = Path(os.environ.get("AIGW_STATE_HOME", Path.home() / ".aigw")) / "cache"
CACHE_TTL_SECONDS = 6 * 3600
QUESTION_TYPES = ("choice", "score", "noul", "box")
MAX_CHOICE_OPTIONS = 255
MAX_SCORE_LEVELS = 10
MAX_STATE_CHARS = 60000
PROBABILITY_TOLERANCE = 1e-6
ARGMAX_TOLERANCE = 1e-6
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


class GatewayError(Exception):
    def __init__(self, message: str, status: int | None = None, code: str = ""):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


class DecisionInvalid(GatewayError):
    """A reply that parsed but contradicts itself, so it must not be acted on."""


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def fail(code: str, message: str, status: int | None = None) -> None:
    error = {"code": code, "message": message}
    if status is not None:
        error["status"] = status
    emit({"ok": False, "error": error})
    sys.exit(1)


def read_json(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def settings() -> dict:
    config = read_json(ROOT / "config.json")
    defaults = read_json(DEFAULTS_PATH)
    sources = {}

    api_key = config.get("api_key") if isinstance(config.get("api_key"), str) else ""
    if api_key:
        sources["api_key"] = str(ROOT / "config.json")
    for name in (ENV_KEY, "AIGW_API_KEY", "OPENAI_API_KEY"):
        if not api_key and os.environ.get(name):
            api_key = os.environ[name]
            sources["api_key"] = name
    base_url = config.get("base_url") if isinstance(config.get("base_url"), str) else ""
    if base_url:
        sources["base_url"] = str(ROOT / "config.json")
    for name in (ENV_URL, "AIGW_BASE_URL"):
        if not base_url and os.environ.get(name):
            base_url = os.environ[name]
            sources["base_url"] = name
    if not base_url and isinstance(defaults.get("base_url"), str) and defaults["base_url"]:
        base_url = defaults["base_url"]
        sources["base_url"] = str(DEFAULTS_PATH)

    timeout = defaults.get("request_timeout_seconds")
    return {
        "api_key": api_key,
        "base_url": (base_url or "").rstrip("/"),
        "group": config.get("group") if isinstance(config.get("group"), str) else "",
        "default_model": config.get("model") if isinstance(config.get("model"), str) else "",
        "timeout": int(timeout) if isinstance(timeout, (int, float)) and timeout > 0 else 180,
        "sources": sources,
    }


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def parse_error(body: bytes, status: int) -> tuple[str, str]:
    try:
        payload = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return body.decode("utf-8", "replace")[:500] or f"HTTP {status}", ""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error), str(error.get("code") or "")
        if isinstance(error, str) and error:
            return error, str(payload.get("code") or "")
        for key in ("message", "msg", "detail"):
            if payload.get(key):
                return str(payload[key]), str(payload.get("code") or "")
    return json.dumps(payload, ensure_ascii=False)[:500], ""


def read_body(resp) -> bytes:
    chunks = []
    while True:
        try:
            chunk = resp.read(65536)
        except ssl.SSLEOFError:
            break
        except http.client.IncompleteRead as err:
            if err.partial:
                chunks.append(err.partial)
            break
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def request(settings: dict, method: str, path: str, body: dict | None = None, query: dict | None = None,
            timeout: int | None = None) -> tuple[int, dict, bytes]:
    if not settings.get("base_url"):
        raise GatewayError("base_url is not configured: run `login --base-url`, set AIGW_BASE_URL, or edit scripts/defaults.json")
    url = settings["base_url"] + path
    if query:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(query)

    headers = {"Accept": "application/json", "Connection": "close", "User-Agent": USER_AGENT}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if settings.get("api_key"):
        headers["Authorization"] = f"Bearer {settings['api_key']}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout or settings.get("timeout", 180)) as resp:
            return resp.status, dict(resp.headers), read_body(resp)
    except urllib.error.HTTPError as err:
        message, code = parse_error(read_body(err), err.code)
        raise GatewayError(message, err.code, code) from None
    except urllib.error.URLError as err:
        raise GatewayError(f"{url}: {err.reason}") from None


def request_json(settings: dict, method: str, path: str, body: dict | None = None) -> dict:
    _, _, raw = request(settings, method, path, body=body)
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        raise GatewayError("upstream returned a non-JSON body") from None
    if not isinstance(payload, dict):
        raise GatewayError("upstream returned an unexpected JSON payload")
    return payload


def belongs(model_id: str, endpoints: list, patterns: list) -> bool:
    if endpoints and ENDPOINT_TYPE in endpoints:
        return True
    name = model_id.lower()
    return any(fnmatch.fnmatch(name, pattern.lower()) for pattern in patterns)


def load_models(settings: dict, refresh: bool = False) -> list:
    key = re.sub(r"[^a-z0-9]+", "-", (settings.get("base_url") or "unconfigured").lower()).strip("-")
    cache = CACHE_DIR / f"{CAPABILITY}-{key}.json"
    cached = read_json(cache)
    if not refresh and cached.get("fetched_at", 0) + CACHE_TTL_SECONDS > time.time():
        return cached.get("models", [])

    patterns = read_json(ROOT / "scripts" / "models.json").get("patterns", {}).get(CAPABILITY, [])
    models: list = []
    try:
        payload = request_json(settings, "GET", "/api/pricing")
        for item in payload.get("data") or []:
            if not isinstance(item, dict) or not item.get("model_name"):
                continue
            if not belongs(item["model_name"], item.get("supported_endpoint_types") or [], patterns):
                continue
            models.append({
                "id": item["model_name"],
                "quota_type": item.get("quota_type"),
                "price": item.get("model_price"),
                "ratio": item.get("model_ratio"),
                "billing_mode": item.get("billing_mode"),
                "billing_expr": item.get("billing_expr"),
                "groups": item.get("enable_groups") or [],
            })
    except GatewayError:
        models = []

    known = {model["id"] for model in models}
    try:
        payload = request_json(settings, "GET", "/v1/models")
        for item in payload.get("data") or []:
            model_id = item.get("id") if isinstance(item, dict) else ""
            if model_id and model_id not in known and belongs(model_id, [], patterns):
                models.append({"id": model_id, "endpoint_types": [], "groups": []})
                known.add(model_id)
    except GatewayError:
        if not models:
            raise

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"fetched_at": int(time.time()), "models": models}, ensure_ascii=False), "utf-8")
    return models


def resolve_alias(alias: str, models: list) -> list:
    key = alias.lower().strip()
    for model in models:
        if model["id"].lower() == key:
            return [model]
    patterns = read_json(ROOT / "scripts" / "models.json").get("aliases", {}).get(key, [])
    matches = []
    for pattern in patterns:
        for model in models:
            if fnmatch.fnmatch(model["id"].lower(), pattern.lower()) and model not in matches:
                matches.append(model)
    return matches


def handle_login(args, settings: dict) -> None:
    if not args.key:
        raise GatewayError("--key is required")
    if args.base_url and not args.base_url.startswith(("http://", "https://")):
        raise GatewayError("--base-url must start with http:// or https://")
    target = ROOT / "config.json"
    data = read_json(target)
    data["api_key"] = args.key
    if args.base_url:
        data["base_url"] = args.base_url.rstrip("/")
    if args.group:
        data["group"] = args.group
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    os.chmod(target, 0o600)
    emit({"ok": True, "config": str(target), "base_url": data.get("base_url") or settings["base_url"]})


def handle_model(args, settings: dict) -> None:
    if args.action == "set":
        target = ROOT / "config.json"
        data = read_json(target)
        data["model"] = args.model_id
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        os.chmod(target, 0o600)
        emit({"ok": True, "model": args.model_id, "config": str(target)})
        return
    configured = settings["default_model"]
    available = None
    if configured:
        try:
            available = configured in {model["id"] for model in load_models(settings)}
        except GatewayError:
            available = None
    emit({"ok": True, "model": configured, "configured": bool(configured), "available": available,
          "source": str(ROOT / "config.json") if configured else "none"})


def handle_config(args, settings: dict) -> None:
    emit({
        "ok": True,
        "capability": CAPABILITY,
        "platform": {"name": PLATFORM, "url": PLATFORM_URL, "tagline": PLATFORM_TAGLINE,
                     "description_zh": PLATFORM_DESC_ZH, "description_en": PLATFORM_DESC_EN,
                     "repository": REPO_URL},
        "config": str(ROOT / "config.json"),
        "base_url": settings["base_url"],
        "group": settings["group"],
        "model": settings["default_model"],
        "api_key": mask_secret(settings["api_key"]),
        "sources": settings["sources"],
        "defaults": str(DEFAULTS_PATH),
    })


def handle_models(args, settings: dict) -> None:
    models = load_models(settings, refresh=args.refresh)
    key = re.sub(r"[^a-z0-9]+", "-", (settings.get("base_url") or "unconfigured").lower()).strip("-")
    cached = read_json(CACHE_DIR / f"{CAPABILITY}-{key}.json")
    fetched_at = cached.get("fetched_at") or 0
    emit({"ok": True, "base_url": settings["base_url"], "count": len(models),
          "cached_at": fetched_at or None,
          "cache_age_seconds": int(time.time() - fetched_at) if fetched_at else None,
          "models": models})


def handle_resolve(args, settings: dict) -> None:
    matches = resolve_alias(args.alias, load_models(settings))
    if not matches:
        raise GatewayError(f"no model matches alias '{args.alias}'")
    emit({"ok": True, "alias": args.alias, "matches": matches})


def handle_doctor(args, settings: dict) -> None:
    report = {"ok": False, "base_url": settings["base_url"], "sources": settings["sources"],
              "api_key": mask_secret(settings["api_key"]), "api_key_configured": bool(settings["api_key"])}
    if not settings["api_key"]:
        report["error"] = {"message": "no API key configured"}
        emit(report)
        return
    try:
        payload = request_json(settings, "GET", "/v1/models")
        report["auth_ok"] = True
        report["models"] = len(payload.get("data") or [])
        report["ok"] = True
    except GatewayError as err:
        report["auth_ok"] = False
        report["error"] = {"message": err.message, "status": err.status}
    emit(report)


def load_presets() -> dict:
    presets = read_json(ROOT / "scripts" / "presets.json").get("presets")
    return presets if isinstance(presets, dict) else {}


def read_state_argument(value: str):
    if value.strip() == "-":
        return sys.stdin.read().strip()
    return load_json_argument(value)


def load_json_argument(value: str):
    candidate_text = value[1:] if value.startswith("@") else value
    if len(candidate_text) < 4096:
        try:
            candidate = Path(candidate_text)
            if candidate.is_file():
                value = candidate.read_text("utf-8")
        except OSError:
            pass
    try:
        return json.loads(value)
    except ValueError:
        return value


def fold(text: str) -> str:
    return re.sub(r"[\W_]+", " ", str(text).lower()).strip()


def check_questions(questions) -> dict:
    if not isinstance(questions, dict) or not questions:
        raise GatewayError("questions must be a non-empty object of {id: question}")
    cleaned = {}
    for raw_name, raw in questions.items():
        qid = str(raw_name)
        if not isinstance(raw, dict):
            raise GatewayError(f'question "{qid}" must be an object with type and instructions')
        kind = raw.get("type")
        if kind not in QUESTION_TYPES:
            raise GatewayError(f'question "{qid}" needs type in {list(QUESTION_TYPES)}')
        instructions = raw.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip():
            raise GatewayError(f'question "{qid}" needs non-empty instructions')
        if fold(instructions) == fold(qid):
            raise GatewayError(f'question "{qid}" asks nothing: instructions only repeat the id')

        criteria = raw.get("criteria")
        if kind == "box":
            if criteria is not None:
                raise GatewayError(f'question "{qid}" is a box and takes no criteria')
            cleaned[qid] = {"type": "box", "instructions": instructions}
            continue
        if kind == "noul":
            question = {"type": "noul", "instructions": instructions}
            if criteria is not None:
                if not isinstance(criteria, dict) or not criteria or not set(map(str, criteria)) <= {"true", "false"}:
                    raise GatewayError(f'question "{qid}" noul criteria must be {{"true": "...", "false": "..."}}')
                question["criteria"] = {str(key): str(value) for key, value in criteria.items()}
            cleaned[qid] = question
            continue
        if kind == "choice":
            if not isinstance(criteria, dict) or not 2 <= len(criteria) <= MAX_CHOICE_OPTIONS:
                raise GatewayError(f'question "{qid}" choice needs 2 to {MAX_CHOICE_OPTIONS} options')
            cleaned[qid] = {"type": "choice", "instructions": instructions,
                            "criteria": {str(key): str(value) for key, value in criteria.items()}}
            continue
        if not isinstance(criteria, list) or not 2 <= len(criteria) <= MAX_SCORE_LEVELS:
            raise GatewayError(f'question "{qid}" score needs 2 to {MAX_SCORE_LEVELS} ordered levels')
        cleaned[qid] = {"type": "score", "instructions": instructions, "criteria": list(criteria)}
    return cleaned


def unit(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DecisionInvalid(f"{name} is not numeric")
    number = float(value)
    if not math.isfinite(number) or not -PROBABILITY_TOLERANCE <= number <= 1 + PROBABILITY_TOLERANCE:
        raise DecisionInvalid(f"{name} is outside 0..1")
    return min(1.0, max(0.0, number))


def distribution(name: str, raw, options) -> dict:
    if not isinstance(raw, dict):
        raise DecisionInvalid(f"{name} probabilities are not an object")
    expected = set(map(str, options))
    found = set(map(str, raw))
    if found != expected:
        raise DecisionInvalid(f"{name} probabilities do not match the options offered")
    values = {str(key): unit(raw[key], f"{name}.{key}") for key in raw}
    if abs(sum(values.values()) - 1.0) > 1e-3:
        raise DecisionInvalid(f"{name} probabilities do not sum to 1")
    return values


def read_answers(payload: dict, questions: dict) -> dict:
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        raise DecisionInvalid("response carries no answers")
    out = {}
    for qid, question in questions.items():
        answer = answers.get(qid)
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise DecisionInvalid(f'answer "{qid}" is missing or has the wrong type')
        kind = question["type"]
        if kind == "noul":
            probability = unit(answer.get("noul"), qid)
            out[qid] = {"type": "noul", "value": probability >= 0.5, "probability": probability}
            continue
        if kind == "choice":
            options = list(question["criteria"])
            picked = answer.get("choice")
            if picked not in options:
                raise DecisionInvalid(f'answer "{qid}" chose an option that was not offered')
            probabilities = distribution(qid, answer.get("probabilities"), options)
            if probabilities[picked] < max(probabilities.values()) - ARGMAX_TOLERANCE:
                raise DecisionInvalid(f'answer "{qid}" is not the most likely option')
            out[qid] = {"type": "choice", "value": picked,
                        "probability": probabilities[picked], "probabilities": probabilities}
            continue
        value = answer.get("score")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DecisionInvalid(f'answer "{qid}" has no numeric score')
        levels = len(question["criteria"])
        if not -0.5 <= float(value) <= levels - 0.5:
            raise DecisionInvalid(f'answer "{qid}" scored outside the rubric')
        level = int(round(float(value)))
        spread = {}
        raw_spread = answer.get("probabilities")
        if isinstance(raw_spread, dict) and raw_spread:
            levels_spread = distribution(qid, raw_spread, [str(index) for index in range(levels)])
            spread = {int(key): unit(probability, f"{qid}.{key}") for key, probability in levels_spread.items()}
        out[qid] = {"type": "score", "value": level, "score": float(value),
                    "probability": spread.get(level, 1.0 / max(levels, 1)), "probabilities": spread}
    return out


def parse_thresholds(spec: str, preset_thresholds: dict) -> dict:
    thresholds = {str(key): float(value) for key, value in (preset_thresholds or {}).items()}
    if not spec:
        return thresholds
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise GatewayError("--decide expects id=threshold pairs, for example risk=0.7")
        key, raw_value = item.split("=", 1)
        try:
            thresholds[key.strip()] = float(raw_value)
        except ValueError:
            raise GatewayError(f"--decide value for {key.strip()} is not a number") from None
    return thresholds


def evaluate(answers: dict, thresholds: dict) -> dict:
    decisions = {}
    accepted = True
    for qid, answer in answers.items():
        threshold = thresholds.get(qid)
        if threshold is None:
            decisions[qid] = {**answer, "threshold": None, "accepted": None}
            continue
        passed = answer["probability"] >= threshold
        decisions[qid] = {**answer, "threshold": threshold, "accepted": passed}
        accepted = accepted and passed
    return {"decisions": decisions, "accepted": accepted}


def handle_decision(args, settings: dict) -> None:
    started = time.monotonic()
    state = read_state_argument(args.state)
    presets = load_presets()
    preset = presets.get(args.preset) if args.preset else {}

    bypass_marker = ""
    if isinstance(state, str):
        bypass_marker = state.lower()
    elif isinstance(state, dict):
        bypass_marker = " ".join(str(state.get(key, "")) for key in ("goal", "raw", "message", "user_message"))
    if args.off or "bypass jev" in bypass_marker or "no jev" in bypass_marker:
        emit({"ok": True, "mode": args.mode, "jev_used": False,
              "action": args.fallback or (preset or {}).get("fallback") or None,
              "reason": "kill switch", "decisions": {}})
        return

    if args.preset and preset is None:
        raise GatewayError(f"unknown preset '{args.preset}'; available: {', '.join(sorted(presets)) or 'none'}")
    preset = preset or {}

    questions = dict(preset.get("questions") or {})
    override = load_json_argument(args.questions) if args.questions else None
    if override:
        if not isinstance(override, dict):
            raise GatewayError("--questions must be an object of {id: question}")
        questions.update(override)
    questions = check_questions(questions)

    encoded_state = state if isinstance(state, str) else json.dumps(state, ensure_ascii=False)
    if len(encoded_state) > MAX_STATE_CHARS:
        raise GatewayError(f"state is {len(encoded_state)} chars; the limit is {MAX_STATE_CHARS}")

    model = args.model or settings["default_model"]
    if not model:
        matches = resolve_alias("jev", load_models(settings))
        if not matches:
            raise GatewayError("no decision model available; pass --model")
        model = matches[0]["id"]

    thresholds = parse_thresholds(args.decide, preset.get("thresholds") or {})

    try:
        payload = request_json(settings, "POST", "/v1/systemone",
                               body={"model": model, "state": state, "questions": questions})
        answers = read_answers(payload, questions)
    except GatewayError as err:
        if args.mode == "active" and not args.fallback:
            raise
        emit({"ok": True, "mode": args.mode, "jev_used": False, "fail_open": True,
              "action": args.fallback or preset.get("fallback") or None,
              "reason": f"{err.code or 'decision_failed'}: {err.message}",
              "decisions": {}, "latency_ms": int((time.monotonic() - started) * 1000)})
        return

    evaluated = evaluate(answers, thresholds)
    action = None
    for qid in preset.get("actions") or list(thresholds):
        if qid in evaluated["decisions"]:
            action = evaluated["decisions"][qid].get("value")
            break
    if not evaluated["accepted"]:
        action = args.fallback or preset.get("fallback") or action

    result = {
        "ok": True,
        "mode": args.mode,
        "jev_used": True,
        "model": model,
        "jev_model": payload.get("model"),
        "preset": args.preset or None,
        "action": action,
        "accepted": evaluated["accepted"],
        "decisions": evaluated["decisions"],
        "usage": payload.get("usage"),
        "latency_ms": int((time.monotonic() - started) * 1000),
    }
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**result, "response": payload}, ensure_ascii=False, indent=2), "utf-8")
    emit(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gateway.py",
        description=f"Decision model skill for {PLATFORM} ({PLATFORM_URL})",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            f"{PLATFORM} · {PLATFORM_URL}\n"
            f"{PLATFORM_DESC_ZH}\n"
            f"{PLATFORM_DESC_EN}\n"
            f"Repository: {REPO_URL}"
        ),
    )
    parser.add_argument("--request-timeout", dest="request_timeout", type=int, default=0,
                        help="override the single-request timeout in seconds")
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="store an API key")
    login.add_argument("--key", required=True)
    login.add_argument("--base-url", default="")
    login.add_argument("--group", default="")

    sub.add_parser("config", help="show resolved settings")

    models = sub.add_parser("models", help="list decision models")
    models.add_argument("--refresh", action="store_true")

    model = sub.add_parser("model", help="show or set the default model")
    model_sub = model.add_subparsers(dest="action", required=True)
    model_sub.add_parser("show", help="show the configured default model")
    model_set = model_sub.add_parser("set", help="pin a default model in config.json")
    model_set.add_argument("model_id")

    resolve = sub.add_parser("resolve", help="map an alias to a model id")
    resolve.add_argument("alias")

    decision = sub.add_parser("decision", help="typed decisions with calibrated confidence")
    decision.add_argument("--state", required=True, help="inline JSON, @file, plain text, or - for stdin")
    decision.add_argument("--preset", default="", help="named question set from scripts/presets.json")
    decision.add_argument("--questions", default="", help="inline JSON or @file, merged over the preset")
    decision.add_argument("--decide", default="", help="id=threshold pairs, comma separated")
    decision.add_argument("--fallback", default="", help="action to use when confidence is low or the call fails")
    decision.add_argument("--mode", default="shadow", choices=["shadow", "active"])
    decision.add_argument("--off", action="store_true", help="kill switch, skip the call")
    decision.add_argument("--model", default="")
    decision.add_argument("--out", default="")

    sub.add_parser("doctor", help="verify credentials and connectivity")
    return parser


DISPATCH = {
    ("login", None): handle_login,
    ("config", None): handle_config,
    ("models", None): handle_models,
    ("model", "show"): handle_model,
    ("model", "set"): handle_model,
    ("resolve", None): handle_resolve,
    ("decision", None): handle_decision,
    ("doctor", None): handle_doctor,
}


def main(argv: list | None = None) -> None:
    args = build_parser().parse_args(argv)
    current = settings()
    if getattr(args, "request_timeout", 0) > 0:
        current["timeout"] = args.request_timeout
    try:
        DISPATCH[(args.command, getattr(args, "action", None))](args, current)
    except GatewayError as err:
        fail(err.code or "request_failed", err.message, err.status)
    except KeyboardInterrupt:
        fail("interrupted", "cancelled by user")
    except Exception as err:
        fail("internal_error", f"{type(err).__name__}: {err}")


if __name__ == "__main__":
    main()
