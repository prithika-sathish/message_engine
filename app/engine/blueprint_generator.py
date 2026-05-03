# Deterministic blueprint: merchant language, single dominant signal, category lexicon.
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

_MAX_BODY_CHARS = 300

_WEAK_PHRASES = ("this means", "this can help", "perhaps", "maybe")

_Lex = Dict[str, str]

_CATEGORY_BUCKETS = (
    ("restaurants", ("restaurant", "food", "dining", "cafe", "bistro")),
    ("gyms", ("gym", "fitness", "workout", "training")),
    ("salons", ("salon", "spa", "beauty", "barber")),
    ("pharmacies", ("pharmac", "chemist", "medical_store")),
    ("dentists", ("dent", "orthodont", "dental")),
)

# Shops / apparel reuse general wording but sharper peer label.
_BUCKET_ALIASES = {
    "fashion_retail": {
        "peers": "similar shops nearby",
        "presence": "your shop page",
        "back_place": "store",
    },
}


def _lex_with_alias(bucket: str, category_name: str) -> _Lex:
    base = _lex(bucket)
    n = (category_name or "").lower()
    if any(k in n for k in ("fashion", "apparel", "clothing", "boutique")):
        base = {**base, **_BUCKET_ALIASES["fashion_retail"]}
    return base

# Vocabulary keyed by bucket (merchant-facing; no internal product words).
_LEXICON: Dict[str, _Lex] = {
    "restaurants": {
        "people": "customers",
        "outcome_hint": "orders",
        "peers": "similar restaurants nearby",
        "discovery": "how often new customers notice you",
        "value_line": "order size",
        "activity_hint": "orders and reservations",
        "promo_focus": "a clear promotion on something you sell well already",
        "presence": "your business page",
        "back_place": "restaurant",
    },
    "gyms": {
        "people": "members",
        "outcome_hint": "activity",
        "peers": "similar gyms nearby",
        "discovery": "how discoverable your gym is",
        "value_line": "per-member value",
        "activity_hint": "class bookings and visits",
        "promo_focus": "a straightforward trial or bundle on what members already join",
        "presence": "your gym page",
        "back_place": "gym",
    },
    "salons": {
        "people": "clients",
        "outcome_hint": "bookings",
        "peers": "similar salons nearby",
        "discovery": "how quickly new bookings find you",
        "value_line": "average booking value",
        "activity_hint": "appointments and repeat visits",
        "promo_focus": "a simple package on services you already book most",
        "presence": "your salon page",
        "back_place": "salon",
    },
    "pharmacies": {
        "people": "patients",
        "outcome_hint": "refills",
        "peers": "similar pharmacies nearby",
        "discovery": "how reliably locals see your services",
        "value_line": "per-visit basket value",
        "activity_hint": "refill pickups and consultations",
        "promo_focus": "a concise offer aligned to what patients already refill",
        "presence": "your pharmacy page",
        "back_place": "pharmacy",
    },
    "dentists": {
        "people": "patients",
        "outcome_hint": "appointments",
        "peers": "similar practices nearby",
        "discovery": "how often people choose you for the next visit",
        "value_line": "value per appointment",
        "activity_hint": "scheduled visits and recalls",
        "promo_focus": "a clear offer on the services you already schedule most",
        "presence": "your practice page",
        "back_place": "practice",
    },
    "general": {
        "people": "customers",
        "outcome_hint": "visit value",
        "peers": "similar businesses nearby",
        "discovery": "how easy it is for customers to find you",
        "value_line": "per-customer spending",
        "activity_hint": "customer activity",
        "promo_focus": "one clear, time-bound deal on something you already sell",
        "presence": "your business page",
        "back_place": "store",
    },
}

_BANNED_PHRASES = (
    "offer block",
    "storefront signal",
    "adjacent mover",
    "visibility boost",
    "stock keeping",
)
_BANNED_WORDS = ("hero", "tags", "retrieval", "sku", "dashboard", "funnel", "kpi")

_PERSONALIZE_MIN_DIGITS = 1


