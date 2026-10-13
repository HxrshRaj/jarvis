import json

import numpy as np
import pytest

from app.config import get_settings
from app.ml import router as router_mod
from app.ml.router import ARTIFACT_DIR, confidence_threshold, model_route, route_request, rule_route
from ml import sklearn_model, torch_model
from ml.dataset import LABELS, NATURAL_TEST, SPEC, build, validate
from tests.conftest import DONE, submit, wait_for


@pytest.fixture(scope="module")
def rows():
    return build(seed=7)


def split(rows, name):
    r = [x for x in rows if x["split"] == name]
    return [x["text"] for x in r], [x["label"] for x in r]


# ---- dataset ------------------------------------------------------------------------------------------
def test_dataset_valid_and_balanced(rows):
    validate(rows, NATURAL_TEST)
    for s in ("train", "val", "test"):
        counts = {l: sum(1 for r in rows if r["split"] == s and r["label"] == l) for l in LABELS}
        assert min(counts.values()) >= 3, (s, counts)
    assert len({l for _, l in NATURAL_TEST}) == len(LABELS) == len(SPEC)


def test_build_is_deterministic():
    assert build(seed=7) == build(seed=7)


def test_leakage_is_detected(rows):
    bad = [dict(r) for r in rows]
    victim = next(r for r in bad if r["split"] == "test")
    twin = dict(victim, split="train")  # same text in train and test
    with pytest.raises(AssertionError, match="leakage"):
        validate(bad + [twin])
    same_template = dict(victim, text=victim["text"] + " extra", split="train")
    with pytest.raises(AssertionError, match="template leakage"):
        validate(bad + [same_template])


def test_natural_set_does_not_overlap_generated(rows):
    gen = {r["text"].lower() for r in rows}
    assert not gen & {t.lower() for t, _ in NATURAL_TEST}


def test_validation_rejects_bad_label_and_empty(rows):
    with pytest.raises(AssertionError):
        validate([])
    with pytest.raises(AssertionError):
        validate(rows + [{"text": "x", "label": "not_a_label", "template": "t", "split": "train"}])


# ---- models -------------------------------------------------------------------------------------------
def test_sklearn_trains_and_is_reproducible(rows):
    trx, try_ = split(rows, "train")
    vax, vay = split(rows, "val")
    p1, sel1 = sklearn_model.train(trx, try_, vax, vay, seed=3)
    p2, sel2 = sklearn_model.train(trx, try_, vax, vay, seed=3)
    probe = [t for t, _ in NATURAL_TEST]
    assert list(p1.predict(probe)) == list(p2.predict(probe)) and sel1 == sel2
    acc = np.mean(p1.predict(trx) == np.array(try_))
    assert acc > 0.95  # it can fit its own training data (sanity, not a quality claim)


def test_torch_trains_loss_decreases_and_reproducible(rows, tmp_path):
    trx, try_ = split(rows, "train")
    vax, vay = split(rows, "val")
    a = torch_model.train(trx, try_, vax, vay, seed=5, epochs=6, checkpoint=tmp_path / "m.pt")
    b = torch_model.train(trx, try_, vax, vay, seed=5, epochs=6)
    assert a.history[-1]["train_loss"] < a.history[0]["train_loss"]
    assert [h["train_loss"] for h in a.history] == [h["train_loss"] for h in b.history]  # identical seeds -> identical run
    # checkpoint round-trip gives the same predictions as the best in-memory weights at that epoch
    loaded = torch_model.load(tmp_path / "m.pt")
    p = torch_model.predict_proba(loaded, ["run the tests"])
    assert p.shape == (1, len(LABELS)) and abs(float(p.sum()) - 1) < 1e-5


def test_torch_checkpoint_rejects_wrong_labels(tmp_path):
    import torch

    torch.save({"state_dict": torch_model.Net().state_dict(), "labels": ["a"], "buckets": 1, "meta": {}}, tmp_path / "bad.pt")
    with pytest.raises(AssertionError):
        torch_model.load(tmp_path / "bad.pt")


def test_featurize_is_stable_across_calls():
    assert torch_model.featurize("Run the tests!") == torch_model.featurize("run the tests")
    assert torch_model.featurize("") == [0]


# ---- shipped artifacts + router ---------------------------------------------------------------------------
def test_committed_artifacts_load_and_predict():
    assert (ARTIFACT_DIR / "sklearn_router.joblib").exists() and (ARTIFACT_DIR / "torch_router.pt").exists()
    d = model_route("how do i fix a KeyError in python", "sklearn")
    assert d is None or d.source == "model"
    m = torch_model.load(ARTIFACT_DIR / "torch_router.pt")
    assert torch_model.predict_proba(m, ["mute"]).shape == (1, len(LABELS))


def test_reported_results_match_artifacts():
    """The numbers in reports/results.json must be reproducible from the committed artifacts (no invented scores)."""
    res = json.loads((ARTIFACT_DIR.parent / "reports" / "results.json").read_text(encoding="utf-8"))
    pipe = sklearn_model.load(ARTIFACT_DIR / "sklearn_router.joblib")
    from sklearn.metrics import f1_score

    texts, labels = zip(*NATURAL_TEST)
    f1 = f1_score(labels, pipe.predict(list(texts)), average="macro", labels=LABELS)
    assert round(float(f1), 4) == res["sklearn"]["natural_test"]["macro_f1"]


def test_missing_or_corrupt_artifact_returns_none(tmp_path):
    router_mod._load.cache_clear()
    assert model_route("anything", "sklearn", tmp_path) is None  # missing
    (tmp_path / "sklearn_router.joblib").write_bytes(b"not a pickle")
    router_mod._load.cache_clear()
    assert model_route("anything", "sklearn", tmp_path) is None  # corrupt -> caller falls back to rules
    router_mod._load.cache_clear()


def test_low_confidence_falls_back_to_rules(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "router", "model")
    monkeypatch.setattr(router_mod, "model_route", lambda text, kind="sklearn", artifact_dir=None: None)
    assert route_request("summarise the document").source == "rules"


def test_threshold_comes_from_training_metadata(tmp_path):
    assert confidence_threshold(tmp_path) == router_mod.DEFAULT_THRESHOLD
    (tmp_path / "router_meta.json").write_text('{"confidence_threshold": 0.31}')
    assert confidence_threshold(tmp_path) == 0.31
    assert 0.1 <= confidence_threshold() <= 0.9


def test_wrong_route_label_cannot_bypass_approval(client, auth, workspace, monkeypatch):
    """A classifier (or attacker steering it) that mislabels 'run the tests' must not remove the approval gate."""
    from app.ml.router import RouteDecision
    from app.services import engine as engine_mod

    (workspace / "test_a.py").write_text("def test_a(): pass\n")
    monkeypatch.setattr(engine_mod, "route_request", lambda text: RouteDecision("voice_command", 0.99, "model"))
    tid = submit(client, auth, "run the tests")
    t = wait_for(client, auth, tid, {"awaiting_approval"} | DONE)
    assert t["status"] == "awaiting_approval" and t["route"] == "voice_command"
    assert t["steps"][0]["output"] is None


def test_rule_route_still_works():
    assert rule_route("what is the mean of 1, 2, 3").route == "data_analysis"
    assert rule_route("tell me a joke").source == "fallback"
