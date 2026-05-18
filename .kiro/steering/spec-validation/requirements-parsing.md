# Requirements Parsing — Steering Document

## Purpose

This document instructs the validation agent on how to parse requirements documents into testable behavioral assertions. The agent MUST extract structured requirements regardless of the input format.

## Supported Requirement Formats

### 1. EARS (Easy Approach to Requirements Syntax)

EARS patterns and their test implications:

| Pattern | Syntax | Test Strategy |
|---------|--------|---------------|
| Ubiquitous | "The system shall [action]" | Always-true invariant; test on every relevant endpoint |
| Event-driven | "When [trigger], the system shall [response]" | Trigger the event → assert the response |
| Unwanted | "If [condition], the system shall [handling]" | Inject the unwanted condition → assert error handling |
| State-driven | "While [state], the system shall [behavior]" | Establish state → assert behavior holds |
| Optional | "Where [feature enabled], the system shall [action]" | Enable feature → assert action; disable → assert absence |

### 2. User Stories

Format: "As a [role], I want [capability] so that [benefit]"

Extraction rules:
- **Role** → authentication/authorization precondition for tests
- **Capability** → the behavior under test (maps to API endpoint or workflow)
- **Benefit** → informs assertion granularity (if benefit is data integrity, assert at field level)

### 3. Structured Requirements (REQ-ID format)

Pattern: `REQ-[TYPE]-[NUMBER]: [description]`

Extraction rules:
- `REQ-F-*` → Functional requirement → generate behavioral test
- `REQ-NF-*` → Non-functional requirement → generate performance/security test
- `REQ-C-*` → Constraint → generate boundary/validation test
- `REQ-IF-*` → Interface requirement → generate contract test

## Parsing Algorithm

For each requirements file:

1. **Identify all REQ-IDs** — scan for patterns matching `REQ-[A-Z]-[0-9]+`
2. **Extract the behavioral assertion** — the SHALL/MUST/WILL statement following the ID
3. **Classify testability**:
   - TESTABLE: Has observable input → output behavior via an API or interface
   - UI-ONLY: Describes screen layout, visual formatting, or user interaction mechanics with no API equivalent
   - INFRASTRUCTURE: Describes deployment, configuration, or operational concerns
4. **Extract preconditions** — any "When", "If", "While", "Given" clauses preceding the action
5. **Extract postconditions** — the expected outcome/response/state after the action
6. **Map to tech.md API** — link each testable requirement to its corresponding API endpoint from the technical tech.mdument (tech.md)

## Output Format

For each parseable requirement, produce a structured assertion:

```yaml
- reqId: REQ-F-005
  classification: TESTABLE
  category: validation
  precondition: "User submits payment with empty account ID"
  action: "POST /api/v1/payments with accountId=''"
  expectedOutcome: "400 Bad Request with error message about empty account ID"
  endpoint: "/api/v1/payments"
  httpMethod: POST
  errorScenario: true
```

## Requirements That Cannot Be Tested

Mark the following as NOT_TESTABLE and exclude from test generation:

- Screen layout / visual formatting requirements (no API equivalent)
- Key-press handling (UI-specific, unless mapped to API actions)
- Performance requirements without quantitative thresholds
- Requirements with open questions (OQ-* prefixed)
- Requirements depending on external systems not available in test environment

## Handling Ambiguity

When a requirement is ambiguous:
1. Check the technical tech.mdument (tech.md) for clarification
2. If still ambiguous, generate a test for the MOST RESTRICTIVE interpretation
3. Annotate the test with `@AmbiguousRequirement("REQ-ID")` to flag for human review
