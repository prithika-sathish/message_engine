from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.engine.signal_extraction import extract_signals
from app.engine.decision_engine import make_decision
from app.engine.blueprint_generator import generate_blueprint
from app.engine.llm_renderer import render_message
from app.engine.suppression import get_suppression_key
from app.engine.state_manager import StateManager
from app.engine.reply_handler import handle_reply

_PUBLIC_RATIONALE_KEYS = (
    "situation",
    "decision",
    "alternatives_considered",
    "why_rejected",
    "expected_impact",
    "confidence",
)


def _public_rationale(r: Dict[str, Any]) -> Dict[str, Any]:
    alts = r.get("alternatives_considered")
    if alts is None:
        alts = []
    if not isinstance(alts, list):
        alts = [str(alts)]
    alts = [str(x) for x in alts]
    return {
        "situation": r.get("situation") or "",
        "decision": r.get("decision") or "",
        "alternatives_considered": alts,
        "why_rejected": r.get("why_rejected") or "",
        "expected_impact": r.get("expected_impact") or "",
        "confidence": r.get("confidence") or "medium",
    }


app = FastAPI(title="Vera AI", version="2.0.0")
state_manager = StateManager()

_ContextEntry = Tuple[int, Dict[str, Any]]
_context_store: Dict[Tuple[str, str], _ContextEntry] = {}


def _normalize_incoming_context(raw: Dict[str, Any]) -> Dict[str, Any]:
    base = dict(raw or {})
    merchant = dict(base.pop("merchant", None) or {})
    category = dict(base.pop("category", None) or {})
    customer = dict(base.pop("customer", None) or {})
    trigger = dict(base.pop("trigger", None) or {})

    flat_keys = {"merchant_id", "category_slug", "identity", "performance", "signals"}
    wants_flat_merge = bool(flat_keys.intersection(base.keys()))

    ident = base.get("identity") if isinstance(base.get("identity"), dict) else {}
    perf = base.get("performance") if isinstance(base.get("performance"), dict) else {}

    if wants_flat_merge:
        mid = base.get("merchant_id")
        if ident.get("name"):
            merchant["name"] = ident["name"]
        elif mid and not merchant.get("name"):
            merchant.setdefault("name", str(mid))

        if "ctr" in perf:
            merchant["ctr"] = float(perf["ctr"])
        for k in (
            "ctr_peer_median",
            "conversion_rate",
            "inactivity_days",
            "recent_trend",
            "has_active_offer",
        ):
            if k in perf:
                merchant[k] = perf[k]

        vw = perf.get("views")
        if vw is not None:
            mperf = merchant.setdefault("performance", {})
            if isinstance(mperf, dict):
                mperf.setdefault("views", vw)

        slug = base.get("category_slug")
        if slug:
            category.setdefault("name", str(slug).replace("_", " "))

    return {
        **base,
        "merchant": merchant,
        "category": category,
        "customer": customer,
        "trigger": trigger,
    }


def _trigger_rank_key(tr: Dict[str, Any]) -> Tuple[float, str]:
    strength = float(tr.get("strength_score", tr.get("strength", 0.5)))
    recency = float(tr.get("recency_weight", tr.get("recency", 1.0)))
    tid = str(tr.get("trigger_id", tr.get("id", "")))
    return (-(strength * recency), tid)


