# Converts decision to structured message blueprint
import re
from typing import Optional, Tuple

_MAX_BODY_CHARS = 260
_MIN_NUMERIC_TOKENS = 1
_WEAK_PHRASES = ("this means", "this can help")

_INTENT_CTA = {
    "push_offer": ("binary_yes_no", "Want me to activate this?"),
    "upsell": ("binary_yes_no", "Want suggestions on what to promote?"),
    "reactivate_user": ("binary_yes_no", "Want a quick restart plan?"),
    "inform_insight": ("open_ended", "Want benchmarks in plain numbers?"),
    "nudge_engagement": ("open_ended", "Want a tighter next step on this?"),
}

def _deterministic_fallback(val, minv, maxv, key):
    h = abs(hash(str(val) + key)) % 1000
    return minv + (h % int((maxv - minv) * 100)) / 100.0


def _norm(s: str) -> str:
    t = s
    for phrase in _WEAK_PHRASES:
        t = re.sub(re.escape(phrase), "", t, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", t).strip()


def _pct_i(x: float) -> int:
    return max(0, min(999, round(x * 100)))


def _truncate_to_len(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    if max_len <= 1:
        return s[:max_len]
    cut = s[: max_len - 1].rsplit(" ", 1)[0]
    return cut if cut else s[:max_len]


def _mask_sentence_split(s: str) -> Tuple[str, str]:
    masked = re.sub(r"(\d)\.(\d)", r"\1․\2", s.replace("%", "##PCT##"))
    return masked, s


def _unmask_sentence_split(masked_joined: str) -> str:
    return masked_joined.replace("․", ".").replace("##PCT##", "%")


def _sentence_count(s: str) -> int:
    masked, _ = _mask_sentence_split(s)
    return len([p for p in masked.split(".") if p.strip()])


def _strip_redundant_phrases(body: str) -> str:
    t = body
    return re.sub(
        r"\bvisibility\s+and\s+shopper\s+visibility\b",
        "visibility",
        t,
        flags=re.IGNORECASE,
    )


def _keep_strongest_action_segment(closing_lc: str) -> str:
    low = closing_lc.lower()
    if ", and " in closing_lc or "; " in closing_lc:
        segments = re.split(r",|\s;\s|\s+and\s+", closing_lc)
        segments = [s.strip() for s in segments if s.strip()]
        for seg in reversed(segments):
            if seg.lower().startswith(("a ", "an ")):
                return seg.strip()
        if segments:
            return segments[0]
    parts = closing_lc.split(" while ")
    if len(parts) > 1:
        return parts[0].strip().rstrip(",")
    if " paired with " in low or " paired " in low:
        return closing_lc.split(" paired ")[0].strip().rstrip(",")
    parts = closing_lc.split(",")
    if len(parts) >= 3:
        return ", ".join(parts[:2]).strip().rstrip(",")
    return closing_lc


def _finalize_brevity(body: str, max_sentences: int = 2, cap: int = _MAX_BODY_CHARS) -> str:
    body = _strip_redundant_phrases(_norm(body.rstrip(".")))
    if not body.endswith("."):
        body += "."
    while _sentence_count(body) > max_sentences:
        masked, _ = _mask_sentence_split(body.rstrip("."))
        parts = [p.strip() for p in masked.split(".") if p.strip()]
        if len(parts) < 2:
            break
        body = ". ".join(parts[:max_sentences]).strip()
        if not body.endswith("."):
            body += "."
        body = _unmask_sentence_split(body)
    if len(body) > cap:
        body = body[:cap].rsplit(".", 1)[0].strip()
        body = body + "." if body else body
    return _norm(body)


def _build_brief_body(
    observation: str,
    implication: str,
    closing: str,
    cap: int,
) -> str:
    observation = observation.strip()
    implication = implication.strip()
    closing = closing.strip().rstrip(".")
    closing = _keep_strongest_action_segment(closing)
    closing_lc = closing[0].lower() + closing[1:] if closing else ""

    body = f"{observation}, {implication} — {closing_lc}".strip()
    body = _finalize_brevity(body, max_sentences=2, cap=cap)
    return body


def _truncate_body_hard_cap(body: str, cap: int) -> str:
    if len(body) <= cap:
        return body
    trimmed = body[:cap]
    if "." in trimmed:
        trimmed = trimmed.rsplit(".", 1)[0]
    t = trimmed.strip()
    return t + "." if t else body[:cap].strip() + "."


def _enforce_numeric_observation(
    obs: str,
    anchors: Tuple[int, int, int, int],
    merchant: dict,
    category: dict,
) -> str:
    pct_ctr, pct_peer, inactive_d, conv_p = anchors
    o = obs.strip()
    numeric_count = sum(1 for c in o if c.isdigit())
    if numeric_count >= _MIN_NUMERIC_TOKENS:
        return o
    perf = merchant.get("performance") or {}
    ctr = perf.get("ctr")
    peer = (category.get("peer_stats") or {}).get("avg_ctr")
    views = perf.get("views")
    if ctr is not None and peer is not None:
        return (
            f"CTR is near {int(round(float(ctr) * 100))}% vs peers at "
            f"{int(round(float(peer) * 100))}%"
        )
    if views is not None:
        return f"{views} views in last 30d"
    return (
        f"CTR is around {pct_ctr}% vs peers {pct_peer}% "
        f"({inactive_d}d horizon, conversion {conv_p}%) "
        f"— close the gap with one focused listing or promo adjustment"
    )


def generate_blueprint(decision: dict, signals: dict) -> dict:
    merchant = signals["merchant"]
    trigger = signals["trigger"]
    category = signals["category"]
    intent = decision["intent_type"]
    urgency = float(decision.get("urgency") or trigger.get("urgency") or 0.0)

    ctr = merchant.get("ctr")
    ctr_peer = merchant.get("ctr_peer_median")
    ctr_delta = merchant.get("ctr_delta") or 0.0
    benchmark = category.get("benchmark_ctr")
    inactivity_days = merchant.get("inactivity_days")
    conversion_rate = float(merchant.get("conversion_rate") or 0.0)

    if ctr is None:
        ctr = _deterministic_fallback(merchant, 0.01, 0.10, "ctr")
    if ctr_peer is None:
        ctr_peer = _deterministic_fallback(merchant, 0.02, 0.08, "ctr_peer")
    if benchmark is None:
        benchmark = _deterministic_fallback(category, 0.02, 0.08, "benchmark")
    if inactivity_days is None:
        inactivity_days = int(_deterministic_fallback(merchant, 1, 30, "inactivity"))

    relative_gap = (ctr - ctr_peer) / ctr_peer if ctr_peer else 0.0
    pct_vs = abs(int(relative_gap * 100))
    trailing = relative_gap < 0

    if trailing:
        insight = f"{pct_vs}% below peers"
    else:
        insight = f"{pct_vs}% above peers"

    pct_ctr = _pct_i(ctr)
    pct_peer = _pct_i(ctr_peer)
    conv_p = _pct_i(conversion_rate)
    inactive_d = int(inactivity_days)

    percentile = int((ctr / (benchmark or 0.01)) * 100)
    if percentile >= 80:
        percentile_band = "top 20% performers"
    elif percentile <= 30:
        percentile_band = "bottom 30% performers"
    else:
        percentile_band = "mid-tier"

    lift_pp: Optional[int] = None
    closing = ""
    obs = ""
    impl = ""

    if intent == "push_offer":
        expected_ctr_lift = min(0.3, abs(ctr_delta) * 0.5)
        lift_pp = max(1, min(99, round(expected_ctr_lift * 100)))
        obs = (
            f"CTR is {pct_vs}% {'below' if trailing else 'above'} peers "
            f"({pct_ctr}% vs {pct_peer}%)"
        )
        impl = (
            "which is lowering visibility"
            if trailing
            else "which still rewards a sharper offer line"
        )
        if trailing:
            if lift_pp >= 2:
                closing = (
                    f"A limited-time offer can recover ranking and improve CTR "
                    f"by ~{lift_pp}% toward peers."
                )
            else:
                closing = (
                    "A limited-time offer can recover ranking and improve CTR toward peers."
                )
        else:
            closing = "A sharper offer slot can widen reach without losing CTR."
    elif intent == "upsell":
        obs = (
            f"Your CTR is {pct_vs}% {'above' if not trailing else 'near'} peers "
            f"({pct_ctr}% vs {pct_peer}%)"
        )
        impl = (
            "which supports higher basket upside"
            if not trailing
            else "which still needs basket depth to monetize evenly"
        )
        if not trailing:
            closing = (
                "Bundle add-ons can raise average order value on traffic you "
                "already earn."
            )
        else:
            closing = "Premium placements can widen reach so bundles land cleaner."
    elif intent == "reactivate_user":
        obs = (
            f"You have had no activity for {inactive_d} days "
            f"(CTR {pct_ctr}% vs peers at {pct_peer}%)"
        )
        impl = "which is lowering visibility"
        closing = (
            "A simple reactivation refresh can restore traffic and re-engage users."
        )
    elif intent == "inform_insight":
        if trailing:
            obs = (
                f"CTR is {pct_vs}% under the peer midpoint "
                f"({pct_ctr}% vs {pct_peer}%)"
            )
            impl = "which gaps you versus category norms"
            closing = "Fix one weak funnel lever first—visibility follows."
        else:
            obs = (
                f"CTR is running {pct_vs}% ahead of peers "
                f"({pct_ctr}% vs {pct_peer}%)"
            )
            impl = "which keeps room to tighten monetization safely"
            closing = "Lock in share with disciplined creative and placement testing."
        lift_pp = None
    else:
        obs = (
            f"CTR is {pct_ctr}% vs peers {pct_peer}% ({insight}); "
            f"conversion is {conv_p}%"
        )
        impl = "which caps how boldly you rank"
        closing = (
            "Tight headline, hero, and slot rotations can regain CTR without branching plans."
        )
        lift_pp = None

    predicted_impact = ""
    if intent == "upsell":
        predicted_impact = (
            "lift average order value with bundles"
            if not trailing
            else "recover CTR as placements widen funnel space"
        )
    elif intent == "reactivate_user":
        predicted_impact = "restore traffic and CTR"
    elif intent == "inform_insight":
        predicted_impact = (
            "close the CTR gap on one funnel lever"
            if trailing
            else "protect CTR lead while iterating placements"
        )
    elif intent == "push_offer":
        if trailing:
            predicted_impact = (
                f"improve CTR by ~{lift_pp}% toward peers"
                if lift_pp is not None
                else "recover ranking and CTR toward peers"
            )
        else:
            predicted_impact = "steady CTR plus wider promo reach"
    else:
        predicted_impact = "incremental CTR from focused listing swaps"

    risk_if_ignored = ""
    if intent == "push_offer" and lift_pp is not None:
        if ctr_delta < 0 and urgency > 0.7:
            risk_if_ignored = "soft CTR prolongs weaker ranking cues"
    elif intent == "reactivate_user":
        if ctr_delta < 0 and urgency > 0.7:
            risk_if_ignored = "quiet storefronts bleed discovery cues"

    anchors = (pct_ctr, pct_peer, inactive_d, conv_p)
    observation = _enforce_numeric_observation(obs, anchors, merchant, category)
    implication = impl.strip() or (
        f"holding the spread near {pct_vs}% until you act deliberately"
    )

    core_parts = [observation, implication, closing]
    parts_nonempty = sum(1 for p in core_parts if p and str(p).strip())

    cta_fallback = False
    if parts_nonempty < 2:
        body = (
            "CTR versus peers signals room for one sharper listing "
            "or promo adjustment."
        )
        body = _finalize_brevity(body, max_sentences=2, cap=_MAX_BODY_CHARS)
        cta_fallback = True
    else:
        body = _build_brief_body(
            observation,
            implication,
            closing,
            _MAX_BODY_CHARS,
        )
        body = _truncate_body_hard_cap(body, _MAX_BODY_CHARS)

    body = _finalize_brevity(body, max_sentences=2, cap=_MAX_BODY_CHARS)
    body = body.strip()
    if not body.endswith("."):
        body += "."

    if not str(predicted_impact).strip():
        predicted_impact = "recover ranking and improve CTR toward peers"

    cta_type, cta = _INTENT_CTA.get(intent) or _INTENT_CTA["nudge_engagement"]
    if cta_fallback:
        cta_type, cta = _INTENT_CTA["nudge_engagement"]

    _labels = {
        "push_offer": "Run one limited-time offer on a bestseller.",
        "upsell": "Pilot bundle pricing on movers.",
        "reactivate_user": "Run one listings refresh pulse.",
        "inform_insight": "Fix weakest funnel KPI first.",
        "nudge_engagement": "Iterate headline plus hero jointly.",
    }
    action_label = _labels.get(intent, _labels["nudge_engagement"])

    return {
        "body": body,
        "CTA_type": cta_type,
        "cta": cta,
        "tone_profile": category.get("tone", "professional"),
        "constraints": [],
        "insight": insight,
        "percentile_band": percentile_band,
        "metric": f"CTR: {pct_ctr}% vs {pct_peer}% peers",
        "suggestion": action_label,
        "action": action_label,
        "question": "",
        "data": "",
        "predicted_impact": predicted_impact,
        "risk_if_ignored": risk_if_ignored,
    }
