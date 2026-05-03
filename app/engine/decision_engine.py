# Deterministic decision engine with rationale trace and choice intelligence
from typing import Any, Dict, List, Tuple

# Contrast only when runner-up is close AND both competing options exceed quality floors (weak-runner-up ⇒ no contrast).
CONTRAST_SCORE_MARGIN = 0.28
CONTRAST_MIN_PAIR_SCORE = 2.1
CONTRAST_MIN_IMPACT_EACH = 0.55
CONTRAST_MIN_RELATIVE_DELTA = 0.06
CONTRAST_MAX_GAP_RATIO = 0.18


def make_decision(signals: dict) -> Tuple[dict, dict]:
    merchant = signals["merchant"]
    trigger = signals["trigger"]
    category = signals["category"]

    ctr = merchant.get("ctr", 0)
    ctr_peer = merchant.get("ctr_peer_median", 0.01)
    ctr_delta = merchant.get("ctr_delta", ctr - ctr_peer)
    inactivity_days = merchant.get("inactivity_days", 0)

    INTENTS = [
        "push_offer",
        "nudge_engagement",
        "inform_insight",
        "reactivate_user",
        "upsell",
    ]

    # --- 1. Candidate actions (2–3 per context) ---
    # Dormancy first so inactive + low CTR still gets reactivation-style options.
    if inactivity_days > 7:
        candidate_actions = ["reactivate_user", "update_listing", "push_offer"]
        context = "inactive"
    elif ctr < ctr_peer * 0.98:
        candidate_actions = ["run_discount", "improve_listing", "increase_visibility"]
        context = "low_ctr"
    elif ctr > ctr_peer * 1.05:
        candidate_actions = ["upsell", "increase_pricing", "expand_catalog"]
        context = "high_ctr"
    else:
        candidate_actions = ["push_offer", "nudge_engagement", "inform_insight"]
        context = "neutral"

    # --- 2. Score each: expected_impact_weight + ease_of_execution + context_fit ---
    def action_components(action: str) -> Dict[str, float]:
        impact = ease = fit = 0.0

        if action in ("run_discount", "push_offer"):
            impact = 0.9 if ctr < ctr_peer else 0.6
            ease = 0.8
            fit = (
                1.0
                if context in ("low_ctr", "inactive", "neutral")
                else 0.5
            )
        elif action in ("improve_listing", "update_listing"):
            impact = 0.7
            ease = 0.7
            fit = 0.8 if context in ("low_ctr", "inactive") else 0.5
        elif action == "increase_visibility":
            impact = 0.6
            ease = 0.6
            fit = 0.7 if context == "low_ctr" else 0.4
        elif action == "upsell":
            impact = 0.8 if ctr > ctr_peer else 0.5
            ease = 0.7
            fit = 1.0 if context == "high_ctr" else 0.5
        elif action == "increase_pricing":
            impact = 0.7
            ease = 0.5
            fit = 0.8 if context == "high_ctr" else 0.4
        elif action == "expand_catalog":
            impact = 0.6
            ease = 0.6
            fit = 0.7 if context == "high_ctr" else 0.4
        elif action == "reactivate_user":
            impact = 0.8
            ease = 0.7
            fit = 1.0 if context == "inactive" else 0.5
        elif action == "nudge_engagement":
            impact = 0.5
            ease = 0.8
            fit = 0.7
        elif action == "inform_insight":
            impact = 0.4
            ease = 0.9
            fit = 0.6

        if inactivity_days > 7 and action == "reactivate_user":
            fit = min(1.0, fit + 0.35)

        return {
            "expected_impact_weight": impact,
            "ease_of_execution": ease,
            "context_fit": fit,
        }

    scored: List[Dict[str, Any]] = []
    for a in candidate_actions:
        comp = action_components(a)
        total = (
            comp["expected_impact_weight"]
            + comp["ease_of_execution"]
            + comp["context_fit"]
        )
        scored.append({"action": a, "score": total, **comp})

    scored.sort(key=lambda x: -x["score"])
    best_action = scored[0]["action"]
    alternatives = [row["action"] for row in scored[1:]]

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

    # Engagement potential + intent_scores (telemetry / reasoning_path)
    if merchant["has_active_offer"] and merchant["ctr_delta"] < -0.01:
        engagement_potential = 1.0
    elif abs(merchant["ctr_delta"]) < 0.005:
        engagement_potential = 0.5
    else:
        engagement_potential = 0.2

    category_name = category.get("name", "other").lower()
    weights = {
        "trigger": 0.35,
        "engagement": 0.20,
        "personalization": 0.20,
        "offer": 0.20,
        "insight": 0.25,
        "urgency": 0.35,
    }
    if category_name in ["food", "restaurant", "restaurants"]:
        weights["trigger"] = 0.4
        weights["engagement"] = 0.3
    elif category_name in ["fashion", "apparel"]:
        weights["personalization"] = 0.3
        weights["offer"] = 0.35
    elif category_name in ["electronics"]:
        weights["insight"] = 0.4
        weights["urgency"] = 0.25

    threshold = 7
    intent_scores = {}
    for intent in INTENTS:
        if intent == "push_offer":
            score = (
                weights["trigger"] * trigger["urgency"]
                + weights["offer"] * abs(merchant["ctr_delta"])
                + weights["engagement"]
                * (1 if merchant["inactivity_days"] > threshold else 0)
                + weights["personalization"] * engagement_potential
            )
        elif intent == "nudge_engagement":
            score = (
                weights["trigger"] * (1 - trigger["urgency"])
                + weights["engagement"] * (1 - abs(merchant["ctr_delta"]))
                + weights["personalization"]
                * (1 if merchant["inactivity_days"] <= threshold else 0)
                + weights["offer"] * (1 - engagement_potential)
            )
        elif intent == "inform_insight":
            score = (
                weights["insight"] * 0.5
                + weights["offer"] * abs(merchant["ctr_delta"])
                + weights["engagement"] * 0
                + weights["personalization"] * 0.5
            )
        elif intent == "reactivate_user":
            score = (
                weights["trigger"] * trigger["urgency"]
                + weights["engagement"]
                * (1 if merchant["inactivity_days"] > 14 else 0)
                + weights["offer"] * abs(merchant["ctr_delta"])
                + weights["personalization"] * engagement_potential
            )
        elif intent == "upsell":
            score = (
                weights["trigger"]
                * (1 if merchant["ctr"] > merchant["ctr_peer_median"] else 0)
                + weights["offer"] * (1 if merchant["conversion_rate"] > 0.15 else 0)
                + weights["engagement"] * (1 if merchant["has_active_offer"] else 0)
                + weights["personalization"] * engagement_potential
            )
        else:
            score = 0
        intent_scores[intent] = score

    reasoning_path = [f"{k}={v:.3f}" for k, v in intent_scores.items()]

    forced_intent = None
    if merchant["inactivity_days"] > 7:
        forced_intent = "reactivate_user"
    elif (
        merchant["ctr_delta"] < -0.01
        and merchant["has_active_offer"]
        and merchant["inactivity_days"] <= 7
    ):
        forced_intent = "push_offer"
    elif (
        merchant["ctr_delta"] > (merchant["ctr_peer_median"] * 0.5)
        and context == "high_ctr"
    ):
        forced_intent = "upsell"

    if forced_intent and forced_intent in INTENTS:
        intent_type = forced_intent
        preferred = {
            "push_offer": (
                "run_discount" if "run_discount" in candidate_actions else "push_offer"
            ),
            "reactivate_user": "reactivate_user",
            "upsell": "upsell",
        }
        target = preferred.get(intent_type, scored[0]["action"])
        if target in candidate_actions:
            best_action = target
        else:
            for name in ("upsell", "increase_pricing", "expand_catalog"):
                if name in candidate_actions:
                    best_action = name
                    break
            else:
                best_action = scored[0]["action"]
        ranked = [r["action"] for r in sorted(scored, key=lambda x: -x["score"])]
        alternatives = [a for a in ranked if a != best_action][:2]
    else:
        intent_type = action_to_intent.get(best_action, "inform_insight")

    urgency = trigger["urgency"]
    offer_to_push = merchant["has_active_offer"]

    relative_gap = (ctr - ctr_peer) / ctr_peer if ctr_peer else 0
    if relative_gap < 0:
        situation = f"CTR is {abs(int(relative_gap * 100))}% below peer median"
    else:
        situation = f"CTR is {abs(int(relative_gap * 100))}% above peer median"
    if inactivity_days > 7:
        situation += f" and inactive for {inactivity_days} days"

    risk_if_ignored = ""
    if intent_type == "push_offer":
        if ctr_delta < 0 and urgency > 0.7:
            risk_if_ignored = "further ranking drop"
    elif intent_type == "reactivate_user":
        if ctr_delta < 0 and urgency > 0.7:
            risk_if_ignored = "prolonged inactivity may reduce discovery"

    def rejection_reason(chosen: str, alt: str) -> str:
        listing = {"improve_listing", "update_listing"}
        promo = {"run_discount", "push_offer"}
        growth = {"increase_visibility", "expand_catalog", "nudge_engagement"}

        if alt in listing and chosen in promo:
            return "slower impact vs offer"
        if alt in promo and chosen in listing:
            return "discount less durable than fixing listing quality first"
        if alt in growth and chosen == "upsell":
            return "lower urgency than monetizing momentum now"
        if alt == "increase_pricing" and chosen == "upsell":
            return "upsell clearer path before broad price moves"
        if alt == "expand_catalog" and chosen == "upsell":
            return "longer runway vs upsell today"
        if alt == "upsell" and chosen == "increase_pricing":
            return "upsell framing fits current funnel better"
        if alt == "inform_insight" and chosen != "inform_insight":
            return "insight-only vs actionable move"
        if alt == "reactivate_user" and chosen != "reactivate_user":
            return "reactivation outweighed by current CTR/context signal"
        if alt == "push_offer" and chosen == "reactivate_user":
            return "offer runs stronger after the storefront is visibly active again"
        return "lower composite score vs chosen action"

    top_alt = alternatives[0] if alternatives else None
    rationale_why_rejected = (
        rejection_reason(best_action, top_alt) if top_alt else "no runner-up in set"
    )
    rationale_alternatives = alternatives[:2]

    # --- 3. Choice contrast (eligible only when gap is narrow and top-2 are both strong enough) ---
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
        if best_action in ("run_discount", "push_offer") and context == "low_ctr":
            contrast_phrase = (
                "Listing fixes help steadily; an offer rebounds clicks faster here."
            )
        elif best_action == "upsell" and context == "high_ctr":
            contrast_phrase = (
                "More SKUs help later; upsell fits your current momentum."
            )
        elif best_action == "reactivate_user":
            contrast_phrase = (
                "Light edits help, but reactivation tackles the dormancy first."
            )
        elif best_action == "increase_pricing" and context == "high_ctr":
            contrast_phrase = (
                "Catalog expansion ranks behind testing price on hot demand."
            )
        elif best_action in ("improve_listing", "update_listing"):
            contrast_phrase = (
                "A flash promo pulls clicks, yet listing fixes last longer "
                "for your setup."
            )
        else:
            t_alt = top_alt.replace("_", " ")
            t_best = best_action.replace("_", " ")
            contrast_phrase = f"{t_best.title()} edges out {t_alt} here."

    choice_contrast = contrast_phrase

    rationale = {
        "situation": situation,
        "decision": intent_type,
        "why_this_action": (
            "discounts increase visibility in ranking algorithms"
            if intent_type == "push_offer"
            else "re-engagement steps help recover lost customers"
            if intent_type == "reactivate_user"
            else "premium positioning leverages strong performance"
            if intent_type == "upsell"
            else "contextual insight for merchant growth"
        ),
        "risk_if_ignored": risk_if_ignored,
        "confidence": "high"
        if abs(relative_gap) > 0.2 or inactivity_days > 7
        else "medium",
        "cta_reason": (
            "aligns activate CTA with offer execution"
            if intent_type == "push_offer"
            else "narrow promote CTA preserves upsell focus"
            if intent_type == "upsell"
            else "restart plan CTA lowers activation cost"
            if intent_type == "reactivate_user"
            else "open numbers CTA avoids fake precision"
            if intent_type == "inform_insight"
            else "tight-step CTA for nudges"
        ),
        "alternatives_considered": rationale_alternatives,
        "why_rejected": rationale_why_rejected,
        "contrast": contrast_phrase,
    }

    decision = {
        "intent_type": intent_type,
        "urgency": urgency,
        "engagement_potential": engagement_potential,
        "offer_to_push": offer_to_push,
        "reasoning_path": reasoning_path,
        "category": category_name,
        "candidate_actions": candidate_actions,
        "action_scores": scored,
        "best_action": best_action,
        "alternatives": alternatives,
        "choice_contrast": choice_contrast,
    }
    return decision, rationale
