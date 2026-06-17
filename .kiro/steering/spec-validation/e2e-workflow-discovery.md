# E2E Workflow Discovery — Steering Document

## Purpose

This document defines the algorithm for automatically discovering which EARS requirements chain together into end-to-end test workflows. Rather than relying on human judgment to compose E2E tests, the agent constructs a **requirement dependency graph** and extracts maximal workflow paths from it.

## Core Insight

Two EARS requirements form a chain when one requirement's **postcondition** is another requirement's **precondition**. State-driven requirements ("While [S]") are particularly chain-friendly because they explicitly declare the state they require — and that state must have been established by a prior requirement.

## Definitions

- **Requirement Node**: A single parsed EARS requirement with its structured assertion (reqId, precondition, action, expectedOutcome, endpoint)
- **State Edge**: A directed edge from REQ-A to REQ-B where REQ-A's postcondition satisfies REQ-B's precondition
- **Workflow Path**: A maximal chain of requirements connected by state edges, representing a complete user journey
- **Domain**: A logical grouping of requirements (e.g., Authentication, Payments, Accounts) derived from the requirements directory structure or explicit tags

## The Dependency Graph Algorithm

### Phase 1: Extract State Tokens

For each parsed requirement, extract **state tokens** — normalized representations of the states it produces and consumes.

**Producing states (postconditions):**

| EARS Pattern | State Token Extraction |
|---|---|
| Event-driven: "When [T], the system shall [R]" | R implies a new state exists (e.g., "shall create account" → `STATE:account_exists`) |
| Ubiquitous: "The system shall [X]" | X is always true — produces no new state (invariant) |
| Unwanted: "If [C], the system shall [H]" | H may produce an error state (e.g., "shall lock account" → `STATE:account_locked`) |

**Consuming states (preconditions):**

| EARS Pattern | State Token Extraction |
|---|---|
| State-driven: "While [S], the system shall [B]" | S is a required precondition (`REQUIRES:S`) |
| Event-driven: "When [T], the system shall [R]" | T may require prior state (e.g., "When user submits payment" → `REQUIRES:user_authenticated`, `REQUIRES:account_exists`) |

**Extraction heuristic — keyword normalization:**

```
Input precondition text → normalized state token:
  "authenticated user"          → STATE:user_authenticated
  "logged in"                   → STATE:user_authenticated
  "valid session"               → STATE:user_authenticated
  "account exists"              → STATE:account_exists
  "account is active"           → STATE:account_active
  "account locked"              → STATE:account_locked
  "payment created"             → STATE:payment_exists
  "transaction recorded"        → STATE:transaction_exists
  "balance updated"             → STATE:balance_updated
```

The agent MUST derive state tokens from the actual requirement text, not from a fixed vocabulary. The examples above illustrate the normalization pattern — reduce clauses to `STATE:{entity}_{condition}` form.

### Phase 2: Build the Directed Graph

```
For each requirement R_i:
  produces_i = set of state tokens R_i's postcondition establishes
  requires_i = set of state tokens R_i's precondition demands

For each pair (R_a, R_b) where a ≠ b:
  if produces_a ∩ requires_b ≠ ∅:
    add edge R_a → R_b with label = produces_a ∩ requires_b
```

**Additional edge sources:**
- **Explicit sequencing**: If a requirement references another by ID ("after REQ-F-003 completes"), add a direct edge
- **Shared resource**: If two requirements operate on the same resource (same endpoint, same entity) and one creates while the other reads/updates/deletes, infer a create→use edge
- **Auth dependency**: Any requirement with a role precondition has an implicit edge from the authentication requirement that establishes that role's session

### Phase 3: Extract Workflow Paths

A workflow path is a **maximal directed path** through the graph — it cannot be extended in either direction without breaking the state dependency chain.

**Algorithm:**

```
1. Identify SOURCE nodes: requirements with no incoming state edges
   (typically: authentication, resource creation, system initialization)

2. Identify SINK nodes: requirements with no outgoing state edges
   (typically: final assertions, cleanup operations, terminal states)

3. For each SOURCE node, perform DFS/BFS to enumerate all paths to SINK nodes

4. Filter paths:
   - Minimum length: 3 requirements (shorter paths are integration tests, not E2E)
   - Maximum length: 8 requirements (longer paths should be split into sub-workflows)
   - No duplicate requirements within a single path

5. Rank paths by coverage value:
   score(path) = |unique_req_ids| × domain_span_bonus × criticality_weight
   where:
     domain_span_bonus = 1.5 if path crosses 2+ domains, 1.0 otherwise
     criticality_weight = 2.0 if path includes a P1-severity requirement, 1.0 otherwise
```

