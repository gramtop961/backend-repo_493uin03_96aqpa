"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    username: str = Field(..., description="Unique username")
    password_hash: str = Field(..., description="Hashed password (bcrypt)")
    display_name: Optional[str] = Field(None, description="Display name for the desktop")
    wallpaper: Optional[str] = Field(None, description="Wallpaper image URL or preset key")
    settings: Dict[str, Optional[str]] = Field(default_factory=dict, description="User settings like theme, accent color")
    tokens: List[str] = Field(default_factory=list, description="Active session tokens")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Add your own schemas here if needed.
