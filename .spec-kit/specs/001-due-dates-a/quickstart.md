# Quickstart: Due Date Synchronization

**Phase**: 1 | **Date**: 2025-09-06 | **Status**: Complete

## Quick Test Scenarios

### Scenario 1: New ADO Work Item with Due Date
```bash
# Setup: Create ADO work item with Due Date = "2025-12-31"
# Expected: Asana task created with due_on = "2025-12-31"

# Test command
uv run python -m ado_asana_sync.sync --project "test-project" --sync-once

# Verification
# 1. Check database for TaskItem with due_date = "2025-12-31"
# 2. Check Asana task has due_on field set to "2025-12-31"
# 3. Check logs show "Due date synchronized: 2025-12-31"
```

### Scenario 2: New ADO Work Item without Due Date
```bash
# Setup: Create ADO work item with no Due Date field
# Expected: Asana task created with no due_on field

# Test command  
uv run python -m ado_asana_sync.sync --project "test-project" --sync-once

# Verification
# 1. Check database for TaskItem with due_date = None
# 2. Check Asana task has no due_on field
# 3. Check logs show no due date messages
```

### Scenario 3: Existing Task Update (Preserve Asana Changes)
```bash
# Setup: 
# 1. ADO work item with Due Date = "2025-12-31"
# 2. Already synced to Asana with due_on = "2025-12-31" 
# 3. User changes Asana due date to "2026-01-15"
# 4. ADO due date changes to "2025-11-30"

# Expected: Asana due date remains "2026-01-15" (user change preserved)

# Test command
uv run python -m ado_asana_sync.sync --project "test-project" --sync-once

# Verification
# 1. Check Asana task still has due_on = "2026-01-15"
# 2. Check database TaskItem.due_date unchanged
# 3. Check logs show task updated but no due date changes
```

### Scenario 4: Invalid Due Date Handling
```bash
# Setup: Create ADO work item with invalid Due Date = "invalid-date"
# Expected: Asana task created with no due_on, warning logged

# Test command
uv run python -m ado_asana_sync.sync --project "test-project" --sync-once

# Verification  
# 1. Check database for TaskItem with due_date = None
# 2. Check Asana task has no due_on field
# 3. Check logs show WARNING: "Invalid due date format: invalid-date"
```

## Development Quick Start

### 1. Run Contract Tests (Should Fail Initially)
```bash
# These tests define the interface and should fail before implementation
uv run pytest .spec-kit/specs/001-due-dates-a/contracts/task-item-contract.py -v

# Expected: All tests fail - this confirms we're starting with RED phase of TDD
```

### 2. Run Existing Tests (Should Pass)
```bash  
# Ensure we don't break existing functionality
uv run pytest tests/ -v

# Expected: All existing tests pass - confirms we have a stable baseline
```

### 3. Implementation Order (TDD Red-Green-Refactor)
```bash
# Phase 1: Make contract tests pass
# 1. Extend TaskItem constructor with due_date parameter
# 2. Add due_date to __eq__ method
# 3. Add due_date to save() method

# Phase 2: Add ADO extraction
# 4. Add ADO_DUE_DATE constant
# 5. Implement extract_due_date_from_ado function

# Phase 3: Add Asana integration  
# 6. Extend create_asana_task_body with due_on field
# 7. Add is_initial_sync detection logic

# Phase 4: Add error handling
# 8. Implement try/catch around due date operations
# 9. Add structured logging for due date warnings
```

### 4. Quality Checks
```bash
# Run all quality checks before commit
uv run check  # Runs ruff, mypy, pytest with coverage

# Expected: All checks pass with >60% test coverage
```

## Integration Test Setup

### Test Environment Requirements
```bash
# Environment variables for integration testing
export ADO_ORG_URL="https://dev.azure.com/test-org"
export ADO_PAT="test-pat-token"  
export ASANA_WORKSPACE_ID="test-workspace-id"
export ASANA_PAT="test-asana-token"
export DATABASE_PATH="test-database.db"
```

### Test Data Setup
```python
# Create test ADO work item with due date
ado_work_item = {
    "id": 12345,
    "rev": 1,
    "fields": {
        "System.Title": "Test Due Date Sync",
        "System.WorkItemType": "Task",
        "System.State": "New", 
        "Microsoft.VSTS.Scheduling.DueDate": "2025-12-31T23:59:59.000Z"
    }
}

# Expected Asana task after sync
asana_task = {
    "gid": "67890",
    "name": "Test Due Date Sync",
    "due_on": "2025-12-31",
    "completed": False
}
```

## Performance Validation

### Large Scale Test
```bash
# Test with 5000+ work items to verify performance goals
uv run python scripts/performance-test.py --items 5000 --with-due-dates 50%

# Expected metrics:
# - Sync completion time: < 10 minutes
# - Memory usage: < 500MB peak
# - Database size: < 100MB for 5000 items
# - No degradation vs baseline sync performance
```

### Error Rate Validation  
```bash
# Test error handling with malformed due dates
uv run python scripts/error-rate-test.py --invalid-dates 10% --items 1000

# Expected:
# - Sync success rate: 100% (due date errors don't block sync)
# - Warning log count: ~100 (10% invalid dates logged)
# - Tasks created successfully: 1000 (all items sync despite date errors)
```

---
**Quickstart Status**: COMPLETE - Ready for task generation