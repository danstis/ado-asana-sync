# Tasks: Due Date Synchronization

**Input**: Design documents from `/.spec-kit/specs/001-due-dates-a/`  
**Prerequisites**: plan.md ✓, research.md ✓, data-model.md ✓, quickstart.md ✓

## Execution Flow (main)
```
1. Load plan.md from feature directory ✓
   → Tech stack: Python 3.11+, pytest, ruff, mypy
   → Libraries: asana, azure-devops (existing)
   → Structure: Single project extending ado_asana_sync package
2. Load design documents ✓:
   → data-model.md: TaskItem entity extension with due_date field
   → research.md: Extend existing architecture, minimal changes (5 files, ~30 lines)
   → quickstart.md: 4 test scenarios + TDD workflow
3. Generate tasks by category:
   → Setup: Quality checks, baseline verification
   → Tests: Contract tests (existing), new integration tests
   → Core: TaskItem extension, sync logic enhancement
   → Integration: ADO field extraction, Asana API integration
   → Polish: Error handling, logging, documentation
4. Apply task rules:
   → Contract tests already in main test suite (tests/sync/)
   → TaskItem tasks sequential (same file)
   → Sync tasks sequential (same file)
   → Test tasks parallel [P] (different files)
5. Number tasks T001-T020
6. Validate: All contracts tested, TDD order enforced
7. SUCCESS (tasks ready for execution)
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact file paths in descriptions

## Path Conventions
- **Single project**: Extending existing `ado_asana_sync/` package structure
- **Tests**: Located in `tests/sync/` (existing structure)

## Phase 3.1: Setup & Verification
- [ ] T001 [P] Run quality checks to ensure clean baseline: `uv run check`
- [ ] T002 [P] Verify existing tests pass: `uv run pytest tests/ -v`
- [ ] T003 [P] Run contract tests to confirm TDD red phase: `uv run pytest tests/sync/test_task_item.py::TestTaskItemDueDateContract -v`

## Phase 3.2: Tests First (TDD) ⚠️ MUST COMPLETE BEFORE 3.3
**CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**

*Note: Contract tests already exist in tests/sync/test_task_item.py and tests/sync/test_sync.py*

- [ ] T004 [P] Integration test: New ADO work item with due date in `tests/sync/test_due_date_integration.py`
- [ ] T005 [P] Integration test: ADO work item without due date in `tests/sync/test_due_date_integration.py`  
- [ ] T006 [P] Integration test: Preserve Asana user changes in `tests/sync/test_due_date_integration.py`
- [ ] T007 [P] Integration test: Invalid due date error handling in `tests/sync/test_due_date_integration.py`
- [ ] T008 [P] Unit test: Date conversion functions in `tests/sync/test_due_date_utils.py`

## Phase 3.3: Core Implementation (ONLY after tests are failing)
- [ ] T009 Extend TaskItem constructor with due_date parameter in `ado_asana_sync/sync/task_item.py`
- [ ] T010 Add due_date to TaskItem.__eq__ method in `ado_asana_sync/sync/task_item.py`
- [ ] T011 Add due_date to TaskItem.save() method in `ado_asana_sync/sync/task_item.py`
- [ ] T012 Add ADO_DUE_DATE constant in `ado_asana_sync/sync/sync.py`
- [ ] T013 Implement extract_due_date_from_ado function in `ado_asana_sync/sync/sync.py`
- [ ] T014 Add due date conversion utility functions in `ado_asana_sync/sync/utils.py`

## Phase 3.4: Integration & API Enhancement
- [ ] T015 Integrate due date extraction in sync process in `ado_asana_sync/sync/sync.py`
- [ ] T016 Add due_on field to Asana task creation in `ado_asana_sync/sync/sync.py`
- [ ] T017 Implement initial vs subsequent sync logic for due dates in `ado_asana_sync/sync/sync.py`
- [ ] T018 Add error handling and warning logs for due date failures in `ado_asana_sync/sync/sync.py`

## Phase 3.5: Polish & Validation
- [ ] T019 [P] Run all contract tests and verify they pass: `uv run pytest tests/sync/test_task_item.py::TestTaskItemDueDateContract tests/sync/test_sync.py::TestSyncDueDateContract -v`
- [ ] T020 [P] Run comprehensive test suite with coverage: `uv run pytest --cov=ado_asana_sync --cov-report=xml --cov-branch`
- [ ] T021 [P] Format and lint all modified files: `uv run ruff format . && uv run ruff check .`
- [ ] T022 [P] Run quickstart scenarios validation from `quickstart.md`

## Dependencies
### Critical Path:
1. **Setup (T001-T003)** → Must complete before any development
2. **Tests (T004-T008)** → Must fail before implementation begins
3. **Core TaskItem (T009-T011)** → Sequential (same file), must complete before sync integration
4. **Sync Constants (T012-T014)** → Must complete before sync integration  
5. **Integration (T015-T018)** → Sequential (same file), requires TaskItem and constants
6. **Polish (T019-T022)** → Can run in parallel, requires all implementation complete

### Specific Dependencies:
- T009 (TaskItem constructor) blocks T010, T011
- T012 (ADO_DUE_DATE constant) blocks T013, T015
- T013 (extract function) blocks T015
- T014 (utilities) blocks T015, T016
- T015-T018 (sync integration) are sequential in same file
- T019-T022 require T009-T018 complete

## Parallel Execution Examples

### Phase 3.1 - Setup (All Parallel):
```bash
# Launch T001-T003 together:
uv run check &                    # T001: Quality checks
uv run pytest tests/ -v &        # T002: Existing tests  
uv run pytest tests/sync/test_task_item.py::TestTaskItemDueDateContract -v &  # T003: Contract tests
wait
```

### Phase 3.2 - Test Creation (All Parallel):
```bash
# Launch T004-T008 together (different files):
Task: "Integration test: New ADO work item with due date in tests/sync/test_due_date_integration.py"
Task: "Integration test: ADO work item without due date in tests/sync/test_due_date_integration.py"  
Task: "Integration test: Preserve Asana user changes in tests/sync/test_due_date_integration.py"
Task: "Integration test: Invalid due date error handling in tests/sync/test_due_date_integration.py"
Task: "Unit test: Date conversion functions in tests/sync/test_due_date_utils.py"
```

### Phase 3.5 - Polish (All Parallel):
```bash
# Launch T019-T022 together:
uv run pytest tests/sync/test_task_item.py::TestTaskItemDueDateContract tests/sync/test_sync.py::TestSyncDueDateContract -v &  # T019
uv run pytest --cov=ado_asana_sync --cov-report=xml --cov-branch &  # T020
uv run ruff format . && uv run ruff check . &  # T021
# T022 manual validation from quickstart.md &
wait
```

## Implementation Notes

### TaskItem Extension Pattern (T009-T011):
```python
# T009: Constructor
def __init__(self, ..., due_date: Optional[str] = None):
    self.due_date = due_date

