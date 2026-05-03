# Reply handler intelligence (stub)
def handle_reply(reply: str, conversation_id: str, state_manager):
    # Classify reply
    reply_lower = reply.lower()
    if any(x in reply_lower for x in ["yes", "ok", "accept"]):
        classification = "accept"
        action = "send"
    elif any(x in reply_lower for x in ["no", "reject"]):
        classification = "reject"
        action = "end"
    elif any(x in reply_lower for x in ["what", "?"]):
        classification = "confused"
        action = "wait"
    else:
        classification = "off-topic"
        action = "wait"
    return {"classification": classification, "action": action}