### Phase 4: Merge Overlapping Paths

When multiple paths share a common prefix (e.g., both start with login → create account):

```
If path_A[0:k] == path_B[0:k] and k ≥ 2:
  Generate a shared setup fixture for the common prefix
  Branch into separate test methods at the divergence point
```

This avoids redundant test setup while maintaining distinct assertions for each workflow variant.

### Phase 5: Generate E2E Test Skeleton

For each discovered workflow path `[R_1, R_2, ..., R_n]`:

```
TestClass: EndToEnd{WorkflowName}FlowTest
  where WorkflowName = derived from the dominant domain + primary action

TestMethod: test{WorkflowName}_{Scenario}

Steps:
  1. SETUP: Authenticate with the role required by R_1
  2. For each R_i in path:
     a. ACT: Execute R_i's action (HTTP request per tech.md contract)
     b. ASSERT_INTERMEDIATE: Verify R_i's postcondition holds
     c. CARRY_FORWARD: Extract state needed by R_{i+1} from R_i's response
  3. ASSERT_FINAL: Verify terminal state consistency across all affected resources
  4. CROSS_VALIDATE: For each resource touched by the workflow, verify via GET that
     its current state is consistent with the full chain of operations
```

## Workflow Naming Convention

Derive the workflow name from the path's characteristics:

```
Pattern: {PrimaryAction}{Resource}Flow
  - PrimaryAction = the dominant verb across the path (Create, Update, Process, Migrate)
  - Resource = the primary entity being acted upon

Examples:
  [login → create_account → add_payment → process_payment → verify_balance]
  → EndToEndProcessPaymentFlowTest

  [login → create_user → assign_role → access_protected_resource]
  → EndToEndRoleAssignmentFlowTest

  [login → create_order → update_order → cancel_order → verify_refund]
  → EndToEndOrderCancellationFlowTest
```

## Handling Cycles

If the graph contains cycles (e.g., "locked account → unlock → use → lock again"):

1. Detect cycles using Tarjan's algorithm or DFS back-edge detection
2. Break cycles by treating the cycle as a **stateful scenario** rather than a linear path
3. Generate a dedicated cycle test that exercises the full state machine:

```
TestMethod: test{Resource}StateMachine_{CycleDescription}
  Steps: establish initial state → transition through all cycle states → return to initial state
  Assert: each transition produces the correct intermediate state
```

## Cross-Domain Workflow Discovery

Workflows that span multiple domains (e.g., Auth → Account → Payment → Transaction) are the highest-value E2E tests because they exercise integration boundaries.

**Detection heuristic:**
```
For each workflow path P:
  domains_touched = { domain(R_i) for R_i in P }
  if |domains_touched| ≥ 2:
    mark P as CROSS_DOMAIN
    priority += 1.5 × |domains_touched|
```

Cross-domain workflows MUST include cross-validation assertions — after the workflow completes, verify consistency across all affected domains by querying each domain's read endpoint.

## Reporting

Append a `## Workflow Discovery` section to `TestsToSpecCoverage.md`:

```markdown
## Workflow Discovery

### Discovered Workflows

| Workflow | Path Length | Domains | Requirements Covered | Priority Score |
|----------|------------|---------|---------------------|----------------|
| ProcessPaymentFlow | 5 | Auth, Account, Payment | REQ-F-001, REQ-F-005, REQ-F-007, REQ-F-008, REQ-F-010 | 12.5 |
| RoleAssignmentFlow | 4 | Auth, Admin | REQ-F-001, REQ-F-020, REQ-F-021, REQ-F-022 | 8.0 |

### Dependency Graph Summary
- Total requirements: {N}
- Requirements with state edges: {N}
- Source nodes (entry points): {list}
- Sink nodes (terminal states): {list}
- Cycles detected: {N}
- Cross-domain workflows: {N}

### Uncovered by E2E (isolated requirements)
| Requirement | Reason |
|-------------|--------|
| REQ-F-015 | No incoming or outgoing state edges — purely stateless operation |
| REQ-NF-003 | Non-functional; excluded from workflow discovery |
```

## Relationship to Other Steering Documents

- **requirements-parsing.md**: Provides the structured assertions that become graph nodes
- **test-generation-patterns.md**: Defines the E2E test skeleton that workflow paths populate
- **traceability-standards.md**: Multi-requirement annotation format applies to discovered workflows
- **spec-mutation.md**: Discovered workflows are prime candidates for side-effect mutation (they claim many REQ-IDs)
