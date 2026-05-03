# Suppression key generator (deterministic, grounded fields only).


def get_suppression_key(signals: dict) -> str:
    trigger = str(signals["trigger"]["type"])
    cat = str(signals["category"].get("name") or "")
    merchant = signals.get("merchant") or {}
    label = str(merchant.get("name") or "").strip() or "unknown_merchant"
    return f"{trigger}:{cat}:{label}"
