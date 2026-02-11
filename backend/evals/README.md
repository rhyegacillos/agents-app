# Evals: Golden Set and Runner

This folder contains a minimal evaluation harness to regression-test the deployed agent end-to-end.

## Run (Local or Deployed API)

```bash
python3 backend/evals/run_evals.py --api-url http://localhost:8000 --user-id evaluser1234
```

If your deployment uses async jobs, the runner auto-detects `202` responses and polls `/jobs/{job_id}`.

## Golden Set Format

`golden.jsonl` is one JSON object per line:

- `id`: stable test id
- `message`: the user message sent to `/chat`
- `assert_regex`: list of regex patterns that must match the final response
- `timeout_s`: optional overall timeout for job completion

