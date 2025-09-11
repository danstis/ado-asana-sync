# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Pull Request Synchronization**: Implemented comprehensive Pull Request sync from Azure DevOps to Asana
  - Creates separate Asana tasks for each Pull Request reviewer
  - Task titles follow format: "Pull Request 5: Update readme (Reviewer Name)"
  - Automatic status management based on review states:
    - Approved reviews (approve/approve with suggestions) → Close Asana task
    - Other review states (waiting for author, reject, no vote) → Keep task open
    - PR completion/abandonment → Close all reviewer tasks
  - Handles reviewer additions, removals, and approval resets
  - Integrates with existing user matching logic
  - Includes comprehensive logging for PR sync operations
- New `PullRequestItem` class for managing PR-reviewer task relationships
- New `pull_request_sync.py` module with complete PR synchronization logic
- Extended `App` class with Azure DevOps Git client support
- Added `pr_matches` TinyDB table for storing PR-reviewer mappings
- Comprehensive unit tests for Pull Request functionality

### Changed

- Updated project description to include pull request synchronization
- Extended main sync workflow to include Pull Request processing
- Enhanced documentation with Pull Request feature details and testing procedures

### Fixed

- **Pull Request Approval Detection**: Fixed reviewer approval status not properly closing Asana tasks
  - Now correctly handles both "approved" and "approvedWithSuggestions" votes
  - Properly maps ADO integer vote values (10, 5, 0, -5, -10) to string equivalents
  - Added comprehensive logging for vote changes and task completion
- **Pull Request Title Updates**: Fixed PR title changes not syncing to Asana
  - Improved change detection to compare PR titles directly
  - Enhanced logging to show when titles are updated
- **Reviewer Removal Handling**: Fixed removed reviewers not having their tasks closed
  - Added automatic detection of reviewer removal
  - Closes Asana tasks when reviewers are removed from PRs
  - Handles edge case where all reviewers are removed
- **Pull Request Approval Reset**: Fixed approval reset not reopening Asana tasks
  - Now properly reopens tasks when reviewer approval is reset from approved to no vote
  - Fixed `is_current()` method to detect review status changes
  - Added comprehensive logging for approval reset scenarios
  - Includes debug logging for task completion state changes
  - Enhanced test coverage for review status change detection

### Technical Details

- Added Azure DevOps Git API integration for Pull Request data retrieval
- Implemented proper error handling and fallback mechanisms for Git API
- Maintained compatibility with existing work item sync patterns
- Added proper database locking for PR matches table
- Integrated with existing Asana task creation and update functions

## Previous Versions

_This changelog was created with the addition of Pull Request sync functionality. Previous versions were not formally tracked._
