# Research: Due Date Synchronization

**Phase**: 0 | **Date**: 2025-09-06 | **Status**: Complete

## Research Findings

### Decision: Extend Existing TaskItem Architecture
**Rationale**: The existing codebase has excellent support for adding new fields through JSON document storage and the TaskItem class already follows the exact pattern needed for due date synchronization.

**Alternatives considered**: 
- Creating a new DueDateItem class - rejected because TaskItem already handles all sync metadata
- Separate due date service - rejected because sync logic is centralized in sync.py

### Decision: Use ADO Microsoft.VSTS.Scheduling.DueDate Field
**Rationale**: This is the standard ADO field name for due dates and matches the pattern used for other system fields like `System.State` and `System.Title`.

**Alternatives considered**:
- Custom field mapping - rejected because standardization is better
- Due date detection by field name - rejected because field names vary by organization

### Decision: Convert ADO DateTime to Asana Date Format
**Rationale**: ADO stores due dates as ISO datetime strings, but Asana `due_on` field expects YYYY-MM-DD date format. The conversion preserves the date while meeting API requirements.

**Alternatives considered**:
- Using Asana `due_at` with time - rejected because due dates typically don't include specific times
- Storing raw ADO format - rejected because Asana API would reject the format

### Decision: Leverage Existing is_current() Logic for Initial vs Subsequent Detection
**Rationale**: The existing `TaskItem.is_current()` method already determines if a task needs updating based on ADO revision and Asana modification timestamps. This naturally distinguishes initial creation from subsequent syncs.

**Alternatives considered**:
- New database flag for initial sync - rejected because existing logic already handles this
- Separate due date tracking table - rejected because JSON storage is sufficient

## Technical Research Results

### Existing Asana API Support
- **CONFIRMED**: Asana API already fetches `due_on` field in `opt_fields` (asana.py:36-42)
- **NO API CHANGES NEEDED**: Task creation and update endpoints already support `due_on` parameter

### Database Schema Compatibility  
- **CONFIRMED**: JSON document storage in `data` TEXT column supports due_date addition
- **NO MIGRATION NEEDED**: Backward compatible due to optional field design

### Date Handling Pattern
- **CONFIRMED**: Existing `iso8601_utc()` utility in utils/date.py for datetime standardization
- **PATTERN**: Convert ADO ISO datetime → extract date part → format as YYYY-MM-DD for Asana

### Error Handling Integration
- **CONFIRMED**: Module-level structured logging pattern established
- **PATTERN**: Use try/catch blocks with warning logs for due date failures (per specification requirement)

### Test Architecture Readiness
- **CONFIRMED**: Existing test structure in tests/sync/ supports TaskItem field additions
- **PATTERN**: Add due_date test cases to test_task_item.py and test_sync.py

## Implementation Discovery

### Key Extension Points Identified:
1. **TaskItem Constructor** (task_item.py:34-47): Add `due_date: Optional[str] = None` parameter
2. **ADO Field Extraction** (sync.py:37-40): Add `ADO_DUE_DATE = "Microsoft.VSTS.Scheduling.DueDate"`  
3. **Asana Task Creation** (sync.py:751-783): Add `"due_on": task.due_date` to request body
4. **Asana Task Updates** (sync.py:785-817): Add `"due_on": task.due_date` to request body
5. **Initial Sync Detection** (sync.py:509-511, 570-575): Use existing `is_current()` logic

### Minimal Code Changes Required:
- 5 file modifications (task_item.py, sync.py, 3 test files)
- ~30 lines of code additions total
- 0 breaking changes to existing functionality
- 0 database migrations required

## Validation Approach

### Integration Testing Strategy:
- Real ADO API calls with work items containing Due Date fields
- Real Asana API calls to verify `due_on` field setting
- Database persistence testing for due_date field in JSON storage
- Error handling testing for malformed dates and API failures

### Constitutional Compliance:
- ✅ Module-first: Extension within existing ado_asana_sync.sync module
- ✅ Test-first: Will write failing tests before implementation  
- ✅ uv-managed: No new dependencies required
- ✅ >60% coverage: Extension will include comprehensive test coverage

---
**Research Status**: COMPLETE - Ready for Phase 1 Design