# Hook: Post-Task Validation

## Trigger

**Event:** `postTaskExecution`

This hook fires automatically after a coding task completes — specifically when the coding agent finishes generating or modifying source code for a feature that has associated specification files.

## Activation Conditions

The hook activates ONLY when ALL of the following are true:

1. The completed task modified source code (not just docs, configs, or tests)
2. Requirements files exist in the project (files matching `**/requirements.md`, `**/requirements/*.md`, or `**/specs/*.md`)
3. A technical design document exists (files matching `**/tech.md`, `**/TECH.md`, or `**/design-doc.md`)
4. The modifications are in a domain that has corresponding requirements

If any condition is not met, the hook exits silently.

## Workflow

```
┌─────────────────────────────────────┐
│ Coding Agent completes task         │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│ Hook: Check activation conditions   │
│ - Source code modified?             │
│ - Requirements files exist?         │
│ - Tech doc (tech.md) exists?        │
└─────────────────┬───────────────────┘
                  │ (all true)
                  ▼
┌─────────────────────────────────────┐
│ Invoke spec-validator sub-agent     │
│ Inputs:                             │
│   requirementsPath: {detected}      │
│   techDocPath: {detected}           │
│   testFramework: auto-detect        │
│   executeTests: true                │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│ Sub-agent generates tests from      │
│ specs (never sees source code)      │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│ Execute generated tests             │
└─────────────────┬───────────────────┘
                  │
          ┌───────┴───────┐
          │               │
     All Pass         Failures
          │               │
          ▼               ▼
┌──────────────┐  ┌──────────────────────┐
│ Report:      │  │ Classify violations  │
│ "Spec-       │  │ Feed to coding agent │
│  compliant"  │  │ Auto-repair cycle    │
└──────────────┘  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │ Re-execute tests     │
                  │ (max 3 iterations)   │
                  └──────────┬───────────┘
                             │
                     ┌───────┴───────┐
                     │               │
                All Pass         Still Failing
                     │               │
                     ▼               ▼
              ┌────────────┐  ┌────────────────┐
              │ Report:    │  │ Report:        │
              │ "Fixed,    │  │ "Unresolved    │
              │  now spec- │  │  violations —  │
              │  compliant"│  │  human review  │
              └────────────┘  │  required"     │
                              └────────────────┘
```

## File Discovery Logic

```
# Requirements discovery (in priority order):
1. Look for directories named: requirements/, specs/, specifications/
2. Look for files matching: **/requirements.md, **/specs.md
3. Look for files containing REQ-* patterns

# Technical design doc discovery (in priority order):
1. Look for: tech.md, TECH.md in project root
2. Look for: docs/tech.md, docs/TECH.md
3. Look for files containing "API Contract" or "## Endpoints" or "## Architecture" headings
```

## Output

The hook writes its results to:
- `TestsToSpecCoverage.md` — coverage of specs/requirements by E2E and integration tests
- `spec-validation-violations.md` — failure report (if any)

And reports a summary to the user:

```
✓ Spec Validation: 79 integration + 12 e2e tests generated
✓ Integration test coverage: 85% of testable requirements
✓ End-to-end test coverage: 60% of testable requirements
✓ Combined coverage: 92% of testable requirements
✓ TestsToSpecCoverage.md report generated
✗ 3 violations detected (2 P2, 1 P3) — auto-repairing...
✓ All violations resolved after 1 repair cycle
```