def _select_best_trigger(available_triggers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not available_triggers:
        return None
    return sorted(available_triggers, key=_trigger_rank_key)[0]


def _tick_enrich_candidate(tr: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(tr)
    if "strength_score" not in out and "strength" not in out:
        if "urgency" in out:
            try:
                u = float(out["urgency"])
                out["strength_score"] = max(0.1, min(1.0, u / 5.0))
            except (TypeError, ValueError):
                out.setdefault("strength_score", 0.5)
        else:
            out.setdefault("strength_score", 0.5)
    if "recency_weight" not in out and "recency" not in out:
        out.setdefault("recency_weight", 1.0)
    return out


def _tick_normalize_available(raw: Sequence[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in raw or []:
        if isinstance(item, str):
            d = {"id": item, "trigger_id": item}
        elif isinstance(item, dict):
            d = dict(item)
        else:
            continue
        out.append(_tick_enrich_candidate(d))
    return out


def _tick_trigger_for_signals(tr: Dict[str, Any]) -> Dict[str, Any]:
    enriched = _tick_enrich_candidate(tr)
    ttype = str(
        enriched.get("type") or enriched.get("trigger_type") or enriched.get("kind") or "neutral"
    )
    try:
        ss = float(enriched.get("strength_score", enriched.get("strength", 0.8)))
    except (TypeError, ValueError):
        ss = 0.8
    try:
        rw = float(enriched.get("recency_weight", enriched.get("recency", 1.0)))
    except (TypeError, ValueError):
        rw = 1.0
    return {"type": ttype, "strength_score": ss, "recency_weight": rw}


def compose(
    category: Dict[str, Any],
    merchant: Dict[str, Any],
    trigger: Dict[str, Any],
    customer: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "category": category or {},
        "merchant": merchant or {},
        "trigger": trigger or {},
        "customer": customer or {},
    }
    signals = extract_signals(payload)
    decision, rationale = make_decision(signals)
    blueprint = generate_blueprint(decision, signals)
    rationale = dict(rationale)
    rationale["expected_impact"] = str(blueprint.get("predicted_impact") or "")
    body, cta, send_as = render_message(blueprint)
    try:
        suppression_key = get_suppression_key(signals)
    except (KeyError, TypeError):
        suppression_key = f"{signals['trigger']['type']}:{signals['category'].get('name', '')}"

    composed = {
        "body": body,
        "cta": cta,
        "send_as": send_as,
        "suppression_key": suppression_key,
        "rationale": _public_rationale(rationale),
    }
    state_manager.state["last_compose_signals"] = signals
    state_manager.state["last_compose_payload"] = payload
    return composed


class ContextRequest(BaseModel):
    scope: str = Field(default="default")
    context_id: str
    version: int = Field(default=0, ge=0)
    context: Optional[Dict[str, Any]] = None
    payload: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Alias for context (same body shape); use either context or payload",
    )

    @model_validator(mode="after")
    def _resolve_context_payload(self):
        blob = self.context if self.context is not None else self.payload
        if blob is None:
            raise ValueError("Provide 'context' or 'payload' (object)")
        if not isinstance(blob, dict):
            raise ValueError("context/payload must be an object")
        object.__setattr__(self, "context", dict(blob))
        return self


class TickRequest(BaseModel):
    scope: str = Field(default="default")
    context_id: str
    trigger: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Contract trigger; selected_trigger_id echoes trigger.type",
    )
    available_triggers: List[Any] = Field(default_factory=list)


class ReplyRequest(BaseModel):
    reply: str
    conversation_id: str


class ComposeRequest(BaseModel):
    context: Optional[Dict[str, Any]] = None
    category: Optional[Dict[str, Any]] = None
    merchant: Optional[Dict[str, Any]] = None
    trigger: Optional[Dict[str, Any]] = None
    customer: Optional[Dict[str, Any]] = None


@app.get("/")
def root():
    return {
        "message": "Vera AI Message Engine is running",
        "docs": "/docs",
        "endpoints": {
            "POST": ["/v1/context", "/v1/tick", "/v1/reply"],
            "GET": ["/v1/healthz", "/v1/metadata"],
        },
        "flow": [
            "POST /v1/context -> load merchant context",
            "POST /v1/tick -> generate decision/message",
            "POST /v1/reply -> handle follow-up",
        ],
        "health": "/v1/healthz",
        "version": "2.0.0",
    }


@app.post("/v1/context")
def post_context(req: ContextRequest):
    key = (req.scope, req.context_id)
    current = _context_store.get(key)
    if current is not None:
        prev_ver, _ = current
        if req.version <= prev_ver:
            return {"status": "ok", "updated": False, "stored_version": prev_ver}

    merged = _normalize_incoming_context(dict(req.context or {}))
    merged.setdefault("_meta", {})
    merged["_meta"]["version"] = req.version

    _context_store[key] = (req.version, merged)
    try:
        sig = extract_signals(merged)
        state_manager.update_context(sig)
    except Exception:
        state_manager.state["last_context_raw"] = merged

    return {"status": "ok", "updated": True, "stored_version": req.version}


@app.post("/v1/tick")
def post_tick(req: TickRequest):
    key = (req.scope, req.context_id)
    entry = _context_store.get(key)
    if entry is None:
        raise HTTPException(status_code=404, detail="unknown context")

    _ver, blob = entry
    candidates = _tick_normalize_available(req.available_triggers)
    if not candidates:
        trig_blob = blob.get("trigger")
        if isinstance(trig_blob, dict) and trig_blob:
            candidates = [_tick_enrich_candidate(dict(trig_blob))]
        else:
            candidates = [_tick_enrich_candidate({"type": "neutral"})]

    best = _select_best_trigger(candidates)

    input_data = dict(blob)
    input_data["trigger"] = _tick_trigger_for_signals(best)

    signals = extract_signals(input_data)
    decision, rationale = make_decision(signals)
    blueprint = generate_blueprint(decision, signals)
    body, cta, send_as = render_message(blueprint)

    state_manager.state["last_compose_signals"] = signals
    state_manager.state["last_compose_payload"] = {
        "category": input_data.get("category") or {},
        "merchant": input_data.get("merchant") or {},
        "trigger": input_data["trigger"],
        "customer": input_data.get("customer") or {},
    }

    state_manager.process_tick(
        {
            "scope": req.scope,
            "context_id": req.context_id,
            "selected_trigger": best,
            "context_version": _ver,
        }
    )

    trig_in = req.trigger if isinstance(req.trigger, dict) else None
    trigger_type = trig_in.get("type") if trig_in else None
    selected_trigger_id = (
        str(trigger_type) if trigger_type not in (None, "") else ""
    )

    return {
        "actions": [{"type": "message", "body": body, "cta": cta, "send_as": send_as}],
        "selected_trigger_id": selected_trigger_id,
        "context_version": _ver,
    }


@app.post("/v1/reply")
def post_reply(req: ReplyRequest):
    out = handle_reply(req.reply, req.conversation_id, state_manager)
    action = out.get("action", "wait")
    if action not in ("send", "wait", "end"):
        action = "wait"
    return {"action": action, "classification": out.get("classification")}


@app.get("/v1/healthz")
def get_healthz():
    return {"status": "ok"}


@app.get("/v1/metadata")
def get_metadata():
    return {
        "team": "Magicpin Vera AI Challenge",
        "service": "Vera AI Message Engine",
        "version": "2.0.0",
        "model": {
            "name": "vera-deterministic",
            "type": "rules-plus-scores",
            "description": "decision_engine + blueprint_generator pipeline",
        },
    }


@app.post("/v1/compose")
def compose_endpoint(req: ComposeRequest):
    if req.context:
        d = req.context
        return compose(
            d.get("category") or {},
            d.get("merchant") or {},
            d.get("trigger") or {},
            d.get("customer"),
        )
    return compose(req.category or {}, req.merchant or {}, req.trigger or {}, req.customer)
