"""Rule-based intent router (baseline). A trained classifier may later sit behind the same interface.

The router only picks a *route label*; it never authorises anything. Policy lives in the task engine.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ROUTES = [
    "general_question", "research", "coding_assistance", "document_analysis",
    "data_analysis", "memory_retrieval", "voice_command", "tool_execution",
]

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


def route_request(text: str) -> RouteDecision:
    for label, pat in _RULES:
        if pat.search(text):
            return RouteDecision(label, 0.7, "rules")
    return RouteDecision("general_question", 0.5, "fallback")
