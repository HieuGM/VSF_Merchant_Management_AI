import datetime
from sqlalchemy import (
    Column, String, Float, Integer, Boolean, Numeric, Time, Date,
    ForeignKey, TIMESTAMP, CheckConstraint, Computed,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import relationship
from database.connection import Base

# Relational schema per docs/2026-07-23-merchant-relational-schema-design.md
# Migration chain: 026b4a8e16d0 → a1b2c3d4e5f6 → b1c2d3e4f5a6 → c2d3e4f5a6b7
_TZ = TIMESTAMP(timezone=True)

class Merchant(Base):
    __tablename__ = "merchants"
    __table_args__ = (
        CheckConstraint(
            "(lat IS NULL AND lng IS NULL) OR (lat IS NOT NULL AND lng IS NOT NULL)",
            name="ck_merchants_coord_pair",
        ),
        CheckConstraint("lat IS NULL OR (lat >= -90 AND lat <= 90)", name="ck_merchants_lat_range"),
        CheckConstraint("lng IS NULL OR (lng >= -180 AND lng <= 180)", name="ck_merchants_lng_range"),
    )

    merchant_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    cuisine = Column(String, nullable=False)
    category = Column(String)
    address = Column(String)
    city = Column(String, nullable=False)
    city_slug = Column(String, nullable=False)
    lat = Column(Float)
    lng = Column(Float)
    opens_at = Column(Time)
    closes_at = Column(Time)
    timezone = Column(String, nullable=False, server_default=sa_text("'Asia/Ho_Chi_Minh'"))
    taste_tags = Column(ARRAY(String), nullable=False, server_default=sa_text("'{}'"))
    diet_tags = Column(ARRAY(String), nullable=False, server_default=sa_text("'{}'"))
    ingredient_tags = Column(ARRAY(String), nullable=False, server_default=sa_text("'{}'"))
    customer_segments = Column(ARRAY(String), nullable=False, server_default=sa_text("'{}'"))
    source = Column(String)
    source_url = Column(String)
    is_active = Column(Boolean, nullable=False, server_default=sa_text("true"))
    is_demo_target = Column(Boolean, nullable=False, server_default=sa_text("false"))
    created_at = Column(_TZ, nullable=False, server_default=sa_text("now()"))
    updated_at = Column(_TZ, nullable=False, server_default=sa_text("now()"))

    menu_items = relationship("MenuItem", back_populates="merchant", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="merchant", cascade="all, delete-orphan")
    delivery_feedbacks = relationship("DeliveryFeedback", back_populates="merchant", cascade="all, delete-orphan")
    food_images = relationship("FoodImage", back_populates="merchant", cascade="all, delete-orphan")
    ratings = relationship("MerchantRating", back_populates="merchant", uselist=False, cascade="all, delete-orphan")
    complaints = relationship("MerchantComplaint", back_populates="merchant", cascade="all, delete-orphan")

class MenuItem(Base):
    __tablename__ = "menu_items"
    __table_args__ = (
        CheckConstraint("discount_price IS NULL OR discount_price >= 0", name="ck_menu_items_discount_price"),
    )

    item_id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    price = Column(Integer, nullable=False)
    discount_price = Column(Integer)
    description = Column(String)
    category = Column(String)
    image_url = Column(String)
    total_like = Column(Integer, nullable=False, server_default=sa_text("0"))
    has_photo = Column(Boolean, nullable=False, server_default=sa_text("false"))
    is_available = Column(Boolean, nullable=False, server_default=sa_text("true"))
    created_at = Column(TIMESTAMP(timezone=False), server_default=sa_text("CURRENT_TIMESTAMP"))

    merchant = relationship("Merchant", back_populates="menu_items")
    food_images = relationship("FoodImage", back_populates="menu_item", cascade="all, delete-orphan")

class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint(
            "rating IS NULL OR (rating >= 0 AND rating <= 10)",
            name="ck_reviews_rating_range",
        ),
        CheckConstraint(
            "source_kind IN ('real', 'synthetic')",
            name="ck_reviews_source_kind",
        ),
    )

    review_id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), nullable=False)
    foody_restaurant_id = Column(Integer)
    rating = Column(Numeric(4, 2))
    text = Column(String, nullable=False)
    sentiment = Column(String, CheckConstraint("sentiment IN ('positive', 'negative', 'neutral')"))
    author_id = Column(String)
    author_name = Column(String)
    total_like = Column(Integer, default=0)
    total_comment = Column(Integer, default=0)
    total_pictures = Column(Integer, default=0)
    review_url = Column(String)
    source_page = Column(String)
    source_kind = Column(String, nullable=False, server_default=sa_text("'real'"))
    created_at = Column(TIMESTAMP(timezone=False), nullable=False)

    merchant = relationship("Merchant", back_populates="reviews")

