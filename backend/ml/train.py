"""Reproducible router experiment: rules baseline vs scikit-learn vs PyTorch.

    cd backend && python -m ml.train

Writes data/, artifacts/ and reports/. Every number in reports/ is produced by this script; nothing is hand-entered.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import numpy as np
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupKFold

from app.ml.router import rule_route
from ml import sklearn_model, torch_model
from ml.dataset import LABELS, NATURAL_TEST, build, read_csv, validate, write_csv
from ml.metrics import report

HERE = Path(__file__).parent
DATA, ART, REP = HERE / "data", HERE / "artifacts", HERE / "reports"
SEEDS = [7, 11, 23, 42, 101]


def _xy(rows):
    return [r["text"] for r in rows], [r["label"] for r in rows]


def run(seed: int = 7) -> dict:
    rows = build(seed=seed)
    validate(rows, NATURAL_TEST)
    write_csv(rows, DATA / "intents.csv")
    write_csv([{"text": t, "label": l, "template": "", "split": "natural_test"} for t, l in NATURAL_TEST], DATA / "natural_test.csv")
    tr, va, te = ([r for r in rows if r["split"] == s] for s in ("train", "val", "test"))
    (trx, try_), (vax, vay), (tex, tey) = _xy(tr), _xy(va), _xy(te)
    natx, naty = [t for t, _ in NATURAL_TEST], [l for _, l in NATURAL_TEST]

    out: dict = {
        "dataset": {"train": len(tr), "val": len(va), "test": len(te), "natural_test": len(NATURAL_TEST),
                    "classes": LABELS, "synthetic": True,
                    "note": "template-generated; split by template AND filler pool; natural_test is hand-written"},
    }

    # 1) rules baseline
    rule_pred = lambda xs: [rule_route(x).route for x in xs]  # noqa: E731
    out["rules"] = {"test": report(tey, rule_pred(tex)), "natural_test": report(naty, rule_pred(natx))}

    # 2) scikit-learn
    pipe, sel = sklearn_model.train(trx, try_, vax, vay, seed)
    sklearn_model.save(pipe, ART / "sklearn_router.joblib")
    out["sklearn"] = {"selection": sel, "test": report(tey, list(pipe.predict(tex))), "natural_test": report(naty, list(pipe.predict(natx)))}

    # Grouped CV over (train+val) by template. C is fixed to the value chosen above, so the held-out folds do not
    # influence hyper-parameters. Out-of-fold probabilities are used to pick the router's confidence threshold, which
    # keeps the natural test set clean.
    cvx, cvy = trx + vax, try_ + vay
    groups = [r["template"] for r in tr + va]
    splits = list(GroupKFold(n_splits=5).split(cvx, cvy, groups))
    scores, oof = [], []
    for a, b in splits:
        p = sklearn_model.make_pipeline(sel["selected_C"], seed).fit([cvx[i] for i in a], [cvy[i] for i in a])
        bx, by = [cvx[i] for i in b], [cvy[i] for i in b]
        scores.append(f1_score(by, p.predict(bx), average="macro"))
        oof += [(pr, c, t) for (pr, c), t in zip(sklearn_model.predict_with_confidence(p, bx), by)]
    out["sklearn"]["grouped_cv_macro_f1"] = {"mean": round(float(np.mean(scores)), 4), "std": round(float(np.std(scores)), 4), "folds": len(scores)}
    rule_cv = [f1_score([cvy[i] for i in b], rule_pred([cvx[i] for i in b]), average="macro") for _, b in splits]
    out["rules"]["grouped_cv_macro_f1"] = {"mean": round(float(np.mean(rule_cv)), 4), "std": round(float(np.std(rule_cv)), 4), "folds": 5}

    grid = [round(0.15 + 0.05 * i, 2) for i in range(10)]
    table = {}
    for th in grid:
        sel_rows = [(pr == t) for pr, c, t in oof if c >= th]
        table[th] = {"coverage": round(len(sel_rows) / len(oof), 3), "accuracy": round(float(np.mean(sel_rows)), 3) if sel_rows else None}
    ok = [th for th in grid if table[th]["accuracy"] is not None and table[th]["accuracy"] >= 0.95 and table[th]["coverage"] >= 0.2]
    threshold = min(ok) if ok else 0.55
    (ART / "router_meta.json").write_text(json.dumps({"confidence_threshold": threshold, "selected_on": "grouped out-of-fold predictions"}), encoding="utf-8")
    out["sklearn"]["threshold_selection"] = {"chosen": threshold, "out_of_fold": table}

    # Hybrid policy actually used at runtime: model when confident, rules otherwise.
    nat_conf = sklearn_model.predict_with_confidence(pipe, natx)
    hybrid = [m if c >= threshold else rule_route(x).route for (m, c), x in zip(nat_conf, natx)]
    out["hybrid"] = {"threshold": threshold, "natural_test": report(naty, hybrid),
                     "model_used_fraction": round(float(np.mean([c >= threshold for _, c in nat_conf])), 3)}
    hybrid_test = [m if c >= threshold else rule_route(x).route for (m, c), x in zip(sklearn_model.predict_with_confidence(pipe, tex), tex)]
    out["hybrid"]["test"] = report(tey, hybrid_test)

    # 3) PyTorch, several seeds
    runs = []
    for s in SEEDS:
        res = torch_model.train(trx, try_, vax, vay, seed=s, checkpoint=ART / "torch_router.pt" if s == SEEDS[0] else None)
        tp = [LABELS[i] for i in torch_model.predict_proba(res.model, tex).argmax(1)]
        npred = [LABELS[i] for i in torch_model.predict_proba(res.model, natx).argmax(1)]
        runs.append({"seed": s, "best_epoch": res.best_epoch, "val_macro_f1": round(res.best_val_f1, 4),
                     "test_macro_f1": report(tey, tp)["macro_f1"], "natural_macro_f1": report(naty, npred)["macro_f1"],
                     "natural_accuracy": report(naty, npred)["accuracy"],
                     "history": res.history if s == SEEDS[0] else None})
        if s == SEEDS[0]:
            first = (tp, npred)
    agg = lambda k: {"mean": round(statistics.mean(r[k] for r in runs), 4), "std": round(statistics.pstdev(r[k] for r in runs), 4)}  # noqa: E731
    out["torch"] = {"seeds": SEEDS, "runs": runs, "test_macro_f1": agg("test_macro_f1"), "natural_macro_f1": agg("natural_macro_f1"),
                    "first_seed_reports": {"test": report(tey, first[0]), "natural_test": report(naty, first[1])}}

    # decision (computed, not asserted)
    nat = {"rules": out["rules"]["natural_test"]["macro_f1"], "sklearn": out["sklearn"]["natural_test"]["macro_f1"],
           "torch": out["torch"]["natural_macro_f1"]["mean"], "hybrid": out["hybrid"]["natural_test"]["macro_f1"]}
    best = max(nat, key=nat.get)
    out["decision"] = {"natural_macro_f1": nat, "best": best,
                       "model_beats_rules_by": round(max(nat["sklearn"], nat["torch"], nat["hybrid"]) - nat["rules"], 4)}
    REP.mkdir(parents=True, exist_ok=True)
    (REP / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    (REP / "results.md").write_text(to_markdown(out), encoding="utf-8")
    return out


def to_markdown(o: dict) -> str:
    d = o["dataset"]
    L = ["# Router experiment results (generated by `python -m ml.train`)", "",
         f"Data: {d['train']} train / {d['val']} val / {d['test']} template-held-out test / {d['natural_test']} hand-written natural test. "
         "**Synthetic data**; treat absolute numbers as optimistic.", "",
         "| model | test macro-F1 | natural-test macro-F1 | natural-test accuracy |", "|---|---|---|---|",
         f"| rules baseline | {o['rules']['test']['macro_f1']} | {o['rules']['natural_test']['macro_f1']} | {o['rules']['natural_test']['accuracy']} |",
         f"| scikit-learn (TF-IDF+LR) | {o['sklearn']['test']['macro_f1']} | {o['sklearn']['natural_test']['macro_f1']} | {o['sklearn']['natural_test']['accuracy']} |",
         f"| PyTorch (mean±std, {len(o['torch']['seeds'])} seeds) | {o['torch']['test_macro_f1']['mean']}±{o['torch']['test_macro_f1']['std']} | "
         f"{o['torch']['natural_macro_f1']['mean']}±{o['torch']['natural_macro_f1']['std']} | - |", "",
         f"Grouped 5-fold CV macro-F1: rules {o['rules']['grouped_cv_macro_f1']['mean']}±{o['rules']['grouped_cv_macro_f1']['std']}, "
         f"sklearn {o['sklearn']['grouped_cv_macro_f1']['mean']}±{o['sklearn']['grouped_cv_macro_f1']['std']}.", "",
         "## Largest confusions on natural test (scikit-learn)"]
    L += [f"- {c['true']} → {c['pred']}: {c['count']}" for c in o["sklearn"]["natural_test"]["top_confusions"]]
    ts = o["sklearn"]["threshold_selection"]
    L += ["", "## Confidence threshold (chosen on grouped out-of-fold predictions, not on the natural test)",
          "| threshold | coverage | accuracy when confident |", "|---|---|---|"]
    L += [f"| {k} | {v['coverage']} | {v['accuracy']} |" for k, v in ts["out_of_fold"].items()]
    h = o["hybrid"]
    L += ["", f"Chosen threshold **{ts['chosen']}**. Hybrid policy (model if confident else rules) on natural test: macro-F1 "
              f"{h['natural_test']['macro_f1']}, accuracy {h['natural_test']['accuracy']}, model used for {h['model_used_fraction']:.0%} of requests.",
          "", "> Caveat: the template-held-out `test` split has only 2 held-out templates per class, so its effective sample "
              "is ~16 templates and its F1 is very noisy (errors come in clusters). Grouped CV and the natural set are the "
              "more informative numbers. Tiny samples; no significance testing was done."]
    dec = o["decision"]
    L += ["", f"**Decision input:** natural-test macro-F1 {dec['natural_macro_f1']}; best = `{dec['best']}`; best model beats rules by {dec['model_beats_rules_by']}.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    res = run()
    print(to_markdown(res))
