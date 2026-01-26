"""Entity identifiers and token structures.

These types answer: "How do we refer to things?"
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class TokenInfo:
    """Identity and data for a token flowing through the DAG.

    Tokens track row instances through forks/joins:
    - row_id: Stable source row identity
    - token_id: Instance of row in a specific DAG path
    - branch_name: Which fork path this token is on (if forked)
    - fork_group_id: Groups all children from a fork operation
    - join_group_id: Groups all tokens merged in a coalesce operation
    - expand_group_id: Groups all children from an expand operation

    Note: NOT frozen because row_data is mutable dict and executors
    update tokens as they flow through the pipeline.
    """

    row_id: str
    token_id: str
    row_data: dict[str, Any]
    branch_name: str | None = None
    fork_group_id: str | None = None
    join_group_id: str | None = None
    expand_group_id: str | None = None
