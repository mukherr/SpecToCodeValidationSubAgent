# Spec Mutation — Steering Document

## Purpose

Spec mutation validates whether generated tests are genuinely tied to the requirements they claim to cover, or merely decorative. It answers: "if this requirement were different, would the test suite notice?"

This is a traceability oracle that complements coverage metrics. A test can "cover" a requirement (by annotation) without actually constraining the implementation toward that requirement. Spec mutation exposes that gap.

## Core Mechanism

1. **Mutate** a single requirement's SHALL/MUST clause
2. **Regenerate** the test(s) annotated to that requirement using the same generation patterns
3. **Diff** the regenerated test against the original
4. **Score** the diff to determine whether coverage is real or vacuous

Signal interpretation:
- Tests that **change** when the spec changes → genuinely tied to the requirement
- Tests that **don't change** when the spec changes → vacuous coverage (decorative)

## When to Apply

Spec mutation is most valuable for:
- **E2E tests** that annotate 4–6 REQ-IDs per test method — mutation reveals which REQ-IDs actually contribute assertions
- **Integration tests** with extensive setup where only a fraction of the test body depends on the requirement under test
- **Any test** claiming coverage of a side-effect requirement (balance updates, audit logs, state transitions)

Spec mutation is less valuable for:
- Tight unit tests where the assertion is a single line and linkage is obvious
- Tests covering UI-ONLY or INFRASTRUCTURE requirements (already excluded from generation)

## Mutation Taxonomy

Apply mutations in isolation — one REQ-ID per mutation. Never mutate the entire spec at once.

### 1. Outcome Inversion (Highest Signal)

Flip the SHALL clause from acceptance to rejection or vice versa.

| Original | Mutated |
|----------|---------|
| SHALL reject empty account_id | SHALL accept empty account_id |
| SHALL return 400 | SHALL return 201 |
| SHALL decrease balance | SHALL NOT decrease balance |

**Expected diff:** Regenerated test asserts the opposite outcome (different status code, different validation expectation).
**If diff is empty:** Test never asserted on the acceptance/rejection semantics of this requirement.

### 2. Boundary Shift

Move numeric or length constraints by one unit.

| Original | Mutated |
|----------|---------|
| max 26 characters | max 25 characters |
| amount > 0 | amount >= 0 |
| minimum 8 characters | minimum 9 characters |

**Expected diff:** Regenerated test uses different boundary values in test data.
**If diff is empty:** Test hardcodes arbitrary values instead of constraint-derived values.

### 3. Status Code Substitution

Change the documented response status to a semantically adjacent code.

| Original | Mutated |
|----------|---------|
| returns 400 | returns 422 |
| returns 403 | returns 401 |
| returns 201 | returns 200 |

**Expected diff:** Regenerated test asserts the new status code.
**If diff is empty:** Test uses loose assertions (`assert status in (400, 422)`) or doesn't assert status at all.

### 4. Side-Effect Mutation (E2E-Specific)

Add, remove, or reorder a downstream effect in a multi-step requirement.

| Original | Mutated |
|----------|---------|
| SHALL decrease source balance AND create transaction record | SHALL create transaction record (drop balance clause) |
| SHALL send notification AND update audit log | SHALL update audit log (drop notification) |
| SHALL update status AND record timestamp | SHALL update status (drop timestamp) |

**Expected diff:** Regenerated test drops the assertion on the removed side effect.
**If diff is empty:** Original test was never verifying that side effect — it was walking through the workflow without asserting on intermediate state.

### 5. Role/Auth Mutation

Change the role permitted to perform the action.

| Original | Mutated |
|----------|---------|
| Admin role can perform X | Auditor role can perform X |
| Authenticated user can access | Unauthenticated user can access |

**Expected diff:** Regenerated test uses a different `loginAs(role)` or removes authentication setup.
**If diff is empty:** Test always authenticates as a privileged role without actually exercising the authorization constraint.

## Mutation Execution Process

### Step 1: Select Target REQ-ID

For each testable requirement that has at least one test claiming coverage:
- Parse the original requirement text from `requirements/{Domain}/requirements.md`
- Identify the SHALL/MUST clause and its constraint type

### Step 2: Generate Mutant

Apply exactly ONE mutation from the taxonomy above. Choose the mutation type that matches the requirement's constraint type:

| Requirement Type | Primary Mutation | Secondary Mutation |
|-----------------|-----------------|-------------------|
| Validation (accepts/rejects input) | Outcome Inversion | Boundary Shift |
| Response format (returns status X) | Status Code Substitution | Outcome Inversion |
| Side effect (triggers downstream action) | Side-Effect Mutation | Outcome Inversion |
| Authorization (role-based access) | Role/Auth Mutation | Outcome Inversion |
| Constraint (length, range, format) | Boundary Shift | Status Code Substitution |

### Step 3: Regenerate Test

Using the SAME test generation patterns from `test-generation-patterns.md`, regenerate the test(s) for the mutated requirement. The regeneration:
- MUST use the same prompt/agent configuration as the original generation
- MUST target only the test(s) annotated to the mutated REQ-ID
- MUST NOT see the original test (to avoid anchoring)

### Step 4: Compute Diff

Compare the regenerated test against the original test for the mutated REQ-ID.

