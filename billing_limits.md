# Billing / Limits Specification

## Plans
Plan names are derived from Clerk tokens.
- Free: default plan (`u:free_user`)
- Premium: any plan in `PREMIUM_PLANS` (ex: `u:premium_subscription`, `u:premium`, `u:pro`)

## Limits (Defaults)
- **Monthly tokens**:
  - Free: 50,000 (`TOKEN_LIMIT_FREE`)
  - Premium: 500,000 (`TOKEN_LIMIT_PREMIUM`)
- **API calls per minute**:
  - Free: 1
  - Premium: 5
- **Emails per day (UTC)**:
  - Free: 0
  - Premium: 10
- **Saved results storage**:
  - Free: 100 MB (`SAVED_RESULTS_LIMIT_FREE_BYTES`)
  - Premium: 1 GB (`SAVED_RESULTS_LIMIT_PREMIUM_BYTES`)

## Enforcement Behavior
- API requests are blocked if rate limits or token limits are exceeded.
- Email sending is blocked if daily email limit is exceeded.
- Saving a result is blocked if storage limits are exceeded.

## Resets
- API rate limit resets every 60 seconds.
- Email limit resets daily (UTC).
- Token usage resets monthly based on `tokens_last_reset_date`.

## User Experience
- Frontend disables buttons when limits are reached.
- Usage card shows current usage with refresh tooltips.
