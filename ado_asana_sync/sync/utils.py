"""Utility functions shared across sync modules."""

import logging

_LOGGER = logging.getLogger(__name__)


def extract_reviewer_vote(reviewer) -> str:
    """
    Extract the vote from an ADO reviewer object.

    ADO vote values include:
    - 'approved' (10) - Approve
    - 'approvedWithSuggestions' (5) - Approve with suggestions
    - 'noVote' (0) - No vote
    - 'waitingForAuthor' (-5) - Waiting for author
    - 'rejected' (-10) - Reject
    """
    try:
        # Try different possible attribute names for the vote
        vote = getattr(reviewer, "vote", None)

        # Vote might be an integer or string, normalize to string
        if vote is not None:
            # Handle integer vote values (ADO API sometimes returns integers)
            if isinstance(vote, int):
                vote_mapping = {
                    10: "approved",
                    5: "approvedWithSuggestions",
                    0: "noVote",
                    -5: "waitingForAuthor",
                    -10: "rejected",
                }
                vote = vote_mapping.get(vote, str(vote))

            _LOGGER.debug("Extracted reviewer vote: %s", vote)
            return str(vote)

        _LOGGER.debug("No vote found for reviewer")
        return "noVote"

    except Exception as e:
        _LOGGER.error("Failed to extract vote from reviewer: %s", e)
        return "noVote"
