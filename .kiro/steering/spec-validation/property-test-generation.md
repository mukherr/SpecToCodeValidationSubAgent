# Property-Test Generation for Ubiquitous Requirements — Steering Document

## Purpose

Ubiquitous EARS requirements ("The system shall [X]") declare invariants that must hold **always**, across all inputs and states. Example-based tests (fixed inputs, fixed assertions) are insufficient for these — they cover specific cases but cannot prove the invariant holds universally.

This document instructs the agent on when and how to generate **property-based tests** that exercise ubiquitous requirements with randomized, bounded inputs and verify the invariant holds across the entire input space.

## When to Generate Property Tests

Generate property-based tests when ALL of the following are true:

1. The requirement uses the **Ubiquitous** EARS pattern ("The system shall [X]") or is classified as an **invariant** (holds regardless of trigger/state)
2. The requirement constrains a **quantifiable** property (length, format, range, response time, data integrity, idempotency, monotonicity)
3. The tech.md provides sufficient schema information to generate valid random inputs
4. The target test framework supports property-based testing (or a property library can be added)

**Do NOT generate property tests for:**
- Event-driven requirements with specific triggers (use example-based integration tests)
- Requirements that test a single code path (property testing adds noise, not signal)
- Requirements where the input space is small and enumerable (exhaustive example tests are clearer)

## Property Test Categories

### Category 1: Format Invariants

**Requirement pattern:** "The system shall [format/constrain] [field] to [constraint]"

**Examples:**
- "The system shall truncate timestamps to 26 characters"
- "The system shall return ISO-8601 formatted dates"
- "The system shall normalize email addresses to lowercase"

**Property:** For ANY valid input, the output's format matches the constraint.

```
PROPERTY: format_invariant(endpoint, field, constraint)
  FOR ALL valid_input IN generate(schema):
    response = HTTP(endpoint, valid_input)
    ASSERT constraint(response.body[field]) == true
```

### Category 2: Boundary Invariants

**Requirement pattern:** "The system shall [reject/accept] [input] [outside/within] [boundary]"

**Examples:**
- "The system shall reject amounts less than or equal to zero"
- "The system shall accept account IDs between 1 and 11 characters"
- "The system shall limit page size to 100 records"

**Property:** The acceptance/rejection boundary is exactly where the spec says it is.

```
PROPERTY: boundary_invariant(endpoint, field, boundary, side)
  FOR ALL value IN generate_around_boundary(boundary, field_type):
    response = HTTP(endpoint, {field: value})
    IF side == ACCEPT:
      ASSERT response.status IN [200, 201]
    ELSE:
      ASSERT response.status IN [400, 422]
```

### Category 3: Idempotency Invariants

**Requirement pattern:** "The system shall [produce same result] [on repeated calls]"

**Examples:**
- "The system shall return identical results for repeated GET requests"
- "The system shall not duplicate records on retry"

**Property:** Calling the same operation N times produces the same observable effect as calling it once.

```
PROPERTY: idempotency(endpoint, method, input)
  FOR ALL valid_input IN generate(schema):
    response_1 = HTTP(method, endpoint, valid_input)
    response_2 = HTTP(method, endpoint, valid_input)
    ASSERT response_1.body == response_2.body
    ASSERT side_effects_count(response_1) == side_effects_count(response_2)
```

### Category 4: Data Integrity Invariants

**Requirement pattern:** "The system shall [preserve/maintain] [data relationship]"

**Examples:**
- "The system shall maintain referential integrity between accounts and transactions"
- "The system shall preserve total balance across transfers (source + destination = constant)"
- "The system shall never return soft-deleted records in list responses"

**Property:** The stated data relationship holds after any sequence of valid operations.

```
PROPERTY: data_integrity(operation_sequence, invariant_check)
  FOR ALL ops IN generate_operation_sequences(valid_operations, length=1..5):
    execute(ops)
    ASSERT invariant_check() == true
```

