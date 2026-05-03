# In-memory state manager (stub)
class StateManager:
    def __init__(self):
        self.state = {}
    def update_context(self, signals):
        self.state["last_context"] = signals
    def process_tick(self, tick_data):
        self.state["last_tick"] = tick_data
    def get_state(self):
        return self.state
