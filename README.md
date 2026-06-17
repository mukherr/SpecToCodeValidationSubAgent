# Spec-to-Code Validation SubAgent

A Kiro subagent that independently validates whether generated code conforms to its specification. It generates executable integration and end-to-end tests solely from requirements and technical design documents — without ever reading source code — then executes those tests against the implementation to detect specification violations.

## How It Works

The subagent enforces a strict **information hiding** principle: it reads only specifications and design documents, never implementation code. This ensures tests represent the specification's intent rather than encoding implementation assumptions.

It operates in two modes:

- **Greenfield** — A hand-written tech doc (DESIGN.md / tech.md) provides API contracts, schemas, and service interfaces. Tests are generated directly from this document.
- **Brownfield** — No tech doc exists. A bundled tree-sitter extractor performs deterministic AST analysis of the codebase to produce a `generated-tech.md`, which the test pipeline then consumes identically.

```
┌───────────────────────┐     ┌──────────────────────────┐
│  Requirements Files   │     │  Tech Doc (existing)     │
│  (REQ-F-001, etc.)   │     │  -OR-                    │
└──────────┬────────────┘     │  Tree-sitter extraction  │
           │                  │  → generated-tech.md     │
           │                  └────────────┬─────────────┘
           └───────────┐   ┌───────────────┘
                       ▼   ▼
            ┌──────────────────────────┐
            │  Spec-Validator Agent    │
            │  (never reads src code)  │
            └──────────────┬───────────┘
                           │
              ┌────────────┼─────────────────┐
              ▼            ▼                  ▼
   ┌────────────────┐  ┌──────────────┐  ┌────────────────┐
   │ Requirement    │  │ State Token  │  │ Ubiquitous Req │
   │ → Endpoint Map │  │ Extraction   │  │ Detection      │
   └───────┬────────┘  └──────┬───────┘  └───────┬────────┘
           │                  ▼                   │
           │         ┌────────────────┐           │
           │         │ Dependency     │           │
           │         │ Graph → Paths  │           │
           │         └───────┬────────┘           │
           ▼                 ▼                    ▼
    ┌──────────────┐ ┌──────────┐ ┌────────────────────┐
    │ Integration  │ │  E2E     │ │ Property Tests     │
    │ Tests        │ │  Tests   │ │ (randomized input) │
    └──────┬───────┘ └────┬─────┘ └──────────┬─────────┘
           │              │                   │
           └──────┬───────┴───────────────────┘
                  │
                  ▼
       ┌──────────────────────┐     ┌────────────────────┐
       │  Spec Mutation       │     │ TestsToSpec        │
       │  (quality gate)      │────▶│ Coverage.md        │
       └──────────┬───────────┘     └────────────────────┘
                  │
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

### Phase 0: Mode Detection (Greenfield vs Brownfield)

The agent checks for a tech doc at `techDocPath`:
- **Exists** → Greenfield mode, skip to Phase 1
- **Missing** → Brownfield mode: run tree-sitter API surface extraction to produce `generated-tech.md`

In brownfield mode, the extractor uses deterministic AST parsing (no LLM) to discover routes, DTOs, service interfaces, and entities from the codebase. After extraction, a **reconciliation report** maps each requirement to its matched endpoint — if >30% of testable requirements are unmapped, the agent halts and reports the gap.

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

### Phase 3: E2E Workflow Discovery

Rather than manually composing end-to-end tests, the agent automatically discovers workflow paths by building a **requirement dependency graph**:

1. **Extract state tokens** — For each requirement, identify postconditions (states it produces) and preconditions (states it requires). State tokens are normalized to `STATE:{entity}_{condition}` form.

2. **Build a directed graph** — An edge from REQ-A → REQ-B exists when REQ-A's postcondition satisfies REQ-B's precondition. Additional edges come from explicit sequencing references, shared-resource create→use patterns, and auth dependencies.

3. **Extract maximal paths** — DFS from source nodes (no incoming edges) to sink nodes (no outgoing edges). Paths are filtered to 3–8 requirements and ranked by coverage value with bonuses for cross-domain span and P1-severity requirements.

4. **Merge overlapping prefixes** — Paths sharing a common prefix of ≥2 requirements share a test fixture and branch into separate assertions.

5. **Handle cycles** — Detected via back-edge detection and converted into dedicated state-machine tests.

### Phase 4: Test Generation

Three categories of tests are generated:

| Type | Purpose | Naming Convention |
|------|---------|-------------------|
| Integration Tests | Per-endpoint coverage (happy path, validation errors, auth failures, boundaries) | `{Resource}ControllerIntegrationTest` |
| End-to-End Tests | Cross-domain workflows from discovered dependency paths | `EndToEnd{Workflow}FlowTest` |
| Property Tests | Invariant verification via randomized inputs (ubiquitous requirements only) | `{Resource}PropertyTest` |

Every test method is instrumented with:
1. The requirement ID(s) it covers
2. A description of what behavior it exercises

#### Property-Based Tests

For requirements using the **Ubiquitous EARS pattern** ("The system shall [X]") that declare invariants over a quantifiable property, property-based tests are generated in addition to example-based tests. These exercise the invariant across randomized, bounded inputs to prove universality.

Six property categories are supported:

| Category | Requirement Pattern | Example |
|----------|-------------------|---------|
| Format Invariants | "shall [format/constrain] [field] to [constraint]" | Timestamps ≤ 26 chars |
| Boundary Invariants | "shall [reject/accept] [outside/within] [boundary]" | Amount > 0 |
| Idempotency | "shall [produce same result] on repeated calls" | GET returns identical results |
| Data Integrity | "shall [preserve/maintain] [data relationship]" | Balance constant across transfers |
| Ordering | "shall [order/sort] [resource] by [criteria]" | Transactions in reverse chronological order |
| Security | "shall [never/always] [security constraint]" | Never expose password hashes |

Generators are derived from the tech.md schema, and failing inputs are shrunk to minimal reproducing cases. Default trial count is 100 per property (configurable up to 1000+ for known flaky areas).

### Phase 5: Spec Mutation (Quality Gate)

Spec mutation validates whether generated tests are genuinely tied to the requirements they claim to cover. For E2E tests claiming 3+ REQ-IDs and any test with status-code-only assertions:

1. Mutate one requirement at a time (outcome inversion, boundary shift, status code substitution, side-effect removal, role change)
2. Regenerate the test from the mutated spec
3. Diff original vs. regenerated — score as KILLED (real coverage) or SURVIVED (vacuous)
4. Tests scoring SURVIVED get remediation hints and are re-generated with missing assertions

### Phase 6: Coverage Report

A `TestsToSpecCoverage.md` report maps every requirement to its covering tests, showing:
- Integration test coverage percentage
- End-to-end test coverage percentage
- Property test coverage (invariant type, trial count, pass/fail, shrunk counterexamples)
- Combined coverage matrix
- Spec mutation analysis (KILLED vs SURVIVED per requirement)
- Workflow discovery summary (dependency graph stats, discovered paths, cross-domain workflows)
- Uncovered requirements with explanations

### Phase 7: Execution and Violation Reporting

Tests run against the implementation. Failures are classified by severity:

| Severity | Label | Definition |
|----------|-------|------------|
| P1 | Critical | Data loss, corruption, or security vulnerability |
| P2 | High | Incorrect functional behavior visible to users |
| P3 | Medium | Degraded experience, cosmetic logic errors |
| P4 | Low | Non-functional deviation |

Violation categories include: Data Integrity, Behavioral, Security, Boundary, State Management, Vacuous Coverage, and Infrastructure/Configuration.

### Phase 8: Auto-Repair Loop

If violations are found, the structured violation report is fed back to the coding agent. The coding agent fixes the violating code, tests re-run, and the cycle repeats up to 3 times.

## Repository Structure

```
.kiro/
├── agents/
│   └── spec-validator.json          # Agent definition (inputs, outputs, system prompt)
├── hooks/
│   ├── spec-code-validation.kiro.hook  # Auto-triggers on src/main/**/*.java edits
│   ├── post-task-validation.kiro.hook  # Fires after coding tasks complete
│   ├── on-demand-validation.kiro.hook  # User-triggered validation
│   ├── post-task-validation.md         # Post-task hook documentation
│   └── on-demand-validation.md         # On-demand hook documentation
├── skills/
│   └── spec-validation-skill.md        # Skill activation patterns and workflow
└── steering/
    └── spec-validation/
        ├── requirements-parsing.md     # How to parse requirements into assertions
        ├── test-generation-patterns.md # Test architecture and quality standards
        ├── traceability-standards.md   # Annotation format, coverage report structure
        ├── violation-classification.md # Severity taxonomy and auto-repair hints
        ├── spec-mutation.md            # Mutation testing for coverage verification
        ├── brownfield-discovery.md     # Tree-sitter extraction workflow
        ├── property-test-generation.md # PBT for ubiquitous EARS invariants
        └── e2e-workflow-discovery.md   # Automated E2E path discovery algorithm