def _norm(s: str) -> str:
    t = s
    for phrase in _WEAK_PHRASES:
        t = re.sub(re.escape(phrase), "", t, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", t).strip()


def _pct_round(x: float) -> int:
    return max(0, min(999, round(x * 100)))


def _mask_sentence_split(s: str) -> Tuple[str, str]:
    masked = re.sub(r"(\d)\.(\d)", r"\1․\2", s.replace("%", "##PCT##"))
    return masked, s


def _unmask_sentence_split(masked_joined: str) -> str:
    return masked_joined.replace("․", ".").replace("##PCT##", "%")


def _sentence_count(s: str) -> int:
    masked, _ = _mask_sentence_split(s)
    return len([p for p in masked.split(".") if p.strip()])


def _strip_redundant_phrases(body: str) -> str:
    return re.sub(
        r"\bvisibility\s+and\s+shopper\s+visibility\b",
        "how customers see you",
        body,
        flags=re.IGNORECASE,
    )


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


def _brief_body(observation: str, implication: str, closing: str, cap: int) -> str:
    """[strong signal — metric proof]. [concrete action]."""
    obs = observation.strip().rstrip(".")
    impl = implication.strip().rstrip(".")
    act = closing.strip().rstrip(".")

    if impl:
        main = f"{obs} \u2014 {impl}"
    else:
        main = obs

    if act:
        body = f"{main}. {act}."
    else:
        body = f"{main}."
    return _finalize_brevity(body, max_sentences=2, cap=cap)


def _truncate_body_hard_cap(body: str, cap: int) -> str:
    if len(body) <= cap:
        return body
    trimmed = body[:cap]
    if "." in trimmed:
        trimmed = trimmed.rsplit(".", 1)[0]
    t = trimmed.strip()
    return t + "." if t else body[:cap].strip() + "."


def _category_bucket(category_name: str) -> str:
    n = (category_name or "").lower()
    for bucket, keys in _CATEGORY_BUCKETS:
        if any(k in n for k in keys):
            return bucket
    return "general"


def _lex(bucket: str) -> _Lex:
    return dict(_LEXICON.get(bucket, _LEXICON["general"]))


def _opening(name: str) -> str:
    n = name.strip()
    return f"{n}, " if n else ""


def _roll(*parts: str) -> int:
    raw = "|".join(str(p) for p in parts)
    h = 0
    for i, c in enumerate(raw):
        h = (h * 131 + ord(c) * (i + 1)) & 0xFFFFFFFF
    return h % 3


def _peer_head(peer_phrase: str) -> str:
    return peer_phrase.replace(" nearby", "").strip()


def _perf_tier_tag(
    dominant: str,
    trailing: Optional[bool],
    inactivity_days: int,
) -> str:
    if dominant == "inactive":
        if inactivity_days >= 14:
            return "in14"
        if inactivity_days >= 7:
            return "in7"
        return "in_small"
    if dominant == "momentum":
        return "mom"
    if dominant == "ctr_headwind":
        if trailing is True:
            return "ctr_trail"
        if trailing is False:
            return "ctr_above"
        return "ctr_miss"
    if trailing is True:
        return "neu_trail"
    if trailing is False:
        return "neu_lead"
    return "neu_mid"


def _pattern_abc(dominant: str, bucket: str, tier: str) -> str:
    return ("A", "B", "C")[_roll(dominant, bucket, tier)]


def _y_ctrl(prefix: str) -> str:
    return "your" if prefix.strip() else "Your"


def _has_jargon(text: str) -> bool:
    low = text.lower()
    if any(p in low for p in _BANNED_PHRASES):
        return True
    tokens = set(re.findall(r"[a-z0-9]+", low))
    return any(w in tokens for w in _BANNED_WORDS)


def _personalized_opener_ok(merchant_name: str, text: str, category_name: str) -> bool:
    if merchant_name.strip() and merchant_name.strip().lower() in text.lower():
        return True
    if any(c.isdigit() for c in text):
        return True
    cat_slug = category_name.strip().lower()
    if cat_slug:
        bn = _category_bucket(category_name)
        for token in (_LEXICON.get(bn, _LEXICON["general"]).values()):
            if len(token) > 8 and token.lower() in text.lower():
                return True
        if cat_slug[:4] in text.lower():
            return True
    return False


def _impl_inactive(days: int, L: _Lex) -> str:
    if days >= 14:
        return f"{L['people']} see you less than {L['peers']} who stay active"
    if days >= 7:
        return f"{L['people']} overlook you beside busy {L['peers']}"
    return f"attention fades next to sharper {L['peers']}"


def _action_reactivate(days: int, L: _Lex) -> str:
    if days >= 14:
        return (
            f"Refresh {L['presence']} plus what you promote to pull {L['people']} "
            f"back to choosing you"
        )
    return (
        f"Update {L['presence']} alongside your promo to put {L['activity_hint']} "
        f"back in view"
    )


def _action_offer_optimize(L: _Lex) -> str:
    return (
        f"Making your offer easier to see helps more {L['people']} pick you"
    )


def _action_engagement_no_offer(L: _Lex) -> str:
    return (
        f"Tightening what you say you sell lifts how fast {L['people']} recognize you"
    )


def _action_push_promo(L: _Lex) -> str:
    return (
        f"Run {L['promo_focus']} to pull more {L['people']} forward today"
    )


def _action_upsell(L: _Lex) -> str:
    return (
        f"Bundle items customers already buy together to lift {L['value_line']} "
        f"without new traffic"
    )


def _action_insight_low(L: _Lex) -> str:
    return (
        f"Fix either your story online, how the deal reads, or how fast people spot you"
    )


def _action_insight_high(L: _Lex) -> str:
    return (
        f"Pair small extras with moves you prove already work for returning {L['people']}"
    )


def _cta_inactive(strong: bool, L: _Lex, bucket: str, pattern: str) -> Tuple[str, str]:
    v = _roll("cta_in", bucket, pattern, "s" if strong else "w")
    oh = L.get("outcome_hint") or "activity"
    opts = [
        "Want me to refresh your listings now?",
        f"Want me to refresh what you publish so {oh} rebound?",
        "Want me to update your listings and promo line today?",
    ]
    idx = (v + (1 if strong else 0)) % len(opts)
    return ("binary_yes_no", opts[idx])


def _cta_ctr_offers(
    has_offer: bool,
    L: _Lex,
    bucket: str,
    pattern: str,
    intent: str,
) -> Tuple[str, str]:
    v = _roll("cta_ctr", bucket, pattern, intent, str(has_offer))
    if has_offer:
        opts = [
            "Want me to make your offer easier to spot?",
            "Want me to tighten the offer wording on your listings?",
            f"Want me to restage how that promotion shows on {L['presence']}?",
        ]
    else:
        opts = [
            "Want me to frame one straight promotion around your bestseller?",
            f"Want me to draft one clear offer line for new {L['people']}?",
            "Want me to pick one product lane and spotlight a clean deal?",
        ]
    return ("binary_yes_no", opts[v])


def _cta_momentum(L: _Lex, bucket: str, pattern: str) -> Tuple[str, str]:
    v = _roll("cta_mom", bucket, pattern)
    oh = L.get("outcome_hint") or "spend"
    opts = [
        f"Want me to bundle what your {L['people']} already buy together to lift {oh}?",
        "Want me to line up bundles beside your movers today?",
        "Want bundle ideas around what your customers already buy?",
    ]
    return ("binary_yes_no", opts[v])


def _cta_neutral_nudge(L: _Lex, bucket: str, pattern: str) -> Tuple[str, str]:
    v = _roll("cta_nudge", bucket, pattern)
    opts = [
        f"Want me to sharpen how new {L['people']} read what you sell?",
        "Want me to tighten your opening listing lines now?",
        f"Want me to spell out where {L['people']} tap you fastest?",
    ]
    return ("binary_yes_no", opts[v])


def _cta_neutral_insight(L: _Lex, bucket: str, pattern: str) -> Tuple[str, str]:
    v = _roll("cta_ins", bucket, pattern)
    opts = [
        "Want me to name the single next fix in plain words?",
        "Want me to pick one lever first and outline it cleanly?",
        "Want me to turn the numbers into one concrete move?",
    ]
    return ("binary_yes_no", opts[v])


def _select_cta(
    dominant: str,
    intent: str,
    has_offer: bool,
    inactivity_days: int,
    L: _Lex,
    bucket: str,
    pattern: str,
) -> Tuple[str, str]:
    strong_inactive = inactivity_days >= 10
    if dominant == "inactive":
        return _cta_inactive(strong_inactive, L, bucket, pattern)
    if dominant == "momentum":
        return _cta_momentum(L, bucket, pattern)
    if dominant == "ctr_headwind":
        if has_offer or intent == "nudge_engagement":
            return _cta_ctr_offers(has_offer, L, bucket, pattern, intent)
        if intent == "push_offer":
            return _cta_ctr_offers(False, L, bucket, pattern, intent)
        return _cta_neutral_nudge(L, bucket, pattern)
    if intent == "inform_insight":
        return _cta_neutral_insight(L, bucket, pattern)
    if intent == "nudge_engagement":
        return _cta_neutral_nudge(L, bucket, pattern)
    return _cta_neutral_nudge(L, bucket, pattern)


def _metric_ctr_direct(
    trailing: bool,
    pct_vs: int,
    pct_ctr: int,
    pct_peer: int,
    peer_head: str,
) -> str:
    if trailing:
        return (
            f"CTR is {pct_vs}% below {peer_head}: {pct_ctr}% vs peers at {pct_peer}%"
        )
    return (
        f"CTR is {pct_vs}% above {peer_head}: {pct_ctr}% vs peers at {pct_peer}%"
    )


def _signal_ctr_trailing(
    prefix: str,
    ppl: str,
    fv: str,
    peer_head: str,
    pattern: str,
) -> str:
    if pattern == "A":
        return f"{prefix}{fv} {ppl} are choosing you"
    if pattern == "B":
        return f"{prefix}{ppl} pick other options over you versus {peer_head}"
    return f"{prefix}you lag {peer_head} on shopper interest"


def _signal_ctr_leading(
    prefix: str,
    ppl: str,
    peer_head: str,
    pattern: str,
) -> str:
    if pattern == "A":
        return f"{prefix}{ppl} already choose you more than {peer_head}"
    if pattern == "B":
        return f"{prefix}{ppl} lean heavier toward you than {peer_head}"
    return f"{prefix}you lead {peer_head} on shopper pulls"


def _compose_single_signal(
    dominant: str,
    intent: str,
    *,
    prefix: str,
    L: _Lex,
    bucket: str,
    pattern: str,
    has_offer: bool,
    has_ctr_facts: bool,
    trailing: Optional[bool],
    pct_vs: Optional[int],
    pct_ctr: Optional[int],
    pct_peer: Optional[int],
    inactivity_days: int,
    category_name: str,
) -> Tuple[str, str, str, str]:
    """Observation, implication, closing (action→outcome), predicted_impact."""

    peer_head = _peer_head(L["peers"])
    yc = _y_ctrl(prefix)
    ppl = L["people"]
    nf = bool(prefix.strip())
    fv = "fewer" if nf else "Fewer"

    if dominant == "inactive":
        d = inactivity_days
        impl = _impl_inactive(d, L)
        closing = _action_reactivate(d, L)
        pred = (
            f"bring {L['people']} back through visible listing updates"
        )
        na = "no activity has been seen"
        if pattern == "A":
            obs = f"{prefix}{na} for {d} days"
        elif pattern == "B":
            obs = f"{prefix}{ppl} see nothing new from you for {d} days"
        else:
            obs = f"{prefix}nothing new has logged for {d} days"
        return obs, impl, closing, pred

    if dominant == "ctr_headwind":
        tr = trailing if trailing is not None else True

        def _trail_actions() -> Tuple[str, str, str]:
            if has_offer and intent == "nudge_engagement":
                return _action_offer_optimize(L), (
                    f"more {L['people']} notice what you promote without invented prices"
                )
            if intent == "push_offer":
                return _action_push_promo(L), (
                    "recover attention versus peers with one focused promotion"
                )
            return _action_engagement_no_offer(L), (
                "clearer wording so people grasp you instantly"
            )

        closing, pred = _trail_actions()

        if has_ctr_facts and None not in (pct_vs, pct_ctr, pct_peer):
            obs = _signal_ctr_trailing(prefix, ppl, fv, peer_head, pattern)
            impl = _metric_ctr_direct(tr, pct_vs, pct_ctr, pct_peer, peer_head)
            return obs, impl, closing, pred

        obs = f"{prefix}you trail {peer_head} on shopper interest"
        impl = ""
        return obs, impl, closing, pred

    if dominant == "momentum":
        closing = _action_upsell(L)
        pred = f"lift {L['value_line']} using bundles you prove already work"
        tr = trailing if trailing is not None else False

        if has_ctr_facts and None not in (pct_vs, pct_ctr, pct_peer):
            obs = _signal_ctr_leading(prefix, ppl, peer_head, pattern)
            impl = _metric_ctr_direct(tr, pct_vs, pct_ctr, pct_peer, peer_head)
            return obs, impl, closing, pred

        var = _roll("mom_open", bucket, pattern)
        openers = [
            f"{prefix}{yc} beat {peer_head}",
            f"{prefix}{ppl} favor you over {peer_head}",
            f"{prefix}you sit ahead of {peer_head}",
        ]
        obs = openers[var]
        impl = ""
        return obs, impl, closing, pred

    # neutral (with CTR facts uses same signals as headwind/lead buckets)
    if (
        has_ctr_facts
        and pct_vs is not None
        and pct_ctr is not None
        and pct_peer is not None
        and trailing is not None
    ):
        met = _metric_ctr_direct(trailing, pct_vs, pct_ctr, pct_peer, peer_head)
        if trailing:
            obs = _signal_ctr_trailing(prefix, ppl, fv, peer_head, pattern)
        else:
            obs = _signal_ctr_leading(prefix, ppl, peer_head, pattern)
        impl = met
        if trailing:
            cg = (
                _action_engagement_no_offer(L)
                if not has_offer
                else _action_offer_optimize(L)
            )
            closing = cg
            pred = "steady clarity on one lever before spending more"
        else:
            closing = _action_insight_high(L)
            pred = "protect your edge while layering proven extras"
        return obs, impl, closing, pred

    obs = f"{prefix}signals sit balanced against {peer_head}"
    impl = ""
    closing = _action_insight_low(L)
    pred = "pick one improvement and measure it plainly next week"
    return obs, impl, closing, pred


def _fallback_body(
    dominant: str,
    prefix: str,
    L: _Lex,
    inactivity_days: int,
    bucket: str,
) -> Tuple[str, str, str, str]:
    if dominant == "inactive":
        return _compose_single_signal(
            "inactive",
            "reactivate_user",
            prefix=prefix,
            L=L,
            bucket=bucket,
            pattern="A",
            has_offer=False,
            has_ctr_facts=False,
            trailing=None,
            pct_vs=None,
            pct_ctr=None,
            pct_peer=None,
            inactivity_days=inactivity_days,
            category_name="",
        )
    obs = f"{prefix}one lever matters for winning back your {L['people']}"
    impl = f"{L['discovery'].capitalize()} governs repeat visits"
    closing = _action_insight_low(L)
    pred = "one focused change your customers can actually notice"
    return obs, impl, closing, pred


def _enforce_grounded_observation(
    obs: str,
    merchant_name: str,
    inactivity_days: int,
    has_ctr_facts: bool,
    dominant: str,
    L: _Lex,
) -> str:
    digits = sum(1 for c in obs if c.isdigit())
    if dominant == "inactive":
        return obs
    if digits >= _PERSONALIZE_MIN_DIGITS or has_ctr_facts:
        return obs
    if inactivity_days > 0:
        label = merchant_name.strip() or "Your business"
        return (
            f"{label}, add your click rate plus the usual rate for similar businesses "
            f"so we state the gap in plain numbers next time."
        )
    label = merchant_name.strip() or "Your business"
    return (
        f"{label}, share your click rate and the peer typical rate to keep this message fully grounded."
    )


def generate_blueprint(decision: dict, signals: dict) -> dict:
    merchant = signals["merchant"]
    trigger = signals["trigger"]
    category = signals["category"]
    intent = decision["intent_type"]
    urgency = float(decision.get("urgency") or trigger.get("urgency") or 0.0)
    dominant = str(decision.get("dominant_signal") or "neutral")

    merchant_name = str(merchant.get("name") or "").strip()
    has_offer = bool(merchant.get("has_active_offer"))
    ctr = merchant.get("ctr")
    ctr_peer = merchant.get("ctr_peer_median")
    ctr_delta = merchant.get("ctr_delta")
    if ctr_delta is None and ctr is not None and ctr_peer is not None:
        ctr_delta = ctr - ctr_peer
    if ctr_delta is None:
        ctr_delta = 0.0

    inactivity_days = int(merchant.get("inactivity_days") or 0)
    bucket = _category_bucket(category.get("name") or "")
    cat_label = str(category.get("name") or "")
    L = _lex_with_alias(bucket, cat_label)
    prefix = _opening(merchant_name)
    category_name = cat_label

    has_ctr_facts = ctr is not None and ctr_peer is not None and ctr_peer > 1e-12
    relative_gap = (ctr - ctr_peer) / ctr_peer if has_ctr_facts else None
    trailing = relative_gap < 0 if relative_gap is not None else None
    pct_vs = abs(int(round(relative_gap * 100))) if relative_gap is not None else None
    pct_ctr = _pct_round(ctr) if ctr is not None else None
    pct_peer = _pct_round(ctr_peer) if ctr_peer is not None else None

    tier_tag = _perf_tier_tag(dominant, trailing, inactivity_days)
    pattern = _pattern_abc(dominant, bucket, tier_tag)

    obs, impl, closing, predicted_impact = _compose_single_signal(
        dominant,
        intent,
        prefix=prefix,
        L=L,
        bucket=bucket,
        pattern=pattern,
        has_offer=has_offer,
        has_ctr_facts=has_ctr_facts,
        trailing=trailing,
        pct_vs=pct_vs,
        pct_ctr=pct_ctr,
        pct_peer=pct_peer,
        inactivity_days=inactivity_days,
        category_name=category_name,
    )

    observation = _enforce_grounded_observation(
        obs, merchant_name, inactivity_days, has_ctr_facts, dominant, L
    )
    implication = impl.strip()

    body = _brief_body(observation, implication, closing, _MAX_BODY_CHARS)
    body = _truncate_body_hard_cap(body, _MAX_BODY_CHARS)
    body = _finalize_brevity(body, max_sentences=2, cap=_MAX_BODY_CHARS).strip()
    if not body.endswith("."):
        body += "."

    cta_type, cta = _select_cta(
        dominant, intent, has_offer, inactivity_days, L, bucket, pattern
    )

    if _has_jargon(body) or _has_jargon(cta):
        fb_obs, fb_impl, fb_close, predicted_impact = _fallback_body(
            dominant, prefix, L, inactivity_days, bucket
        )
        body = _brief_body(fb_obs, fb_impl, fb_close, _MAX_BODY_CHARS).strip()
        if not body.endswith("."):
            body += "."
        cta_type, cta = _select_cta(
            dominant, intent, has_offer, inactivity_days, L, bucket, pattern
        )

    if not _personalized_opener_ok(merchant_name, body, category_name):
        if category_name.strip() and merchant_name.strip() == "":
            tail = body[0].lower() + body[1:] if body else body
            body = _finalize_brevity(
                f"As a {category_name.strip()} business, {tail}",
                cap=_MAX_BODY_CHARS,
            ).strip()
            if not body.endswith("."):
                body += "."

    risk_if_ignored = ""
    if dominant == "ctr_headwind" and trailing and urgency > 0.7:
        risk_if_ignored = "thin interest hides you when people compare nearby options"
    elif dominant == "inactive" and urgency > 0.7:
        risk_if_ignored = "quiet pages are easier for people to skip over"

    return {
        "body": body,
        "CTA_type": cta_type,
        "cta": cta,
        "tone_profile": category.get("tone", "professional"),
        "constraints": [],
        "insight": (
            f"{pct_vs}% vs peers" if pct_vs is not None else "inputs partial for peer gap"
        ),
        "percentile_band": "",
        "metric": (
            f"CTR {pct_ctr}% vs peer {pct_peer}%"
            if pct_ctr is not None and pct_peer is not None
            else "CTR inputs partial"
        ),
        "suggestion": closing[:120],
        "action": closing[:120],
        "question": "",
        "data": "",
        "predicted_impact": predicted_impact,
        "risk_if_ignored": risk_if_ignored,
        "dominant_signal": dominant,
        "has_active_offer": has_offer,
    }
