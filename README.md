# Spec-to-Code Validation SubAgent

A Kiro subagent that independently validates whether generated code conforms to its specification. It generates executable integration and end-to-end tests solely from requirements and technical design documents — without ever reading source code — then executes those tests against the implementation to detect specification violations.

## How It Works

The subagent enforces a strict **information hiding** principle: it reads only specifications and design documents, never implementation code. This ensures tests represent the specification's intent rather than encoding implementation assumptions.

```
┌───────────────────────┐     ┌──────────────────────────┐
│  Requirements Files   │     │  Technical Design Doc    │
│  (REQ-F-001, etc.)   │     │  (DESIGN.md / tech.md)   │
└──────────┬────────────┘     └────────────┬─────────────┘
           │                               │
           └───────────┐   ┌───────────────┘
                       ▼   ▼
            ┌──────────────────────────┐
            │  Spec-Validator Agent    │
            │  (never reads src code)  │
            └──────────────┬───────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
    ┌──────────────┐ ┌──────────┐ ┌────────────────────┐
    │ Integration  │ │  E2E     │ │ TestsToSpec        │
    │ Tests        │ │  Tests   │ │ Coverage.md        │
    └──────┬───────┘ └────┬─────┘ └────────────────────┘
           │              │
           └──────┬───────┘
                  ▼
       ┌────────────────────┐
       │  Execute Against   │
       │  Implementation    │
       └─────────┬──────────┘
                 │
         ┌───────┴───────┐
         │               │
    All Pass         Failures
         │               │
         ▼               ▼
   ┌──────────┐  ┌──────────────────┐
   │  Spec    │  │ Violation Report │
   │  Compliant│  │ + Auto-Repair   │
   └──────────┘  │ Loop (max 3x)   │
                 └──────────────────┘
```

## Workflow Phases

### Phase 1: Requirements Parsing

The agent scans requirement files and extracts structured behavioral assertions. It supports:

- **EARS format** — "When [trigger], the system shall [response]"
- **User stories** — "As a [role], I want [capability] so that [benefit]"
- **Structured REQ-IDs** — `REQ-F-001`, `REQ-NF-002`, etc.

Each requirement is classified as TESTABLE, UI-ONLY, INFRASTRUCTURE, or AMBIGUOUS.

### Phase 2: Technical Design Document Analysis

The agent reads the technical design document to extract:

- API contracts (endpoints, HTTP methods, request/response schemas)
- Entity schemas (field names, types, constraints)
- Authentication/authorization model
- Seed data for test fixtures
- Error response formats and exact error messages

### Phase 3: Test Generation

Two categories of tests are generated:

| Type | Purpose | Naming Convention |
|------|---------|-------------------|
| Integration Tests | Per-endpoint coverage (happy path, validation errors, auth failures, boundaries) | `{Resource}ControllerIntegrationTest` |
| End-to-End Tests | Cross-domain workflows exercising complete user journeys | `EndToEnd{Workflow}FlowTest` |

Every test method is instrumented with:
1. The requirement ID(s) it covers
2. A description of what behavior it exercises

### Phase 4: Coverage Report

A `TestsToSpecCoverage.md` report maps every requirement to its covering tests, showing:
- Integration test coverage percentage
- End-to-end test coverage percentage
- Combined coverage matrix
- Uncovered requirements with explanations

### Phase 5: Execution and Violation Reporting

Tests run against the implementation. Failures are classified by severity:

| Severity | Label | Definition |
|----------|-------|------------|
| P1 | Critical | Data loss, corruption, or security vulnerability |
| P2 | High | Incorrect functional behavior visible to users |
| P3 | Medium | Degraded experience, cosmetic logic errors |
| P4 | Low | Non-functional deviation |

### Phase 6: Auto-Repair Loop

If violations are found, the structured violation report is fed back to the coding agent. The coding agent fixes the violating code, tests re-run, and the cycle repeats up to 3 times.

## Repository Structure

```
.kiro/
├── agents/
│   └── spec-validator.json          # Agent definition (inputs, outputs, system prompt)
├── hooks/
│   ├── spec-code-validation.kiro.hook  # Auto-triggers on src/main/**/*.java edits
│   ├── post-task-validation.md         # Fires after coding tasks complete
│   └── on-demand-validation.md         # User-triggered validation docs
├── skills/
│   └── spec-validation-skill.md        # Skill activation patterns and workflow
└── steering/
    └── spec-validation/
        ├── requirements-parsing.md     # How to parse requirements into assertions
        ├── test-generation-patterns.md # Test architecture and quality standards
        ├── traceability-standards.md   # Annotation format, coverage report structure
        └── violation-classification.md # Severity taxonomy and auto-repair hints
DESIGN.md                               # Example technical design document (CardDemo)
prompt.md                               # Example invocation prompt
```

## Trigger Mechanisms

### 1. Automatic (File Edit Hook)

The `.kiro.hook` triggers automatically when any Java source file in `src/main/java/` is edited. The agent runs the spec validation tests and reports violations inline.

### 2. Automatic (Post-Task)

After a coding agent completes a task that modified source code, the hook checks whether requirements and a tech doc exist, then invokes the subagent automatically.

### 3. On-Demand

Users explicitly invoke validation with options:

```
/spec-validate
/spec-validate --specs ./path/to/requirements --tech ./DESIGN.md
/spec-validate --framework junit5 --output ./src/test/
/spec-validate --no-exec          # Generate tests only, skip execution
/spec-validate --no-repair        # Skip the auto-repair loop
```

## Example Prompt

To trigger the spec-validator subagent, use the following prompt in Kiro (or adapt for your IDE agent):

```
Run the spec-validator agent against my requirements in requirements/ and design doc at DESIGN.md
```

For a more detailed invocation with explicit parameters:

```
Run the spec-validator agent with these inputs:
- requirementsPath: ./requirements/
- techDocPath: ./DESIGN.md
- testFramework: junit5
- outputDir: ./src/test/java/
- executeTests: true
- maxRepairIterations: 3

Generate integration and end-to-end tests from the specifications only (do not read source code), 
execute them against the implementation, classify any failures by severity, and produce:
1. The generated test files
2. A TestsToSpecCoverage.md report showing requirement-to-test traceability
3. A spec-validation-violations.md report if any tests fail
```

## Key Design Principles

1. **Spec is ground truth** — If a test fails, the implementation is wrong. Tests are never weakened to match observed behavior.

2. **Information hiding** — The validation agent never reads source code. It operates exclusively from requirements and the technical design document.

3. **Observable behavior only** — Tests exercise externally observable behavior through documented interfaces (APIs, CLI, events). Internal implementation details are never tested.

4. **Test independence** — Every test is independently runnable with no ordering dependencies.

5. **Meaningful assertions** — Tests verify semantic correctness (field values, relationships, side effects), not just HTTP status codes.

## Supported Test Frameworks

The agent auto-detects the framework from project files, or accepts explicit specification:

| Framework | Detection Signal |
|-----------|-----------------|
| JUnit 5 | `pom.xml` present |
| pytest | `requirements.txt` or `pyproject.toml` present |
| Jest | `package.json` present |
| Go test | `go.mod` present |
| xUnit | `.csproj` present |

## Output Files

| File | Description |
|------|-------------|
| `TestsToSpecCoverage.md` | Full traceability matrix: requirements to tests (both E2E and integration) |
| `spec-validation-violations.md` | Classified failures with severity, root cause, and repair hints |
| Generated test files | Executable tests in `src/test/` (or configured output directory) |
