"""A toy support agent used as a demo target for Modelpin (illustrative; not executed
by the test suite). It depends on a specific model id -- exactly the kind of dependency
Modelpin watches.
"""

MODEL = "claude-opus-4-6"  # <- `mp scan` should detect this


def handle(message: str) -> str:
    # In a real agent this calls MODEL with tools (lookup_order, issue_refund, ...).
    return f"[{MODEL}] would handle: {message}"
