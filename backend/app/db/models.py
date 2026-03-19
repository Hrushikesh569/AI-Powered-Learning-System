from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, JSON, Text, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True, default='')
    hashed_password = Column(String, nullable=False)
    study_hours_per_day = Column(Float, nullable=True, default=2.0)
    study_start_hour = Column(Integer, nullable=True, default=9)  # e.g., 9 for 9 AM
    study_end_hour = Column(Integer, nullable=True, default=23)   # e.g., 23 for 11 PM
    learning_goal = Column(String, nullable=True, default='')
    grade = Column(String, nullable=True, default='')  # e.g. "10", "12", "B.Tech Year 2"
    course = Column(String, nullable=True, default='')  # e.g. "Computer Science", "Engineering"
    profile_cluster = Column(Integer, nullable=True)  # set after profiling
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    profiles = relationship('UserProfile', back_populates='user')

class UserProfile(Base):
    __tablename__ = 'user_profiles'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    profile_label = Column(String, index=True)
    features = Column(JSON)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user = relationship('User', back_populates='profiles')

class StudyPlan(Base):
    __tablename__ = 'study_plans'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    plan_json = Column(JSON)
    generated_by_agent_id = Column(Integer, ForeignKey('agent_decisions.id'))
    valid_from = Column(DateTime)
    valid_to = Column(DateTime)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ProgressLog(Base):
    __tablename__ = 'progress_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    academic_metric = Column(Float)
    attendance = Column(Float)
    study_time = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    logged_by_agent_id = Column(Integer, ForeignKey('agent_decisions.id'))

class StressLog(Base):
    __tablename__ = 'stress_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    stress_level = Column(Float)
    sleep_hours = Column(Float)
    physical_activity = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    logged_by_agent_id = Column(Integer, ForeignKey('agent_decisions.id'))

class MotivationLog(Base):
    __tablename__ = 'motivation_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    motivation_score = Column(Float)
    category = Column(String)
    intervention = Column(String)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    logged_by_agent_id = Column(Integer, ForeignKey('agent_decisions.id'))

class GroupData(Base):
    __tablename__ = 'group_data'
    id = Column(Integer, primary_key=True)
    group_label = Column(String, index=True)
    group_features = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class GroupMembership(Base):
    __tablename__ = 'group_membership'
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey('group_data.id'), index=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

