# Test Generation Patterns — Steering Document

## Purpose

This document instructs the validation agent on how to generate high-quality, executable tests from parsed requirements. Tests MUST be generated solely from the specification and technical design document (tech.md) — never from source code.

## Core Principle: Information Hiding

The validation agent:
- **HAS ACCESS TO**: Requirements files, technical design documents — tech.md (API contracts, schemas, response formats, architecture, forward engineering details)
- **MUST NEVER ACCESS**: Source code, implementation files, internal class structures, database schemas beyond what the technical design document specifies

Tests assert **observable external behavior** only. If a behavior cannot be observed through the API or documented interface, it cannot be tested by this agent.

## Test Quality Standards

Every generated test MUST meet these quality criteria:

1. **Meaningful assertions**: Tests must verify business-relevant behavior, not just trivial conditions
2. **Realistic data**: Test data must be derived from the tech.md schemas with realistic values, not placeholder strings like "test123"
3. **Comprehensive coverage**: Each endpoint must have tests for happy path, error paths, boundaries, and security
4. **Self-documenting**: Each test must include instrumentation explaining what it exercises and which requirements it covers
5. **Independence**: Each test must run in isolation without depending on other test state
6. **Semantic verification**: Assert on response semantics (correct data, relationships, side effects), not just HTTP status codes

## Test Architecture

### Integration Tests (Per-Endpoint)

One test class per API endpoint/resource. Multiple test methods per requirement to cover different scenarios (happy path, error cases, boundaries).

```
TestClass naming: {Resource}Controller{IntegrationTest | ApiTest}
TestMethod naming: test{Behavior}_{Condition}
```

**Required instrumentation per test method:**
- Requirement ID(s) covered by this test
- Description explaining what the test is performing or exercising

Structure per test:
1. **Instrument** — Annotate with requirement IDs and description of what is being tested
2. **Arrange** — Set up preconditions (authentication, seed data via API calls)
3. **Act** — Make the HTTP request matching the requirement's trigger
4. **Assert** — Verify the response matches the requirement's expected outcome with meaningful semantic assertions

**Quality expectations for integration tests:**
- Each endpoint MUST have tests for: happy path, validation errors (invalid input), authorization failures (wrong role), boundary values, and error handling
- Assertions must verify response body content semantically (field values, relationships), not just status codes
- Test data must be realistic and derived from tech.md schema definitions
- Error scenarios must verify both the status code AND the error message content

### End-to-End Tests (Cross-Domain Workflows)

Multi-step tests that exercise a complete user workflow spanning multiple endpoints and domains.

```
TestClass naming: EndToEnd{Workflow}FlowTest
TestMethod naming: test{WorkflowName}_{Scenario}
```

**Required instrumentation per test method:**
- All requirement IDs covered across the workflow steps
- Description explaining the complete business scenario being exercised

Structure per test:
1. **Instrument** — Annotate with all requirement IDs covered by this workflow and explain the business scenario
2. **Setup** — Authenticate, establish initial state
3. **Steps** — Sequential API calls representing the full user journey
4. **Verify** — Assert final state is consistent across all affected resources
5. **Cross-validate** — Verify side effects on related resources are consistent

**Quality expectations for E2E tests:**
- Must cover complete user journeys from start to finish
- Must verify cross-resource data consistency after multi-step operations
- Must cover both success workflows and failure/recovery scenarios
- Must test workflows that span multiple domains or services
- Must verify that intermediate states are correct throughout the workflow
- Must test concurrency scenarios where applicable

## Language-Agnostic Test Templates

### HTTP API Tests

For any REST/HTTP API, regardless of language:

```
TEMPLATE: Happy Path
  GIVEN: authenticated user with required role
  AND: valid input data matching schema from tech.md
  WHEN: {HTTP_METHOD} {ENDPOINT} with {REQUEST_BODY}
  THEN: status code is {EXPECTED_STATUS}
  AND: response body matches {EXPECTED_SCHEMA}
  AND: {DOMAIN_SPECIFIC_ASSERTIONS}

TEMPLATE: Validation Error
  GIVEN: authenticated user
  AND: invalid input (violates constraint from requirement)
  WHEN: {HTTP_METHOD} {ENDPOINT} with {INVALID_BODY}
  THEN: status code is 400
  AND: response contains error message matching requirement text

TEMPLATE: Authorization Check
  GIVEN: user WITHOUT required role
  WHEN: {HTTP_METHOD} {ENDPOINT}
  THEN: status code is 403

TEMPLATE: Not Found
  GIVEN: authenticated user
  AND: resource identifier that does not exist
  WHEN: {HTTP_METHOD} {ENDPOINT}/{NON_EXISTENT_ID}
  THEN: status code is 404
  AND: response contains descriptive error message

TEMPLATE: Boundary Test
  GIVEN: authenticated user
  AND: input at boundary of constraint (max length, min value, etc.)
  WHEN: {HTTP_METHOD} {ENDPOINT} with {BOUNDARY_INPUT}
  THEN: behavior matches requirement for that boundary
```

## Test Data Strategy

### Derive Test Data From Technical Design Document Only

