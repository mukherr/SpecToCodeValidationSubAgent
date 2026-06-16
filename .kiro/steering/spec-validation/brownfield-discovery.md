# Brownfield API Discovery — Steering Document

## Purpose

For brownfield applications where no DESIGN.md or tech.md exists, the validation agent cannot generate tests without knowing the API surface — endpoints, request/response types, service method signatures, and authentication mechanisms.

This document defines a **deterministic, tool-based discovery phase** that extracts the API surface from an existing codebase using tree-sitter AST parsing. The output is a generated tech.md that the test generation pipeline consumes identically to a hand-written design document.

## Core Principle: Determinism Over Intelligence

API surface extraction MUST be deterministic:
- **Tree-sitter AST parsing** — exhaustive by construction, scales to any codebase size
- **No LLM for discovery** — LLMs are probabilistic; extraction needs completeness guarantees
- **LLM for synthesis only** — format the deterministically-extracted data into coherent documentation

## When to Use

This discovery phase runs when:
1. No `DESIGN.md` or `tech.md` exists in the project
2. The existing design document is stale (out of sync with implementation)
3. User explicitly requests brownfield mode (`--brownfield` flag)
4. The spec-validator agent detects missing API contracts during test generation

## Extraction Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Tree-sitter Static Extraction (deterministic, exhaustive)   │
│     Source files → AST → Route registrations, DTOs, interfaces  │
│     Tool: tools/api-surface-extractor                           │
├─────────────────────────────────────────────────────────────────┤
│  2. Runtime Validation (optional, if app can be started)        │
│     Hit /openapi.json, /actuator/mappings, /swagger-ui          │
│     Diff against static extraction → find dynamic routes        │
├─────────────────────────────────────────────────────────────────┤
│  3. Requirement Reconciliation                                  │
│     For each REQ-ID: does the extracted surface contain an      │
│     endpoint that could exercise this requirement?              │
│     YES → proceed    NO → flag as UNMAPPED                      │
├─────────────────────────────────────────────────────────────────┤
│  4. LLM Synthesis (bounded scope)                               │
│     Format extracted data into tech.md structure                 │
│     Enrich with business semantics from requirements            │
│     ONLY for MAPPED requirements                                │
├─────────────────────────────────────────────────────────────────┤
│  5. Test Generation                                             │
│     Existing pipeline, unchanged — consumes generated tech.md   │
└─────────────────────────────────────────────────────────────────┘
```

## Agent Invocation Sequence

The tree-sitter extractor is bundled inside this repository at `tools/api-surface-extractor/`. The subagent MUST execute the following commands to bootstrap and run extraction against the target codebase.

### Prerequisites

- Python 3.10+ available in the environment
- `pip` available (standard with Python)

### Bootstrap & Extraction Commands

```bash
# 1. Install the extractor from THIS repository (idempotent — pip skips if already installed)
pip install -e {AGENT_SOURCE_ROOT}/tools/api-surface-extractor

# 2. Run extraction against the TARGET codebase
extract-api-surface {TARGET_CODEBASE_PATH} --output {TARGET_CODEBASE_PATH}/generated-tech.md

