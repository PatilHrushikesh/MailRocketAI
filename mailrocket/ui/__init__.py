"""FastAPI-based review UI for inspecting posts and editing their analyses.

Posts are read-only (with a deep-link to the LinkedIn URL); analyses are
editable so you can tweak subjects/bodies/contacts before queueing them
for the next `make send`.
"""
from mailrocket.ui.server import create_app, run

__all__ = ["create_app", "run"]
