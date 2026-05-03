# Extracts structured signals from raw context JSON (grounded inputs only).


def _opt_float(raw: dict, key: str):
    if key not in raw or raw[key] is None:
        return None
    try:
        return float(raw[key])
    except (TypeError, ValueError):
        return None


def _opt_int(raw: dict, key: str, default: int = 0):
    if key not in raw or raw[key] is None:
        return default
    try:
        return int(raw[key])
    except (TypeError, ValueError):
        return default


def extract_signals(context: dict) -> dict:
    merchant_raw = context.get("merchant") or {}

    ctr = _opt_float(merchant_raw, "ctr")
    ctr_peer_median = _opt_float(merchant_raw, "ctr_peer_median")
    if ctr is not None and ctr_peer_median is not None:
        ctr_delta = ctr - ctr_peer_median
    else:
        ctr_delta = None

    conversion_rate = _opt_float(merchant_raw, "conversion_rate")

    merchant_name = (
        merchant_raw.get("name")
        or (merchant_raw.get("identity") or {}).get("name")
        or ""
    )
    merchant_name = str(merchant_name).strip()

    merchant = {
        "name": merchant_name,
        "ctr": ctr,
        "ctr_peer_median": ctr_peer_median,
        "ctr_delta": ctr_delta,
        "conversion_rate": conversion_rate,
        "inactivity_days": _opt_int(merchant_raw, "inactivity_days", 0),
        "recent_trend": str(merchant_raw.get("recent_trend") or ""),
        "has_active_offer": bool(merchant_raw.get("has_active_offer", False)),
        "performance": merchant_raw.get("performance")
        if isinstance(merchant_raw.get("performance"), dict)
        else {},
    }

    trigger_raw = context.get("trigger") or {}

    trigger_type = str(trigger_raw.get("type", "neutral") or "neutral")
    strength_score = float(trigger_raw.get("strength_score", 0.8) or 0.8)
    recency_weight = float(trigger_raw.get("recency_weight", 1.0) or 1.0)
    urgency = strength_score * recency_weight

    trigger = {
        "type": trigger_type,
        "strength_score": strength_score,
        "recency_weight": recency_weight,
        "urgency": urgency,
    }

    category_raw = context.get("category") or {}

    category = {
        "name": str(category_raw.get("name") or "general").strip(),
        "tone": str(category_raw.get("tone") or "professional"),
        "typical_cta_style": str(
            category_raw.get("typical_cta_style") or "binary_yes_no"
        ),
        "benchmark_ctr": _opt_float(category_raw, "benchmark_ctr"),
        "voice": category_raw.get("voice")
        if isinstance(category_raw.get("voice"), dict)
        else {},
        "peer_stats": category_raw.get("peer_stats")
        if isinstance(category_raw.get("peer_stats"), dict)
        else {},
    }

    customer = context.get("customer") if isinstance(context.get("customer"), dict) else {}

    return {
        "merchant": merchant,
        "trigger": trigger,
        "category": category,
        "customer": customer,
    }
