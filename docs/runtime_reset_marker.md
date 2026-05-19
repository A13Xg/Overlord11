# Runtime Reset Marker (Shell-Only Baseline)

This marker documents the hard-cut reset to a shell-only runtime.

## Invariants

- No runtime tool execution paths.
- No runtime agent orchestration paths.
- Job execution sends user prompt directly to configured provider API.
- Session workspace output is deterministic:
  - `output/answer.md`
  - `artifacts/logs/provider_response.json`

## Branching Rule

- Baseline branch is `origin/main`.
- `Staging` is reference-only for ideas/tests.

## Future Rebuild Contract

Future tool runtime must be strict-only:

1. `ParamsModel` with `extra=forbid`
2. `execute(params, context)` entrypoint
3. deterministic alias normalization + forbidden alias rejection
4. deterministic semantic preflight
5. deterministic error envelope
