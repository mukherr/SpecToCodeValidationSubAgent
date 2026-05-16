# Violation Classification — Steering Document

## Purpose

When tests fail against the implementation, each failure must be classified by severity and category to enable prioritized auto-repair. This document defines the classification taxonomy.

## Severity Levels

| Level | Label | Definition | SLA |
|-------|-------|------------|-----|
| P1 | Critical | Data loss, corruption, or security vulnerability | Must fix before merge |
| P2 | High | Incorrect functional behavior visible to users | Must fix before merge |
| P3 | Medium | Degraded experience, cosmetic logic errors | Should fix before merge |
| P4 | Low | Non-functional deviation, style issues | Fix if time permits |

## Violation Categories

### Data Integrity Violations (typically P1)

Failures where data is lost, truncated, or corrupted:

- **Column overflow**: Value exceeds storage constraint → truncation/data loss
- **Type mismatch**: Numeric precision loss (e.g., float vs. decimal)
- **Encoding corruption**: Character encoding issues causing data garbling
- **Silent truncation**: String/number silently cut without error

Classification signal: Test asserts on data round-trip fidelity and fails.

### Behavioral Violations (typically P2)

Failures where the system does the wrong thing:

- **Validation ordering**: Checks happen in wrong sequence, masking real errors
- **Missing validation**: Input accepted that should be rejected
- **Wrong status code**: Returns 200 when spec says 400, or vice versa
- **Missing side effect**: Action doesn't trigger required downstream effect
- **Wrong error message**: Error reported but with incorrect/misleading text

Classification signal: Test asserts on response status or body content and gets a different valid-looking but incorrect response.

### Security Violations (typically P2)

Failures exposing security gaps:

- **Missing authentication**: Endpoint accessible without credentials
- **Missing authorization**: Endpoint accessible by wrong role
- **Attribute omission**: Security headers/cookie attributes missing
- **Information leakage**: Error responses revealing internal details
- **Injection vulnerability**: Input not sanitized per spec constraints

Classification signal: Test sends unauthenticated/unauthorized request expecting rejection; gets success instead.

### Boundary Violations (typically P2-P3)

Failures at constraint boundaries:

- **Empty string bypass**: Empty/whitespace strings circumventing required-field guards
- **Off-by-one**: Boundary at N characters accepts N+1 or rejects N
- **Overflow handling**: Large numbers not handled per spec
- **Null handling**: Null input not rejected when field is required

Classification signal: Test sends boundary-value input; behavior doesn't match spec's boundary rules.

### State Management Violations (typically P3)

Failures in state tracking or comparison:

- **Comparison bugs**: Using identity comparison instead of semantic comparison
- **Stale state**: Reading cached/old state instead of current
- **Race conditions**: Concurrent operations producing inconsistent state
- **Change detection**: False positives/negatives in "has this changed?" logic

Classification signal: Test exercises state transitions; intermediate or final state doesn't match expectation.

### Infrastructure/Configuration Violations (typically P3-P4)

Failures from misconfiguration rather than logic errors:

- **Missing dependency**: Required library not included
- **Wrong profile/config**: Test profile not activating correct settings
- **Port/path mismatch**: Service listening on wrong port or path
- **Timeout misconfiguration**: Timeouts too short for test data volume

Classification signal: Tests fail with connection errors, ClassNotFoundExceptions, or configuration-related stack traces.

## Classification Algorithm

For each test failure:

1. **Parse the exception/assertion type**:
   - `AssertionError` with status code mismatch → Behavioral or Security
   - `AssertionError` with body content mismatch → Behavioral or Data Integrity
   - `SQLException` or data exception → Data Integrity
   - `ConnectException` / `TimeoutException` → Infrastructure
   - `4xx response when expecting 2xx` → Behavioral
   - `2xx response when expecting 4xx` → Security or Boundary

2. **Examine the assertion context**:
   - What did the test expect? (from the requirement)
   - What did the test get? (from the actual response)
   - Is the delta in status code, response body, headers, or timing?

3. **Assign severity based on blast radius**:
   - Could this cause data loss in production? → P1
   - Could this cause incorrect behavior visible to users? → P2
   - Could this cause degraded but functional experience? → P3
   - Is this cosmetic or non-functional? → P4

## Violation Report Format

```markdown
## Violation #{N}

| Field | Value |
|-------|-------|
| **Requirement** | REQ-F-XXX: {description} |
| **Test** | {TestClass}.{testMethod} |
| **Category** | {Data Integrity / Behavioral / Security / Boundary / State / Infrastructure} |
| **Severity** | P{1-4} — {label} |
| **Expected** | {what the spec says should happen} |
| **Actual** | {what actually happened} |
| **Root Cause** | {classification of why — to guide auto-repair} |
| **Auto-fixable** | Yes/No — {brief explanation} |
| **Suggested Fix** | {structured fix hint for the coding agent} |
```

## Auto-Repair Guidance

For each violation category, provide structured hints to the coding agent:

| Category | Fix Pattern |
|----------|-------------|
| Column overflow | Reduce field size or add truncation at boundary |
| Validation ordering | Move validation logic before competing checks |
| Empty string bypass | Add `.isBlank()` / `.strip().isEmpty()` guard |
| Comparison bugs | Use semantic comparison (`.compareTo()`, `.equals()` with normalization) |
| Missing security attribute | Add attribute to response configuration |
| Wrong status code | Fix conditional branching in controller/handler |
| Missing side effect | Add the missing call in the service layer |

The suggested fix MUST be specific enough for an AI coding agent to locate and fix the issue programmatically. Include:
- The API endpoint affected
- The expected vs. actual behavior delta
- The type of code change needed (but NOT the specific file/line — that's for the coding agent to find)
