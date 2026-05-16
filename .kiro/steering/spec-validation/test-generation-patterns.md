# Test Generation Patterns — Steering Document

## Purpose

This document instructs the validation agent on how to generate executable tests from parsed requirements. Tests MUST be generated solely from the specification and design document — never from source code.

## Core Principle: Information Hiding

The validation agent:
- **HAS ACCESS TO**: Requirements files, design documents (API contracts, schemas, response formats)
- **MUST NEVER ACCESS**: Source code, implementation files, internal class structures, database schemas beyond what the design document specifies

Tests assert **observable external behavior** only. If a behavior cannot be observed through the API or documented interface, it cannot be tested by this agent.

## Test Architecture

### Integration Tests (Per-Endpoint)

One test class per API endpoint/resource. Each test method validates one requirement.

```
TestClass naming: {Resource}Controller{IntegrationTest | ApiTest}
TestMethod naming: test{Behavior}_{Condition}
```

Structure per test:
1. **Arrange** — Set up preconditions (authentication, seed data via API calls)
2. **Act** — Make the HTTP request matching the requirement's trigger
3. **Assert** — Verify the response matches the requirement's expected outcome

### End-to-End Tests (Cross-Domain Workflows)

Multi-step tests that exercise a complete user workflow spanning multiple endpoints.

```
TestClass naming: EndToEnd{Workflow}FlowTest
TestMethod naming: test{WorkflowName}
```

Structure per test:
1. **Setup** — Authenticate, establish initial state
2. **Steps** — Sequential API calls representing the workflow
3. **Verify** — Assert final state is consistent across all affected resources

## Language-Agnostic Test Templates

### HTTP API Tests

For any REST/HTTP API, regardless of language:

```
TEMPLATE: Happy Path
  GIVEN: authenticated user with required role
  AND: valid input data matching schema from design doc
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

### Derive Test Data From Design Document Only

- Use exact field names, types, and constraints from the design doc's schema definitions
- Use boundary values derived from constraints (max length strings, min/max numeric values)
- For required fields: test with empty/null/missing values
- For optional fields: test with present and absent values
- For enums: test with valid values and invalid values

### Authentication Setup

Read the design doc for:
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
    void test{Behavior}() { ... }
}
```

### Python (pytest + httpx)

```python
@pytest.mark.integration
class TestResourceApi:
    @pytest.mark.requirement("REQ-F-XXX")
    def test_behavior(self, authenticated_client):
        ...
```

### TypeScript (Jest + supertest)

```typescript
describe('Resource API', () => {
  it('REQ-F-XXX: should {behavior}', async () => {
    ...
  });
});
```

### Go (testing + net/http/httptest)

```go
func TestResource_Behavior(t *testing.T) {
    // REQ-F-XXX: {description}
    ...
}
```

## Test Independence

Each test MUST:
- Be independently runnable (no ordering dependencies)
- Set up its own preconditions (don't rely on prior test state)
- Clean up or use isolated data (avoid shared mutable state)

## What NOT to Test

- Internal implementation details (private methods, internal data structures)
- Database schema directly (test via API behavior)
- Logging output (non-functional, not observable via API)
- Performance characteristics (unless quantitative requirement exists)
- UI rendering (outside scope of API-level validation)
