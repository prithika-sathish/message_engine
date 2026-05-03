import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

_PROMPT_TEMPLATE = """Convert the structured merchant insight into a concise, high-conversion message.

STRICT RULES:

* Do NOT add or remove any facts, numbers, or percentages
* Preserve predicted impact exactly
* Keep ≤ 2 sentences before CTA
* Maintain causal flow: observation → implication → action → outcome
* Write for the merchant owner: no insider words (hero, tags, retrieval, SKU, storefront signals, dashboards).
* Use a crisp, professional tone (like a growth analyst)
* Do NOT include CTA in the output

Return only the message text.

INPUT:
__BLUEPRINT_JSON__
"""

_MAX_CACHE_ENTRIES = 256
_RESPONSE_CACHE: "OrderedDict[str, str]" = OrderedDict()


def _slim_blueprint(blueprint: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "body",
        "insight",
        "metric",
        "predicted_impact",
        "risk_if_ignored",
        "percentile_band",
        "tone_profile",
        "suggestion",
        "action",
    )
    return {k: blueprint.get(k) for k in keys if blueprint.get(k) not in (None, "", [])}


def _cache_key(slim: Dict[str, Any]) -> str:
    raw = json.dumps(slim, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Optional[str]:
    if key not in _RESPONSE_CACHE:
        return None
    _RESPONSE_CACHE.move_to_end(key)
    return _RESPONSE_CACHE[key]


def _cache_put(key: str, value: str) -> None:
    _RESPONSE_CACHE[key] = value
    _RESPONSE_CACHE.move_to_end(key)
    while len(_RESPONSE_CACHE) > _MAX_CACHE_ENTRIES:
        _RESPONSE_CACHE.popitem(last=False)


def _mask_decimals(s: str) -> str:
    return re.sub(r"(\d)\.(\d)", r"\1․\2", s.replace("%", "##PCT##"))


def _unmask_decimals(s: str) -> str:
    return s.replace("․", ".").replace("##PCT##", "%")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _nums(s: str) -> list:
    return re.findall(r"\d+(?:\.\d+)?%?", _mask_decimals(s))


def _numeric_fingerprint(blueprint: Dict[str, Any]) -> set:
    parts = [
        str(blueprint.get("body") or ""),
        str(blueprint.get("predicted_impact") or ""),
    ]
    return set(_nums(" ".join(parts)))


def _sentence_count(s: str) -> int:
    masked = _mask_decimals(s)
    return len([p for p in masked.split(".") if p.strip()])


def _has_impact(s: str) -> bool:
    low = s.lower()
    if any(
        k in low
        for k in (
            "improve",
            "increase",
            "recover",
            "restore",
            "lift",
            "headroom",
            "traction",
            "uplift",
        )
    ):
        return True
    if re.search(r"~\s*\d", low):
        return True
    if re.search(r"\d+\s*%", low) and any(
            x in low for x in ("ctr", "aov", "vs peer", "vs peers", "gap", "drift")
    ):
        return True
    return False


def _valid(llm_text: str, blueprint: Dict[str, Any]) -> bool:
    if not llm_text or len(llm_text.strip()) < 12:
        return False
    body = str(blueprint.get("body") or "")
    fp = _numeric_fingerprint(blueprint)
    if fp:
        if set(_nums(llm_text)) != fp:
            return False
    else:
        if _nums(llm_text) != _nums(body):
            return False
    if _sentence_count(llm_text) > 2:
        return False
    if body and len(llm_text) > max(700, min(1200, len(body) * 4)):
        return False
    if not _has_impact(llm_text):
        return False
    return True


def _strip_trailing_cta(llm_text: str, cta: str) -> str:
    if not cta or not llm_text:
        return llm_text
    nt, nc = _norm(llm_text), _norm(cta)
    if nc and nt.endswith(nc):
        pat = re.compile(re.escape(cta.strip()) + r"\s*$", re.IGNORECASE)
        return pat.sub("", llm_text).rstrip(" \n\"\t'")
    return llm_text


def _cap_two_sentences(llm_text: str) -> str:
    masked = _mask_decimals(llm_text)
    parts = [p.strip() for p in masked.split(".") if p.strip()]
    if len(parts) <= 2:
        return _unmask_decimals(llm_text.rstrip()).strip()
    joined = ". ".join(parts[:2]).rstrip(".") + "."
    return _unmask_decimals(joined).strip()


def _gemini_generate_text(
    api_key: str, prompt: str, model: str, timeout_sec: float
) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={urllib.parse.quote(api_key, safe='')}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    cand = raw.get("candidates") or []
    if not cand:
        raise ValueError("no candidates")
    parts = ((cand[0].get("content") or {}).get("parts")) or []
    texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
    return "".join(texts).strip()


def _clean_llm_body(text: str, max_len: int = 600) -> str:
    t = text.strip()
    t = re.sub(r"^[\s\"']+|[\s\"']+$", "", t)
    for line in ("CTA:", "Call to action:", "---"):
        if line.lower() in t.lower():
            t = t.split(line)[0].strip()
    if len(t) > max_len:
        t = t[: max_len - 1].rsplit(" ", 1)[0] + "."
    return t


def render_message(blueprint: Dict[str, Any]) -> Tuple[str, str, str]:
    body = blueprint.get("body") or ""
    cta = blueprint.get("cta") or ""
    send_as = "system"

    if os.environ.get("VERA_USE_GEMINI_RENDERER", "").lower() not in (
        "1",
        "true",
        "yes",
    ):
        return body, cta, send_as

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return body, cta, send_as

    model = os.environ.get("VERA_GEMINI_MODEL", "gemini-1.5-flash")
    try:
        timeout_sec = float(os.environ.get("VERA_GEMINI_TIMEOUT_SEC", "1.0"))
    except ValueError:
        timeout_sec = 1.0
    timeout_sec = max(0.8, min(timeout_sec, 12.0))

    slim = _slim_blueprint(blueprint)
    prompt = _PROMPT_TEMPLATE.replace(
        "__BLUEPRINT_JSON__",
        json.dumps(slim, ensure_ascii=False, indent=2),
    )
    ck = _cache_key(slim)

    try:
        cached = _cache_get(ck)
        if cached is not None:
            polished = _clean_llm_body(cached)
            polished = _strip_trailing_cta(polished, cta)
            polished = _cap_two_sentences(polished)
            if _valid(polished, blueprint):
                return polished, cta, send_as
            try:
                del _RESPONSE_CACHE[ck]
            except KeyError:
                pass

        out = _gemini_generate_text(api_key, prompt, model, timeout_sec)
        polished = _clean_llm_body(out)
        polished = _strip_trailing_cta(polished, cta)
        polished = _cap_two_sentences(polished)

        if not _valid(polished, blueprint):
            return body, cta, send_as

        _cache_put(ck, polished)
        return polished, cta, send_as

    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        pass
    except Exception:
        pass

    return body, cta, send_as
