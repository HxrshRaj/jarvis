"""Classical baseline: TF-IDF (word + char n-grams) -> logistic regression."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.pipeline import FeatureUnion, Pipeline

C_GRID = [0.5, 2, 10, 50]


def make_pipeline(C: float, seed: int) -> Pipeline:
    feats = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, lowercase=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, lowercase=True)),
    ])
    return Pipeline([("tfidf", feats), ("clf", LogisticRegression(C=C, max_iter=2000, class_weight="balanced", random_state=seed))])


def train(train_x: list[str], train_y: list[str], val_x: list[str], val_y: list[str], seed: int = 7) -> tuple[Pipeline, dict]:
    """Choose C on the validation split only (the test split is never touched here)."""
    best, best_f1, scores = None, -1.0, {}
    for C in C_GRID:
        pipe = make_pipeline(C, seed).fit(train_x, train_y)
        f1 = f1_score(val_y, pipe.predict(val_x), average="macro")
        scores[C] = round(float(f1), 4)
        if f1 > best_f1:
            best, best_f1, best_C = pipe, f1, C
    return best, {"selected_C": best_C, "val_macro_f1_by_C": scores}


def save(pipe: Pipeline, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, path)


def load(path: Path) -> Pipeline:
    """Only load artifacts you trained yourself: joblib/pickle can execute code on load."""
    return joblib.load(path)


def predict_with_confidence(pipe: Pipeline, texts: list[str]) -> list[tuple[str, float]]:
    proba = pipe.predict_proba(texts)
    classes = pipe.classes_
    idx = np.argmax(proba, axis=1)
    return [(str(classes[i]), float(proba[n][i])) for n, i in enumerate(idx)]
