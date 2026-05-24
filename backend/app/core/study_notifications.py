"""Study notification worker for reminders, streak milestones, and deadlines."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from celery import shared_task
from sqlalchemy import select, func

from app.db.models import DeadlineItem, ProgressLog, ScheduledTopic, User, UserNotification
from app.db.session import AsyncSessionLocal
from app.core.messaging import send_email, send_sms

_STREAK_MILESTONES = {5, 10, 20}


@dataclass
class _Notification:
    channel: str
    kind: str
    title: str
    body: str
    dedupe_key: str
    payload: dict


async def _already_sent(db, dedupe_key: str) -> bool:
    result = await db.execute(select(UserNotification.id).where(UserNotification.dedupe_key == dedupe_key))
    return result.scalar_one_or_none() is not None


async def _store_notification(db, user_id: int, notification: _Notification) -> bool:
    if await _already_sent(db, notification.dedupe_key):
        return False
    db.add(UserNotification(
        user_id=user_id,
        channel=notification.channel,
        kind=notification.kind,
        title=notification.title,
        body=notification.body,
        payload=notification.payload,
        dedupe_key=notification.dedupe_key,
        scheduled_for=datetime.now(timezone.utc),
        status='queued',
    ))
    await db.commit()
    return True


async def _deliver_notification(user: User, notification: _Notification) -> None:
    if notification.channel == 'sms':
        if user.sms_notifications_enabled and user.phone_number:
            await send_sms(user.phone_number, f"{notification.title}\n\n{notification.body}")
    else:
        if user.email_notifications_enabled:
            send_email(user.email, notification.title, notification.body)
        if user.sms_notifications_enabled and user.phone_number:
            await send_sms(user.phone_number, f"{notification.title}\n\n{notification.body}")


async def _user_streak(db, user_id: int) -> int:
    result = await db.execute(
        select(ProgressLog.timestamp)
        .where(ProgressLog.user_id == user_id)
        .order_by(ProgressLog.timestamp.desc())
        .limit(60)
    )
    days = []
    for ts in result.scalars().all():
        if ts:
            days.append(ts.astimezone(timezone.utc).date())

    topic_result = await db.execute(
        select(ScheduledTopic.completed_date)
        .where(ScheduledTopic.user_id == user_id)
        .where(ScheduledTopic.completed_date.isnot(None))
        .order_by(ScheduledTopic.completed_date.desc())
    )
    for ts in topic_result.scalars().all():
        if ts:
            days.append(ts.astimezone(timezone.utc).date())

    if not days:
        return 0

    unique_days = sorted(set(days), reverse=True)
    today = datetime.now(timezone.utc).date()
    streak = 0
    current = unique_days[0]
    for idx, day in enumerate(unique_days):
        if day == current - timedelta(days=idx):
            streak += 1
        else:
            break
    if streak and unique_days[0] < today - timedelta(days=1):
        return 0
    return min(streak, 365)


async def _has_activity_today(db, user_id: int) -> bool:
    today = datetime.now(timezone.utc).date()
    progress_result = await db.execute(
        select(func.count(ProgressLog.id))
        .where(ProgressLog.user_id == user_id)
        .where(func.date(ProgressLog.timestamp) == today.isoformat())
    )
    topic_result = await db.execute(
        select(func.count(ScheduledTopic.id))
        .where(ScheduledTopic.user_id == user_id)
        .where(func.date(ScheduledTopic.completed_date) == today.isoformat())
    )
    return (progress_result.scalar_one() or 0) > 0 or (topic_result.scalar_one() or 0) > 0


async def _build_notifications_for_user(db, user: User) -> list[_Notification]:
    now = datetime.now(timezone.utc)
    today = now.date()
    notifications: list[_Notification] = []

    pending_today_result = await db.execute(
        select(func.count(ScheduledTopic.id))
        .where(ScheduledTopic.user_id == user.id)
        .where(ScheduledTopic.scheduled_date.isnot(None))
        .where(func.date(ScheduledTopic.scheduled_date) <= today.isoformat())
        .where(func.lower(ScheduledTopic.status) != 'completed')
    )
    pending_today = int(pending_today_result.scalar_one() or 0)

    deadlines_result = await db.execute(
        select(DeadlineItem)
        .where(DeadlineItem.user_id == user.id)
        .where(DeadlineItem.status != 'done')
        .where(DeadlineItem.due_date.isnot(None))
    )
    deadlines = deadlines_result.scalars().all()

    streak = await _user_streak(db, user.id)
    activity_today = await _has_activity_today(db, user.id)

    if pending_today > 0 and now.hour >= 18 and not activity_today:
        notifications.append(_Notification(
            channel='email',
            kind='study_reminder',
            title='Your study day is still open',
            body=f'You still have {pending_today} topic(s) pending for today. A short session now will keep your plan on track.',
            dedupe_key=f'study-reminder-{user.id}-{today.isoformat()}',
            payload={'pending_topics': pending_today},
        ))

    if activity_today and pending_today == 0:
        notifications.append(_Notification(
            channel='email',
            kind='daily_completion',
            title='Nice work finishing today',
            body='You completed your planned study work for today. That consistency is what compounds over time.',
            dedupe_key=f'daily-complete-{user.id}-{today.isoformat()}',
            payload={'streak': streak},
        ))

    if not activity_today and streak >= 3 and now.hour >= 19:
        notifications.append(_Notification(
            channel='email',
            kind='streak_warning',
            title='Keep your streak alive',
            body=f'You are on a {streak}-day streak. A small session today keeps it going.',
            dedupe_key=f'streak-warning-{user.id}-{today.isoformat()}',
            payload={'streak': streak},
        ))

    if streak in _STREAK_MILESTONES and activity_today:
        notifications.append(_Notification(
            channel='email',
            kind='streak_milestone',
            title=f'{streak}-day streak',
            body=f'You have studied for {streak} days in a row. That is a strong habit.',
            dedupe_key=f'streak-milestone-{user.id}-{streak}',
            payload={'streak': streak},
        ))

    for item in deadlines:
        days_left = (item.due_date.astimezone(timezone.utc).date() - today).days
        if days_left <= 3:
            notifications.append(_Notification(
                channel='email',
                kind='deadline_reminder',
                title=f'Deadline in {max(days_left, 0)} day(s): {item.title}',
                body=f'{item.title} is due on {item.due_date.date().isoformat()}. You still have time, but this is the window to finish it.',
                dedupe_key=f'deadline-{item.id}-{days_left}',
                payload={'deadline_id': item.id, 'days_left': days_left},
            ))

    return notifications


async def _run_notifications_once() -> dict:
    sent = 0
    queued = 0
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()
        for user in users:
            notifications = await _build_notifications_for_user(db, user)
            for notification in notifications:
                queued += 1
                if await _store_notification(db, user.id, notification):
                    sent += 1
                    await _deliver_notification(user, notification)
    return {"users": len(users), "queued": queued, "sent": sent}


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def run_study_notifications_task(self):
    try:
        return asyncio.run(_run_notifications_once())
    except Exception as exc:
        raise self.retry(exc=exc)
