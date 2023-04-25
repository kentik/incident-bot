"""create github_issue column

Revision ID: 3d3aea5506dc
Revises: 6e7e162ffdb6
Create Date: 2023-04-24 21:17:19.200684

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3d3aea5506dc'
down_revision = '6e7e162ffdb6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("incidents", sa.Column("github_issue", sa.String()))


def downgrade():
    pass
