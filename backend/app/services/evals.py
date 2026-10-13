"""Deterministic evaluation suite. No network, no LLM. Every number is computed from the cases below.

Live-model evaluations (response usefulness, LLM planning quality) are listed as SKIPPED: they need a configured
provider and are intentionally kept separate from these deterministic checks.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from app.agents.rag_graph import MAX_DRAFTS, SYSTEM as RAG_SYSTEM, answer_with_citations, verify_citations
from app.llm.providers import LLMError
from app.ml.router import rule_route
from app.services.planner import PLANNER_SYSTEM, PlanError, make_plan, rule_plan, validate_plan
from app.services.retrieval import Candidate, chunk_text, embed, hybrid_search
from app.tools.registry import ToolError, get_registry
from app.tools.sandbox import resolve_in_workspace, validate_command

EVAL_VERSION = "1.0"

# ---- cases -------------------------------------------------------------------------------------------------------
TOOL_SELECTION = [  # request -> expected ordered tool list (and optional expected args subset)
    ("list the files in the project", ["list_directory"], {}),
    ("what is the mean of 3, 5, 10", ["calculate_statistics"], {"values": [3.0, 5.0, 10.0]}),
    ("run the tests", ["run_command"], {"argv": ["python", "-m", "pytest", "-q"]}),
    ("run npm test", ["run_command"], {"argv": ["npm", "test"]}),
    ("read README.md", ["read_file"], {"path": "README.md"}),
    ("show me something recent", [], {}),  # ambiguous: must NOT invent a plan
    ("show my recent tasks", ["task_history"], {}),
    ("search for 'TODO' in the project", ["search_files"], {"query": "TODO"}),
    ("remember that I prefer dark mode", ["save_memory"], {"kind": "preference"}),
    ("what do you remember about dark mode?", ["search_memory"], {}),
    ("search my documents for the launch date", ["search_documents"], {"query": "the launch date"}),
    ("analyze sales.csv", ["analyze_csv"], {"path": "sales.csv"}),
    ("tell me a joke", [], {}),
    ("what is the capital of France", [], {}),
    ("git status", ["run_command"], {"argv": ["git", "status"]}),
]

PERMISSION_CASES = [  # (kind, input, must_be) ; must_be in {"denied", "approval", "allowed"}
    ("command", ["python", "-m", "pytest", "-q"], "approval"), ("command", ["git", "status"], "allowed"),
    ("command", ["npm", "test"], "approval"), ("command", ["rm", "-rf", "/"], "denied"),
    ("command", ["bash", "-c", "id"], "denied"), ("command", ["python", "-c", "import os"], "denied"),
    ("command", ["pytest", "-p", "evil"], "denied"), ("command", ["git", "push"], "denied"),
    ("command", ["npm", "install", "left-pad"], "denied"), ("command", ["curl", "http://x"], "denied"),
    ("path", "../../etc/passwd", "denied"), ("path", "/etc/passwd", "denied"), ("path", ".env", "denied"),
    ("path", "id_rsa", "denied"), ("path", ".git/config", "denied"), ("path", "src/main.py", "allowed"),
    ("path", "README.md", "allowed"),
]

RAG_CORPUS = {
    "hr_policy": "Employees accrue 1.5 vacation days per month. Unused vacation days carry over up to a maximum of ten days. "
                 "Parental leave is sixteen weeks at full pay for either parent.",
    "security": "All laptops must use full disk encryption. Passwords must be rotated every ninety days and cannot be reused. "
                "Security incidents must be reported to the helpdesk within one hour.",
    "falcon": "Project Falcon launches on March 14. The budget owner is Dana Whitfield. The main risk is supplier delays "
              "for the sensor modules.",
    "onboarding": "New hires receive a laptop on day one. The first week includes orientation, a buddy assignment and access "
                  "requests for the code repository and ticketing system.",
    "travel": "Flights over six hours may be booked in premium economy. Hotel stays are capped at two hundred dollars per night. "
              "Receipts must be submitted within thirty days.",
    "recipes": "Sourdough needs a mature starter, strong flour and a long cold fermentation. Bake in a preheated dutch oven "
               "at a high temperature for crisp crust.",
}
RAG_QUESTIONS = [
    ("how many vacation days do I earn each month", "hr_policy"), ("how long is parental leave", "hr_policy"),
    ("how often do I have to change my password", "security"), ("what must I do after a security incident", "security"),
    ("when does falcon go live", "falcon"), ("who owns the falcon budget", "falcon"),
    ("what do new employees get on their first day", "onboarding"), ("what does orientation week include", "onboarding"),
    ("what is the nightly hotel limit", "travel"), ("when do I need to turn in receipts", "travel"),
    ("how do I get a crispy sourdough crust", "recipes"), ("is full disk encryption required", "security"),
    ("can unused leave roll over to next year", "hr_policy"), ("what's the biggest risk for the falcon project", "falcon"),
]
OUT_OF_SCOPE = ["what is the boiling point of tungsten", "explain quantum chromodynamics lattice gauge theory"]

MEMORIES = {
    "m1": "I prefer dark mode in all editors", "m2": "My sister's birthday is on June 3rd",
    "m3": "Project Atlas uses PostgreSQL and FastAPI", "m4": "I am allergic to peanuts",
    "m5": "Weekly team meeting is on Tuesdays at 10am", "m6": "My preferred programming language is Python",
}
MEMORY_QUERIES = [
    ("which theme do I like in my editor", "m1"), ("when is my sister's birthday", "m2"),
    ("what database does atlas use", "m3"), ("do I have any food allergies", "m4"),
    ("what day is the team meeting", "m5"), ("what language do I like to code in", "m6"),
]

CITATION_CASES = [  # (draft, n_sources, expected_valid)
    ("It launches March 14 [1].", 2, True), ("Both agree [1][2].", 2, True), ("No citations here.", 2, False),
    ("Cites a ghost [3].", 2, False), ("", 2, False), ("NOT_IN_SOURCES", 2, True), ("Zero index [0].", 2, False),
]


# ---- scripted providers (for fault-injection) ----------------------------------------------------------------
class _Provider:
    name, is_real, supports_vision, supports_speech = "eval-scripted", True, False, False

    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def complete(self, system, user, *, json_mode=False):
        self.calls += 1
        r = self.replies[min(self.calls - 1, len(self.replies) - 1)]
        if isinstance(r, Exception):
            raise r
        return r


# ---- metrics -------------------------------------------------------------------------------------------------
def _routing() -> dict:
    from ml.dataset import NATURAL_TEST

    ok = [rule_route(t).route == l for t, l in NATURAL_TEST]
    out = {"cases": len(ok), "rules_accuracy": round(sum(ok) / len(ok), 4)}
    try:
        from app.ml.router import model_route

        hybrid = []
        for t, l in NATURAL_TEST:
            d = model_route(t) or rule_route(t)
            hybrid.append(d.route == l)
        out["hybrid_accuracy"] = round(sum(hybrid) / len(hybrid), 4)
    except Exception:
        out["hybrid_accuracy"] = None
    return out


def _tool_selection() -> dict:
    fails, sel_ok, arg_ok, arg_total = [], 0, 0, 0
    for req, tools, args in TOOL_SELECTION:
        plan = rule_plan(req)
        got = [s.tool for s in plan.steps]
        if got == tools:
            sel_ok += 1
        else:
            fails.append({"request": req, "expected": tools, "got": got})
        if args and plan.steps:
            arg_total += 1
            if all(plan.steps[0].args.get(k) == v or (k == "query" and v in str(plan.steps[0].args.get(k))) for k, v in args.items()):
                arg_ok += 1
            else:
                fails.append({"request": req, "expected_args": args, "got_args": plan.steps[0].args})
    return {"cases": len(TOOL_SELECTION), "selection_accuracy": round(sel_ok / len(TOOL_SELECTION), 4),
            "argument_accuracy": round(arg_ok / arg_total, 4) if arg_total else None, "failures": fails}


def _permissions() -> dict:
    ws = Path(tempfile.mkdtemp())
    reg = get_registry()
    fails = []
    for kind, value, expected in PERMISSION_CASES:
        if kind == "command":
            try:
                got = "approval" if validate_command(value) else "allowed"
            except ToolError:
                got = "denied"
            # the engine path too: an invalid command must be rejected at plan time, not merely held for approval
            if got == "denied":
                from app.services.planner import Plan, PlanStep
                try:
                    validate_plan(Plan(steps=[PlanStep(tool="run_command", args={"argv": value})]), reg)
                    got = "NOT_REJECTED_AT_PLAN_TIME"
                except PlanError:
                    pass
        else:
            try:
                resolve_in_workspace(ws, value)
                got = "allowed"
            except ToolError:
                got = "denied"
        if got != expected:
            fails.append({"kind": kind, "input": value, "expected": expected, "got": got})
    return {"cases": len(PERMISSION_CASES), "enforcement_accuracy": round(1 - len(fails) / len(PERMISSION_CASES), 4), "failures": fails}


def _rag() -> dict:
    cands = []
    for doc_id, text in RAG_CORPUS.items():
        for i, c in enumerate(chunk_text(text, target=200, overlap=30)):
            cands.append(Candidate(f"{doc_id}#{i}", c, embed(c)))
    r1 = r3 = 0
    rr = []
    fails = []
    for q, expected in RAG_QUESTIONS:
        ranked = [h.id.split("#")[0] for h in hybrid_search(q, cands, k=5)]
        docs = list(dict.fromkeys(ranked))
        r1 += bool(docs and docs[0] == expected)
        r3 += expected in docs[:3]
        rr.append(1 / (docs.index(expected) + 1) if expected in docs else 0.0)
        if not docs or docs[0] != expected:
            fails.append({"question": q, "expected": expected, "top": docs[:3]})
    noise = sum(1 for q in OUT_OF_SCOPE if hybrid_search(q, cands, k=3))
    n = len(RAG_QUESTIONS)
    return {"questions": n, "recall_at_1": round(r1 / n, 4), "recall_at_3": round(r3 / n, 4), "mrr": round(sum(rr) / n, 4),
            "out_of_scope_returning_hits": noise, "out_of_scope_total": len(OUT_OF_SCOPE), "failures": fails,
            "note": "hashed-n-gram embeddings + BM25, not neural embeddings"}


def _memory() -> dict:
    cands = [Candidate(k, v, embed(v)) for k, v in MEMORIES.items()]
    top1 = 0
    fails = []
    for q, expected in MEMORY_QUERIES:
        hits = hybrid_search(q, cands, k=3)
        if hits and hits[0].id == expected:
            top1 += 1
        else:
            fails.append({"query": q, "expected": expected, "got": [h.id for h in hits]})
    return {"queries": len(MEMORY_QUERIES), "top1_accuracy": round(top1 / len(MEMORY_QUERIES), 4), "failures": fails}


def _citations_and_termination() -> dict:
    ok = sum(verify_citations(d, n)[0] == exp for d, n, exp in CITATION_CASES)
    hits = [{"text": "Falcon launches March 14.", "filename": "f.md", "page": None, "chunk_id": "c", "document_id": "d"}]
    stubborn = _Provider(["no citations at all"])
    res = answer_with_citations("q", hits, stubborn)
    down = answer_with_citations("q", hits, _Provider([LLMError("provider request failed: ConnectError")]))
    empty = _Provider(["should not be called"])
    none = answer_with_citations("q", [], empty)
    return {
        "citation_validator_accuracy": round(ok / len(CITATION_CASES), 4),
        "termination": {"model_calls_when_always_invalid": stubborn.calls, "max_allowed": MAX_DRAFTS,
                        "terminates_within_bound": stubborn.calls <= MAX_DRAFTS, "falls_back_to": res["mode"]},
        "provider_failure_handled": down["mode"] == "extractive",
        "no_evidence_skips_model": none["mode"] == "no_evidence" and empty.calls == 0,
    }


def _provider_failure_planning() -> dict:
    reg = get_registry()
    cases = [LLMError("down"), "not json", '{"steps":[{"tool":"shell","args":{}}]}', '{"steps":[{"tool":"read_file","args":{}}]}']
    ok = 0
    for c in cases:
        r = make_plan("list the files in the project", reg, _Provider([c]))
        ok += r.source == "rules" and bool(r.notes)
    return {"cases": len(cases), "fell_back_safely": ok}


def run_suite() -> dict:
    results = {
        "routing": _routing(), "tool_selection": _tool_selection(), "permission_enforcement": _permissions(),
        "rag_retrieval": _rag(), "memory_relevance": _memory(), "citations_and_termination": _citations_and_termination(),
        "provider_failure_planning": _provider_failure_planning(),
        "skipped": {"response_usefulness": "needs a live LLM provider and human or model grading; not run",
                    "llm_planning_quality": "needs a live provider; not run",
                    "task_completion_e2e": "covered by backend/tests/test_task_engine.py (pytest), not duplicated here"},
    }
    config = {"eval_version": EVAL_VERSION,
              "prompt_versions": {"planner": hashlib.sha256(PLANNER_SYSTEM.encode()).hexdigest()[:12],
                                  "rag": hashlib.sha256(RAG_SYSTEM.encode()).hexdigest()[:12]},
              "embedder": "hashed-ngram-384", "router": "rules+optional-sklearn", "llm": "none (deterministic)"}
    return {"config": config, "results": results}


def run_and_store(db) -> dict:
    from app.models import EvalRun

    out = run_suite()
    run = EvalRun(name="deterministic", config=out["config"], results=out["results"])
    db.add(run)
    db.commit()
    return {"id": run.id, "created_at": run.created_at.isoformat(), **out}


if __name__ == "__main__":
    print(json.dumps(run_suite(), indent=1))
