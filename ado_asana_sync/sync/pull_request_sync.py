"""Pull request sync - re-exports from modular sub-modules for backward-compatible import surface.

Note: this facade preserves import-name compatibility only. Monkeypatching functions through
this module will not intercept calls made within the sub-modules (pr_sync_core, pr_processor);
patch at the originating module level instead.
"""

try:
    from azure.devops.v7_0.git.models import GitPullRequestSearchCriteria
except ImportError:
    GitPullRequestSearchCriteria = None  # type: ignore[assignment,misc]

from ado_asana_sync.utils.date import iso8601_utc

from .asana import get_asana_task
from .group_member_cache import GroupMemberCache
from .pr_asana_helpers import (
    _PR_CLOSED_STATES,
    _REVIEWER_APPROVED_STATES,
    _get_cached_asana_task,
    _get_cached_custom_field,
    add_closure_comment_to_pr_task,
    add_tag_to_pr_task,
    create_asana_pr_task,
    update_asana_pr_task,
)
from .pr_processor import (
    _collect_expanded_member_gids,
    _handle_expand_group_reviewer,
    _handle_group_reviewer,
    _resolve_group_members_from_ado,
    _resolve_group_reviewer_default_user,
    create_ado_user_from_reviewer,
    create_new_pr_reviewer_task,
    handle_removed_reviewers,
    is_group_reviewer,
    process_pr_reviewer,
    process_pull_request,
    update_existing_pr_reviewer_task,
)
from .pr_sync_core import (
    process_closed_pull_requests,
    process_repository_pull_requests,
    sync_pull_requests,
)
from .pull_request_item import PullRequestItem
from .sync import (
    ADOAssignedUser,
    find_custom_field_by_name,
    get_asana_project_tasks,
    get_asana_task_by_name,
    get_asana_users,
    matching_user,
)
from .utils import encode_url_for_asana, extract_reviewer_vote

__all__ = [
    "ADOAssignedUser",
    "GitPullRequestSearchCriteria",
    "GroupMemberCache",
    "PullRequestItem",
    "_PR_CLOSED_STATES",
    "_REVIEWER_APPROVED_STATES",
    "_get_cached_asana_task",
    "_get_cached_custom_field",
    "add_closure_comment_to_pr_task",
    "add_tag_to_pr_task",
    "create_asana_pr_task",
    "update_asana_pr_task",
    "_collect_expanded_member_gids",
    "_handle_expand_group_reviewer",
    "_handle_group_reviewer",
    "_resolve_group_members_from_ado",
    "_resolve_group_reviewer_default_user",
    "create_ado_user_from_reviewer",
    "create_new_pr_reviewer_task",
    "handle_removed_reviewers",
    "is_group_reviewer",
    "process_pr_reviewer",
    "process_pull_request",
    "update_existing_pr_reviewer_task",
    "process_closed_pull_requests",
    "process_repository_pull_requests",
    "sync_pull_requests",
    "find_custom_field_by_name",
    "get_asana_project_tasks",
    "get_asana_task_by_name",
    "get_asana_users",
    "matching_user",
    "encode_url_for_asana",
    "extract_reviewer_vote",
    "get_asana_task",
    "iso8601_utc",
]
