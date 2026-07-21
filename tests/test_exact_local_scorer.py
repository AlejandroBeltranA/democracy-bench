"""Direct tests of the exact local option scorer (Q1 measurement gate, Sol v2 sign-off item 2).

The summed exact path in `activation_steer.mlx_logprob_fn(top_k=None)` must:
  - SUM probability over every accepted token variant of an option (mutually exclusive
    first-token events), not take the max;
  - renormalise over options only;
  - report coverage fields consistent with the returned vector.

Uses a stub tokenizer/model over a tiny vocabulary in which option 1 has TWO accepted
variants ('1' and ' 1') while options 2-4 have one each — the case that distinguishes
sum from max. Requires mlx (skipped where unavailable), no model download.
"""
import numpy as np
import pytest

mx = pytest.importorskip("mlx.core")

from alignment.steer import activation_steer as A


VOCAB = ["x", "1", " 1", "2", "junk", "3", "4", "(2", "?"]
#         0    1     2    3     4      5    6    7     8
# accepted-variant map the scanner should produce:
#   "1" -> ids [1, 2]; "2" -> ids [3, 7]; "3" -> [5]; "4" -> [6]


class StubTok:
    vocab_size = len(VOCAB)

    def decode(self, ids):
        return "".join(VOCAB[i] for i in ids)

    def get_vocab(self):
        return {s: i for i, s in enumerate(VOCAB)}

    def apply_chat_template(self, msgs, add_generation_prompt=True):
        return [0]                      # any valid ids; the stub model ignores them


class StubModel:
    """Returns fixed logits [1, 1, V] regardless of input ids."""

    def __init__(self, logits_row):
        self._row = np.asarray(logits_row, dtype=np.float32)

    def __call__(self, ids):
        return mx.array(self._row.reshape(1, 1, -1))


def _fresh_tok():
    tok = StubTok()                     # new instance -> no cached _option_token_ids
    return tok


def test_option_token_ids_finds_all_variants():
    ids = A._option_token_ids(_fresh_tok())
    assert sorted(ids["1"].tolist()) == [1, 2]
    assert sorted(ids["2"].tolist()) == [3, 7]
    assert ids["3"].tolist() == [5]
    assert ids["4"].tolist() == [6]


def test_exact_scorer_sums_variants_and_renormalises():
    row = np.zeros(len(VOCAB))
    row[1] = 2.0    # '1'
    row[2] = 1.0    # ' 1'  (second variant of option 1 — must be SUMMED, not maxed)
    row[3] = 2.5    # '2'
    row[7] = 0.5    # '(2'  (second variant of option 2)
    row[5] = 1.5    # '3'
    row[6] = 0.5    # '4'
    tok = _fresh_tok()
    fn = A.mlx_logprob_fn(StubModel(row), tok)          # exact path (top_k=None)
    probs = fn("irrelevant prompt", 4)

    # expected: softmax over the whole vocab, sum per option's variant ids, renormalise
    p = np.exp(row - row.max()); p /= p.sum()
    per_opt = np.array([p[1] + p[2], p[3] + p[7], p[5], p[6]])
    expected = per_opt / per_opt.sum()
    np.testing.assert_allclose(probs, expected, atol=1e-10)

    # a max-variant estimator would give a DIFFERENT vector here — guard against regression
    per_opt_max = np.array([max(p[1], p[2]), max(p[3], p[7]), p[5], p[6]])
    assert not np.allclose(probs, per_opt_max / per_opt_max.sum())


def test_exact_scorer_coverage_fields_consistent():
    row = np.zeros(len(VOCAB)); row[1] = 3.0; row[2] = 1.0; row[3] = 2.0; row[5] = 1.0; row[6] = 0.5
    tok = _fresh_tok()
    fn = A.mlx_logprob_fn(StubModel(row), tok)
    probs = fn("q", 4)
    cov = fn.coverage_log[-1]
    p = np.exp(row - row.max()); p /= p.sum()
    union = [1, 2, 3, 7, 5, 6]
    assert cov["n_options"] == 4
    assert cov["option_mass"] == pytest.approx(p[union].sum(), abs=1e-9)
    # per_option_mass is the pre-renormalisation summed mass and must renormalise to probs
    pm = np.array(cov["per_option_mass"])
    np.testing.assert_allclose(pm / pm.sum(), probs, atol=1e-5)
    assert cov["top1_is_option"] is True                 # argmax is id 1 ('1')
    assert fn.matched_token_ids["1"] == [1, 2]


def test_legacy_top_k_path_still_max_variant():
    """The opt-in legacy estimator must keep its historical max-variant semantics."""
    row = np.zeros(len(VOCAB)); row[1] = 2.0; row[2] = 1.0; row[3] = 2.5; row[5] = 1.5; row[6] = 0.5
    tok = _fresh_tok()
    fn = A.mlx_logprob_fn(StubModel(row), tok, top_k=len(VOCAB))
    probs = fn("q", 4)
    p = np.exp(row - row.max()); p /= p.sum()
    per_opt_max = np.array([max(p[1], p[2]), p[3], p[5], p[6]])
    np.testing.assert_allclose(probs, per_opt_max / per_opt_max.sum(), atol=1e-6)
