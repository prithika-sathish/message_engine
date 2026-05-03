# Extracts structured signals from raw context JSON

def extract_signals(context: dict) -> dict:
    # Extract and normalize analytics-driven metrics from context
    merchant_raw = context.get("merchant", {})
    trigger_raw = context.get("trigger", {})
    category_raw = context.get("category", {})

    # Merchant metrics
    ctr = float(merchant_raw.get("ctr", 0.021))
    ctr_peer_median = float(merchant_raw.get("ctr_peer_median", 0.034))
    ctr_delta = ctr - ctr_peer_median
    conversion_rate = float(merchant_raw.get("conversion_rate", 0.12))
    inactivity_days = int(merchant_raw.get("inactivity_days", 12))
    recent_trend = merchant_raw.get("recent_trend", "down")
    has_active_offer = bool(merchant_raw.get("has_active_offer", True))

    merchant = {
        "ctr": ctr,
        "ctr_peer_median": ctr_peer_median,
        "ctr_delta": ctr_delta,
        "conversion_rate": conversion_rate,
        "inactivity_days": inactivity_days,
        "recent_trend": recent_trend,
        "has_active_offer": has_active_offer
    }

    # Trigger metrics
    trigger_type = trigger_raw.get("type", "recall")
    strength_score = float(trigger_raw.get("strength_score", 0.8))
    recency_weight = float(trigger_raw.get("recency_weight", 1.0))
    urgency = strength_score * recency_weight

    trigger = {
        "type": trigger_type,
        "strength_score": strength_score,
        "recency_weight": recency_weight,
        "urgency": urgency
    }

    # Category metrics
    category_name = category_raw.get("name", "restaurants")
    tone = category_raw.get("tone", "casual")
    typical_cta_style = category_raw.get("typical_cta_style", "binary_yes_no")
    benchmark_ctr = float(category_raw.get("benchmark_ctr", 0.03))

    category = {
        "name": category_name,
        "tone": tone,
        "typical_cta_style": typical_cta_style,
        "benchmark_ctr": benchmark_ctr
    }

    # Customer (optional, pass through)
    customer = context.get("customer", {})

    return {
        "merchant": merchant,
        "trigger": trigger,
        "category": category,
        "customer": customer
    }