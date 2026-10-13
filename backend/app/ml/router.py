"""Intent router. Rules are the default; a trained classifier is OPTIONAL (JARVIS_ROUTER=model).

The router only picks a *route label*. It never authorises anything: tool policy and approvals live in the task
engine, so a wrong or adversarially-induced label cannot cause a sensitive action.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import ROOT, get_settings

log = logging.getLogger("jarvis.router")

ROUTES = [
    "general_question", "research", "coding_assistance", "document_analysis",
    "data_analysis", "memory_retrieval", "voice_command", "tool_execution",
]
ARTIFACT_DIR = ROOT / "backend" / "ml" / "artifacts"
DEFAULT_THRESHOLD = 0.55


def confidence_threshold(artifact_dir: Path = ARTIFACT_DIR) -> float:
    """Threshold selected during training on out-of-fold predictions (ml/train.py); conservative default otherwise."""
    try:
        return float(json.loads((artifact_dir / "router_meta.json").read_text(encoding="utf-8"))["confidence_threshold"])
    except Exception:
        return DEFAULT_THRESHOLD

_RULES: list[tuple[str, re.Pattern]] = [
    ("data_analysis", re.compile(r"\b(statistic|average|mean|median|std|stdev|variance|dataset|csv|chart)\w*", re.I)),
    ("coding_assistance", re.compile(r"\b(test|tests|pytest|bug|stack ?trace|compile|refactor|function|code|repo|project)\b", re.I)),
    ("tool_execution", re.compile(r"\b(run|execute|list|read|open|search|find|show)\b.*\b(file|files|folder|directory|dir|history|tasks?)\b", re.I)),
    ("memory_retrieval", re.compile(r"\b(remember|recall|my preference|did i (say|tell))\b", re.I)),
    ("document_analysis", re.compile(r"\b(summari[sz]e|document|pdf|report on this)\b", re.I)),
    ("research", re.compile(r"\b(research|sources?|compare|literature|investigate)\b", re.I)),
    ("voice_command", re.compile(r"\b(speak|say aloud|read (it )?out|mute|volume)\b", re.I)),
]


@dataclass
class RouteDecision:
    route: str
    confidence: float
    source: str  # "rules" | "model" | "fallback"


def rule_route(text: str) -> RouteDecision:
    for label, pat in _RULES:
        if pat.search(text):
            return RouteDecision(label, 0.7, "rules")
    return RouteDecision("general_question", 0.5, "fallback")


@lru_cache(maxsize=2)
def _load(kind: str, artifact_dir: str):
    d = Path(artifact_dir)
    if kind == "torch":
        from ml import torch_model

        return torch_model.load(d / "torch_router.pt")
    from ml import sklearn_model

    return sklearn_model.load(d / "sklearn_router.joblib")


def model_route(text: str, kind: str = "sklearn", artifact_dir: Path = ARTIFACT_DIR) -> RouteDecision | None:
    """Return a decision only if the artifact loads and the model is confident; otherwise None (caller falls back)."""
    try:
        model = _load(kind, str(artifact_dir))
        if kind == "torch":
            from ml import torch_model
            from ml.dataset import LABELS

            proba = torch_model.predict_proba(model, [text])[0]
            i = int(proba.argmax())
            label, conf = LABELS[i], float(proba[i])
        else:
            from ml import sklearn_model

            label, conf = sklearn_model.predict_with_confidence(model, [text])[0]
    except Exception as e:  # missing/corrupt artifact must never break routing
        log.warning("router model unavailable (%s); using rules", type(e).__name__)
        return None
    return RouteDecision(label, conf, "model") if conf >= confidence_threshold(artifact_dir) and label in ROUTES else None


def route_request(text: str) -> RouteDecision:
    s = get_settings()
    if s.router == "model":
        d = model_route(text, s.router_model)
        if d is not None:
            return d
    return rule_route(text)
