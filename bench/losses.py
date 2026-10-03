#!/usr/bin/env python3
"""The two losses left out of the first training run, written and tested before use.

They were omitted from the overnight run deliberately: untested code in an unattended 2-hour job is
how you lose the night. Written here, unit-tested on CPU (so they do not contend with the running
job for MPS memory), ready to drop into `train_decision_model.py` for run 2.

**Ranked Probability Score** — for ordinal questions. Predicting level 1 when the truth is 5 must
cost more than predicting level 4. Plain cross-entropy treats those as equally wrong.

**Permutation-KL** — for option-order sensitivity. A twin batch with shuffled options is scored and
the symmetric KL between the two predictions is added to the loss. Our own JevBench work found
exactly this failure in this model class; `verdict-2.0` reports flip rate 4.76% vs Kev's 7.41%
because of it.

usage: python bench/losses.py     # runs the unit tests
"""
from __future__ import annotations

import torch
import torch.nn.functional as F


def rps_loss(logits: torch.Tensor, target: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Ranked Probability Score over the valid option slots.

    RPS is the squared difference of *cumulative* distributions, so it is sensitive to distance
    along the ordinal axis in a way cross-entropy is not.
    """
    p = F.softmax(logits, dim=-1)
    valid = mask.bool()
    p = p * valid
    t = target * valid
    # renormalise over valid slots only
    p = p / p.sum(-1, keepdim=True).clamp_min(1e-9)
    t = t / t.sum(-1, keepdim=True).clamp_min(1e-9)
    cp, ct = torch.cumsum(p, dim=-1), torch.cumsum(t, dim=-1)
    rps = ((cp - ct) ** 2).sum(-1) / (valid.sum(-1) - 1).clamp_min(1)
    return rps[valid.any(-1)].mean()


def permutation_kl(logits_a: torch.Tensor, logits_b: torch.Tensor,
                  perm: torch.Tensor, mask_a: torch.Tensor) -> torch.Tensor:
    """Symmetric KL between a prediction and the same prediction with options shuffled.

    `logits_b` is the twin's output in *shuffled* order; `perm` maps shuffled index -> original
    index, so `logits_b` can be scattered back and compared like for like.
    """
    B, K = logits_a.shape
    # scatter the twin back into the original option order
    unshuffled = torch.zeros_like(logits_b)
    for i in range(B):
        for j in range(K):
            unshuffled[i, perm[i, j]] = logits_b[i, j]
    va = mask_a.bool()
    la, lb = F.log_softmax(logits_a, -1), F.log_softmax(unshuffled, -1)
    pa, pb = la.exp(), lb.exp()
    # only compare where the ORIGINAL had valid slots
    kl_a = (pa * (la - lb)).sum(-1)
    kl_b = (pb * (lb - la)).sum(-1)
    sym = (kl_a + kl_b) / 2
    return sym[va.any(-1)].mean()


# --------------------------------------------------------------------------- tests
def _t():
    torch.manual_seed(0)
    K = 5
    mask = torch.ones(2, K)
    # --- RPS: predicting level 1 when truth is 5 must cost more than predicting level 4 ---
    logits_far = torch.tensor([[5.0, 0, 0, 0, 0], [5.0, 0, 0, 0, 0]])
    logits_near = torch.tensor([[0, 0, 0, 0, 5.0], [0, 0, 0, 0, 5.0]])
    target = torch.tensor([[0, 0, 0, 0, 1.0], [0, 0, 0, 0, 1.0]])
    far, near = rps_loss(logits_far, target, mask), rps_loss(logits_near, target, mask)
    print(f"  RPS  predict-1-when-truth-is-5 : {far:.4f}")
    print(f"  RPS  predict-5-when-truth-is-5 : {near:.4f}")
    assert far > near, "RPS must penalise distance along the ordinal axis"
    assert near < 1e-3, "a correct ordinal prediction should score ~0 (softmax tail, not exactly 0)"
    print("  PASS  RPS penalises ordinal distance")

    # --- permutation-KL: identical predictions -> 0; different -> positive ---
    a = torch.randn(2, K)
    # a consistent pair: the twin's options were reversed, so its output is `a` reversed, and the
    # permutation says so for BOTH rows. Scattering back must recover `a` exactly.
    rev = torch.tensor([4, 3, 2, 1, 0])
    perm = rev.unsqueeze(0).repeat(2, 1)
    b_shuffled_same = a[:, rev]
    kl_zero = permutation_kl(a, b_shuffled_same, perm, mask)
    b_diff = torch.randn(2, K)
    kl_pos = permutation_kl(a, b_diff, perm, mask)
    print(f"\n  permKL identical answer (order-invariant) : {kl_zero:.4f}")
    print(f"  permKL different answer                    : {kl_pos:.4f}")
    assert kl_zero < 1e-4, "an order-invariant model must score 0"
    assert kl_pos > 0.1, "a genuinely different prediction must be penalised"
    print("  PASS  permutation-KL is 0 for order-invariance and positive otherwise")
    return 0


if __name__ == "__main__":
    print("  unit tests (CPU)\n")
    raise SystemExit(_t())
