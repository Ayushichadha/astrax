# Astrax

Hypothesis-driven metacontrol for verified mathematical search. Astrax studies
whether observations of a running search help a controller choose useful actions
under a fixed resource budget. The completed suite includes 26- and 32-circle packing (AlphaEvolve problem 36)
and a 64-coefficient first-autoconvolution task (problem 2). Workers use SciPy
SLSQP and linear programming; they are not HRM.

Read the [research brief and ridge guide](papers/metacontrol/README.md),
[working manuscript](papers/metacontrol/MANUSCRIPT.md), and
[suite confirmation figure](papers/metacontrol/benchmark-suite-results.svg).

## Current evidence

The fresh-state test compared conditioned ridge with time-only action selection on 72 fresh polishing states. Mean normalized gain was −0.000113 (95% interval [−0.000251, +0.000016]). See the [manuscript](papers/metacontrol/MANUSCRIPT.md#fresh-state-terminal-action-prediction).

None of the three predeclared primary improvement gates passed.

| Primary contrast | Equal-task normalized gain | Adjusted 98.333% interval | Gate |
|---|---:|---|---|
| Tree sequential − selected fixed | -0.000042777 | [-0.000510150, +0.000415338] | Not passed |
| Tree sequential − ridge sequential | +0.000030288 | [-0.000509384, +0.000562167] | Not passed |
| Tree sequential − tree myopic | -0.000087398 | [-0.000429721, +0.000261888] | Not passed |

The 26-circle ridge baseline is numerically fragile because a theoretically zero
radius-CV feature was scaled by about 6.5e-17. H2 therefore compares the frozen
implementations; it does not establish a clean capacity advantage over a
well-conditioned linear baseline. H1 and H3 do not use ridge.


Each task uses 96 training, 16 validation and 48 fresh paired confirmation seeds.
The comparison uses task-specific models and normalized gains; individual task
results and limitations are in the research brief. No mathematical record or
zero-shot transfer is claimed. The conditional autoresearch pilot was not triggered.

## Install and test

The standalone numerical suite passes 58 tests; the offline artifact audit also passes.
Python 3.11 is the reference environment. No GPU is needed for these tests or audits.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -q
```

## Reproduce the saved evidence without cloud spending

The three-task suite archive includes 487 call receipts, all constructions,
models and original frozen sources. Extract and audit without cloud spending:

```bash
tar -xzf papers/metacontrol/artifacts/benchmark-suite-evidence.tar.gz
python -m scripts.audit_benchmark_suite --output outputs/benchmark-suite-v1
python -m scripts.plot_benchmark_suite --output outputs/benchmark-suite-v1
```

Recorded suite function execution is approximately $0.1648, excluding
startup/build/idle/egress. This is a rate-based estimate, not an invoice.

The earlier single-task study remains separately reproducible:

Its archive contains original and amended records, fitted models, full
traces, and audit receipts. From a fresh checkout:

```bash
tar -xzf papers/metacontrol/artifacts/sequential-controller-evidence.tar.gz
python -m scripts.audit_sequential_controller --output outputs/sequential-controller-v2
python -m scripts.plot_sequential_controller
```

The audit verifies 2,304 training transitions and 336 evaluation rollouts, source
and model hashes, geometry, objective counts, predictions and reported statistics.
It makes no Modal or Exa calls. The evidence archive SHA-256 is
`9e78f5eaab1263fd1b070b830fd43cc5d73f0a8e2b6069f6e49310f1ce82e124`.

A separately authorized numerical reproduction can prepare a new manifest and
run the CPU dispatcher. Do not launch it merely to inspect the saved result:

```bash
python -m scripts.sequential_controller --prepare outputs/sequential-reproduction
modal run -m scripts.modal_sequential_controller --output outputs/sequential-reproduction
```

The completed study used 163 unique CPU calls, about $0.0463 in recorded function
execution at published rates, excluding setup/idle/egress. This is not an invoice.
No confirmation seed may be reused to tune a new model.

## Code map

- `scripts/benchmark_suite.py`: frozen tasks, exact checks, training and comparison rules.
- `scripts/modal_benchmark_suite.py`: bounded three-task CPU dispatcher.
- `scripts/audit_benchmark_suite.py`: offline suite verification and recorded audit-only amendment.
- `scripts/sequential_controller.py`: bounded options, causal observations and fitted Q models.
- `scripts/modal_sequential_controller.py`: frozen splits, CPU execution, checkpoint receipts.
- `scripts/audit_sequential_controller.py`: offline evidence replay.
- `scripts/check_math_packing.py`: independent floating-point geometry verifier.
- `scripts/matched_revision.py`, `predict_revision.py`, `revision_hypotheses.py`: earlier timing studies.
- `scripts/run_packing_autoresearch.py`: historical restricted parameter proposer, not the learned controller.
- `scripts/exa_research_audit.py`: optional literature retrieval; reads an environment key.

GPU infrastructure is retained as historical code and is not part of the completed
CPU study. No cloud or API call is made by installation, tests, or the offline audit.
Credentials are not included; use your existing Modal profile and environment
variables. Do not commit `.env` files.

## Project lineage

Astrax was separated from [hidden_stars](https://github.com/Ayushichadha/hidden_stars),
formerly `saint`, after research commit `69de8ee`. The older repository retains
HRM/feudal work, prior papers, earlier records, and complete Git history. This
repository is a curated independent snapshot, not a rewritten HRM history.

The nine production files hashed by the completed study are byte-identical to
the source repository. Historical Modal app names still contain `saint` because
renaming those frozen sources would invalidate the evidence manifest. The original
protocol commit was `d3bc409`; the audit-only portability correction was `4ef0cea`.
No model, hypothesis, split or recorded result changed during separation.

This is a working research release. Submission formatting, older-study public
artifact packaging and venue checks remain outstanding; no autonomous code
invention or general safe-improvement guarantee is claimed.