### Category 5: Monotonicity / Ordering Invariants

**Requirement pattern:** "The system shall [order/sort/sequence] [resource] by [criteria]"

**Examples:**
- "The system shall return transactions in reverse chronological order"
- "The system shall assign sequential IDs to new records"
- "The system shall never decrease a version number"

**Property:** The ordering constraint holds regardless of insertion order or data content.

```
PROPERTY: ordering_invariant(list_endpoint, order_field, direction)
  insert N random records with varying order_field values
  response = HTTP(GET, list_endpoint)
  ASSERT is_sorted(response.body[*].order_field, direction)
```

### Category 6: Security Invariants

**Requirement pattern:** "The system shall [never/always] [security constraint]"

**Examples:**
- "The system shall never expose password hashes in API responses"
- "The system shall always require authentication for protected endpoints"
- "The system shall never return data belonging to other users"

**Property:** The security constraint holds across all reachable states and input combinations.

```
PROPERTY: security_invariant(endpoints, forbidden_pattern)
  FOR ALL endpoint IN endpoints:
    FOR ALL valid_input IN generate(schema):
      response = HTTP(endpoint, valid_input)
      ASSERT forbidden_pattern NOT IN serialize(response)
```

## Generator Strategies

### Input Generators

Derive generators from the tech.md schema:

| Schema Type | Generator Strategy |
|---|---|
| `string` (no constraints) | Random alphanumeric, 1–256 chars |
| `string` (maxLength: N) | Random strings of length 0, 1, N-1, N, N+1 |
| `string` (pattern: regex) | Regex-guided generation + boundary violations |
| `string` (enum: [...]) | Uniform selection from enum values + one invalid |
| `integer` (min: A, max: B) | Uniform [A, B] + boundary values A-1, A, B, B+1 |
| `number` | IEEE-754 interesting values: 0, -0, MIN, MAX, NaN, ±Infinity, small fractions |
| `boolean` | Both values |
| `array` (maxItems: N) | Empty, single-element, N-1, N, N+1 elements |
| `object` | Combine field generators; also test with missing optional fields |

### Shrinking

When a property violation is found, shrink the failing input to the minimal reproducing case:
- Strings: binary-search on length, then simplify characters
- Numbers: binary-search toward zero or boundary
- Arrays: remove elements one at a time
- Objects: remove optional fields one at a time

Report the shrunk input in the violation report for easier debugging.

## Framework-Specific Templates

### Java (JUnit 5 + jqwik)

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class {Resource}PropertyTest extends BaseIntegrationTest {

    @Property(tries = 100)
    @Tag("property")
    @Label("REQ-F-XXX: {invariant description}")
    void {invariantName}(@ForAll @StringLength(min = 1, max = 50) String input) {
        // Requirements covered: REQ-F-XXX
        // Property: {formal statement of what must always hold}
        var response = restTemplate.postForEntity(
            baseUrl() + "/api/v1/resource",
            buildRequest(input),
            ResponseDto.class
        );
        assertThat(response.getBody().getField())
            .satisfies(value -> /* invariant assertion */);
    }
}
```

### Python (pytest + Hypothesis)

```python
from hypothesis import given, strategies as st, settings

@pytest.mark.property
class TestResourceProperties:

    @given(input_value=st.text(min_size=1, max_size=50))
    @settings(max_examples=100)
    @pytest.mark.requirement("REQ-F-XXX")
    def test_invariant_name(self, authenticated_client, input_value):
        """
        Requirements: REQ-F-XXX
        Property: {formal statement of what must always hold}
        """
        response = authenticated_client.post(
            "/api/v1/resource",
            json=build_request(input_value)
        )
        assert invariant_holds(response.json())
```

### TypeScript (Jest + fast-check)

```typescript
import fc from 'fast-check';

