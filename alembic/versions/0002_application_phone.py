"""application: phone column

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "applications", sa.Column("phone", sa.String(length=32), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("applications", "phone")
