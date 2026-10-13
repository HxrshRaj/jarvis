"""PyTorch experiment: hashed word+char n-gram EmbeddingBag -> small MLP. CPU only, seeded, checkpointed.

This is a small text classifier trained from scratch on a small synthetic dataset. It is NOT a language model and
makes no claim about general language understanding.
"""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch import nn

from ml.dataset import LABELS

BUCKETS = 4096
_WORD = re.compile(r"[a-z0-9']+")


def featurize(text: str) -> list[int]:
    """Hash word unigrams/bigrams and char trigrams into BUCKETS ids (deterministic across processes)."""
    words = _WORD.findall(text.lower())
    feats = [f"w:{w}" for w in words] + [f"b:{a}_{b}" for a, b in zip(words, words[1:])]
    for w in words:
        p = f"#{w}#"
        feats += [f"c:{p[i:i + 3]}" for i in range(len(p) - 2)]
    ids = [int.from_bytes(hashlib.blake2b(f.encode(), digest_size=4).digest(), "big") % BUCKETS for f in feats]
    return ids or [0]


class Net(nn.Module):
    def __init__(self, dim: int = 64, hidden: int = 64, n_classes: int = len(LABELS), dropout: float = 0.3):
        super().__init__()
        self.emb = nn.EmbeddingBag(BUCKETS, dim, mode="mean")
        self.head = nn.Sequential(nn.Linear(dim, hidden), nn.ReLU(), nn.Dropout(dropout), nn.Linear(hidden, n_classes))

    def forward(self, ids: torch.Tensor, offsets: torch.Tensor) -> torch.Tensor:
        return self.head(self.emb(ids, offsets))


def _batch(texts: list[str]) -> tuple[torch.Tensor, torch.Tensor]:
    seqs = [featurize(t) for t in texts]
    offsets = torch.tensor([0] + list(np.cumsum([len(s) for s in seqs])[:-1]), dtype=torch.long)
    return torch.tensor([i for s in seqs for i in s], dtype=torch.long), offsets


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


@dataclass
class TrainResult:
    model: Net
    history: list[dict]
    best_epoch: int
    best_val_f1: float


def predict_proba(model: Net, texts: list[str]) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        ids, off = _batch(texts)
        return torch.softmax(model(ids, off), dim=-1).numpy()


def train(train_x, train_y, val_x, val_y, seed: int = 7, epochs: int = 40, lr: float = 5e-3, batch_size: int = 32,
          patience: int = 8, checkpoint: Path | None = None) -> TrainResult:
    seed_everything(seed)
    torch.set_num_threads(1)  # determinism + no oversubscription
    y_idx = torch.tensor([LABELS.index(y) for y in train_y])
    model = Net()
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-2)
    loss_fn = nn.CrossEntropyLoss()
    gen = torch.Generator().manual_seed(seed)
    history, best_f1, best_epoch, best_state, bad = [], -1.0, 0, None, 0
    for epoch in range(1, epochs + 1):
        model.train()
        perm = torch.randperm(len(train_x), generator=gen).tolist()
        total = 0.0
        for i in range(0, len(perm), batch_size):
            idx = perm[i:i + batch_size]
            ids, off = _batch([train_x[j] for j in idx])
            opt.zero_grad()
            loss = loss_fn(model(ids, off), y_idx[idx])
            loss.backward()
            opt.step()
            total += float(loss.detach()) * len(idx)
        val_pred = [LABELS[i] for i in predict_proba(model, val_x).argmax(1)]
        vf1 = float(f1_score(val_y, val_pred, average="macro"))
        history.append({"epoch": epoch, "train_loss": round(total / len(train_x), 4), "val_macro_f1": round(vf1, 4)})
        if vf1 > best_f1 + 1e-6:
            best_f1, best_epoch, bad = vf1, epoch, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            if checkpoint:
                save(model, checkpoint, {"seed": seed, "epoch": epoch, "val_macro_f1": vf1})
        else:
            bad += 1
            if bad >= patience:
                break
    model.load_state_dict(best_state)
    return TrainResult(model, history, best_epoch, best_f1)


def save(model: Net, path: Path, meta: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "labels": LABELS, "buckets": BUCKETS, "meta": meta or {}}, path)


def load(path: Path) -> Net:
    ckpt = torch.load(path, map_location="cpu", weights_only=True)  # tensors + plain types only
    assert ckpt["labels"] == LABELS and ckpt["buckets"] == BUCKETS, "checkpoint/label mismatch"
    model = Net()
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model