class DeliveryFeedback(Base):
    __tablename__ = "delivery_feedbacks"
    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('real', 'synthetic', 'heuristic', 'mixed', 'development_fixture')",
            name="ck_delivery_feedbacks_source_kind",
        ),
    )

    feedback_id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), nullable=False)
    driver_id = Column(String, nullable=False)
    rating = Column(Integer, CheckConstraint("rating BETWEEN 1 AND 5"))
    comment = Column(String)
    on_time = Column(Boolean)
    issue = Column(String)
    source_kind = Column(String, nullable=False, server_default=sa_text("'synthetic'"))
    created_at = Column(TIMESTAMP(timezone=False), nullable=False)

    merchant = relationship("Merchant", back_populates="delivery_feedbacks")

class FoodImage(Base):
    __tablename__ = "food_images"
    
    image_id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), nullable=False)
    item_id = Column(String, ForeignKey("menu_items.item_id", ondelete="SET NULL"))
    url = Column(String, nullable=False)
    dish_image_quality = Column(Float, CheckConstraint("dish_image_quality BETWEEN 0 AND 1"))
    logo_quality = Column(Float, CheckConstraint("logo_quality BETWEEN 0 AND 1"))
    blur_score = Column(Float, CheckConstraint("blur_score BETWEEN 0 AND 1"))
    created_at = Column(TIMESTAMP(timezone=False), server_default=sa_text("CURRENT_TIMESTAMP"))
    
    merchant = relationship("Merchant", back_populates="food_images")
    menu_item = relationship("MenuItem", back_populates="food_images")

class OperationalMetric(Base):
    __tablename__ = "operational_metrics"
    __table_args__ = (
        CheckConstraint("avg_prep_time_min IS NULL OR avg_prep_time_min >= 0", name="ck_opmetrics_prep_time"),
        CheckConstraint("estimated_daily_orders IS NULL OR estimated_daily_orders >= 0", name="ck_opmetrics_daily_orders"),
        CheckConstraint("avg_delivery_time_min IS NULL OR avg_delivery_time_min >= 0", name="ck_opmetrics_delivery_time"),
    )

    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), primary_key=True)
    avg_prep_time_min = Column(Numeric(6, 2))
    cancel_rate = Column(Numeric(5, 4))
    acceptance_rate = Column(Numeric(5, 4))
    estimated_daily_orders = Column(Integer)
    peak_hours = Column(ARRAY(String), nullable=False, server_default=sa_text("'{}'"))
    avg_delivery_time_min = Column(Numeric(6, 2))
    on_time_rate = Column(Numeric(5, 4))
    driver_rating = Column(Numeric(3, 2))
    packaging_ok_rate = Column(Numeric(5, 4))
    source_kind = Column(String, nullable=False, server_default=sa_text("'synthetic'"))
    updated_at = Column(_TZ, nullable=False, server_default=sa_text("now()"))


class MerchantRating(Base):
    """External platform rating facts (migration b1c2d3e4f5a6). One row/merchant."""
    __tablename__ = "merchant_ratings"

    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), primary_key=True)
    shopeefood_rating = Column(Numeric(3, 2))  # 0..5
    shopeefood_review_count = Column(Integer)
    foody_rating = Column(Numeric(4, 2))  # 0..10
    foody_review_count = Column(Integer)
    updated_at = Column(_TZ, server_default=sa_text("now()"))

    merchant = relationship("Merchant", back_populates="ratings")


class MerchantProfile(Base):
    """Current eight computed dimensions and profile classification. One row per merchant.
    `overall_score_internal` is a DB-generated column — NEVER serialize to API/agent output.
    """
    __tablename__ = "merchant_profiles"
    __table_args__ = (
        CheckConstraint("tier IN ('hero', 'background')", name="ck_merchant_profiles_tier"),
        CheckConstraint("price_level IN ('rẻ', 'trung bình', 'cao cấp')", name="ck_merchant_profiles_price_level"),
    )

    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), primary_key=True)
    tier = Column(String, nullable=False)
    price_level = Column(String, nullable=False)
    food_quality_score = Column(Numeric(4, 3), nullable=False)
    image_quality_score = Column(Numeric(4, 3), nullable=False)
    delivery_quality_score = Column(Numeric(4, 3), nullable=False)
    packaging_score = Column(Numeric(4, 3), nullable=False)
    service_score = Column(Numeric(4, 3), nullable=False)
    waiting_time_score = Column(Numeric(4, 3), nullable=False)
    menu_diversity_score = Column(Numeric(4, 3), nullable=False)
    price_competitiveness_score = Column(Numeric(4, 3), nullable=False)
    overall_score_internal = Column(
        Numeric(4, 3),
        Computed(
            "ROUND(("
            "food_quality_score + image_quality_score + delivery_quality_score + "
            "packaging_score + service_score + waiting_time_score + "
            "menu_diversity_score + price_competitiveness_score"
            ") / 8, 3)",
            persisted=True,
        ),
    )
    scoring_version = Column(String, nullable=False)
    scored_at = Column(_TZ, nullable=False)
    updated_at = Column(_TZ, nullable=False, server_default=sa_text("now()"))


