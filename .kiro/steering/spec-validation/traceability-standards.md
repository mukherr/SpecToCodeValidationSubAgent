# Traceability Standards — Steering Document

## Purpose

Every generated test MUST be traceable to the specific requirement(s) it validates. This enables:
1. Coverage analysis (which requirements have tests, which don't)
2. Impact analysis (when a requirement changes, which tests need updating)
3. Violation attribution (when a test fails, which requirement is violated)

## Traceability Annotation Format

### Per-Test Annotation

Every test method MUST include a traceability annotation linking it to one or more requirement IDs.

**Java:**
```java
@Test
@DisplayName("REQ-F-005: Empty account ID returns validation error")
void testEmptyAccountId_ReturnsValidationError() { ... }
```

**Python:**
```python
@pytest.mark.requirement("REQ-F-005")
def test_empty_account_id_returns_validation_error(self):
    """REQ-F-005: Empty account ID returns validation error"""
```

**TypeScript:**
```typescript
it('REQ-F-005: Empty account ID returns validation error', async () => { ... });
```

**Go:**
```go
func TestEmptyAccountId_ReturnsValidationError(t *testing.T) {
    // Requirement: REQ-F-005
    ...
}
```

### Multi-Requirement Tests

When a single test validates multiple requirements (common in E2E flows):

```java
@Test
@DisplayName("E2E Payment: REQ-F-005, REQ-F-007, REQ-F-008, REQ-F-010")
void testPaymentFlow() { ... }
```

## Coverage Report Format

After test generation, produce a traceability matrix as a markdown file:

```markdown
# Requirements Traceability Matrix

## Summary
- Total requirements parsed: {N}
- Testable requirements: {N}
- Requirements with tests: {N}
- Coverage: {percentage}%

## Coverage by Domain

| Domain | Total | Testable | Covered | Coverage |
|--------|-------|----------|---------|----------|
| Authentication | 14 | 9 | 9 | 100% |
| Bill Payment | 12 | 10 | 9 | 90% |
| ... | ... | ... | ... | ... |

## Detailed Mapping

### {Domain Name}

| Requirement | Description | Test(s) | Status |
|-------------|-------------|---------|--------|
| REQ-F-001 | Screen display | N/A | UI-ONLY |
| REQ-F-005 | Empty userId validation | AuthTest.testEmptyUserId | COVERED |
| REQ-F-015 | Rate limiting | | UNCOVERED |
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
├── spec-validation-coverage.md          # Traceability matrix
├── spec-validation-violations.md        # Failure report (after execution)
└── spec-validation-summary.md           # Executive summary
```
