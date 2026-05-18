# Spec-to-Code Validation Skill

## Activation

This skill activates when the user requests specification validation, test generation from specs, or compliance checking against requirements.

**Trigger patterns:**
- "validate against spec"
- "generate tests from requirements"
- "check spec compliance"
- "run spec validation"
- "/spec-validate"

## Inputs

The user must provide or the agent must locate:

1. **Requirements path** — directory or file(s) containing structured requirements (EARS format, user stories, or REQ-ID based)
2. **Technical design document path** — tech.md file containing architecture, API contracts, schemas, interface definitions, and forward engineering details
3. **Test framework** (optional) — auto-detected from project if not specified
4. **Output directory** (optional) — defaults to project's standard test location

## Workflow

### Phase 1: Requirements Parsing

1. Scan the requirements path for all requirement files
2. For each file, extract requirements using the parsing rules in `steering/spec-validation/requirements-parsing.md`
3. Classify each requirement as TESTABLE, UI-ONLY, INFRA, or AMBIGUOUS
4. Produce a structured list of testable behavioral assertions

### Phase 2: Technical Design Document Analysis

1. Read the technical design document (tech.md)
2. Extract architecture overview: system components, interactions, data flows
3. Extract API contracts: endpoints, HTTP methods, request/response schemas
4. Extract entity schemas: field names, types, constraints, relationships
5. Extract authentication/authorization model: roles, token mechanism, session handling
6. Extract forward engineering details: implementation patterns, technology stack, deployment model
7. Map each testable requirement to its corresponding API endpoint

### Phase 3: Test Generation

1. Detect the project's test framework (or use the specified one)
2. Generate a `BaseTest` class/fixture providing authentication helpers and base URL config
3. **Integration Tests** — For each API endpoint with mapped requirements:
   - Generate an integration test class
   - Generate high-quality test methods covering: happy path, validation errors, authorization failures, boundary values, and error handling
   - Each test method MUST be instrumented with:
     a. The requirement ID(s) it covers (e.g., `@Requirement("REQ-F-005")` or equivalent annotation)
     b. A clear explanation of what the test is performing or exercising (e.g., `@Description("Verifies that submitting a payment with an empty account ID returns a 400 validation error, exercising the input validation guard for required fields")`)
   - Follow patterns from `steering/spec-validation/test-generation-patterns.md`
4. **End-to-End Tests** — For cross-domain workflows and complete user journeys:
   - Generate E2E test classes covering full business workflows, multi-service interactions, and system-level scenarios
   - Multi-step sequences exercising the complete workflow from start to finish
   - Each E2E test method MUST be instrumented with:
     a. All requirement IDs that the workflow covers across its steps
     b. A clear explanation of the end-to-end scenario being exercised, including what business process it validates
   - E2E tests must verify data consistency across all affected resources
   - E2E tests must cover both success paths and failure/recovery scenarios
5. **Test Quality Enforcement**:
   - Tests must use realistic, schema-derived data (not trivial placeholders)
   - Assertions must verify semantic correctness, not just status codes
   - Tests must be meaningful enough to catch real regressions
   - Each test must be self-documenting through its instrumentation
6. Annotate every test with traceability metadata per `steering/spec-validation/traceability-standards.md`

### Phase 4: TestsToSpecCoverage Report

1. Generate the `TestsToSpecCoverage.md` report containing:
   - A summary of total requirements, testable requirements, and coverage percentages
   - Coverage breakdown by test type (end-to-end tests vs. integration tests)
   - A detailed traceability matrix for **integration tests**: mapping every requirement to its covering integration test(s)
   - A detailed traceability matrix for **end-to-end tests**: mapping every requirement to its covering E2E test(s)
   - Combined coverage view showing which requirements are covered by both test types, only one, or neither
   - List of uncovered requirements with explanation of why (ambiguous, depends on external system, etc.)
2. Write the `TestsToSpecCoverage.md` report to the output directory

### Phase 5: Execution & Violation Reporting (if source code exists)

1. Execute the generated tests against the source code using the project's test runner
2. Collect failures
3. Classify each failure per `steering/spec-validation/violation-classification.md`
4. Produce a structured violation report with:
   - Severity classification
   - Requirement being violated
   - Expected vs. actual behavior
   - Auto-repair hints for the coding agent
5. Write the violation report to the output directory

### Phase 6: Feedback to Coding Agent (automated loop)

If violations are found and the coding agent is active:
1. Feed the structured violation report back to the coding agent
2. The coding agent locates and fixes the violating code
3. Re-run the failing tests to verify the fix
4. Repeat until all tests pass or max iterations (3) reached

## Constraints

- **NEVER read source code** — the validation agent operates exclusively from specs and tech.md
- **NEVER modify tests to match implementation** — tests are the ground truth from specs
- **NEVER weaken assertions** — if a test fails, the code is wrong, not the test
- Tests must be independently runnable with no ordering dependencies
- All test data must be derivable from the tech.md schemas and constraints

## Output Format

After completion, report:

```
## Spec Validation Complete

**Requirements parsed:** {N} across {M} domains
**Testable requirements:** {N}
**Integration tests generated:** {N} (covering {N} requirements)
**End-to-end tests generated:** {N} (covering {N} requirements)
**Combined coverage:** {percentage}%
**TestsToSpecCoverage report:** {path to TestsToSpecCoverage.md}

### Execution Results (if applicable)
- **Integration tests — Passed:** {N} / **Failed:** {N}
- **End-to-end tests — Passed:** {N} / **Failed:** {N}
- **Violations report:** {path}
- **Auto-repair status:** {N} fixed / {N} remaining
```
