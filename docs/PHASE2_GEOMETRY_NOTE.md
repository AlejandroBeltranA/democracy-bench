# W3 — Arrow geometry: why the diff-of-means steer fails (mechanism note)

Artifact: `out/act_steer_geometry_3b.json` (Llama-3.2-3B-Instruct-4bit, 16 contestable
4-option items, 7 domains; per-item arrow = the (median-UK-adult persona − default)
last-token residual shift at each layer; two forward passes per item per layer, no sweep).

## What we measured

For each layer we capture one **arrow per item** — the residual-stream shift the persona
instruction induces — instead of averaging them into the single diff-of-means direction that
steering actually injects. Then, per layer: the pairwise cosine matrix (items × items), the
mean within-domain vs cross-domain cosine, and each arrow's cosine to the mean arrow.

| Layer | mean off-diag cos | within-domain | cross-domain | within−cross gap | cos(arrow, mean) |
|------:|------------------:|--------------:|-------------:|-----------------:|-----------------:|
|   7   | **+0.807**        | 0.977         | 0.779        | 0.198            | +0.905           |
|  11   | **+0.817**        | 0.972         | 0.791        | 0.181            | +0.910           |
|  14   | +0.707            | 0.946         | 0.667        | 0.279            | +0.851           |
|  17   | +0.602            | 0.920         | 0.550        | 0.370            | +0.791           |
|  21   | +0.556            | 0.903         | 0.499        | 0.404            | +0.764           |

At layer 11 even the **minimum** off-diagonal cosine over all 120 item pairs is +0.658.

## What it means

**The arrows are NOT divergent — they are strongly aligned at every layer.** This inverts the
hypothesis the plan floated ("mid-layer arrows aligned = single concept, late-layer arrows not").
There is a single dominant direction at all depths; it is strongest early/mid (cos-to-mean 0.91 at
L11) and only loosens toward the output (0.76 at L21).

**But that dominant direction is generic, not item-specific.** Each arrow is the shift from
"answer as yourself" to "answer as the median UK adult (2024)". That ~0.8–0.9 shared alignment
across 16 items whose *public targets differ* means the persona framing induces nearly the **same**
residual shift regardless of the item's content. The diff-of-means direction is therefore dominated
by a persona/style component — "sound like a surveyed member of the public" — and carries almost no
per-item "match *this* item's public distribution" signal.

This is the mechanism behind the whole R-battery:

- **R1 (no held-out gain):** injecting an item-generic direction cannot move a held-out item toward
  *its* specific target — there is no item-specific content in the vector to transfer.
- **R2 (α=4 beats random in-sample only):** the shared direction is a real, non-random axis, so it
  fits the capture items slightly better than noise — but that is memorisation of those items.
- **R3 (wrong-way at low α, valley baseline):** a generic style push has no correct polarity w.r.t.
  each item's target, so adding it can lower representation as easily as raise it.
- **Phase 1 (global logit-bias failed):** a single shared shift on the *output* is the same move as
  a single shared shift in the *stream* — both assume one direction fits all items; it does not.

**Depth adds domain fracture.** within-domain cosine stays high (0.90–0.98) while cross-domain
falls (0.78 → 0.50), so the within−cross gap doubles from layer 7 (0.20) to layer 21 (0.40). As the
representation approaches the output it splits into domain-specific directions (NHS vs welfare vs
tax/trust). Even if one wanted item/domain-specific steering, no single late-layer direction can
serve all domains at once — the motivation W2 would have chased, now moot because R1 already killed
the global claim and the late-layer in-sample gain did not survive held-out capture either
(`out/act_steer_holdout_late_3b.json`).

## One-line takeaway

The "public-agreement direction" is real and clean — but it is a *persona-style* axis, not a
*public-content* axis: highly shared across items (so it looks steerable), item-generic (so it does
not generalise), and domain-fractured at the layers nearest the output. Activation steering with a
diff-of-means vector cannot align this model to per-item public opinion, and the geometry says why.
