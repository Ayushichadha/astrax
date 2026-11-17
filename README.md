# Astrax

Hypothesis-driven metacontrol for verified mathematical search. Astrax studies
whether observations of a running search help a controller choose useful actions
under a fixed resource budget. The present benchmark is AlphaEvolve problem 36:
packing 26 unequal circles in a unit square. The worker is SciPy SLSQP; it is not HRM.

Read the [research brief and ridge guide](papers/metacontrol/README.md),
[working manuscript](papers/metacontrol/MANUSCRIPT.md), and
[confirmation figure](papers/metacontrol/sequential-controller-results.svg).

## Current evidence

The completed sequential study uses 96 training, 16 validation and 48 fresh paired
confirmation seeds. Ridge and ExtraTrees critics share observations, local/moderate/
restart options, and 640 objective evaluations; each has myopic and sequential
credit variants. Neither primary comparison established improvement:

| Primary contrast | Mean score difference | Paired 97.5% interval |
|---|---:|---|
| Tree sequential − ridge sequential | +0.000075914 | [-0.001680902, +0.001831500] |
| Tree sequential − tree myopic | -0.000629639 | [-0.002553465, +0.001322107] |

The intervals do not rule out useful positive effects. Adaptive behavior is present,
but useful policy value and mathematical record improvement remain unestablished.
Earlier fixed moderate-revision gains remain separate findings.

## Install and test

The standalone numerical suite passes 41 tests; the offline artifact audit also passes.
Python 3.11 is the reference environment. No GPU is needed for these tests or audits.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -q
```

## Reproduce the saved evidence without cloud spending

The single archive contains original and amended records, fitted models, full
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
