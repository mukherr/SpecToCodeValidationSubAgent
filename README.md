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
              ┌────────────┼────────────┐
              ▼            ▼            ▼
    ┌──────────────┐ ┌──────────┐ ┌────────────────────┐
    │ Integration  │ │  E2E     │ │ Spec Mutation       │
    │ Tests        │ │  Tests   │ │ (quality gate)      │
    └──────┬───────┘ └────┬─────┘ └──────────┬─────────┘
           │              │                   │
           └──────┬───────┘                   │
                  ▼                           ▼
       ┌────────────────────┐     ┌────────────────────┐
       │  Execute Against   │     │ TestsToSpec        │
       │  Implementation    │     │ Coverage.md        │
       └─────────┬──────────┘     └────────────────────┘
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

### Phase 3: Test Generation

Two categories of tests are generated:

| Type | Purpose | Naming Convention |
|------|---------|-------------------|
| Integration Tests | Per-endpoint coverage (happy path, validation errors, auth failures, boundaries) | `{Resource}ControllerIntegrationTest` |
| End-to-End Tests | Cross-domain workflows exercising complete user journeys | `EndToEnd{Workflow}FlowTest` |

Every test method is instrumented with:
1. The requirement ID(s) it covers
2. A description of what behavior it exercises

### Phase 4: Spec Mutation (Quality Gate)

Spec mutation validates whether generated tests are genuinely tied to the requirements they claim to cover. For E2E tests claiming 3+ REQ-IDs and any test with status-code-only assertions:

1. Mutate one requirement at a time (outcome inversion, boundary shift, status code substitution, side-effect removal, role change)
2. Regenerate the test from the mutated spec
3. Diff original vs. regenerated — score as KILLED (real coverage) or SURVIVED (vacuous)
4. Tests scoring SURVIVED get remediation hints and are re-generated with missing assertions

### Phase 5: Coverage Report

A `TestsToSpecCoverage.md` report maps every requirement to its covering tests, showing:
- Integration test coverage percentage
- End-to-end test coverage percentage
- Combined coverage matrix
- Spec mutation analysis (KILLED vs SURVIVED per requirement)
- Uncovered requirements with explanations

### Phase 6: Execution and Violation Reporting

Tests run against the implementation. Failures are classified by severity:

| Severity | Label | Definition |
|----------|-------|------------|
| P1 | Critical | Data loss, corruption, or security vulnerability |
| P2 | High | Incorrect functional behavior visible to users |
| P3 | Medium | Degraded experience, cosmetic logic errors |
| P4 | Low | Non-functional deviation |

Violation categories include: Data Integrity, Behavioral, Security, Boundary, State Management, Vacuous Coverage, and Infrastructure/Configuration.

### Phase 7: Auto-Repair Loop

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
        └── brownfield-discovery.md     # Tree-sitter extraction workflow

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
