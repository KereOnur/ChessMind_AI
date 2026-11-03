"""Shared deterministic monotonic time provider for UI acceptance tests."""
class FakeTime:
    def __init__(self):self.value=0.
    def __call__(self):return self.value
    def advance(self,seconds):self.value+=seconds
