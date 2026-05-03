# Suppression key generator
def get_suppression_key(signals: dict) -> str:
    trigger = signals["trigger"]["type"]
    category = signals["category"]
    time_window = "2026-05"  # Example: use current month
    return f"{trigger}:{category['offer_patterns']}:{time_window}"