class MerchantDimensionCalculation(Base):
    """How each current dimension was calculated. Exactly 8 rows per complete profile."""
    __tablename__ = "merchant_dimension_calculations"
    __table_args__ = (
        CheckConstraint(
            "dimension IN ('food_quality', 'image_quality', 'delivery_quality', "
            "'packaging', 'service', 'waiting_time', 'menu_diversity', 'price_competitiveness')",
            name="ck_dim_calc_dimension",
        ),
        CheckConstraint(
            "source_kind IN ('real', 'synthetic', 'heuristic', 'mixed', 'development_fixture')",
            name="ck_dim_calc_source_kind",
        ),
    )

    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), primary_key=True)
    dimension = Column(String, primary_key=True)
    basis = Column(String, nullable=False)
    source_kind = Column(String, nullable=False)
    scoring_version = Column(String, nullable=False)
    calculated_at = Column(_TZ, nullable=False)


class MerchantDimensionEvidence(Base):
    """Typed scalar evidence facts. Exactly one of value_numeric/value_text/value_boolean must be set."""
    __tablename__ = "merchant_dimension_evidence"
    __table_args__ = (
        CheckConstraint(
            "dimension IN ('food_quality', 'image_quality', 'delivery_quality', "
            "'packaging', 'service', 'waiting_time', 'menu_diversity', 'price_competitiveness')",
            name="ck_dim_evidence_dimension",
        ),
        CheckConstraint(
            "source_kind IN ('real', 'synthetic', 'heuristic', 'mixed', 'development_fixture')",
            name="ck_dim_evidence_source_kind",
        ),
        CheckConstraint(
            "num_nonnulls(value_numeric, value_text, value_boolean) = 1",
            name="ck_dim_evidence_single_value",
        ),
    )

    evidence_id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), nullable=False)
    dimension = Column(String, nullable=False)
    evidence_type = Column(String, nullable=False)
    value_numeric = Column(Numeric)
    value_text = Column(String)
    value_boolean = Column(Boolean)
    unit = Column(String)
    reference_type = Column(String)
    reference_ids = Column(ARRAY(String), nullable=False, server_default=sa_text("'{}'"))
    source_kind = Column(String, nullable=False)
    observed_at = Column(_TZ)
    created_at = Column(_TZ, nullable=False, server_default=sa_text("now()"))


class MerchantComplaint(Base):
    """First-class complaint rows extracted from profile source data."""
    __tablename__ = "merchant_complaints"
    __table_args__ = (
        CheckConstraint(
            "category IN ('giao_hàng_trễ', 'món_nguội', 'sai_hoặc_thiếu_món', "
            "'đóng_gói_kém', 'thái_độ_phục_vụ', 'giá_cao', 'vệ_sinh', 'chất_lượng_món')",
            name="ck_complaints_category",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high')",
            name="ck_complaints_severity",
        ),
        CheckConstraint(
            "source_kind IN ('real', 'synthetic', 'heuristic', 'mixed', 'development_fixture')",
            name="ck_complaints_source_kind",
        ),
    )

    complaint_id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), nullable=False)
    category = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    text = Column(String, nullable=False)
    occurred_on = Column(Date)
    review_id = Column(String, ForeignKey("reviews.review_id", ondelete="SET NULL"))
    source_kind = Column(String, nullable=False)
    created_at = Column(_TZ, nullable=False, server_default=sa_text("now()"))

    merchant = relationship("Merchant", back_populates="complaints")


class MarketTrendingDish(Base):
    """Current market aggregate — one ranked set per city/cuisine market."""
    __tablename__ = "market_trending_dishes"
    __table_args__ = (
        CheckConstraint("rank > 0", name="ck_trending_rank_positive"),
    )

    city_slug = Column(String, primary_key=True)
    cuisine = Column(String, primary_key=True)
    dish_name = Column(String, primary_key=True)
    trend_score = Column(Numeric, nullable=False)
    rank = Column(Integer, nullable=False)
    updated_at = Column(_TZ, nullable=False, server_default=sa_text("now()"))