**Normalization rules** (to avoid false positives from LLM nondeterminism):
- Ignore whitespace-only changes
- Ignore comment-only changes (changes to `// Requirements covered:` or docstrings don't count)
- Ignore variable name differences that don't change semantics
- Focus on **assertion statements**: changes to `assert`, `expect`, `assertEquals`, status code checks, body content checks
- Focus on **request construction**: changes to request body, headers, authentication setup

### Step 5: Score

| Diff Content | Score | Interpretation |
|-------------|-------|----------------|
| Assertion(s) changed or removed | KILLED | Requirement genuinely covered |
| Request construction changed | KILLED | Test exercises the mutated aspect |
| Only comments/names changed | SURVIVED | Vacuous coverage — test is decorative |
| No diff at all | SURVIVED | Vacuous coverage — test is decorative |
| Test removed entirely | KILLED | Requirement was sole purpose of the test |

## Scoring Rubric for Multi-Requirement Tests

When an E2E test covers N requirements (e.g., `@pytest.mark.requirement("REQ-F-005", "REQ-F-007", "REQ-F-008")`):

- Mutate each REQ-ID in isolation
- Score each mutation independently
- A test receives a **per-REQ coverage score**:

| E2E Test | REQ-F-005 | REQ-F-007 | REQ-F-008 |
|----------|-----------|-----------|-----------|
| test_payment_happy_path | KILLED | KILLED | SURVIVED |

Interpretation: The test genuinely validates REQ-F-005 and REQ-F-007, but its claim on REQ-F-008 is vacuous.

## Report Format

### Mutation Survival Report

Append a `## Spec Mutation Analysis` section to `TestsToSpecCoverage.md`:

```markdown
## Spec Mutation Analysis

### Summary
- Requirements mutated: {N}
- Mutations killed (real coverage): {N} ({percentage}%)
- Mutations survived (vacuous coverage): {N} ({percentage}%)

### Mutation Results by Domain

#### {Domain Name}

| Requirement | Mutation Type | Test(s) | Verdict | Detail |
|-------------|--------------|---------|---------|--------|
| REQ-F-005 | Outcome Inversion | test_empty_account_id | KILLED | Assertion changed from 400→201 |
| REQ-F-008 | Side-Effect Mutation | test_payment_happy_path | SURVIVED | No balance assertion in original |
| REQ-F-010 | Boundary Shift | test_amount_validation | KILLED | Boundary value changed from 0 to -1 |

### Vacuous Coverage (Action Required)

| Requirement | Claimed By | Mutation Type | Remediation |
|-------------|-----------|--------------|-------------|
| REQ-F-008 | test_payment_happy_path | Side-Effect Mutation | Add balance assertion after payment |
| REQ-F-012 | test_auth_flow | Role/Auth Mutation | Add role-specific test path |
```

## Integration with Violation Classification

Vacuous coverage constitutes a new violation category:

| Field | Value |
|-------|-------|
| **Category** | Vacuous Coverage |
| **Severity** | P3 — Medium |
| **Definition** | Test annotates requirement but mutation analysis proves no assertion validates it |
| **Remediation** | Add assertion(s) that specifically exercise the mutated aspect of the requirement |

When a requirement has SURVIVED status:
1. Flag it in the coverage report as `VACUOUS` (distinct from COVERED and UNCOVERED)
2. Generate a remediation hint describing what assertion is missing
3. If a side-effect mutation survived, specify which downstream check to add

## Status Values (Extended)

Add to the existing status taxonomy in `traceability-standards.md`:

| Status | Meaning |
|--------|---------|
| COVERED | Test validates this requirement (confirmed by mutation kill) |
| VACUOUS | Test claims coverage but mutation survived — assertions don't exercise this requirement |
| UNCOVERED | Testable requirement but no test generated |
| UI-ONLY | Requirement is UI-specific; cannot test via API |
| INFRA | Infrastructure/deployment requirement; out of scope |
| AMBIGUOUS | Requirement unclear; test generated with restrictive interpretation |
| DEFERRED | Depends on external system not available in test env |

## Sampling Strategy

Full mutation of every requirement on every run is expensive. Use these heuristics:

1. **Always mutate**: Requirements with COVERED status that are annotated on E2E tests covering 3+ requirements
2. **Always mutate**: Requirements whose sole test has no domain-specific assertions (only status code checks)
3. **Sample on CI**: Randomly select 20–30% of remaining requirements per run; rotate across runs for full coverage
4. **Mutate on change**: When a requirement is modified in a PR, mutate both the old and new versions

## Failure Modes and Mitigations

| Failure Mode | Symptom | Mitigation |
|-------------|---------|------------|
| Equivalent mutant | Mutation doesn't change observable behavior | Only mutate documented observable outcomes; skip reorderings of independent side effects |
| LLM nondeterminism | Regenerated test differs from original due to randomness, not mutation | Normalize diffs to assertion-level; ignore cosmetic variation |
| Generator anchoring | Regeneration produces identical test because model memorizes patterns | Use a different model or temperature for regeneration; never show original test to the regenerator |
| Over-fitting detection | Flagging a test as vacuous when it validates through an indirect path | Allow tests to claim "indirect coverage" with explicit justification; exempt from mutation |

## Relationship to Other Steering Documents

- **requirements-parsing.md**: Provides the structured requirement format that mutation operates on
- **test-generation-patterns.md**: Defines the generation process that mutation re-invokes
- **traceability-standards.md**: Defines the annotation format that mutation audits; extended with VACUOUS status
- **violation-classification.md**: Extended with "Vacuous Coverage" category at P3 severity
