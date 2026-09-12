"""Drop unused in-app notifications table

Revision ID: c8f4e1a90b21
Revises: edf2272c0a9d
Create Date: 2026-09-11

Home and History replaced the on-machine inbox. Outbound Apprise/device
alerts are unchanged. ui_settings.notify_refresh is still present; dropping
it needs a later revision. Downgrade is a no-op because the table had no
data worth restoring.
"""
from alembic import op


revision = 'c8f4e1a90b21'
down_revision = 'edf2272c0a9d'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('notifications')


def downgrade():
    pass
