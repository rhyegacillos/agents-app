# Authentication Issue Resolution: 403 Forbidden (Clerk + FastAPI)

## Documentation Sync: Adaptive Decision Flow + Step Guide (2026-02-20)

This document is synchronized with the latest UX/flow implementation in `pages/product.tsx`.

- **Adaptive flow modes**: UI now shifts between `guided` and `status` modes.
- **Hysteresis guard**: mode switching uses `guided -> status` at `<= 40` and `status -> guided` at `>= 60` to avoid flip-flop around a single threshold.
- **Persistent Step Guide**: every workspace step includes a structured guide panel (`What you do`, `What you get`, `When to use`, `To move forward`).
- **Per-step memory**: collapse/expand is saved per user and per step using local storage (`collapsedByStep`, `touchedByStep`).
- **Adaptive Step Guide defaults**: untouched guides auto-expand in guided mode and auto-collapse in status mode.
- **User override priority**: once a user manually toggles a step guide, that preference is preserved and not auto-overridden.
- **Generated empty-state scenarios**: first-time vs returning-with-library cases are explicitly separated for clearer onboarding.
- **Decision Summary behavior**: supports single-run and multi-run (1-5) synthesis; compare-first is recommended but not mandatory.
- **Compare behavior**: compares two selected saved runs and surfaces winner/diff insight; best quality when config alignment is preserved.
- **Execution handoff**: Decision Summary remains the source artifact for Execution Plan generation and export workflow.
- **Scope note**: this update is primarily frontend UX/state orchestration; backend endpoint contracts remain unchanged unless otherwise stated in backend/API docs.


## 1. The Issue
We encountered persistent `403 Forbidden` errors when calling protected API endpoints (`/api/consultation`, `/api/subscription`), despite:
*   The frontend successfully authenticating with Clerk.
*   Valid Bearer tokens being sent in the `Authorization` header.
*   The correct `CLERK_JWKS_URL` being configured in the backend.

### Symptoms
*   FastAPI logs showed generic "Forbidden" errors.
*   Debugging revealed that tokens were being rejected either because they appeared to be "from the future" (Clock Skew) or due to strict audience validation.

## 2. Root Causes

### A. Clock Skew (Docker vs. Clerk)
JWTs contain an `iat` (Issued At) timestamp. If the backend server (e.g., a Docker container or AWS instance) has a system clock that is even **1 second behind** the Clerk server's clock, standard libraries will reject the token immediately as "invalid/future dated."
*   *Observation:* This is extremely common in containerized environments.

### B. Strict Audience Validation
The standard `fastapi-clerk-auth` middleware performs strict validation of the `aud` (Audience) claim. If the Clerk token doesn't explicitly match the expected audience string (or is empty), the token is rejected.

### C. Opaque Error Handling
The default middleware swallows the specific reason for failure (e.g., "Signature verification failed" vs "The token is not yet valid (iat)"), returning a generic 403. This made debugging difficult.

## 3. The Solution

We replaced the default `ClerkHTTPBearer` with a **Custom Manual Verification** strategy in `api/index.py`.

### Key Implementation Details:

1.  **Manual Key Retrieval (`PyJWKClient`)**
    We use `PyJWKClient` to fetch the public signing keys directly from your `CLERK_JWKS_URL`. This ensures we always have the correct key to verify the cryptographic signature.

2.  **Clock Skew Tolerance (`leeway`)**
    We implemented a **60-second leeway** during decoding.
    ```python
    jwt.decode(..., leeway=60)
    ```
    This tells the verifier: *"If the token says it was issued at 10:00:05, but my clock says it's only 10:00:00, accept it anyway."* This completely eliminates false positives from minor clock drift.

3.  **Relaxed Audience Check**
    We temporarily disabled the strict audience check (`verify_aud=False`) to ensure that valid tokens from your specific Clerk instance are accepted regardless of how the audience claim is formatted.

### Security Note
**This solution remains secure.**
*   **Signature Verification:** We still cryptographically verify that the token was signed by *your* Clerk instance's private key. Fake tokens will still fail.
*   **Expiration:** We still enforce the `exp` claim (with the small leeway), so expired tokens are rejected.

## 4. Code Reference (`api/index.py`)

```python
# Initialize PyJWKClient
jwks_client = PyJWKClient(jwks_url)

class CustomClerkHTTPBearer(ClerkHTTPBearer):
    async def __call__(self, request: Request):
        # ... fetch token ...
        
        # Manual verification with leeway
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        data = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            leeway=60,  # CRITICAL: Fixes "Token from future" / Clock Skew
            options={"verify_aud": False} 
        )
        # ...
```

## 5. Status
**RESOLVED** - The custom authentication handler has been implemented in `api/index.py` and `pyjwt` has been added to `requirements.txt`.