describe('Resource Properties', () => {
  it('REQ-F-XXX: {invariant description}', async () => {
    // Requirements covered: REQ-F-XXX
    // Property: {formal statement of what must always hold}
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 50 }),
        async (input) => {
          const response = await request(app)
            .post('/api/v1/resource')
            .send(buildRequest(input));
          expect(invariantHolds(response.body)).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });
});
```

### Go (testing + rapid)

```go
func TestResource_InvariantName(t *testing.T) {
    // Requirements covered: REQ-F-XXX
    // Property: {formal statement of what must always hold}
    rapid.Check(t, func(t *rapid.T) {
        input := rapid.String().Draw(t, "input")
        resp := httpPost(t, "/api/v1/resource", buildRequest(input))
        if !invariantHolds(resp.Body) {
            t.Fatalf("invariant violated for input: %q", input)
        }
    })
}
```

## Integration with Existing Test Suite

Property tests complement — not replace — example-based integration tests:

| Test Type | Covers | Strengths | Weaknesses |
|---|---|---|---|
| Example-based integration | Specific scenarios from EARS trigger/response | Readable, deterministic, fast | Misses edge cases outside author's imagination |
| Property-based | Entire input space for invariants | Discovers unknown edge cases, proves universality | Slower, harder to debug, requires good generators |

**Layering strategy:**
1. Generate example-based integration tests for ALL testable requirements (per test-generation-patterns.md)
2. Generate property tests ADDITIONALLY for ubiquitous requirements that declare invariants
3. Property tests run with `@Tag("property")` so they can be executed separately (they're slower)

## Trial Count Guidance

| Context | Trials | Rationale |
|---|---|---|
| CI / fast feedback | 50 | Catch obvious violations quickly |
| Full test suite | 100 | Good coverage without excessive runtime |
| Pre-release | 500 | Thorough boundary exploration |
| Investigating a known flaky area | 1000+ | Maximize chance of reproducing intermittent failure |

Default to 100 trials in generated tests. The developer can scale up via configuration.

## Reporting

Property test results integrate into the standard `TestsToSpecCoverage.md` report:

```markdown
## Property Test Coverage

| Requirement | Invariant Type | Property | Trials | Result | Shrunk Counterexample |
|-------------|---------------|----------|--------|--------|----------------------|
| REQ-F-003 | Format | Timestamps ≤ 26 chars | 100 | PASS | — |
| REQ-F-011 | Boundary | Amount > 0 | 100 | FAIL | amount = 0.0 |
| REQ-F-018 | Security | No password in response | 100 | PASS | — |

### Property Violations

| Requirement | Property | Counterexample (shrunk) | Severity |
|-------------|----------|------------------------|----------|
| REQ-F-011 | Amount must be > 0 | `{"amount": 0.0, "accountId": "A1"}` → 201 Created | P2 — accepts zero amount |
```

## Spec Mutation Interaction

Property tests are **resistant to spec mutation by design** — if a boundary invariant property test exists for "amount > 0" and the spec mutates to "amount >= 0", the property test generator changes its boundary to include 0, making the mutation KILLED.

However, property tests can still be vacuous if:
- The generator doesn't cover the mutated region (e.g., only generates positive integers, never tests the boundary)
- The property assertion is too broad (e.g., `assert status < 500` instead of `assert status == 400`)

Apply spec mutation to property tests using **Boundary Shift** mutations. If the shifted boundary doesn't change the generator's edge cases, the property test is vacuous for that boundary.

## Relationship to Other Steering Documents

- **requirements-parsing.md**: Identifies Ubiquitous EARS patterns that trigger property test generation
- **test-generation-patterns.md**: Property tests supplement the example-based tests defined there
- **traceability-standards.md**: Property tests use the same REQ-ID annotation format
- **spec-mutation.md**: Boundary Shift mutations validate property test generators
- **e2e-workflow-discovery.md**: Data Integrity properties (Category 4) may use workflow paths as operation sequences