class AgentDecision(Base):
    __tablename__ = 'agent_decisions'
    id = Column(Integer, primary_key=True)
    agent_name = Column(String, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    input_features = Column(JSON)
    output_decision = Column(JSON)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    event_id = Column(String, index=True)

class ScheduleHistory(Base):
    __tablename__ = 'schedule_history'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    old_plan_id = Column(Integer, ForeignKey('study_plans.id'))
    new_plan_id = Column(Integer, ForeignKey('study_plans.id'))
    reason = Column(String)
    changed_by_agent_id = Column(Integer, ForeignKey('agent_decisions.id'))
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

class ModelPrediction(Base):
    __tablename__ = 'model_predictions'
    id = Column(Integer, primary_key=True)
    agent_name = Column(String, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    prediction = Column(JSON)
    model_version = Column(String)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class SyllabusDocument(Base):
    __tablename__ = 'syllabus_documents'
    id = Column(Integer, primary_key=True)
    kind = Column(String, index=True)  # 'schedule' or 'material'
    subject = Column(String, nullable=True)
    original_filename = Column(String)
    stored_path = Column(String)
    topics = Column(JSON)  # extracted topic lines, mainly for schedule docs
    metadata_json = Column(JSON)  # extra info like num_days, hours_per_day
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class StudyMaterial(Base):
    """User-specific uploaded file (syllabus PDF, lecture notes, etc.)."""
    __tablename__ = 'study_materials'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    subject = Column(String, index=True, nullable=True)
    unit_name = Column(String, nullable=True, index=True)  # which unit/module this file covers
    filename = Column(String)
    stored_path = Column(String)
    kind = Column(String, default='material')  # 'syllabus' | 'material'
    topics = Column(JSON, nullable=True)
    topic_pages = Column(JSON, nullable=True)  # {"Topic Name": page_number, ...}
    file_size = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class CommunityPost(Base):
    """A post inside a study-group community feed."""
    __tablename__ = 'community_posts'
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, index=True)          # 0-4 cluster id
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    author_name = Column(String, default='Anonymous')
    content = Column(String, nullable=False)
    tag = Column(String, nullable=True, default='discussion')  # question|tip|discussion
    likes = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    comments = relationship('CommunityComment', back_populates='post',
                            cascade='all, delete-orphan')


class CommunityComment(Base):
    """A reply/comment on a CommunityPost."""
    __tablename__ = 'community_comments'
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey('community_posts.id'), index=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    author_name = Column(String, default='Anonymous')
    content = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    post = relationship('CommunityPost', back_populates='comments')


class DocumentChunk(Base):
    """A chunked piece of a study material, with its Ollama embedding stored as a JSON array.

    The RAG pipeline embeds these on upload and does numpy cosine-similarity
    search at query time — no separate vector-DB required.
    """
    __tablename__ = 'document_chunks'
    id            = Column(Integer, primary_key=True)
    user_id       = Column(Integer, ForeignKey('users.id'), index=True)
    material_id   = Column(Integer, ForeignKey('study_materials.id', ondelete='CASCADE'), index=True)
    subject       = Column(String, nullable=True)
    filename      = Column(String, nullable=True)
    chunk_index   = Column(Integer, nullable=False, default=0)
    content       = Column(Text, nullable=False)
    embedding     = Column(JSON, nullable=True)   # list[float] from nomic-embed-text
    created_at    = Column(DateTime(timezone=True), server_default=func.now())


class SubjectAnalysis(Base):
    """LLM-powered curriculum analysis of an uploaded study material.

    Stores the full output of syllabus_intelligence.analyze_syllabus() as JSON:
    units, topics, difficulty estimates, prerequisite chains, key concepts.
    Auto-created on first container start (no migration required).
    """
    __tablename__ = 'subject_analyses'
    id          = Column(Integer, primary_key=True)
    material_id = Column(Integer, ForeignKey('study_materials.id', ondelete='CASCADE'),
                         unique=True, index=True)
    user_id     = Column(Integer, ForeignKey('users.id'), index=True)
    subject     = Column(String, nullable=True)
    analysis_json = Column(JSON, nullable=True)   # full analyze_syllabus() result
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class ScheduledTopic(Base):
    """Hierarchical topic structure with scheduling metadata.
    
    Represents: Subject → Unit → Topic with scheduling info.
    Created during syllabus extraction and updated as topics are scheduled/completed.
    """
    __tablename__ = 'scheduled_topics'
    id                  = Column(Integer, primary_key=True)
    user_id             = Column(Integer, ForeignKey('users.id'), index=True)
    material_id         = Column(Integer, ForeignKey('study_materials.id', ondelete='CASCADE'), index=True)
    subject             = Column(String, index=True, nullable=False)  # e.g., "Computer Networks"
    subject_code        = Column(String, nullable=True)  # e.g., "CS301"
    unit_name           = Column(String, index=True, nullable=False)  # e.g., "UNIT-1"
    unit_index          = Column(Integer, nullable=False, default=0)  # 0-indexed order within subject
    topic_name          = Column(String, nullable=False)  # e.g., "OSI Model"
    topic_index         = Column(Integer, nullable=False, default=0)  # 0-indexed order within unit
    page_number         = Column(Integer, nullable=True)  # reference page in original PDF
    estimated_hours     = Column(Float, nullable=True, default=1.0)  # LLM-estimated learning time
    difficulty          = Column(String, nullable=True, default='Medium')  # Easy|Medium|Hard
    
    # Scheduling & completion tracking
    scheduled_date      = Column(DateTime(timezone=True), nullable=True)  # when topic should be studied
    completed_date      = Column(DateTime(timezone=True), nullable=True)  # when user marked complete
    rescheduled_date    = Column(DateTime(timezone=True), nullable=True)  # last rescheduled timestamp
    status              = Column(String, default='pending', index=True)  # pending|completed|rescheduled|skipped
    completion_notes    = Column(String, nullable=True)  # user notes on completion
    
    # Metadata
    created_at          = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at          = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('material_id', 'subject', 'unit_name', 'topic_name', name='uq_scheduled_topic'),
    )
