# Deterministic decision engine: one dominant signal, trigger + merchant + category.
from typing import Any, Dict, List, Tuple

CONTRAST_SCORE_MARGIN = 0.28
CONTRAST_MIN_PAIR_SCORE = 2.1
CONTRAST_MIN_IMPACT_EACH = 0.55
CONTRAST_MIN_RELATIVE_DELTA = 0.06
CONTRAST_MAX_GAP_RATIO = 0.18

INTENTS = [
    "push_offer",
    "nudge_engagement",
    "inform_insight",
    "reactivate_user",
    "upsell",
]


def _norm_trigger(tid: str) -> str:
    return str(tid or "").lower().replace("_", "")


def _dominant_signal(signals: dict) -> Tuple[str, str]:
    """Return (dominant_label, reason_tag). Single primary driver."""
    merchant = signals["merchant"]
    trigger = signals["trigger"]
    tid = _norm_trigger(trigger.get("type") or "")
    idays = int(merchant.get("inactivity_days") or 0)
    ctr = merchant.get("ctr")
    peer = merchant.get("ctr_peer_median")

    ctr_ratio = None
    if ctr is not None and peer is not None and peer > 1e-12:
        ctr_ratio = ctr / peer

    trig_inactive = any(k in tid for k in ("inactiv", "dormancy", "dormant", "silent"))
    trig_ctr_problem = any(
        k in tid for k in ("ctrdrop", "ctr.Drop", "perfdip", "dip", "underperform", "drop")
    )
    trigger_clarify_ctr = trig_ctr_problem or (
        "ctr" in tid and "rise" not in tid and "spike" not in tid
    )
    trig_spike = any(k in tid for k in ("spike", "momentum", "peak", "surge", "winner"))

    w_inactive = 0.0
    if trig_inactive:
        w_inactive += 4.5
    w_inactive += min(8.0, 0.45 * float(max(0, idays)))

    w_ctr_head = 0.0
    if trig_ctr_problem or trigger_clarify_ctr:
        w_ctr_head += 3.8
    if ctr_ratio is not None:
        if ctr_ratio < 0.98:
            w_ctr_head += 3.0
        elif ctr_ratio < 1.0:
            w_ctr_head += 1.0

    w_momentum = 0.0
    if trig_spike:
        w_momentum += 4.0
    if ctr_ratio is not None and ctr_ratio > 1.05:
        w_momentum += 3.0

    buckets = {"inactive": w_inactive, "ctr_headwind": w_ctr_head, "momentum": w_momentum}
    best = max(buckets.values())
    label = (
        max(buckets, key=buckets.__getitem__) if best >= 1.05 else "neutral"
    )

    tie_note = ":" + max(buckets, key=buckets.__getitem__)

    why = {"inactive": "dormancy", "ctr_headwind": "discovery", "momentum": "momentum"}
    note = (
        ("trigger aligns" + tie_note) if trig_inactive or trig_ctr_problem or trig_spike else "state aligns"
    )
    return label, note + "=" + why.get(label, "balanced")


_ACTION_POOLS = {
    "inactive": ["reactivate_user", "update_listing", "nudge_engagement"],
    "ctr_headwind_offer_on": ["improve_listing", "increase_visibility", "nudge_engagement"],
    "ctr_headwind_offer_off": ["push_offer", "run_discount", "improve_listing"],
    "momentum": ["upsell", "expand_catalog", "increase_pricing"],
    "neutral": ["inform_insight", "nudge_engagement", "improve_listing"],
}


action_to_intent = {
    "run_discount": "push_offer",
    "push_offer": "push_offer",
    "improve_listing": "nudge_engagement",
    "increase_visibility": "nudge_engagement",
    "upsell": "upsell",
    "increase_pricing": "upsell",
    "expand_catalog": "upsell",
    "reactivate_user": "reactivate_user",
    "update_listing": "nudge_engagement",
    "nudge_engagement": "nudge_engagement",
    "inform_insight": "inform_insight",
}


def _situation_lines(
    dominant: str,
    merchant: Dict[str, Any],
    ctr_ratio: Any,
    idays: int,
) -> str:
    ctr = merchant.get("ctr")
    peer = merchant.get("ctr_peer_median")
    if dominant == "inactive":
        return f"Quiet storefront: {idays} inactive days — one strong reactivation beats scattered tweaks."
    if dominant == "ctr_headwind":
        if ctr is not None and peer is not None and peer > 1e-12:
            pct = abs(int(round((ctr - peer) / peer * 100)))
            return (
                f"CTR trails the peer median by about {pct}% — discovery needs one focused lever."
            )
        return (
            "Performance signal shows weaker shopper pull versus peers — "
            "tighten one discovery lever instead of layering weak fixes."
        )
    if dominant == "momentum":
        if ctr is not None and peer is not None and peer > 1e-12:
            pct = abs(int(round((ctr - peer) / peer * 100)))
            return (
                f"CTR clears peer median by about {pct}% — capitalize before the window cools."
            )
        return "Momentum trigger shows stronger pull than peers — monetize cleanly without risking CTR."


