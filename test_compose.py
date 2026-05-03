from app.engine.signal_extraction import extract_signals
from app.engine.decision_engine import make_decision
from app.engine.blueprint_generator import generate_blueprint
from app.main import compose
import os

# Toggle this
os.environ["VERA_USE_GEMINI_RENDERER"] = "1"  # set "0" to compare

cases = [
    {
        "name": "Low CTR + Offer",
        "input": {
            "category": {"name": "food"},
            "merchant": {
                "name": "Spice Villa",
                "ctr": 2.1 / 100,
                "ctr_peer_median": 3.4 / 100,
                "inactivity_days": 1,
                "has_active_offer": True,
            },
            "trigger": {"type": "ctr_drop", "strength_score": 0.8},
        },
    },
    {
        "name": "High Performer",
        "input": {
            "category": {"name": "fashion"},
            "merchant": {
                "name": "Urban Threads",
                "ctr": 5.2 / 100,
                "ctr_peer_median": 3.8 / 100,
                "inactivity_days": 0,
                "has_active_offer": False,
            },
            "trigger": {"type": "performance_spike", "strength_score": 0.7},
        },
    },
    {
        "name": "Inactive",
        "input": {
            "category": {"name": "electronics"},
            "merchant": {
                "name": "TechHub",
                "ctr": 2.9 / 100,
                "ctr_peer_median": 3.0 / 100,
                "inactivity_days": 10,
                "has_active_offer": False,
            },
            "trigger": {"type": "inactivity", "strength_score": 0.9},
        },
    },
]

for case in cases:
    d = case["input"]
    out = compose(d["category"], d["merchant"], d["trigger"], None)
    signals = extract_signals(case["input"])
    decision, _ = make_decision(signals)
    blueprint = generate_blueprint(decision, signals)
    ei = (out["rationale"] or {}).get("expected_impact", "")
    pi = blueprint.get("predicted_impact", "")
    assert ei == pi and ei, (
        "expected_impact must match blueprint predicted_impact: "
        f"{ei!r} vs {pi!r}"
    )
    forbidden = frozenset(("blueprint", "decision", "trigger_id"))
    leaked = forbidden.intersection(out.keys())
    assert not leaked, f"unexpected API fields: {leaked}"

    print("\n---", case["name"], "---")
    print("BODY:", out["body"])
    print("CTA:", out["cta"])
    print("DECISION (internal):", decision["intent_type"])
    print("IMPACT:", ei)
