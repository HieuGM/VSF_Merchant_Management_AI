from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    Date,
    Float,
    ForeignKey,
    Integer,
    Index,
    Numeric,
    String,
    Text,
    Time,
    TIMESTAMP,
    event,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import relationship
from database.connection import Base
from models.merchant_agentic import normalize_city_slugs
from services.geo.h3_index import H3CandidateIndex


_H3_INDEXES = {
    6: H3CandidateIndex(resolution=6),
    8: H3CandidateIndex(resolution=8),
    9: H3CandidateIndex(resolution=9),
}

class Merchant(Base):
    __tablename__ = "merchants"
    
    merchant_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    cuisine = Column(String, nullable=False)
    category = Column(Text)
    address = Column(String)
    lat = Column(Float)
    lng = Column(Float)
    h3_index_6 = Column(String(32), index=True)
    merchant_h3_cell = Column(String(32), index=True)
    h3_index_9 = Column(String(32), index=True)
    opens_at = Column(Time)
    closes_at = Column(Time)
    timezone = Column(String, nullable=False, default="Asia/Ho_Chi_Minh")
    taste_tags = Column(ARRAY(Text), nullable=False, default=list)
    diet_tags = Column(ARRAY(Text), nullable=False, default=list)
    ingredient_tags = Column(ARRAY(Text), nullable=False, default=list)
    customer_segments = Column(ARRAY(Text), nullable=False, default=list)
    city = Column(String, nullable=False)
    city_slug = Column(String, nullable=False)
    source = Column(String, default="shopeefood")
    source_url = Column(String)
    is_active = Column(Boolean, nullable=False, default=True)
    is_demo_target = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("CURRENT_TIMESTAMP"))
    updated_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        CheckConstraint(
            "(lat IS NULL AND lng IS NULL) OR (lat IS NOT NULL AND lng IS NOT NULL)",
            name="ck_merchants_coordinate_pair",
        ),
        CheckConstraint("lat IS NULL OR lat BETWEEN -90 AND 90", name="ck_merchants_lat"),
        CheckConstraint("lng IS NULL OR lng BETWEEN -180 AND 180", name="ck_merchants_lng"),
    )
    
    menu_items = relationship("MenuItem", back_populates="merchant", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="merchant", cascade="all, delete-orphan")
    delivery_feedbacks = relationship("DeliveryFeedback", back_populates="merchant", cascade="all, delete-orphan")
    food_images = relationship("FoodImage", back_populates="merchant", cascade="all, delete-orphan")


@event.listens_for(Merchant, "before_insert")
@event.listens_for(Merchant, "before_update")
def _synchronize_merchant_h3_cell(_mapper, _connection, merchant: Merchant) -> None:
    """Keep persisted location fields canonical when a merchant changes."""
    if merchant.city_slug:
        merchant.city_slug = normalize_city_slugs(merchant.city_slug) or merchant.city_slug
    elif merchant.city:
        merchant.city_slug = normalize_city_slugs(merchant.city)
    has_location = merchant.lat is not None and merchant.lng is not None
    merchant.h3_index_6 = (
        _H3_INDEXES[6].cell_for(merchant.lat, merchant.lng) if has_location else None
    )
    merchant.merchant_h3_cell = (
        _H3_INDEXES[8].cell_for(merchant.lat, merchant.lng) if has_location else None
    )
    merchant.h3_index_9 = (
        _H3_INDEXES[9].cell_for(merchant.lat, merchant.lng) if has_location else None
    )

class MenuItem(Base):
    __tablename__ = "menu_items"
    
    item_id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    price = Column(Integer, nullable=False)
    description = Column(String)
    category = Column(String)
    image_url = Column(String)
    discount_price = Column(Integer)
    total_like = Column(Integer, nullable=False, default=0)
    has_photo = Column(Boolean, nullable=False, default=False)
    is_available = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_menu_items_price"),
        CheckConstraint(
            "discount_price IS NULL OR discount_price >= 0",
            name="ck_menu_items_discount_price",
        ),
        CheckConstraint("total_like >= 0", name="ck_menu_items_total_like"),
    )
    
    merchant = relationship("Merchant", back_populates="menu_items")
    food_images = relationship("FoodImage", back_populates="menu_item", cascade="all, delete-orphan")