tools/
└── api-surface-extractor/              # Bundled tree-sitter extraction tool
    ├── pyproject.toml                  # Python package config (requires Python 3.10+)
    ├── extractor/
    │   ├── __init__.py
    │   ├── cli.py                      # CLI: extract-api-surface <path> --output <file>
    │   ├── core.py                     # Data models (Endpoint, TypeDefinition, etc.)
    │   ├── scanner.py                  # File discovery and orchestration
    │   ├── formatter.py                # Markdown and YAML output formatters
    │   ├── java_extractor.py           # Spring Boot: @GetMapping, @RequestBody, etc.
    │   ├── python_extractor.py         # FastAPI/Flask/Django: decorators, Pydantic models
    │   ├── typescript_extractor.py     # Express/NestJS: router calls, @Controller
    │   └── go_extractor.py             # Gin/Chi/Echo: router.GET, struct tags

DESIGN.md                               # Example technical design document (CardDemo)
prompt.md                               # Example invocation prompt
```

## Trigger Mechanisms

### 1. Automatic (File Edit Hook)

The `.kiro.hook` triggers automatically when any Java source file in `src/main/java/` is edited. The agent runs the spec validation tests and reports violations inline.

### 2. Automatic (Post-Task)

After a coding agent completes a task that modified source code, the hook checks whether requirements and a tech doc exist, then invokes the subagent automatically. If no tech doc exists, it runs brownfield extraction first.

### 3. On-Demand

Users explicitly invoke validation with options:

```
/spec-validate
/spec-validate --specs ./path/to/requirements --tech ./DESIGN.md
/spec-validate --framework junit5 --output ./src/test/
/spec-validate --no-exec          # Generate tests only, skip execution
/spec-validate --no-repair        # Skip the auto-repair loop
```

## API Surface Extractor (Brownfield Tool)

The bundled tree-sitter extractor at `tools/api-surface-extractor/` provides deterministic, exhaustive API surface discovery without requiring an LLM.

### Installation

```bash
pip install -e tools/api-surface-extractor
```

### Usage

```bash
# Standard extraction (surface-pattern files only)
extract-api-surface /path/to/codebase --output /path/to/codebase/generated-tech.md

