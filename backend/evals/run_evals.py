import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


@dataclass
class EvalCase:
    case_id: str
    message: str
    assert_regex: List[str]
    timeout_s: int = 180


def _http_json(method: str, url: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[int, Dict[str, Any]]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except HTTPError as e:
        raw = e.read().decode("utf-8") if hasattr(e, "read") else ""
        try:
            body = json.loads(raw) if raw else {"error": raw}
        except Exception:
            body = {"error": raw}
        return e.code, body
    except URLError as e:
        return 0, {"error": str(e)}


def _load_cases(path: str) -> List[EvalCase]:
    cases: List[EvalCase] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            cases.append(
                EvalCase(
                    case_id=str(obj["id"]),
                    message=str(obj["message"]),
                    assert_regex=list(obj.get("assert_regex") or []),
                    timeout_s=int(obj.get("timeout_s") or 180),
                )
            )
    return cases


def _poll_job(api_url: str, job_id: str, user_id: str, timeout_s: int) -> Dict[str, Any]:
    deadline = time.time() + timeout_s
    while True:
        if time.time() > deadline:
            return {"status": "failed", "error": f"eval timeout after {timeout_s}s", "job_id": job_id}
        q = urlencode({"user_id": user_id})
        url = urljoin(api_url.rstrip("/") + "/", f"jobs/{job_id}") + f"?{q}"
        code, body = _http_json("GET", url)
        if code != 200:
            return {"status": "failed", "error": f"job status http {code}: {body}", "job_id": job_id}
        status = body.get("status")
        if status in {"completed", "failed"}:
            return body
        time.sleep(2)


def _assert_response(text: str, patterns: List[str]) -> List[str]:
    failures: List[str] = []
    for pat in patterns:
        if not re.search(pat, text or "", flags=re.IGNORECASE | re.MULTILINE):
            failures.append(pat)
    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url", required=True, help="Base API URL, e.g. http://localhost:8000 or https://.../dev/")
    ap.add_argument("--user-id", default="evaluser1234", help="User id used for eval runs")
    ap.add_argument("--golden", default="backend/evals/golden.jsonl", help="Path to golden jsonl")
    ap.add_argument("--out", default="", help="Optional path to write JSON results")
    args = ap.parse_args()

    cases = _load_cases(args.golden)
    if not cases:
        print("No cases found.", file=sys.stderr)
        return 2

    results: List[Dict[str, Any]] = []
    passed = 0

    for c in cases:
        started = time.time()
        post_url = urljoin(args.api_url.rstrip("/") + "/", "chat")
        code, body = _http_json(
            "POST",
            post_url,
            {
                "message": c.message,
                "user_id": args.user_id,
            },
        )

        final_text = ""
        error = ""
        if code == 200:
            final_text = str(body.get("response") or "")
        elif code == 202:
            job_id = str(body.get("job_id") or "")
            job = _poll_job(args.api_url, job_id, args.user_id, c.timeout_s)
            if job.get("status") == "completed":
                final_text = str(job.get("response") or "")
            else:
                error = str(job.get("error") or "job failed")
        else:
            error = f"http {code}: {body}"

        duration_s = round(time.time() - started, 3)
        failures = _assert_response(final_text, c.assert_regex) if not error else c.assert_regex
        ok = (not error) and (len(failures) == 0)
        if ok:
            passed += 1

        results.append(
            {
                "id": c.case_id,
                "ok": ok,
                "duration_s": duration_s,
                "error": error,
                "missing_patterns": failures,
            }
        )

        status = "PASS" if ok else "FAIL"
        print(f"{status} {c.case_id} ({duration_s}s)")
        if error:
            print(f"  error: {error}")
        elif failures:
            print(f"  missing: {failures}")

    summary = {
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "pass_rate": round(passed / max(1, len(cases)), 3),
        "results": results,
    }

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    print(f"Summary: {passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())