def _action_components(action: str, dominant: str, merchant: Dict[str, Any]) -> Dict[str, float]:
    ctr_raw = merchant.get("ctr")
    peer_raw = merchant.get("ctr_peer_median")
    ctr = float(ctr_raw) if ctr_raw is not None else None
    peer = float(peer_raw) if peer_raw is not None else None
    ctr_ratio = None
    if ctr is not None and peer is not None and peer > 1e-12:
        ctr_ratio = ctr / peer
    inactivity_days = int(merchant.get("inactivity_days") or 0)

    impact = ease = fit = 0.0
    has_offer = merchant.get("has_active_offer")

    if action in ("run_discount", "push_offer"):
        impact = 0.9 if ctr_ratio is not None and ctr_ratio < 1 else 0.55
        ease = 0.75 if not has_offer else 0.4
        fit = 1.0 if dominant in ("neutral", "ctr_headwind") and not has_offer else 0.45

    elif action in ("improve_listing", "update_listing"):
        impact = 0.72 if dominant == "ctr_headwind" else 0.6
        ease = 0.72
        fit = (
            1.0 if dominant == "ctr_headwind" or (has_offer and dominant == "ctr_headwind") else 0.55
        )
        if has_offer and dominant == "ctr_headwind":
            fit = 1.0

    elif action == "increase_visibility":
        impact = 0.68
        ease = 0.62
        fit = 1.0 if has_offer and dominant == "ctr_headwind" else 0.5

    elif action == "upsell":
        impact = (
            0.85 if ctr_ratio is not None and ctr_ratio > 1 else 0.45
        )
        ease = 0.68
        fit = 1.0 if dominant == "momentum" else 0.45

    elif action == "increase_pricing":
        impact = 0.65
        ease = 0.45
        fit = 0.75 if dominant == "momentum" else 0.35

    elif action == "expand_catalog":
        impact = 0.58
        ease = 0.55
        fit = 0.75 if dominant == "momentum" else 0.4

    elif action == "reactivate_user":
        impact = 0.88 if dominant == "inactive" else 0.42
        ease = 0.68 if dominant == "inactive" else 0.42
        fit = 1.0 if dominant == "inactive" else 0.35

    elif action == "nudge_engagement":
        impact = 0.52
        ease = 0.82
        fit = (
            0.85 if dominant == "inactive" else 0.75 if dominant == "neutral" else 0.6
        )

    elif action == "inform_insight":
        impact = 0.45
        ease = 0.9
        fit = 0.85 if dominant == "neutral" else 0.45

    if dominant == "inactive" and action == "reactivate_user":
        impact = max(impact, 0.92)

    return {
        "expected_impact_weight": impact,
        "ease_of_execution": ease,
        "context_fit": fit,
    }


