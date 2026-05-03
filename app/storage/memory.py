# In-memory storage (stub, can be replaced with SQLite)
class MemoryStorage:
    def __init__(self):
        self.conversations = {}
        self.triggers = {}
        self.merchants = {}

    def save_conversation(self, conv_id, data):
        self.conversations[conv_id] = data

    def get_conversation(self, conv_id):
        return self.conversations.get(conv_id, {})

    def save_merchant(self, merchant_id, data):
        self.merchants[merchant_id] = data

    def get_merchant(self, merchant_id):
        return self.merchants.get(merchant_id, {})

    def save_trigger(self, trigger_id, data):
        self.triggers[trigger_id] = data

    def get_trigger(self, trigger_id):
        return self.triggers.get(trigger_id, {})
