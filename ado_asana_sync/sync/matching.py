"""User and task matching logic between ADO and Asana.

ADO assignees are resolved to Asana users with a tiered ladder of rules,
evaluated rule-major (each rule is tried across the whole candidate list
before moving to the next), so precedence is deterministic:

1. ``exact_email`` - case-insensitive exact match of the ADO ``uniqueName``
   against the Asana ``email``.
2. ``email_local_part`` - case-insensitive match of the part before the last
   ``@`` (e.g. ``john.doe@seconddomain.com`` -> ``john.doe@maindomain.com``).
3. ``display_name`` - match of the normalized display name, tolerant of
   surrounding/inner whitespace and ``Last, First`` vs ``First Last`` ordering.

How far down the ladder to walk is controlled by ``USER_MATCH_STRATEGY``
(``exact`` | ``prefix`` | ``name``, default ``name`` - all rules enabled).
If a single rule matches more than one distinct Asana user the match is
ambiguous: a warning is logged and ``None`` is returned rather than guessing.
"""

from __future__ import annotations

import os

from ado_asana_sync.utils.logging_tracing import setup_logging_and_tracing

from .ado_parser import ADOAssignedUser

_LOGGER, _TRACER = setup_logging_and_tracing(__name__)

# Ordered rule ladders keyed by strategy name. Each strategy is a prefix of the
# full ladder, so a stricter deployment can opt out of the looser rules.
_STRATEGY_RULES: dict[str, tuple[str, ...]] = {
    "exact": ("exact_email",),
    "prefix": ("exact_email", "email_local_part"),
    "name": ("exact_email", "email_local_part", "display_name"),
}

DEFAULT_USER_MATCH_STRATEGY = "name"


def resolve_strategy(raw: str | None) -> str:
    """Normalize a strategy value, falling back to the default on an unknown one."""
    value = (raw or "").strip().lower()
    if value in _STRATEGY_RULES:
        return value
    if value:
        _LOGGER.warning(
            "Invalid USER_MATCH_STRATEGY '%s', using '%s'",
            raw,
            DEFAULT_USER_MATCH_STRATEGY,
        )
    return DEFAULT_USER_MATCH_STRATEGY


USER_MATCH_STRATEGY = resolve_strategy(os.environ.get("USER_MATCH_STRATEGY", DEFAULT_USER_MATCH_STRATEGY))


def _email_local_part(value: str | None) -> str | None:
    """Return the lower-cased local part of an email, or None if not extractable."""
    if not isinstance(value, str) or "@" not in value:
        return None
    local = value.rsplit("@", 1)[0].strip().lower()
    return local or None


def _normalized_name_key(value: str | None) -> tuple[str, ...] | None:
    """Return a whitespace/order/comma-tolerant token key for a display name."""
    if not isinstance(value, str) or not value.strip():
        return None
    tokens = value.replace(",", " ").lower().split()
    return tuple(sorted(tokens)) if tokens else None


def _rule_predicate(rule: str, ado_user: ADOAssignedUser):
    """Build a predicate for a rule, or return None if the rule cannot apply."""
    if rule == "exact_email":
        target = ado_user.email
        if not isinstance(target, str) or not target:
            return None
        target = target.lower()
        return lambda user: isinstance(user.get("email"), str) and user["email"].lower() == target
    if rule == "email_local_part":
        local = _email_local_part(ado_user.email)
        if local is None:
            return None
        return lambda user: _email_local_part(user.get("email")) == local
    if rule == "display_name":
        key = _normalized_name_key(ado_user.display_name)
        if key is None:
            return None
        return lambda user: _normalized_name_key(user.get("name")) == key
    return None


def _candidates(user_list: list[dict], predicate) -> list[dict]:
    """Return every user satisfying the predicate."""
    return [user for user in user_list if predicate(user)]


def _is_ambiguous(candidates: list[dict]) -> bool:
    """True when the candidates resolve to more than one distinct Asana user."""
    seen = {(c.get("gid"), c.get("email"), c.get("name")) for c in candidates}
    return len(seen) > 1


def _select(candidates: list[dict], rule: str, ado_user: ADOAssignedUser) -> dict | None:
    """Pick the single candidate, or None on an ambiguous tier (with a warning)."""
    if not candidates:
        return None
    if _is_ambiguous(candidates):
        _LOGGER.warning(
            "ambiguous %s match for ADO user %s <%s>: %d candidates; refusing to guess",
            rule,
            ado_user.display_name,
            ado_user.email,
            len(candidates),
        )
        return None
    return candidates[0]


def _match_user_with_rule(
    user_list: list[dict],
    ado_user: ADOAssignedUser,
    rules: tuple[str, ...],
) -> tuple[dict | None, str | None]:
    """Walk the rule ladder, stopping at the first tier that produces candidates."""
    for rule in rules:
        predicate = _rule_predicate(rule, ado_user)
        if predicate is None:
            continue
        candidates = _candidates(user_list, predicate)
        if candidates:
            return _select(candidates, rule, ado_user), rule
    return None, None


def matching_user(
    user_list: list[dict],
    ado_user: ADOAssignedUser | None,
    strategy: str | None = None,
) -> dict | None:
    """Resolve an ADO assignee to an Asana user via the tiered matching ladder."""
    if ado_user is None:
        return None

    active_strategy = resolve_strategy(strategy) if strategy is not None else USER_MATCH_STRATEGY
    rules = _STRATEGY_RULES[active_strategy]

    user, rule = _match_user_with_rule(user_list, ado_user, rules)
    if user is not None and rule != "exact_email":
        _LOGGER.info(
            "matched ADO user %s <%s> to Asana user %s <%s> via rule '%s'",
            ado_user.display_name,
            ado_user.email,
            user.get("name"),
            user.get("email"),
            rule,
        )
    return user
