from __future__ import annotations

from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from ml.dataset import LABELS


def report(y_true: list[str], y_pred: list[str]) -> dict:
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=LABELS, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=LABELS)
    confusions = sorted(
        ({"true": LABELS[i], "pred": LABELS[j], "count": int(cm[i][j])}
         for i in range(len(LABELS)) for j in range(len(LABELS)) if i != j and cm[i][j]),
        key=lambda d: -d["count"])
    return {
        "n": len(y_true),
        "accuracy": round(sum(a == b for a, b in zip(y_true, y_pred)) / len(y_true), 4),
        "macro_f1": round(float(f.mean()), 4),
        "per_class": {l: {"precision": round(float(p[i]), 3), "recall": round(float(r[i]), 3), "f1": round(float(f[i]), 3),
                          "support": int(s[i])} for i, l in enumerate(LABELS)},
        "top_confusions": confusions[:6],
        "confusion_matrix": {"labels": LABELS, "matrix": cm.tolist()},
    }