# T010: Equality
def __eq__(self, other):
    return ... and self.due_date == other.due_date

# T011: Serialization  
def save(self):
    return {..., "due_date": self.due_date}
```

### Sync Integration Pattern (T015-T018):
```python  
# T012: Constant
ADO_DUE_DATE = "Microsoft.VSTS.Scheduling.DueDate"

# T013: Extraction
def extract_due_date_from_ado(ado_task):
    ado_due_date = ado_task.fields.get(ADO_DUE_DATE)
    if ado_due_date:
        return convert_ado_date_to_asana_format(ado_due_date)
    return None

# T016: Asana API Integration
if task.due_date and is_initial_sync:
    body["data"]["due_on"] = task.due_date
```

## Constitutional Compliance
- ✅ **TDD Enforced**: Tests (T004-T008) must fail before implementation (T009-T018)
- ✅ **Module Extension**: Extending existing ado_asana_sync.sync module
- ✅ **Test Coverage**: Comprehensive contract + integration + unit tests
- ✅ **Quality Gates**: T019-T022 ensure >60% coverage and code quality
- ✅ **Backward Compatible**: Optional due_date field, no breaking changes

## Success Criteria
1. All contract tests pass after implementation
2. Integration tests validate 4 quickstart scenarios  
3. Test coverage remains >60%
4. All quality checks pass (ruff, mypy)
5. 5 files modified, ~30 lines added (per research findings)
6. Zero breaking changes to existing functionality

---
**Task Generation Status**: COMPLETE - 22 tasks ready for execution