# 3. Verify output
test -f {TARGET_CODEBASE_PATH}/generated-tech.md && echo "OK" || echo "FAILED"
```

Where:
- `{AGENT_SOURCE_ROOT}` = root of the SpecToCodeValidationSubAgent repository (where `.kiro/agents/spec-validator.json` lives)
- `{TARGET_CODEBASE_PATH}` = the `codebasePath` input parameter passed to the agent

### Full Scan Mode (Unconventional File Names)

If the default surface-pattern filtering misses endpoints (extraction reports 0 endpoints but you know the codebase has routes):

```bash
extract-api-surface {TARGET_CODEBASE_PATH} --scan-all --output {TARGET_CODEBASE_PATH}/generated-tech.md
```

### YAML Output (For Programmatic Consumption)

```bash
extract-api-surface {TARGET_CODEBASE_PATH} --format yaml --output {TARGET_CODEBASE_PATH}/generated-tech.yaml
```

### Error Handling

| Condition | Agent Action |
|-----------|-------------|
| `pip install` fails | Report: "Python 3.10+ required. Install tree-sitter dependencies." |
| Extraction produces 0 endpoints | Retry with `--scan-all`. If still 0, HALT and report unsupported framework. |
| Extraction produces warnings | Log warnings but proceed — partial extraction is still useful. |
| `generated-tech.md` not written | HALT — extraction failed. Report the error from stderr. |

---

## Step 1: Tree-sitter Static Extraction

### Invocation

```bash
extract-api-surface /path/to/codebase --output /path/to/codebase/generated-tech.md
```

### What It Extracts

| Artifact | Source (Java/Spring) | Source (Python/FastAPI) | Source (TypeScript/NestJS) | Source (Go/Gin) |
|----------|---------------------|------------------------|---------------------------|-----------------|
| Route registrations | `@GetMapping`, `@PostMapping` | `@app.get()`, `@router.post()` | `@Get()`, `@Post()` | `r.GET()`, `r.POST()` |
| Base paths | `@RequestMapping` on class | Blueprint prefix | `@Controller()` path | Router group |
| Request body types | `@RequestBody` param type | Type-annotated param | `@Body()` param type | Binding struct |
| Path parameters | `@PathVariable` | Path params in route | `@Param()` | `:param` in path |
| Query parameters | `@RequestParam` | `Query()` type hint | `@Query()` | `c.Query()` binding |
| Response types | Return type of handler | Return annotation | Return type | N/A (inferred) |
| Auth requirements | `@PreAuthorize`, `@Secured` | `@login_required` | `@UseGuards()` | Middleware chain |
| DTO/Schema types | Classes with field annotations | `BaseModel` subclasses | Interface/class definitions | Struct definitions |
| Service interfaces | `interface XService { }` | Classes ending in `Service` | `@Injectable()` classes | Interface types |
| Entity/Model types | `@Entity` classes | SQLAlchemy/Django models | TypeORM entities | GORM models |

### Completeness Guarantee

Tree-sitter parses every file that matches the surface patterns. It finds every node matching the query grammar — this is exhaustive by construction, equivalent to `grep` but with structural awareness.

**What it covers**: Any route, type, or interface defined through standard framework patterns (annotations, decorators, function calls).

**What it cannot cover** (flagged as warnings):
- Dynamically registered routes (e.g., routes built from database config at runtime)
- Reflection-based route binding
- Code-generated endpoints (e.g., from protobuf/gRPC service definitions)
- Middleware-only endpoints with no handler function

These gaps are flagged in the extraction output and addressed by Step 2 (runtime validation).

### Surface Pattern Filtering

By default, the extractor only scans files matching known API-surface patterns:

- `*Controller.java`, `*Resource.java`, `*Request.java`, `*Response.java`, `*Service.java`
- `*views.py`, `*routes.py`, `*schemas.py`, `*models.py`, `*service.py`
- `*.controller.ts`, `*.routes.ts`, `*.dto.ts`, `*.service.ts`
- `*handler*.go`, `*router*.go`, `*model*.go`, `*service*.go`

Use `--scan-all` to scan every source file (slower but catches unconventionally-named files).

## Step 2: Runtime Validation (Optional)

If the application can be started in a test environment:

1. Start the application
2. Probe self-describing endpoints:
   - Spring Boot: `GET /actuator/mappings`
   - FastAPI: `GET /openapi.json`
   - Express (swagger): `GET /api-docs`
   - Any framework with OpenAPI: `GET /openapi.json` or `GET /swagger.json`
3. Diff the runtime-discovered routes against the static extraction
4. Any routes found at runtime but not in static extraction → dynamic routes → flag for manual annotation

## Step 3: Requirement Reconciliation

After extraction, verify that every testable requirement can be exercised:

```
For each REQ-ID with classification=TESTABLE:
  1. Extract the action verb and resource from the requirement
  2. Find matching endpoint(s) in the extraction result:
     - Match HTTP method to action (create→POST, read→GET, update→PUT, delete→DELETE)
     - Match path segment to resource name
  3. Score the match:
     - MAPPED: Endpoint found that can exercise this requirement
     - PARTIAL: Endpoint exists but missing parameter/type information
     - UNMAPPED: No endpoint found — requires human input or deeper discovery
```

### Reconciliation Report

```markdown
## Requirement-to-API Reconciliation

| Requirement | Action | Matched Endpoint | Status |
|-------------|--------|-----------------|--------|
| REQ-F-005 | Validate input | POST /api/v1/payments | MAPPED |
| REQ-F-008 | Create transaction | POST /api/v1/transactions | MAPPED |
| REQ-F-012 | Check permissions | - | UNMAPPED |