class Review(Base):
    __tablename__ = "reviews"
    
    review_id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), nullable=False)
    rating = Column(Numeric(4, 2))
    text = Column(Text, nullable=False)
    sentiment = Column(String, CheckConstraint("sentiment IN ('positive', 'negative', 'neutral')"))
    total_like = Column(Integer, default=0)
    source_page = Column(String)
    source_kind = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("rating IS NULL OR rating BETWEEN 0 AND 10", name="ck_reviews_rating"),
        CheckConstraint(
            "source_kind IN ('real', 'synthetic', 'heuristic', 'mixed', 'development_fixture')",
            name="ck_reviews_source_kind",
        ),
    )
    
    merchant = relationship("Merchant", back_populates="reviews")

class DeliveryFeedback(Base):
    __tablename__ = "delivery_feedbacks"
    
    feedback_id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), nullable=False)
    driver_id = Column(String, nullable=False)
    rating = Column(Integer, CheckConstraint("rating BETWEEN 1 AND 5"))
    comment = Column(Text)
    on_time = Column(Boolean)
    issue = Column(Text)
    source_kind = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('real', 'synthetic', 'heuristic', 'mixed', 'development_fixture')",
            name="ck_delivery_feedbacks_source_kind",
        ),
    )
    
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
    created_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("CURRENT_TIMESTAMP"))
    
    merchant = relationship("Merchant", back_populates="food_images")
    menu_item = relationship("MenuItem", back_populates="food_images")

class OperationalMetric(Base):
    __tablename__ = "operational_metrics"
    
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), primary_key=True)
    avg_prep_time_min = Column(Numeric(6, 2))
    cancel_rate = Column(Numeric(5, 4))
    acceptance_rate = Column(Numeric(5, 4))
    estimated_daily_orders = Column(Integer)
    peak_hours = Column(ARRAY(Text), nullable=False, default=list)
    avg_delivery_time_min = Column(Numeric(6, 2))
    on_time_rate = Column(Numeric(5, 4))
    driver_rating = Column(Numeric(3, 2))
    packaging_ok_rate = Column(Numeric(5, 4))
    source_kind = Column(String, nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        CheckConstraint(
            "avg_prep_time_min IS NULL OR avg_prep_time_min >= 0",
            name="ck_operational_metrics_prep",
        ),
        CheckConstraint(
            "cancel_rate IS NULL OR cancel_rate BETWEEN 0 AND 1",
            name="ck_operational_metrics_cancel_rate",
        ),
        CheckConstraint(
            "acceptance_rate IS NULL OR acceptance_rate BETWEEN 0 AND 1",
            name="ck_operational_metrics_acceptance_rate",
        ),
        CheckConstraint(
            "estimated_daily_orders IS NULL OR estimated_daily_orders >= 0",
            name="ck_operational_metrics_daily_orders",
        ),
        CheckConstraint(
            "avg_delivery_time_min IS NULL OR avg_delivery_time_min >= 0",
            name="ck_operational_metrics_delivery_time",
        ),
        CheckConstraint(
            "on_time_rate IS NULL OR on_time_rate BETWEEN 0 AND 1",
            name="ck_operational_metrics_on_time_rate",
        ),
        CheckConstraint(
            "driver_rating IS NULL OR driver_rating BETWEEN 0 AND 5",
            name="ck_operational_metrics_driver_rating",
        ),
        CheckConstraint(
            "packaging_ok_rate IS NULL OR packaging_ok_rate BETWEEN 0 AND 1",
            name="ck_operational_metrics_packaging_rate",
        ),
    )

class MerchantProfile(Base):
    __tablename__ = "merchant_profiles"

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
            "("
            "food_quality_score + image_quality_score + delivery_quality_score + "
            "packaging_score + service_score + waiting_time_score + "
            "menu_diversity_score + price_competitiveness_score"
            ") / 8.0",
            persisted=True,
        ),
    )
    scoring_version = Column(String, nullable=False)
    scored_at = Column(TIMESTAMP(timezone=True), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        CheckConstraint("tier IN ('hero', 'background')", name="ck_merchant_profiles_tier"),
        CheckConstraint(
            "price_level IN ('rẻ', 'trung bình', 'cao cấp')",
            name="ck_merchant_profiles_price_level",
        ),
        *tuple(
            CheckConstraint(
                f"{name} BETWEEN 0 AND 1",
                name=f"ck_merchant_profiles_{name}",
            )
            for name in (
                "food_quality_score",
                "image_quality_score",
                "delivery_quality_score",
                "packaging_score",
                "service_score",
                "waiting_time_score",
                "menu_diversity_score",
                "price_competitiveness_score",
            )
        ),
    )


