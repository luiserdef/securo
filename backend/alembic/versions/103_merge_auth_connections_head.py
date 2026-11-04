"""merge auth connections and main migration branches

Revision ID: 103_merge
Revises: 102, 084_custom
Create Date: 2026-11-03

"""

from typing import Sequence, Union

revision: str = "103_merge"
down_revision: Union[str, Sequence[str], None] = ("102", "084_custom")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
