# Hook: On-Demand Validation

## Trigger

**Event:** `userTriggered`

This hook fires when the user explicitly requests spec validation — useful for:
- Validating existing/legacy code against specs
- Running validation after manual code changes
- Checking contractor deliverables against requirements
- Re-validating after dependency updates

## Invocation

The user triggers this via:
```
/spec-validate
/spec-validate --specs ./path/to/requirements --tech ./tech.md
/spec-validate --framework pytest --output ./tests/generated/
```

## Parameters

| Parameter | Flag | Default | Description |
|-----------|------|---------|-------------|
| Specs path | `--specs` | Auto-discover | Path to requirements |
| Tech doc | `--tech` | Auto-discover | Path to technical design document (tech.md) |
| Framework | `--framework` | Auto-detect | Test framework to use |
| Output dir | `--output` | Standard test dir | Where to write tests |
| Execute | `--no-exec` | true | Skip test execution (generation only) |
| Repair | `--no-repair` | true | Skip auto-repair loop |
| Verbose | `--verbose` | false | Include detailed parsing log |

## Workflow

Same as `post-task-validation` but with explicit user control over:
1. Which specs to validate against (can target a subset)
2. Whether to execute tests or just generate them
3. Whether to trigger the auto-repair loop

## Use Cases

### 1. Legacy Code Validation

Validate existing code that was written before specs existed:
```
/spec-validate --specs ./new-requirements/ --tech ./tech.md
```

Expected outcome: High failure rate revealing spec gaps in legacy code. The violation report becomes a remediation backlog.

### 2. Generation-Only Mode

Generate tests without executing (for review before running):
```
/spec-validate --no-exec
```

Expected outcome: Test files written, coverage report generated, but no execution or violation report.

### 3. Targeted Domain Validation

Validate only a specific domain:
```
/spec-validate --specs ./BillPaymentProcessing/requirements.md
```

Expected outcome: Only bill-payment-related tests generated and executed.

### 4. Different Framework

Override auto-detection for a specific framework:
```
/spec-validate --framework jest --output ./tests/integration/
```

## Output

Same as post-task-validation hook:
- `TestsToSpecCoverage.md` — coverage of specs/requirements by E2E and integration tests
- `spec-validation-violations.md` (if executed and failures found)
- Summary printed to user