class MerchantRating(Base):
    __tablename__ = "merchant_ratings"

    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), primary_key=True)
    shopeefood_rating = Column(Numeric(3, 2))
    shopeefood_review_count = Column(Integer)
    foody_rating = Column(Numeric(4, 2))
    foody_review_count = Column(Integer)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        CheckConstraint(
            "shopeefood_rating IS NULL OR shopeefood_rating BETWEEN 0 AND 5",
            name="ck_merchant_ratings_shopeefood",
        ),
        CheckConstraint(
            "foody_rating IS NULL OR foody_rating BETWEEN 0 AND 10",
            name="ck_merchant_ratings_foody",
        ),
        CheckConstraint(
            "shopeefood_review_count IS NULL OR shopeefood_review_count >= 0",
            name="ck_merchant_ratings_shopeefood_count",
        ),
        CheckConstraint(
            "foody_review_count IS NULL OR foody_review_count >= 0",
            name="ck_merchant_ratings_foody_count",
        ),
    )


class MerchantDimensionCalculation(Base):
    __tablename__ = "merchant_dimension_calculations"

    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), primary_key=True)
    dimension = Column(String, primary_key=True)
    basis = Column(Text, nullable=False)
    source_kind = Column(String, nullable=False)
    scoring_version = Column(String, nullable=False)
    calculated_at = Column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "dimension IN ('food_quality', 'image_quality', 'delivery_quality', "
            "'packaging', 'service', 'waiting_time', 'menu_diversity', "
            "'price_competitiveness')",
            name="ck_dimension_calculations_dimension",
        ),
        CheckConstraint(
            "source_kind IN ('real', 'synthetic', 'heuristic', 'mixed', "
            "'development_fixture')",
            name="ck_dimension_calculations_source",
        ),
    )


class MerchantDimensionEvidence(Base):
    __tablename__ = "merchant_dimension_evidence"

    evidence_id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), nullable=False)
    dimension = Column(String, nullable=False)
    evidence_type = Column(String, nullable=False)
    value_numeric = Column(Numeric)
    value_text = Column(Text)
    value_boolean = Column(Boolean)
    unit = Column(String)
    reference_type = Column(String)
    reference_ids = Column(ARRAY(Text), nullable=False, default=list)
    source_kind = Column(String, nullable=False)
    observed_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        CheckConstraint(
            "dimension IN ('food_quality', 'image_quality', 'delivery_quality', "
            "'packaging', 'service', 'waiting_time', 'menu_diversity', "
            "'price_competitiveness')",
            name="ck_dimension_evidence_dimension",
        ),
        CheckConstraint(
            "source_kind IN ('real', 'synthetic', 'heuristic', 'mixed', "
            "'development_fixture')",
            name="ck_dimension_evidence_source",
        ),
        CheckConstraint(
            "num_nonnulls(value_numeric, value_text, value_boolean) = 1",
            name="ck_dimension_evidence_one_value",
        ),
    )


class MerchantComplaint(Base):
    __tablename__ = "merchant_complaints"

    complaint_id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), nullable=False)
    category = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    occurred_on = Column(Date)
    review_id = Column(String, ForeignKey("reviews.review_id", ondelete="SET NULL"))
    source_kind = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        CheckConstraint(
            "category IN ('giao_hàng_trễ', 'món_nguội', "
            "'sai_hoặc_thiếu_món', 'đóng_gói_kém', 'thái_độ_phục_vụ', "
            "'giá_cao', 'vệ_sinh', 'chất_lượng_món')",
            name="ck_merchant_complaints_category",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high')",
            name="ck_merchant_complaints_severity",
        ),
        CheckConstraint(
            "source_kind IN ('real', 'synthetic', 'heuristic', 'mixed', "
            "'development_fixture')",
            name="ck_merchant_complaints_source",
        ),
    )


class MarketTrendingDish(Base):
    __tablename__ = "market_trending_dishes"

    city_slug = Column(String, primary_key=True)
    cuisine = Column(String, primary_key=True)
    dish_name = Column(Text, primary_key=True)
    trend_score = Column(Numeric, nullable=False)
    rank = Column(Integer, nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        CheckConstraint("rank > 0", name="ck_market_trending_dishes_rank"),
    )

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
    __table_args__ = (
        Index(
            "uq_agent_events_trace_semantic_seq",
            "trace_id",
            "seq",
            unique=True,
            postgresql_where=sa_text("seq IS NOT NULL"),
        ),
    )

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
    # Semantic timeline v2.  These remain nullable so existing legacy trace
    # events and already-running deployments continue to be readable.
    seq = Column(Integer)
    span_id = Column(String)
    parent_span_id = Column(String)
    phase = Column(String)
    kind = Column(String)
    actor_type = Column(String)
    actor_name = Column(String)
    metrics_json = Column(JSONB)
    debug_payload_json = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=False), server_default=sa_text("CURRENT_TIMESTAMP"))