- Use exact field names, types, and constraints from the tech.md schema definitions
- Use realistic values that represent actual business data (not "test123" placeholders)
- Use boundary values derived from constraints (max length strings, min/max numeric values)
- For required fields: test with empty/null/missing values
- For optional fields: test with present and absent values
- For enums: test with valid values and invalid values
- For relationships: test with valid references, invalid references, and null references

### Authentication Setup

Read the tech.md for:
- Authentication endpoint and request format
- Session/token mechanism (cookie, bearer token, etc.)
- Role definitions and what roles can access what endpoints

Generate a `BaseTest` class/fixture that provides:
- `loginAs(role)` → returns authenticated session/headers
- `baseUrl()` → configurable base URL for the API under test

## Framework-Specific Generation Rules

### Java (JUnit 5 + Spring Boot Test)

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class {Resource}ControllerIntegrationTest extends BaseIntegrationTest {
    @Test
    @DisplayName("REQ-F-XXX: {requirement description}")
    @Tag("integration")
    void test{Behavior}() {
        // Requirements covered: REQ-F-XXX
        // Test exercises: {clear explanation of what this test is performing,
        //   what behavior it validates, and what condition it exercises}
        ...
    }
}

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class EndToEnd{Workflow}FlowTest extends BaseIntegrationTest {
    @Test
    @DisplayName("E2E: {workflow description} — REQ-F-XXX, REQ-F-YYY, REQ-F-ZZZ")
    @Tag("e2e")
    void test{Workflow}_{Scenario}() {
        // Requirements covered: REQ-F-XXX, REQ-F-YYY, REQ-F-ZZZ
        // Test exercises: {clear explanation of the complete business workflow
        //   being exercised, including what user journey it represents and
        //   what cross-domain interactions it validates}
        ...
    }
}
```

### Python (pytest + httpx)

```python
@pytest.mark.integration
class TestResourceApi:
    @pytest.mark.requirement("REQ-F-XXX")
    @pytest.mark.description("Verifies that {clear explanation of what this test exercises}")
    def test_behavior(self, authenticated_client):
        """
        Requirements: REQ-F-XXX
        Exercises: {what this test is performing — the specific behavior,
        condition, or scenario being validated}
        """
        ...

@pytest.mark.e2e
class TestEndToEnd{Workflow}Flow:
    @pytest.mark.requirement("REQ-F-XXX", "REQ-F-YYY", "REQ-F-ZZZ")
    @pytest.mark.description("End-to-end test for {workflow}: {explanation}")
    def test_{workflow}_{scenario}(self, authenticated_client):
        """
        Requirements: REQ-F-XXX, REQ-F-YYY, REQ-F-ZZZ
        Exercises: {complete explanation of the business workflow being tested,
        what user journey it represents, and what cross-domain behavior it validates}
        """
        ...
```

### TypeScript (Jest + supertest)

```typescript
describe('Resource API - Integration Tests', () => {
  it('REQ-F-XXX: should {behavior} — exercises {what is being tested}', async () => {
    // Requirements covered: REQ-F-XXX
    // Exercises: {clear explanation of what this test is performing
    //   and what behavior/condition it validates}
    ...
  });
});

describe('E2E: {Workflow} Flow', () => {
  it('REQ-F-XXX, REQ-F-YYY: should {complete workflow} — exercises {scenario}', async () => {
    // Requirements covered: REQ-F-XXX, REQ-F-YYY
    // Exercises: {clear explanation of the end-to-end business workflow,
    //   what user journey it represents, and cross-domain interactions tested}
    ...
  });
});
```

### Go (testing + net/http/httptest)

```go
func TestResource_Behavior(t *testing.T) {
    // Requirements covered: REQ-F-XXX
    // Exercises: {clear explanation of what this test is performing
    //   and what behavior/condition it validates}
    ...
}

func TestEndToEnd_{Workflow}_{Scenario}(t *testing.T) {
    // Requirements covered: REQ-F-XXX, REQ-F-YYY, REQ-F-ZZZ
    // Exercises: {clear explanation of the complete business workflow,
    //   what user journey it represents, and cross-domain interactions tested}
    ...
}
```

## Test Independence

Each test MUST:
- Be independently runnable (no ordering dependencies)
- Set up its own preconditions (don't rely on prior test state)
- Clean up or use isolated data (avoid shared mutable state)

## Property-Based Tests (Ubiquitous Requirements)

For requirements using the Ubiquitous EARS pattern ("The system shall [X]") that declare invariants over a quantifiable property, generate property-based tests in addition to example-based integration tests. Property tests exercise the invariant across randomized inputs to prove universality rather than specific-case coverage.

See `property-test-generation.md` for the full taxonomy of property categories (format, boundary, idempotency, data integrity, ordering, security), generator strategies, framework templates, and trial count guidance.

## E2E Workflow Composition

End-to-end tests are not manually composed — they are derived from the requirement dependency graph. The agent builds a directed graph where edges connect requirements whose postconditions satisfy other requirements' preconditions, then extracts maximal workflow paths.

See `e2e-workflow-discovery.md` for the graph construction algorithm, path extraction heuristics, cross-domain prioritization, cycle handling, and workflow naming conventions.

## What NOT to Test

- Internal implementation details (private methods, internal data structures)
- Database schema directly (test via API behavior)
- Logging output (non-functional, not observable via API)
- Performance characteristics (unless quantitative requirement exists)
- UI rendering (outside scope of API-level validation)
