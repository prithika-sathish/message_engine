from app.engine.signal_extraction import extract_signals
from app.engine.decision_engine import make_decision
from app.engine.blueprint_generator import generate_blueprint
from app.engine.llm_renderer import render_message
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
    signals = extract_signals(case["input"])
    decision, rationale = make_decision(signals)
    blueprint = generate_blueprint(decision, signals)
    body, cta, send_as = render_message(blueprint)

    print("\n---", case["name"], "---")
    print("BODY:", body)
    print("CTA:", cta)
    print("DECISION:", decision["intent_type"])
    print("IMPACT:", blueprint.get("predicted_impact"))