# Full scan (unconventional file names)
extract-api-surface /path/to/codebase --scan-all --output generated-tech.md

# YAML output for programmatic consumption
extract-api-surface /path/to/codebase --format yaml --output surface.yaml
```

### Supported Frameworks

| Language | Frameworks | Detection Signals |
|----------|-----------|-------------------|
| Java | Spring Boot | `@GetMapping`, `@PostMapping`, `@RequestBody`, `@Entity` |
| Python | FastAPI, Flask, Django REST | `@app.get()`, `@router.post()`, `BaseModel`, `Serializer` |
| TypeScript | Express, NestJS, Hono | `app.get()`, `@Controller`, `@Get()`, interfaces |
| Go | Gin, Chi, Echo, net/http | `r.GET()`, `r.Get()`, `http.HandleFunc`, struct tags |

### What It Extracts

- **Endpoints** — HTTP method, path, handler name, file location, parameters, request/response types, auth requirements
- **Type definitions** — DTOs, entities, request/response classes with field names, types, and constraints
- **Service interfaces** — Method signatures with parameters and return types

### Surface Pattern Filtering

By default, only files matching API-surface naming conventions are scanned (e.g., `*Controller.java`, `*routes.py`, `*.controller.ts`, `*handler*.go`). Use `--scan-all` to scan every source file.

## Example Invocation

To trigger the spec-validator subagent in Kiro:

```
Run the spec-validator agent against my requirements in requirements/ and design doc at DESIGN.md
```

For a detailed invocation with explicit parameters:

```
Run the spec-validator agent with these inputs:
- requirementsPath: ./requirements/
- codebasePath: ./src/
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

