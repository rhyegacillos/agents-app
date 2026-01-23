# Current Usage Implementation Details

This document outlines the architecture and implementation of the user usage tracking system (quotas, rate limits, and token usage) for the IdeaGen application.

## 1. Database Schema (SQLite)

Data is persisted in a SQLite database located at `data/usage.db` (inside the container volume).

**Table:** `user_usage`

| Column | Type | Description |
| :--- | :--- | :--- |
| `user_id` | TEXT (PK) | The unique Subject ID from Clerk. |
| `plan` | TEXT | Current plan ('free' or 'premium'). Used to detect plan changes. |
| `total_tokens` | INTEGER | Cumulative count of tokens used by all AI models. |
| `api_calls_count` | INTEGER | Number of API calls made in the current 60s window. |
| `api_window_start` | REAL | Timestamp (epoch) when the current API rate limit window started. |
| `emails_sent_count` | INTEGER | Number of emails sent in the current day (UTC). |
| `emails_last_sent_date` | TEXT | Date string (YYYY-MM-DD) of the last email sent. |
| `tokens_last_reset_date`| TEXT | Month string (YYYY-MM) of the last token reset. |

**Persistence:**
The database file is persisted using a Docker volume (`VOLUME /app/data`) ensuring data survives container restarts and redeployments.

## 2. Backend Logic (`api/db.py`)

The database module handles all state transitions and checks.

### Rate Limiting (API Calls)
*   **Limit:** 5 calls/min (Premium), 1 call/min (Free).
*   **Logic:**
    *   On every call, check `time.time() - api_window_start`.
    *   If > 60 seconds, reset `api_calls_count` to 0 and update `api_window_start`.
    *   If count < limit, increment count and allow.
    *   Else, return `False` (429 Too Many Requests).

### Quotas (Emails)
*   **Limit:** 10 emails/day (Premium), 0 (Free).
*   **Logic:**
    *   On call, check if `current_date != emails_last_sent_date`.
    *   If different, reset `emails_sent_count` to 0.
    *   If count < limit, increment and update date.
    *   Else, return `False`.

### Token Tracking
*   **Accumulation:** Adds tokens from every model run to `total_tokens`.
*   **Monthly Reset:** Before updating, checks if `current_month != tokens_last_reset_date`. If so, resets `total_tokens` to 0 before adding the new usage.
*   **Monthly Limit:** Enforced before generation. If `total_tokens` is at or above the plan limit, the API call is blocked until the next monthly reset. Defaults are 50k (Free) and 100k (Premium), configurable via `TOKEN_LIMIT_FREE` and `TOKEN_LIMIT_PREMIUM`.

### Plan Synchronization
*   On every request, the user's plan from the Clerk token is compared with the DB record.
*   If the plan changes (upgrade/downgrade), usage counters (`api_calls_count`, `emails_sent_count`) are reset immediately.

## 3. API Endpoints (`api/index.py`)

### `GET /api/subscription`
*   Returns the user's plan status and **persistent usage stats** from the DB.
*   Response: `{ ..., usage: { "total_tokens": 1234, "api_calls_count": 2, "emails_sent_count": 5 } }`

### `POST /api` (Idea Generation)
*   **Check:** Calls `db.check_and_increment_api_call`. Raises 429 if limited.
*   **Track:** After generation, aggregates tokens from all models and calls `db.track_token_usage`.
*   **Response:** Returns generation results AND an updated `usage` object containing the latest counters from the DB (to update frontend immediately).

### `POST /api/recommend-combination`
*   **Check:** Calls `db.check_and_increment_api_call`.
*   **Track:** Calls `db.track_token_usage`.

### `POST /api/email`
*   **Check:** Calls `db.check_and_increment_email`.

## 4. Frontend Integration (`pages/product.tsx`)

### State Management
*   `tokenUsage` state holds: `total_tokens`, `api_calls_count`, `emails_sent_count`.
*   **Initialization:** Fetches `/api/subscription` on mount to get persistent data.
*   **Updates:**
    *   **Real-time:** After every `generateIdeas` or `recommendCombination` call, the response includes updated usage, which is merged into the state via `addUsage`.
    *   **Polling:** A `useEffect` polls `/api/subscription` every **3 seconds**. This ensures that when the 60s rate limit window expires on the server, the frontend receives the reset counter (`api_calls_count: 0`) almost immediately, re-enabling the buttons.
    *   **Monthly Tokens:** The subscription poll also reflects the monthly token reset so buttons re-enable after the period rolls over.

### UI Components
*   **Current Usage Card:** Displays the 3 metrics (Tokens, API Calls, Emails) in a grid, showing `Current / Limit`.
*   **Button Disabling:**
    *   "Generate Ideas" & "Recommend Combination" buttons are disabled if `api_calls_count >= limit`.
    *   Both buttons are also disabled if `total_tokens >= token_limit`.
    *   "Send Email" button is disabled if `emails_sent_count >= limit`.
*   **Error Modal:** If a request fails with 429 (detected in catch block), a `LimitModal` appears informing the user.