def make_decision(signals: dict) -> Tuple[dict, dict]:
    merchant = signals["merchant"]
    trigger = signals["trigger"]
    category = signals["category"]
    ctr = merchant.get("ctr")
    ctr_peer = merchant.get("ctr_peer_median")

    ctr_ratio = None
    if ctr is not None and ctr_peer is not None and ctr_peer > 1e-12:
        ctr_ratio = ctr / ctr_peer

    inactivity_days = int(merchant.get("inactivity_days") or 0)
    ctr_delta_safe = merchant.get("ctr_delta")
    if ctr_delta_safe is None and ctr is not None and ctr_peer is not None:
        ctr_delta_safe = ctr - ctr_peer
    if ctr_delta_safe is None:
        ctr_delta_safe = 0.0

    dominant, dom_note = _dominant_signal(signals)

    conversion_rate = float(merchant.get("conversion_rate") or 0.0)

    if merchant.get("has_active_offer") and ctr_delta_safe < -0.01:
        engagement_potential = 1.0
    elif abs(float(ctr_delta_safe)) < 0.005:
        engagement_potential = 0.5
    else:
        engagement_potential = 0.2

    category_name = str(category.get("name") or "other").lower()

    weights = {
        "trigger": 0.35,
        "engagement": 0.20,
        "personalization": 0.20,
        "offer": 0.20,
        "insight": 0.25,
        "urgency": 0.35,
    }
    cn = category_name
    if any(x in cn for x in ("restaurant", "food", "dining")):
        weights["trigger"] = 0.4
        weights["engagement"] = 0.3
    elif any(x in cn for x in ("fashion", "apparel")):
        weights["personalization"] = 0.3
        weights["offer"] = 0.35
    elif "electronics" in cn:
        weights["insight"] = 0.4
        weights["urgency"] = 0.25

    intent_scores: Dict[str, float] = {}
    threshold = 7
    trig_urgency = trigger["urgency"]
    inactive_flag = float(inactivity_days > threshold)
    for intent in INTENTS:
        if intent == "push_offer":
            delta_weight = abs(float(ctr_delta_safe))
            intent_scores[intent] = (
                weights["trigger"] * trig_urgency
                + weights["offer"] * delta_weight
                + weights["engagement"] * inactive_flag
                + weights["personalization"] * engagement_potential
            )
        elif intent == "nudge_engagement":
            intent_scores[intent] = (
                weights["trigger"] * (1.0 - trig_urgency)
                + weights["engagement"]
                * (1.0 - abs(float(ctr_delta_safe)))
                + weights["personalization"]
                * ((1.0 - inactive_flag) if inactivity_days <= threshold else 0.0)
                + weights["offer"]
                * (1.0 - engagement_potential)
            )
        elif intent == "inform_insight":
            intent_scores[intent] = (
                weights["insight"] * 0.5
                + weights["offer"] * abs(float(ctr_delta_safe))
                + weights["personalization"] * 0.5
            )
        elif intent == "reactivate_user":
            ire = 1.0 if inactivity_days > 14 else (0.6 if inactivity_days > 7 else 0.0)
            intent_scores[intent] = (
                weights["trigger"] * trig_urgency
                + weights["engagement"] * ire
                + weights["offer"] * abs(float(ctr_delta_safe))
                + weights["personalization"] * engagement_potential
            )
        elif intent == "upsell":
            ctr_above = (
                ctr is not None
                and ctr_peer is not None
                and ctr > ctr_peer
            )
            conv_ok = conversion_rate > 0.15
            intent_scores[intent] = (
                weights["trigger"] * float(ctr_above)
                + weights["offer"] * float(conv_ok or ctr_above)
                + weights["engagement"] * float(merchant.get("has_active_offer"))
                + weights["personalization"] * engagement_potential
            )
        else:
            intent_scores[intent] = 0.0

    reasoning_path = [f"{k}={v:.3f}" for k, v in intent_scores.items()]

    urgency = trig_urgency
    offer_on = merchant.get("has_active_offer")

    pool_key_map = {
        "inactive": "inactive",
        "neutral": "neutral",
        "momentum": "momentum",
        "ctr_headwind": ("ctr_headwind_offer_on" if offer_on else "ctr_headwind_offer_off"),
    }
    pk = pool_key_map[dominant]
    candidate_actions = list(_ACTION_POOLS[pk if isinstance(pk, str) else pk])

    scored: List[Dict[str, Any]] = []
    for a in candidate_actions:
        comp = _action_components(a, dominant, merchant)
        total = (
            comp["expected_impact_weight"]
            + comp["ease_of_execution"]
            + comp["context_fit"]
        )
        scored.append({"action": a, "score": total, **comp})
    scored.sort(key=lambda x: -x["score"])

    forced_intent = None
    if dominant == "inactive":
        forced_intent = "reactivate_user"
    elif dominant == "momentum":
        forced_intent = "upsell"
    elif dominant == "ctr_headwind":
        forced_intent = "nudge_engagement" if offer_on else "push_offer"

    best_action = scored[0]["action"]
    alternatives = [row["action"] for row in scored[1:]]

    if forced_intent == "reactivate_user" and dominant == "inactive":
        best_action = "reactivate_user"
        alternatives = [a for a in candidate_actions if a != best_action][:2]

    elif forced_intent == "upsell":
        pref = ["upsell", "expand_catalog", "increase_pricing"]
        for name in pref:
            if name in candidate_actions:
                best_action = name
                break
        alternatives = [a for a in candidate_actions if a != best_action][:2]

    elif forced_intent == "nudge_engagement":
        preferred = ["improve_listing", "increase_visibility"]
        picked = False
        for name in preferred:
            if name in candidate_actions:
                best_action = name
                picked = True
                break
        if not picked:
            best_action = scored[0]["action"]
        alternatives = [a for a in candidate_actions if a != best_action][:2]

    elif forced_intent == "push_offer":
        if "push_offer" in candidate_actions:
            best_action = "push_offer"
        elif "run_discount" in candidate_actions:
            best_action = "run_discount"
        else:
            best_action = scored[0]["action"]
        alternatives = [a for a in candidate_actions if a != best_action][:2]

    intent_type = action_to_intent.get(best_action, "inform_insight")

    relative_gap = (ctr_ratio - 1.0) if ctr_ratio is not None else 0.0
    situation = _situation_lines(dominant, merchant, ctr_ratio, inactivity_days)

    risk_if_ignored = ""
    if intent_type == "push_offer":
        if ctr_delta_safe < 0 and trig_urgency > 0.7:
            risk_if_ignored = "further ranking drop"
    elif intent_type == "reactivate_user":
        if ctr_delta_safe < 0 and trig_urgency > 0.7:
            risk_if_ignored = "quiet storefronts bleed discovery cues"

    def rejection_reason(chosen: str, alt: str) -> str:
        listing = {"improve_listing", "update_listing"}
        promo = {"run_discount", "push_offer"}
        growth = {"increase_visibility", "expand_catalog", "nudge_engagement"}

        if alt in listing and chosen in promo:
            return "slower durability vs sharper listing move"
        if alt in promo and chosen in listing:
            return "offer noise when listing clarity is blocking visibility"
        if alt in growth and chosen == "upsell":
            return "lower urgency than monetizing momentum now"
        if alt == "expand_catalog" and chosen == "upsell":
            return "longer runway vs upsell today"
        if alt == "inform_insight" and chosen != "inform_insight":
            return "insight-only vs one actionable lever"
        if alt == "reactivate_user" and chosen != "reactivate_user":
            return "signals favor reactivation but runner-up clears smaller gaps"
        if alt == "push_offer" and chosen == "reactivate_user":
            return "reactivation primes the storefront before offer spend"
        return "lower composite score vs chosen action"

    top_alt = alternatives[0] if alternatives else None
    rationale_why_rejected = (
        rejection_reason(best_action, top_alt) if top_alt else "no runner-up in set"
    )
    rationale_alternatives = alternatives[:2]

    s0 = scored[0]
    s1 = scored[1] if len(scored) > 1 else None
    gap = abs(s1["score"] - s0["score"]) if s1 is not None else None
    gap_narrow = s1 is not None and gap is not None and gap < CONTRAST_SCORE_MARGIN
    relative_close = (
        s1 is not None
        and s0["score"] > 0
        and gap is not None
        and CONTRAST_MIN_RELATIVE_DELTA
        <= (gap / s0["score"])
        <= CONTRAST_MAX_GAP_RATIO
    )
    both_strong = (
        s1 is not None
        and s0["score"] >= CONTRAST_MIN_PAIR_SCORE
        and s1["score"] >= CONTRAST_MIN_PAIR_SCORE
        and s0["expected_impact_weight"] >= CONTRAST_MIN_IMPACT_EACH
        and s1["expected_impact_weight"] >= CONTRAST_MIN_IMPACT_EACH
    )
    scores_close_for_contrast = gap_narrow and relative_close and both_strong

    contrast_phrase = ""
    if scores_close_for_contrast and alternatives and top_alt:
        if best_action in ("run_discount", "push_offer"):
            contrast_phrase = "Listing quality compounds; sharper promo accelerates retrieval here."
        elif best_action == "upsell" and dominant == "momentum":
            contrast_phrase = (
                "Catalog breadth helps later; upsell concentrates demand you already earned."
            )
        elif best_action == "reactivate_user":
            contrast_phrase = "Reactive polish helps, but dormant traffic needs renewal first."
        elif best_action in ("improve_listing", "update_listing"):
            contrast_phrase = "Promotions spike clicks while listing edits earn durable placement."
        else:
            contrast_phrase = f"{best_action.replace('_', ' ')} edges out {top_alt.replace('_', ' ')} on fit."

    choice_contrast = contrast_phrase

    rationale = {
        "situation": situation,
        "decision": intent_type,
        "why_this_action": dom_note[:120],
        "risk_if_ignored": risk_if_ignored,
        "confidence": (
            "high"
            if (ctr_ratio is not None and abs(ctr_ratio - 1.0) > 0.2)
            or inactivity_days > 7
            else "medium"
        ),
        "cta_reason": "single focused lever with low-friction merchant reply",
        "alternatives_considered": rationale_alternatives,
        "why_rejected": rationale_why_rejected,
        "contrast": contrast_phrase,
        "dominant_signal": dominant,
    }

    decision = {
        "intent_type": intent_type,
        "urgency": urgency,
        "engagement_potential": engagement_potential,
        "offer_to_push": offer_on,
        "reasoning_path": reasoning_path,
        "category": category_name,
        "candidate_actions": candidate_actions,
        "action_scores": scored,
        "best_action": best_action,
        "alternatives": alternatives,
        "choice_contrast": choice_contrast,
        "dominant_signal": dominant,
    }
    return decision, rationale