For brownfield codebases (no tech doc):

```
Run the spec-validator agent with these inputs:
- requirementsPath: ./requirements/
- codebasePath: ./my-legacy-app/
- testFramework: auto-detect
- executeTests: true

The codebase has no tech.md — use brownfield mode to extract the API surface first.
```

## Key Design Principles

1. **Spec is ground truth** — If a test fails, the implementation is wrong. Tests are never weakened to match observed behavior.

2. **Information hiding** — The validation agent never reads source code. It operates exclusively from requirements and the technical design document.

3. **Determinism for discovery, LLM for synthesis** — API surface extraction uses tree-sitter (exhaustive, deterministic). LLMs are only used to format and enrich the extracted data, never to discover endpoints.

4. **Observable behavior only** — Tests exercise externally observable behavior through documented interfaces (APIs, CLI, events). Internal implementation details are never tested.

5. **Test independence** — Every test is independently runnable with no ordering dependencies.

6. **Meaningful assertions** — Tests verify semantic correctness (field values, relationships, side effects), not just HTTP status codes. Spec mutation validates this.

7. **Algorithmic workflow composition** — E2E tests are discovered via graph algorithms over requirement dependencies, not hand-composed. This ensures complete coverage of cross-domain paths that a human might miss.

8. **Universality for invariants** — Ubiquitous requirements are tested with property-based testing (randomized bounded inputs), not just fixed examples. A passing property test provides stronger evidence than any finite set of examples.

## Supported Test Frameworks

The agent auto-detects the framework from project files, or accepts explicit specification:

| Framework | Detection Signal | Property Testing Library |
|-----------|-----------------|--------------------------|
| JUnit 5 | `pom.xml` present | jqwik |
| pytest | `requirements.txt` or `pyproject.toml` present | Hypothesis |
| Jest | `package.json` present | fast-check |
| Go test | `go.mod` present | rapid |
| xUnit | `.csproj` present | FsCheck |

## Output Files

| File | Description |
|------|-------------|
| `TestsToSpecCoverage.md` | Full traceability matrix: requirements → tests (E2E + integration), spec mutation verdicts |
| `spec-validation-violations.md` | Classified failures with severity, root cause, and repair hints |
| `generated-tech.md` | Extracted API surface (brownfield only) |
| `reconciliation-report.md` | REQ-ID → endpoint mapping status (brownfield only) |
| Generated test files | Executable tests in `src/test/` (or configured output directory) |

## Coverage Status Taxonomy

| Status | Meaning |
|--------|---------|
| COVERED | Test validates this requirement (confirmed by mutation kill) |
| VACUOUS | Test claims coverage but spec mutation survived — assertions don't exercise the requirement |
| UNCOVERED | Testable requirement but no test generated |
| UI-ONLY | Requirement is UI-specific; cannot test via API |
| INFRA | Infrastructure/deployment requirement; out of scope |
| AMBIGUOUS | Requirement unclear; test generated with restrictive interpretation |
| DEFERRED | Depends on external system not available in test env |
