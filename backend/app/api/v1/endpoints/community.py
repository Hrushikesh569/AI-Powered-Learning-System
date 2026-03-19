"""Community endpoint — peer matching + group chat feed (mini Reddit/Twitter)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional, List

from app.core.security import get_current_user_dep
from app.db.session import get_db
from app.db.models import User, CommunityPost, CommunityComment

router = APIRouter()
_get_user = get_current_user_dep()

PEER_LABELS = {
    0: "High Achievers",
    1: "Consistent Learners",
    2: "Developing Learners",
    3: "At-Risk Learners",
    4: "Emerging Learners",
}

GROUP_DESC = {
    0: "Top performers who consistently excel across all subjects.",
    1: "Steady learners who show up every day and build strong habits.",
    2: "Growing students working on closing knowledge gaps.",
    3: "Students who benefit most from peer support and structured plans.",
    4: "New learners building confidence and foundational skills.",
}


def _compute_group_similarity(user: User, group_id: int) -> float:
    """Compute similarity score (0-100) between user profile and group.
    
    Higher score = more similar. Used for sorting groups.
    """
    user_cluster = user.profile_cluster or 0
    
    # Base score: inverse of cluster distance
    if group_id == user_cluster:
        base_score = 100.0
    else:
        cluster_distance = abs(group_id - user_cluster)
        base_score = max(0, 100 - (cluster_distance * 15))  # 15 points per cluster step
    
    # Bonus for shared course/grade
    bonus = 0.0
    user_course = (user.course or "").strip().lower()
    user_grade = (user.grade or "").strip().lower()
    
    # Check if enough peers in group share similar course/grade to warrant bonus
    # (This would require additional database queries, so we'll keep it simple for now)
    
    return min(100, base_score + bonus)


# ──────────────────────────────────────────────────────────────────────────────
# Peers & Groups
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/peers")
async def get_peer_compatibility(
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    cluster = current_user.profile_cluster
    result = await db.execute(
        select(User)
        .where(User.profile_cluster == cluster)
        .where(User.id != current_user.id)
        .limit(10)
    )
    peers = result.scalars().all()
    return {
        "my_cluster": cluster,
        "group_name": PEER_LABELS.get(cluster, "Study Group"),
        "peers": [
            {
                "id": p.id,
                "name": p.name or p.email.split("@")[0],
                "learner_type": PEER_LABELS.get(p.profile_cluster, "Learner"),
                "study_hours": p.study_hours_per_day or 2.0,
            }
            for p in peers
        ],
        "total_in_group": len(peers) + 1,
    }


@router.get("/groups")
async def list_study_groups(
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    """List study groups with smart prioritization based on user profile."""
    groups = []
    for gid, name in PEER_LABELS.items():
        members_res = await db.execute(select(User).where(User.profile_cluster == gid))
        member_count = len(members_res.scalars().all())

        posts_res = await db.execute(
            select(CommunityPost).where(CommunityPost.group_id == gid)
        )
        post_count = len(posts_res.scalars().all())

        is_my_group = current_user.profile_cluster == gid
        similarity_score = _compute_group_similarity(current_user, gid)
        
        groups.append({
            "id": gid,
            "name": name,
            "description": GROUP_DESC.get(gid, f"Students classified as {name}"),
            "memberCount": member_count,
            "postCount": post_count,
            "isMyGroup": is_my_group,
            "similarityScore": similarity_score,  # For sorting (higher = more similar)
        })
    
    # Sort: my group first, then by similarity, then by group ID
    groups.sort(key=lambda g: (-g["isMyGroup"], -g["similarityScore"], g["id"]))
    
    return {"groups": groups}


# ──────────────────────────────────────────────────────────────────────────────
# Group Feed
# ──────────────────────────────────────────────────────────────────────────────

class PostCreate(BaseModel):
    content: str
    tag: Optional[str] = "discussion"   # "question" | "tip" | "discussion"


class CommentCreate(BaseModel):
    content: str


@router.get("/groups/{group_id}/feed")
async def get_group_feed(
    group_id: int,
    limit: int = 30,
    offset: int = 0,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    if group_id not in PEER_LABELS:
        raise HTTPException(status_code=404, detail="Group not found")

    result = await db.execute(
        select(CommunityPost)
        .where(CommunityPost.group_id == group_id)
        .order_by(CommunityPost.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    posts = result.scalars().all()

    post_list = []
    for post in posts:
        comment_res = await db.execute(
            select(CommunityComment).where(CommunityComment.post_id == post.id)
        )
        comment_count = len(comment_res.scalars().all())
        post_list.append({
            "id": post.id,
            "author": post.author_name or "Anonymous",
            "content": post.content,
            "tag": post.tag or "discussion",
            "likes": post.likes or 0,
            "commentCount": comment_count,
            "isOwn": post.user_id == current_user.id,
            "createdAt": post.created_at.isoformat() if post.created_at else None,
        })

    return {
        "posts": post_list,
        "groupName": PEER_LABELS.get(group_id, "Group"),
        "groupDesc": GROUP_DESC.get(group_id, ""),
    }


@router.post("/groups/{group_id}/posts")
async def create_post(
    group_id: int,
    body: PostCreate,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    if group_id not in PEER_LABELS:
        raise HTTPException(status_code=404, detail="Group not found")
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Post content cannot be empty")

    post = CommunityPost(
        group_id=group_id,
        user_id=current_user.id,
        author_name=current_user.name or current_user.email.split("@")[0],
        content=body.content.strip(),
        tag=body.tag or "discussion",
        likes=0,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    return {
        "id": post.id,
        "author": post.author_name,
        "content": post.content,
        "tag": post.tag,
        "likes": 0,
        "commentCount": 0,
        "isOwn": True,
        "createdAt": post.created_at.isoformat() if post.created_at else None,
    }


@router.post("/posts/{post_id}/like")
async def like_post(
    post_id: int,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    post.likes = (post.likes or 0) + 1
    await db.commit()
    return {"likes": post.likes}


@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: int,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own posts")
    await db.delete(post)
    await db.commit()
    return {"ok": True}


@router.get("/posts/{post_id}/comments")
async def get_comments(
    post_id: int,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CommunityComment)
        .where(CommunityComment.post_id == post_id)
        .order_by(CommunityComment.created_at.asc())
    )
    comments = result.scalars().all()
    return {
        "comments": [
            {
                "id": c.id,
                "author": c.author_name or "Anonymous",
                "content": c.content,
                "isOwn": c.user_id == current_user.id,
                "createdAt": c.created_at.isoformat() if c.created_at else None,
            }
            for c in comments
        ]
    }


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CommunityComment).where(CommunityComment.id == comment_id))
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own comments")
    await db.delete(comment)
    await db.commit()
    return {"ok": True}


@router.post("/posts/{post_id}/comments")
async def add_comment(
    post_id: int,
    body: CommentCreate,
    current_user: User = Depends(_get_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Comment cannot be empty")

    comment = CommunityComment(
        post_id=post_id,
        user_id=current_user.id,
        author_name=current_user.name or current_user.email.split("@")[0],
        content=body.content.strip(),
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    return {
        "id": comment.id,
        "author": comment.author_name,
        "content": comment.content,
        "isOwn": True,
        "createdAt": comment.created_at.isoformat() if comment.created_at else None,
    }

