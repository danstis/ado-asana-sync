# Data Model: Due Date Synchronization

**Phase**: 1 | **Date**: 2025-09-06 | **Status**: Complete

## Entity Extensions

### TaskItem (Extended)
**Location**: `ado_asana_sync/sync/task_item.py`
**Purpose**: Core data structure representing sync state between ADO work items and Asana tasks

#### New Field
- **due_date**: `Optional[str]`
  - Format: YYYY-MM-DD (Asana date format)
  - Source: ADO `Microsoft.VSTS.Scheduling.DueDate` field
  - Validation: ISO date string or None
  - Storage: JSON document in database `data` column

#### Field Relationships
- **due_date** ↔ **ado_id**: Due date extracted from ADO work item during sync
- **due_date** ↔ **asana_gid**: Due date applied to Asana task via `due_on` field
- **due_date** ↔ **ado_rev**: Due date updates respect initial-sync-only rule

#### State Transitions
```
ADO Work Item Creation:
  due_date=None → due_date=YYYY-MM-DD (if ADO Due Date present)
  due_date=None → due_date=None (if ADO Due Date absent/invalid)

Subsequent ADO Updates:
  due_date=YYYY-MM-DD → due_date=YYYY-MM-DD (preserved, no overwrite)
  due_date=None → due_date=None (preserved, no overwrite)

Asana Task Creation:
  TaskItem.due_date=YYYY-MM-DD → Asana due_on=YYYY-MM-DD
  TaskItem.due_date=None → Asana due_on not set

Asana Task Updates:
  TaskItem.due_date → Not applied (preserve user changes)
```

## Validation Rules

### Due Date Format Validation
```python
def validate_due_date(due_date: Optional[str]) -> bool:
    """Validate due date format is YYYY-MM-DD or None"""
    if due_date is None:
        return True
    
    try:
        datetime.strptime(due_date, '%Y-%m-%d')
        return True
    except ValueError:
        return False
```

### ADO Due Date Extraction Rules
1. **Field Present & Valid**: Extract date portion from ADO datetime
2. **Field Present & Invalid**: Set due_date=None, log warning
3. **Field Absent**: Set due_date=None, no logging
4. **Field Empty/Null**: Set due_date=None, no logging

### Asana Due Date Application Rules
1. **Initial Sync + due_date Present**: Set Asana `due_on` field
2. **Initial Sync + due_date None**: Omit `due_on` from Asana API call
3. **Subsequent Sync**: Never include `due_on` in Asana API call
4. **API Failure**: Log warning, continue sync operation

## Integration Points

### ADO API Integration
```python
# sync.py constant addition
ADO_DUE_DATE = "Microsoft.VSTS.Scheduling.DueDate"

# Field extraction pattern
ado_due_date = ado_task.fields.get(ADO_DUE_DATE)
if ado_due_date:
    # Convert ADO datetime to YYYY-MM-DD format
    due_date = convert_ado_date_to_asana_format(ado_due_date)
else:
    due_date = None
```

### Asana API Integration
```python
# Task creation body extension
body = {
    "data": {
        # ... existing fields ...
        "due_on": task.due_date,  # Only for initial sync
    }
}

# Due date omission for subsequent syncs
if not is_initial_sync:
    body["data"].pop("due_on", None)
```

### Database Schema Extension
**No changes required** - JSON document storage accommodates new field:
```json
{
  "ado_id": "12345",
  "due_date": "2025-12-31",
  // ... existing fields ...
}
```

## Error Handling Model

### Error Categories
1. **Date Conversion Errors**: Invalid ADO date format → due_date=None + warning log
2. **Asana API Errors**: due_on field rejection → warning log + continue sync
3. **Validation Errors**: Invalid due_date format → due_date=None + warning log

### Error Propagation
- **Non-blocking**: Due date errors never stop task sync operation
- **Logged**: All due date issues logged at WARNING level
- **Graceful degradation**: Task syncs successfully without due date

## Backward Compatibility

### Existing Data
- **No migration required**: Existing TaskItem records work without due_date field
- **Default behavior**: Missing due_date field treated as None
- **API compatibility**: Existing sync operations unaffected

### Code Compatibility
- **Constructor**: due_date parameter defaults to None
- **Comparison**: __eq__ method handles missing due_date fields
- **Serialization**: JSON storage handles optional fields naturally

---
**Design Status**: COMPLETE - Ready for contract generation