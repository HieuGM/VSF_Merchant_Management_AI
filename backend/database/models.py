import datetime
from sqlalchemy import Column, String, Float, Integer, ForeignKey, TIMESTAMP, CheckConstraint, text as sa_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from database.connection import Base

class Merchant(Base):
    __tablename__ = "merchants"
    
    merchant_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    cuisine = Column(String, nullable=False)
    address = Column(String)
    lat = Column(Float)
    lng = Column(Float)
    open_hours = Column(JSONB)
    city = Column(String, nullable=False)
    city_slug = Column(String, nullable=False)
    source = Column(String, default="shopeefood")
    source_url = Column(String)
    is_demo_target = Column(Integer, default=0)
    created_at = Column(TIMESTAMP(timezone=False), server_default=sa_text("CURRENT_TIMESTAMP"))
    
    menu_items = relationship("MenuItem", back_populates="merchant", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="merchant", cascade="all, delete-orphan")
    delivery_feedbacks = relationship("DeliveryFeedback", back_populates="merchant", cascade="all, delete-orphan")
    food_images = relationship("FoodImage", back_populates="merchant", cascade="all, delete-orphan")

class MenuItem(Base):
    __tablename__ = "menu_items"
    
    item_id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    price = Column(Integer, nullable=False)
    description = Column(String)
    category = Column(String)
    image_url = Column(String)
    diet_tags = Column(JSONB)
    ingredient_tags = Column(JSONB)
    taste_tags = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=False), server_default=sa_text("CURRENT_TIMESTAMP"))
    
    merchant = relationship("Merchant", back_populates="menu_items")
    food_images = relationship("FoodImage", back_populates="menu_item", cascade="all, delete-orphan")

class Review(Base):
    __tablename__ = "reviews"
    
    review_id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), nullable=False)
    foody_restaurant_id = Column(Integer)
    rating = Column(Float)
    text = Column(String, nullable=False)
    sentiment = Column(String, CheckConstraint("sentiment IN ('positive', 'negative', 'neutral')"))
    author_id = Column(String)
    author_name = Column(String)
    total_like = Column(Integer, default=0)
    total_comment = Column(Integer, default=0)
    total_pictures = Column(Integer, default=0)
    review_url = Column(String)
    source_page = Column(String)
    comments_json = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=False), nullable=False)
    
    merchant = relationship("Merchant", back_populates="reviews")

class DeliveryFeedback(Base):
    __tablename__ = "delivery_feedbacks"
    
    feedback_id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), nullable=False)
    driver_id = Column(String, nullable=False)
    rating = Column(Integer, CheckConstraint("rating BETWEEN 1 AND 5"))
    comment = Column(String)
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
    
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), primary_key=True)
    avg_prep_time_min = Column(Float, default=12.0)
    peak_hours = Column(JSONB)

class MerchantProfile(Base):
    __tablename__ = "merchant_profiles"
    
    merchant_id = Column(String, ForeignKey("merchants.merchant_id", ondelete="CASCADE"), primary_key=True)
    dimensions_json = Column(JSONB, nullable=False)
    updated_at = Column(TIMESTAMP(timezone=False), server_default=sa_text("CURRENT_TIMESTAMP"))

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
    timestamp = Column(TIMESTAMP(timezone=False), server_default=sa_text("CURRENT_TIMESTAMP"))
    
    session = relationship("ChatSession", back_populates="chat_messages")