### Unmapped Requirements (Action Required)

| Requirement | Description | Possible Reason |
|-------------|-------------|-----------------|
| REQ-F-012 | Admin-only access | Authorization handled by middleware — no dedicated endpoint |
```

## Step 4: LLM Synthesis

The LLM receives ONLY the structured extraction output and produces a formatted tech.md. It does NOT discover — it organizes.

LLM synthesis responsibilities:
- Group endpoints by domain (authentication, payments, accounts, etc.)
- Infer response schemas from return types and field patterns
- Cross-reference request body types with extracted DTOs
- Add semantic labels from requirement descriptions (e.g., "this endpoint handles bill payment confirmation")
- Flag inconsistencies (endpoint references a type that wasn't found)

LLM synthesis constraints:
- MUST NOT invent endpoints not found in extraction
- MUST NOT invent fields not found in type definitions
- MUST flag any inference with `[INFERRED]` annotation
- MUST preserve file paths and line numbers from extraction

## Output File Locations

All extraction outputs are written to the project root, alongside existing reports:

```
{project-root}/
├── DESIGN.md                        # Hand-written (greenfield) — OR:
├── generated-tech.md                # Extracted API surface (brownfield, consumed by test generation)
├── reconciliation-report.md         # REQ-ID → endpoint mapping status (MAPPED/PARTIAL/UNMAPPED)
├── TestsToSpecCoverage.md           # Tests-to-specification coverage report
├── spec-validation-violations.md    # Failure report
└── spec-validation-summary.md       # Executive summary
```

| File | Producer | Consumer |
|------|----------|----------|
| `generated-tech.md` | `extract-api-surface` tool (Step 1) + LLM synthesis (Step 4) | Test generation pipeline |
| `reconciliation-report.md` | Requirement reconciliation (Step 3) | Human review, spec-validator agent |

The `extract-api-surface` CLI defaults to writing `generated-tech.md` in the working directory. Override with `--output /path/to/file.md`.

## Step 5: Output Format

The generated tech.md follows the same structure as a hand-written design document (see DESIGN.md sections 4, 5):

```markdown
# {Project} — API Surface (Extracted)

## API Endpoints

### Authentication
#### POST `/api/v1/auth/login`
**Handler**: `AuthController.login`
**File**: `src/main/java/.../AuthController.java:45`
**Request Body**: `LoginRequest`
**Response**: `LoginResponse`

## Type Definitions

### Request/Response Types
#### `LoginRequest`
| Field | Type | Required |
|-------|------|----------|
| userId | String | yes |
| password | String | yes |

## Service Interfaces

### AuthService
- `authenticate(userId: String, password: String) → LoginResponse`
- `logout(sessionId: String) → void`
```

## Integration with spec-validator Agent

The spec-validator agent's workflow becomes:

```
IF tech.md or DESIGN.md exists:
    Use existing document (greenfield path — unchanged)
ELSE:
    Run tree-sitter extraction → generated-tech.md
    Run requirement reconciliation
    IF unmapped requirements > threshold (e.g., 30%):
        HALT — report to user that too many requirements have no API mapping
    ELSE:
        Use generated-tech.md for test generation
        Mark unmapped requirements as DEFERRED in coverage report
```

## Limitations and Mitigations

| Limitation | Impact | Mitigation |
|-----------|--------|------------|
| Dynamic routes not discovered | Missing endpoints in generated tech.md | Runtime validation (Step 2) catches these |
| No response body schema for languages without return types (Go) | Test assertions limited to status codes | Use struct tags and common patterns to infer response shape |
| Middleware-based auth not always detectable | Auth requirements missing from endpoints | Scan middleware registration files; flag endpoints without detected auth |
| Multi-module projects | May miss cross-module routes | Pass `--scan-all` or specify multiple roots |
| Code-generated endpoints (gRPC, protobuf) | Not in source files | Extract from `.proto` files separately (future enhancement) |

## Relationship to Other Steering Documents

- **requirements-parsing.md**: Provides the structured requirements that reconciliation maps against
- **test-generation-patterns.md**: Consumes the generated tech.md identically to a hand-written document
- **traceability-standards.md**: UNMAPPED requirements get status DEFERRED in coverage reports
- **spec-mutation.md**: Operates on generated tests regardless of whether tech.md was hand-written or extracted
