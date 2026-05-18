# Traceability Standards — Steering Document

## Purpose

Every generated test MUST be traceable to the specific requirement(s) it validates. This enables:
1. Coverage analysis (which requirements have tests, which don't)
2. Impact analysis (when a requirement changes, which tests need updating)
3. Violation attribution (when a test fails, which requirement is violated)

## Traceability Annotation Format

### Per-Test Annotation

Every test method MUST include TWO instrumentation elements:
1. **Requirement ID(s)** — linking the test to the specific requirement(s) it covers
2. **Test explanation** — describing what the test is performing or exercising

**Java:**
```java
@Test
@DisplayName("REQ-F-005: Empty account ID returns validation error")
void testEmptyAccountId_ReturnsValidationError() {
    // Requirements covered: REQ-F-005
    // Exercises: Verifies that the payment endpoint rejects requests with an
    //   empty account ID field, returning a 400 status with a specific validation
    //   error message, exercising the required-field input validation guard
    ...
}
```

**Python:**
```python
@pytest.mark.requirement("REQ-F-005")
def test_empty_account_id_returns_validation_error(self):
    """
    Requirements: REQ-F-005
    Exercises: Verifies that the payment endpoint rejects requests with an
    empty account ID field, returning a 400 status with a specific validation
    error message, exercising the required-field input validation guard
    """
```

**TypeScript:**
```typescript
it('REQ-F-005: Empty account ID returns validation error', async () => {
  // Requirements covered: REQ-F-005
  // Exercises: Verifies that the payment endpoint rejects requests with an
  //   empty account ID field, returning a 400 status with a specific validation
  //   error message, exercising the required-field input validation guard
  ...
});
```

**Go:**
```go
func TestEmptyAccountId_ReturnsValidationError(t *testing.T) {
    // Requirements covered: REQ-F-005
    // Exercises: Verifies that the payment endpoint rejects requests with an
    //   empty account ID field, returning a 400 status with a specific validation
    //   error message, exercising the required-field input validation guard
    ...
}
```

### Multi-Requirement Tests (E2E flows)

When a single test validates multiple requirements (common in E2E flows):

```java
@Test
@DisplayName("E2E Payment: REQ-F-005, REQ-F-007, REQ-F-008, REQ-F-010")
void testPaymentFlow_HappyPath() {
    // Requirements covered: REQ-F-005, REQ-F-007, REQ-F-008, REQ-F-010
    // Exercises: End-to-end payment workflow — authenticates a user, creates a
    //   payment with valid account details (REQ-F-005), processes the payment
    //   through the approval pipeline (REQ-F-007), verifies transaction recording
    //   with correct timestamps (REQ-F-008), and confirms balance update on the
    //   source account (REQ-F-010). Validates cross-domain consistency between
    //   payment, transaction, and account resources.
    ...
}
```

## TestsToSpecCoverage Report Format

After test generation, produce the `TestsToSpecCoverage.md` report with the following structure:

```markdown
# Tests to Specification Coverage Report

## Summary
- Total requirements parsed: {N}
- Testable requirements: {N}
- Requirements covered by integration tests: {N} ({percentage}%)
- Requirements covered by end-to-end tests: {N} ({percentage}%)
- Requirements covered by BOTH integration and E2E tests: {N} ({percentage}%)
- Combined coverage (covered by at least one test type): {N} ({percentage}%)
- Uncovered requirements: {N}

## Coverage by Test Type

### Integration Test Coverage

| Domain | Total Reqs | Testable | Covered by Integration | Coverage % |
|--------|-----------|----------|----------------------|------------|
| Authentication | 14 | 9 | 9 | 100% |
| Bill Payment | 12 | 10 | 9 | 90% |
| ... | ... | ... | ... | ... |

### End-to-End Test Coverage

| Domain | Total Reqs | Testable | Covered by E2E | Coverage % |
|--------|-----------|----------|----------------|------------|
| Authentication | 14 | 9 | 6 | 67% |
| Bill Payment | 12 | 10 | 8 | 80% |
| ... | ... | ... | ... | ... |

## Detailed Integration Test Mapping

### {Domain Name}

| Requirement | Description | Integration Test(s) | What Test Exercises | Status |
|-------------|-------------|--------------------|--------------------|--------|
| REQ-F-001 | Screen display | N/A | N/A | UI-ONLY |
| REQ-F-005 | Empty userId validation | AuthTest.testEmptyUserId | Verifies empty user ID returns 400 with validation error | COVERED |
| REQ-F-015 | Rate limiting | | | UNCOVERED |

## Detailed End-to-End Test Mapping

### {Domain Name}

| Requirement | Description | E2E Test(s) | What Test Exercises | Status |
|-------------|-------------|------------|--------------------|---------| 
| REQ-F-005 | Empty userId validation | EndToEndAuthFlowTest.testLoginFlow_InvalidCredentials | Tests complete login failure workflow including invalid userId handling | COVERED |
| REQ-F-007 | Payment approval | EndToEndPaymentFlowTest.testPaymentFlow_HappyPath | Full payment lifecycle from creation through approval to balance update | COVERED |

## Combined Coverage Matrix

| Requirement | Integration Tests | E2E Tests | Overall Status |
|-------------|------------------|-----------|----------------|
| REQ-F-005 | ✓ (2 tests) | ✓ (1 test) | FULLY COVERED |
| REQ-F-007 | ✓ (3 tests) | ✓ (2 tests) | FULLY COVERED |
| REQ-F-015 | ✗ | ✗ | UNCOVERED |
| REQ-F-020 | ✓ (1 test) | ✗ | PARTIAL (integration only) |

## Uncovered Requirements

| Requirement | Description | Reason |
|-------------|-------------|--------|
| REQ-F-015 | Rate limiting | Depends on external infrastructure not available in test env |
| REQ-NF-003 | Page load < 2s | Non-functional, no quantitative test harness available |
```

## Status Values

| Status | Meaning |
|--------|---------|
| COVERED | At least one test validates this requirement |
| UNCOVERED | Testable requirement but no test generated (gap) |
| UI-ONLY | Requirement is UI-specific; cannot test via API |
| INFRA | Infrastructure/deployment requirement; out of scope |
| AMBIGUOUS | Requirement unclear; test generated with restrictive interpretation |
| DEFERRED | Depends on external system not available in test env |

## Traceability in Violation Reports

When tests fail, the violation report MUST reference the requirement:

```markdown
## Violation: REQ-F-008 — Timestamp Column Constraint

**Requirement:** Transaction timestamp SHALL NOT exceed 26 characters
**Test:** TransactionControllerIntegrationTest.testCreateTransaction
**Observed:** Timestamp "2026-05-14T10:30:00.123456Z" is 27 characters
**Expected:** Timestamp truncated or formatted to ≤26 characters
**Severity:** P1 — Data loss (column truncation)
**Auto-fixable:** Yes — reduce timestamp precision
```

## File Naming Convention for Reports

```
{project-root}/
├── TestsToSpecCoverage.md               # Tests-to-specification coverage report (E2E + integration)
├── spec-validation-violations.md        # Failure report (after execution)
└── spec-validation-summary.md           # Executive summary
```
