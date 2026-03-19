"""Add unit_name and topic_pages columns to study_materials."""
from alembic import op
import sqlalchemy as sa

revision = '0002_add_unit_topic_pages'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'study_materials',
        sa.Column('unit_name', sa.String(), nullable=True),
    )
    op.add_column(
        'study_materials',
        sa.Column('topic_pages', sa.JSON(), nullable=True),
    )
    op.create_index('ix_study_materials_unit_name', 'study_materials', ['unit_name'])


def downgrade() -> None:
    op.drop_index('ix_study_materials_unit_name', table_name='study_materials')
    op.drop_column('study_materials', 'topic_pages')
    op.drop_column('study_materials', 'unit_name')
