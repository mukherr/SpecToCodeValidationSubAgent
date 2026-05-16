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
2. **Design document path** — file containing API contracts, schemas, and interface definitions
3. **Test framework** (optional) — auto-detected from project if not specified
4. **Output directory** (optional) — defaults to project's standard test location

## Workflow

### Phase 1: Requirements Parsing

1. Scan the requirements path for all requirement files
2. For each file, extract requirements using the parsing rules in `steering/spec-validation/requirements-parsing.md`
3. Classify each requirement as TESTABLE, UI-ONLY, INFRA, or AMBIGUOUS
4. Produce a structured list of testable behavioral assertions

### Phase 2: Design Document Analysis

1. Read the design document
2. Extract API contracts: endpoints, HTTP methods, request/response schemas
3. Extract entity schemas: field names, types, constraints, relationships
4. Extract authentication/authorization model: roles, token mechanism, session handling
5. Map each testable requirement to its corresponding API endpoint

### Phase 3: Test Generation

1. Detect the project's test framework (or use the specified one)
2. Generate a `BaseTest` class/fixture providing authentication helpers and base URL config
3. For each API endpoint with mapped requirements:
   - Generate an integration test class
   - One test method per testable requirement
   - Follow patterns from `steering/spec-validation/test-generation-patterns.md`
4. For cross-domain workflows identified in requirements:
   - Generate E2E test classes
   - Multi-step sequences exercising the full workflow
5. Annotate every test with traceability metadata per `steering/spec-validation/traceability-standards.md`

### Phase 4: Coverage Report

1. Produce a traceability matrix mapping every requirement to its test(s)
2. Calculate coverage percentage (covered / total testable requirements)
3. List uncovered requirements with explanation of why (ambiguous, depends on external system, etc.)
4. Write the coverage report to the output directory

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

- **NEVER read source code** — the validation agent operates exclusively from specs and design docs
- **NEVER modify tests to match implementation** — tests are the ground truth from specs
- **NEVER weaken assertions** — if a test fails, the code is wrong, not the test
- Tests must be independently runnable with no ordering dependencies
- All test data must be derivable from the design document's schemas and constraints

## Output Format

After completion, report:

```
## Spec Validation Complete

**Requirements parsed:** {N} across {M} domains
**Testable requirements:** {N}
**Tests generated:** {N} integration + {N} e2e
**Coverage:** {percentage}%

### Execution Results (if applicable)
- **Passed:** {N}
- **Failed:** {N} ({classification breakdown})
- **Violations report:** {path}
- **Auto-repair status:** {N} fixed / {N} remaining
```