class UserProfile(Base):
    __tablename__ = "user_profiles"
    
    user_id = Column(String, primary_key=True)
    liked_cuisines = Column(JSONB)
    disliked_cuisines = Column(JSONB)
    spice_tolerance = Column(String, CheckConstraint("spice_tolerance IN ('none', 'mild', 'medium', 'hot')"))
    dietary = Column(JSONB)
    budget_level = Column(String, CheckConstraint("budget_level IN ('student', 'standard', 'premium')"))
    distance_preference_km = Column(Float, default=5.0)
    current_lat = Column(Float)
    current_lng = Column(Float)
    location_updated_at = Column(TIMESTAMP(timezone=False))
    context_memory = Column(JSONB)
    interaction_history = Column(JSONB)
    updated_at = Column(TIMESTAMP(timezone=False), server_default=sa_text("CURRENT_TIMESTAMP"))
    
    chat_sessions = relationship("ChatSession", back_populates="user")

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    
    session_id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("user_profiles.user_id", ondelete="SET NULL"))
    title = Column(String)
    # §6.2 extension: durable recovery snapshot (Redis stays hot copy)
    context_snapshot_json = Column(JSONB)
    last_trace_id = Column(String)
    created_at = Column(TIMESTAMP(timezone=False), server_default=sa_text("CURRENT_TIMESTAMP"))
    updated_at = Column(TIMESTAMP(timezone=False), server_default=sa_text("CURRENT_TIMESTAMP"))
    
    user = relationship("UserProfile", back_populates="chat_sessions")
    chat_messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    
    message_id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), nullable=False)
    sender = Column(String, CheckConstraint("sender IN ('user', 'agent')"))
    text = Column(String, nullable=False)
    # §6.2 extension: connect visible messages to results and traces
    trace_id = Column(String)
    structured_payload_json = Column(JSONB)
    timestamp = Column(TIMESTAMP(timezone=False), server_default=sa_text("CURRENT_TIMESTAMP"))

    session = relationship("ChatSession", back_populates="chat_messages")


# ---------------------------------------------------------------------------
# §6.2 runtime records added before agent integration (Phase 0 — FROZEN)
# ---------------------------------------------------------------------------
class PreferenceEvent(Base):
    """Append-only preference audit (§6.6). Never replaces user_profiles."""
    __tablename__ = "preference_events"

    event_id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("user_profiles.user_id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String)
    field = Column(String, nullable=False)
    operation = Column(String, nullable=False)
    value_json = Column(JSONB)
    scope = Column(String, nullable=False)
    source = Column(String, nullable=False)
    confidence = Column(Float, default=1.0)
    status = Column(String, default="candidate")
    evidence_refs_json = Column(JSONB)
    expires_at = Column(TIMESTAMP(timezone=False))
    created_at = Column(TIMESTAMP(timezone=False), server_default=sa_text("CURRENT_TIMESTAMP"))
    resolved_at = Column(TIMESTAMP(timezone=False))


class InteractionEvent(Base):
    """Append-only UI/chat signal (§11.7). Evidence only — cannot mutate profiles."""
    __tablename__ = "interaction_events"

    event_id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("user_profiles.user_id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String)
    event_type = Column(String, nullable=False)
    merchant_id = Column(String)
    menu_item_id = Column(String)
    metadata_json = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=False), server_default=sa_text("CURRENT_TIMESTAMP"))


class AgentRun(Base):
    """One record per CrewAI Flow run (§6.2 agent_runs)."""
    __tablename__ = "agent_runs"

    trace_id = Column(String, primary_key=True)
    session_id = Column(String)
    user_id = Column(String)
    crew_name = Column(String, nullable=False)
    intent = Column(String)
    status = Column(String, default="running")
    started_at = Column(TIMESTAMP(timezone=False), server_default=sa_text("CURRENT_TIMESTAMP"))
    finished_at = Column(TIMESTAMP(timezone=False))
    error_code = Column(String)
    token_usage_json = Column(JSONB)


class AgentEvent(Base):
    """Task/tool/delegation trace (§6.2 agent_events). Listener contract."""
    __tablename__ = "agent_events"

    event_id = Column(String, primary_key=True)
    trace_id = Column(String, ForeignKey("agent_runs.trace_id", ondelete="CASCADE"), nullable=False)
    parent_event_id = Column(String)
    event_type = Column(String, nullable=False)
    agent_name = Column(String)
    task_name = Column(String)
    tool_name = Column(String)
    input_hash = Column(String)
    output_summary_json = Column(JSONB)
    duration_ms = Column(Integer)
    status = Column(String, default="ok")
    error_code = Column(String)
    created_at = Column(TIMESTAMP(timezone=False), server_default=sa_text("CURRENT_TIMESTAMP"))
