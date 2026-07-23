"""Semantic layer (SEMANTIC_LAYER.md Part 2).

Builds a SemanticFrame between JWT verification and dispatch in routers/ask.py.
P0 ships typed stubs; entity resolution, classification, and gating land in P1/P2.
"""

from .frame import QueryClass, SemanticFrame, build_frame
from .gating import GateDecision, gate

__all__ = ["SemanticFrame", "QueryClass", "build_frame", "GateDecision", "gate"]
