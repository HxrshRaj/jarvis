"""Intent / task-routing dataset.

SYNTHETIC. Examples are generated from hand-written templates and slot fillers, so scores on the template-held-out
split measure generalisation to *new phrasings built from new fillers*, not real-world performance. A separate
hand-written `natural_test` set (written independently of the templates) gives a second, tougher check.

Leakage control: every template belongs to exactly one split (train/val/test) and filler pools are split too, so no
(template) and no (filler) is shared between train and test. `validate()` asserts this.
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import random
from pathlib import Path

LABELS = [
    "general_question", "research", "coding_assistance", "document_analysis",
    "data_analysis", "memory_retrieval", "voice_command", "tool_execution",
]

# label -> (templates, filler pool). {a} and {b} are drawn from the pool (a != b).
SPEC: dict[str, tuple[list[str], list[str]]] = {
    "general_question": (
        ["what is {a}", "explain {a} to me in simple terms", "why does {a} matter", "can you tell me about {a}",
         "give me a quick overview of {a}", "how does {a} work", "what's the difference between {a} and {b}",
         "I'm curious about {a}", "is {a} worth learning about", "define {a}", "what are the pros and cons of {a}",
         "help me understand {a}", "tell me a fun fact about {a}", "how would you describe {a} to a child"],
        ["photosynthesis", "inflation", "the French revolution", "black holes", "jazz music", "the stock market",
         "vaccines", "the water cycle", "stoicism", "climate change", "the Roman empire", "sleep cycles", "volcanoes",
         "tides", "democracy"]),
    "research": (
        ["research {a} and give me sources", "compare the main approaches to {a} with citations",
         "write a literature review on {a}", "investigate recent developments in {a}", "find credible sources about {a}",
         "prepare a sourced report on {a}", "what does the evidence say about {a}",
         "gather perspectives on {a} from different sources", "do a deep dive on {a} and cite where you got it",
         "survey the state of the art in {a}", "compile a briefing on {a} with references",
         "look into the history and key studies of {a}", "build a comparison of competing views on {a}",
         "analyse the last decade of {a} research and cite it"],
        ["remote work productivity", "battery recycling", "urban heat islands", "microplastics", "intermittent fasting",
         "solid state batteries", "four day work weeks", "carbon capture", "gene therapy", "ocean acidification",
         "vertical farming", "universal basic income", "coral restoration", "fusion energy", "digital education"]),
    "coding_assistance": (
        ["why does my {a} function throw a {b}", "help me debug this {a} stack trace", "refactor this {a} class to be cleaner",
         "write a {a} function that reverses a linked list", "explain what this {a} snippet does",
         "my {a} tests are failing with a {b}", "review my {a} code for bugs", "how do I fix a {b} in {a}",
         "optimise this {a} loop", "convert this {a} code to use async", "add type hints to my {a} module",
         "why is my {a} build failing", "write unit tests for my {a} parser", "what's wrong with this {a} regex"],
        ["Python", "TypeScript", "Rust", "Go", "Java", "C++", "Ruby", "Kotlin", "Swift", "PHP", "Scala", "Haskell",
         "NullPointerException", "segfault", "ImportError", "KeyError", "off-by-one error", "race condition"]),
    "document_analysis": (
        ["summarise the attached {a}", "extract the key dates from this {a}", "what are the main points of my {a}",
         "pull out all action items from the {a}", "give me a one page summary of the {a}",
         "list the obligations mentioned in this {a}", "what does section three of the {a} say",
         "highlight anything unusual in this {a}", "turn this {a} into bullet points", "find the names of all people in the {a}",
         "translate the key clauses of the {a} into plain English", "check the {a} for missing information",
         "compare the two versions of the {a}", "what's the conclusion of the {a}"],
        ["contract", "PDF report", "meeting minutes", "research paper", "lease agreement", "invoice", "whitepaper",
         "policy document", "thesis chapter", "term sheet", "user manual", "annual report", "press release", "proposal"]),
    "data_analysis": (
        ["calculate the mean and standard deviation of {a}", "plot a histogram of {a}", "what is the correlation between {a} and {b}",
         "find outliers in the {a} column", "summarise the statistics of this dataset by {a}", "group the rows by {a} and total {b}",
         "what's the median {a} in the spreadsheet", "is there a trend in {a} over time", "clean the missing values in {a}",
         "build a pivot table of {a} by {b}", "run a regression of {b} on {a}", "describe the distribution of {a}",
         "what percentage of rows have {a} above average", "compute the variance of {a} across the table"],
        ["sales", "age", "revenue", "temperature", "price", "response time", "rating", "income", "weight", "duration",
         "attendance", "rainfall", "clicks", "score"]),
    "memory_retrieval": (
        ["what did I tell you about {a}", "do you remember my {b}", "recall what I said about {a} yesterday",
         "what are my saved preferences for {b}", "remind me what we decided about {a}", "what do you know about my {b}",
         "did I mention {a} earlier", "look up my notes about {a}", "which {b} did I say I liked",
         "bring up what I saved regarding {a}", "what's in my memory about {a}", "have I told you my {b}",
         "retrieve my earlier note on {a}", "what was it I said about {a} last week"],
        ["the budget meeting", "my travel plans", "the client deadline", "my diet", "the garden plan", "the move to Lisbon",
         "my sister's birthday", "the marathon training", "the kitchen renovation", "my reading list",
         "favourite editor", "coffee order", "work schedule", "preferred language", "meeting times"]),
    "voice_command": (
        ["read {a} aloud", "say {a} out loud", "speak {a} to me", "narrate {a} for me", "can you read {a} to me please",
         "play {a} as audio", "dictate {a} slowly", "turn the volume up so I can hear {a}", "mute while {a} plays",
         "pause after reading {a}", "read {a} in a softer voice", "repeat {a} aloud", "stop reading {a}",
         "talk me through {a} using your voice"],
        ["the summary", "the report", "my last message", "the answer", "the result", "the headlines", "the instructions",
         "the list", "the schedule", "the forecast", "the recipe", "that paragraph", "the explanation", "the reminder"]),
    "tool_execution": (
        ["list the files in {a}", "read the file {b}", "open {b} and show me the contents", "search the project for {a}",
         "run the test suite in {a}", "show me git status", "execute the pytest command", "show the recent task history",
         "find every file mentioning {a}", "cat {b}", "show the directory tree of {a}", "grep for {a} in the workspace",
         "run npm test", "check what changed with git diff"],
        ["src", "the workspace", "docs", "the tests folder", "the root directory", "scripts", "lib", "the app folder",
         "README.md", "config.yaml", "main.py", "notes.txt", "package.json", "setup.cfg", "TODO", "parse_config",
         "handle_error", "deprecated"]),
}

# Written independently of the templates; deliberately varied, informal, and ambiguous in places.
NATURAL_TEST: list[tuple[str, str]] = [
    ("why is the sky blue", "general_question"), ("how do airplanes stay up", "general_question"),
    ("whats the capital of australia and why isnt it sydney", "general_question"),
    ("explain recursion like im five", "general_question"), ("who was ada lovelace", "general_question"),
    ("is it bad to crack your knuckles", "general_question"), ("how many moons does jupiter have", "general_question"),
    ("what causes the northern lights", "general_question"),
    ("I need a well sourced overview of the evidence on creatine supplements", "research"),
    ("what do peer reviewed studies say about meditation and anxiety", "research"),
    ("collect articles and compare how different countries regulate AI", "research"),
    ("write me a cited summary of the debate over nuclear power", "research"),
    ("find out what the literature says about spaced repetition", "research"),
    ("put together a reference backed brief on lab grown meat", "research"),
    ("compare three sources on the effects of tariffs", "research"),
    ("survey academic work on sleep and memory and list the papers", "research"),
    ("my script crashes with an IndexError on line 40", "coding_assistance"),
    ("can you rewrite this function so it isn't O(n^2)", "coding_assistance"),
    ("npm build fails with module not found, help", "coding_assistance"),
    ("write a bash one-liner to rename all jpgs", "coding_assistance"),
    ("what does this SQL join actually return", "coding_assistance"),
    ("why won't my docker container start", "coding_assistance"),
    ("implement binary search in rust", "coding_assistance"),
    ("fix the null pointer in my java service", "coding_assistance"),
    ("tl;dr this pdf for me", "document_analysis"),
    ("what are the termination clauses in the agreement i uploaded", "document_analysis"),
    ("go through the minutes and tell me who owns each follow up", "document_analysis"),
    ("does this lease mention pets anywhere", "document_analysis"),
    ("give me the key figures from the quarterly report", "document_analysis"),
    ("pull the deadlines out of this syllabus", "document_analysis"),
    ("is there anything risky in this NDA", "document_analysis"),
    ("outline the argument of the paper i attached", "document_analysis"),
    ("average order value by month please", "data_analysis"),
    ("are there any weird spikes in the traffic numbers", "data_analysis"),
    ("how correlated are height and weight in my csv", "data_analysis"),
    ("show a bar chart of units sold per region", "data_analysis"),
    ("what's the 90th percentile of latency", "data_analysis"),
    ("which customers churned most, break it down by plan", "data_analysis"),
    ("fit a line through these points and give me the slope", "data_analysis"),
    ("how many rows have blank emails", "data_analysis"),
    ("what was that restaurant I mentioned last month", "memory_retrieval"),
    ("remind me what my wifi router brand was", "memory_retrieval"),
    ("what's my usual order at the coffee place", "memory_retrieval"),
    ("what did we agree on for the launch timeline", "memory_retrieval"),
    ("you saved something about my allergies, what was it", "memory_retrieval"),
    ("which hotel did I say I preferred in Rome", "memory_retrieval"),
    ("pull up the note I made on the quarterly goals", "memory_retrieval"),
    ("do you still have my preferred meeting times", "memory_retrieval"),
    ("can you say that out loud", "voice_command"), ("quieter please", "voice_command"),
    ("read me the last answer", "voice_command"), ("stop talking", "voice_command"),
    ("louder", "voice_command"), ("speak slower", "voice_command"),
    ("switch to the british voice", "voice_command"), ("start listening to me now", "voice_command"),
    ("what files are in this folder", "tool_execution"), ("show me what's in config.json", "tool_execution"),
    ("run the unit tests and tell me what broke", "tool_execution"), ("grep the repo for FIXME", "tool_execution"),
    ("list what changed in git", "tool_execution"), ("open the readme", "tool_execution"),
    ("display my last five tasks", "tool_execution"), ("search every file for the word secret", "tool_execution"),
]


def _split_pool(pool: list[str]) -> dict[str, list[str]]:
    n = len(pool)
    a, b = int(n * 0.6), int(n * 0.8)
    return {"train": pool[:a], "val": pool[a:b], "test": pool[b:]}


def _split_templates(templates: list[str]) -> dict[str, list[str]]:
    ordered = sorted(templates, key=lambda t: hashlib.sha1(t.encode()).hexdigest())
    return {"train": ordered[:10], "val": ordered[10:12], "test": ordered[12:]}


def build(seed: int = 7, per_template: int = 4) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for label, (templates, pool) in SPEC.items():
        tsplit, psplit = _split_templates(templates), _split_pool(pool)
        for split in ("train", "val", "test"):
            fillers = psplit[split]
            pairs = [(a, b) for a, b in itertools.permutations(fillers, 2)]
            for t in tsplit[split]:
                if "{b}" in t:
                    chosen = rng.sample(pairs, min(per_template, len(pairs)))
                else:
                    chosen = [(a, "") for a in rng.sample(fillers, min(per_template, len(fillers)))]
                for a, b in chosen:
                    rows.append({"text": t.format(a=a, b=b), "label": label, "template": t, "split": split})
    seen, out = set(), []
    for r in rows:  # drop accidental duplicate texts
        if r["text"] not in seen:
            seen.add(r["text"])
            out.append(r)
    return out


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["text", "label", "template", "split"])
        w.writeheader()
        w.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def validate(rows: list[dict], natural: list[tuple[str, str]] | None = None) -> None:
    """Raise AssertionError on schema problems or train/val/test leakage."""
    assert rows, "empty dataset"
    by = {s: [r for r in rows if r["split"] == s] for s in ("train", "val", "test")}
    assert all(by.values()), "every split must be non-empty"
    for r in rows:
        assert r["label"] in LABELS and r["text"].strip(), f"bad row {r}"
    for label in LABELS:
        assert all(any(r["label"] == label for r in by[s]) for s in by), f"{label} missing from a split"
    texts = {s: {r["text"].lower() for r in by[s]} for s in by}
    assert not texts["train"] & texts["test"] and not texts["train"] & texts["val"] and not texts["val"] & texts["test"], "text leakage"
    tmpl = {s: {r["template"] for r in by[s]} for s in by}
    assert not tmpl["train"] & tmpl["test"] and not tmpl["train"] & tmpl["val"] and not tmpl["val"] & tmpl["test"], "template leakage"
    if natural is not None:
        nat = {t.lower() for t, _ in natural}
        assert not nat & (texts["train"] | texts["val"] | texts["test"]), "natural test overlaps generated data"
        assert {l for _, l in natural} == set(LABELS)
