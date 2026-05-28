# Error Model

## Error Categories

- `ConfigurationError`: invalid or missing env/config values
- `AuthenticationError`: invalid credentials or unauthorized scopes
- `AuthorizationError`: endpoint/scope access denied
- `RateLimitError`: provider throttling or local budget exceeded
- `TransientIntegrationError`: timeout/network/5xx, retryable
- `PermanentIntegrationError`: 4xx invalid request/non-retryable
- `DataValidationError`: payload parse/contract mismatch
- `DataSourceError`: missing/invalid Cardmarket bulk data file or provenance
- `WorkflowExecutionError`: step-level orchestration failure

## Retry Policy

- retry only `RateLimitError` and `TransientIntegrationError`
- use bounded exponential backoff with jitter
- honor provider `Retry-After` headers where provided
- stop retries when retry budget is exhausted and persist failure details

## Workflow Failure Semantics

- record-level failures should not abort full batch by default
- step-level critical failures mark step as failed and stop dependent steps
- run status transitions: `pending -> running -> succeeded|failed|cancelled`

## CLI Exit Codes

- `0`: success
- `2`: configuration/validation failure
- `3`: authentication/authorization failure
- `4`: unrecoverable provider or policy violation
- `5`: workflow execution failure

## Compliance-Specific Behavior

- treat permission violations as non-retryable
- stop execution when policy checks detect disallowed endpoint usage
- redact credentials/tokens from all error logs and stored payloads

