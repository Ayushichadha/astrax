# Astrax contributor instructions

This repository studies sequential metacontrol of verified mathematical search.
It is independent of hidden_stars/HRM; no HRM checkout or submodule is required.

- Use Python 3.11 and `requirements.txt`; run `python -m pytest tests/ -q`.
- The single active research brief is `papers/metacontrol/README.md`; update it and
  the manuscript rather than adding competing experiment plans.
- Preserve frozen source bytes and seed partitions for completed studies.
  New hypotheses need fresh confirmation data and a new versioned protocol.
- Use `scripts/audit_sequential_controller.py` for offline artifact verification.
  Installation, tests and audit must not start cloud jobs.
- Cloud collection requires a user-authorized scope and budget. No silent retries.
- Keep credentials in environment variables or ignored local configuration.
  Never copy or publish secrets, private working files, or unrelated HRM data.
- Report behavior, prediction quality, verified construction scores and policy
  improvement separately. A floating-point check is not a rigorous certificate.
- Before editing old source files, inspect the manifest hashes; adapt new code
  without invalidating archived evidence or relabeling confirmation as training.
