"""Add auth verification and study notifications.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-23 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('phone_number', sa.String(), nullable=True))
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('auth_provider', sa.String(), nullable=False, server_default='password'))
    op.add_column('users', sa.Column('google_sub', sa.String(), nullable=True))
    op.add_column('users', sa.Column('email_notifications_enabled', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('users', sa.Column('sms_notifications_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index('ix_users_google_sub', 'users', ['google_sub'], unique=True)

    op.create_table(
        'email_verification_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('code_hash', sa.String(), nullable=False),
        sa.Column('purpose', sa.String(), nullable=False, server_default='verify_email'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_email_verification_tokens_user_id', 'email_verification_tokens', ['user_id'])
    op.create_index('ix_email_verification_tokens_expires_at', 'email_verification_tokens', ['expires_at'])
    op.create_index('ix_email_verification_tokens_created_at', 'email_verification_tokens', ['created_at'])

    op.create_table(
        'user_notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('channel', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('dedupe_key', sa.String(), nullable=False),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='queued'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_user_notifications_user_id', 'user_notifications', ['user_id'])
    op.create_index('ix_user_notifications_dedupe_key', 'user_notifications', ['dedupe_key'], unique=True)
    op.create_index('ix_user_notifications_scheduled_for', 'user_notifications', ['scheduled_for'])
    op.create_index('ix_user_notifications_sent_at', 'user_notifications', ['sent_at'])

    op.execute("UPDATE users SET email_verified = 1 WHERE email_verified IS NULL")
    op.execute("UPDATE users SET auth_provider = 'password' WHERE auth_provider IS NULL OR auth_provider = ''")
    op.execute("UPDATE users SET email_notifications_enabled = 1 WHERE email_notifications_enabled IS NULL")
    op.execute("UPDATE users SET sms_notifications_enabled = 0 WHERE sms_notifications_enabled IS NULL")


def downgrade() -> None:
    op.drop_index('ix_user_notifications_sent_at', table_name='user_notifications')
    op.drop_index('ix_user_notifications_scheduled_for', table_name='user_notifications')
    op.drop_index('ix_user_notifications_dedupe_key', table_name='user_notifications')
    op.drop_index('ix_user_notifications_user_id', table_name='user_notifications')
    op.drop_table('user_notifications')

    op.drop_index('ix_email_verification_tokens_created_at', table_name='email_verification_tokens')
    op.drop_index('ix_email_verification_tokens_expires_at', table_name='email_verification_tokens')
    op.drop_index('ix_email_verification_tokens_user_id', table_name='email_verification_tokens')
    op.drop_table('email_verification_tokens')

    op.drop_index('ix_users_google_sub', table_name='users')
    op.drop_column('users', 'sms_notifications_enabled')
    op.drop_column('users', 'email_notifications_enabled')
    op.drop_column('users', 'google_sub')
    op.drop_column('users', 'auth_provider')
    op.drop_column('users', 'email_verified_at')
    op.drop_column('users', 'email_verified')
    op.drop_column('users', 'phone_number')
