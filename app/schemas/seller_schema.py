from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from decimal import Decimal

class ProductCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Nama produk")
    description: Optional[str] = None
    price: Decimal = Field(..., ge=0, description="Harga harus >= 0")
    stock: int = Field(..., ge=0, description="Stok harus >= 0")
    category_id: int = Field(..., description="ID Kategori produk")
    image_url: Optional[str] = Field(None, description="URL gambar produk dari Supabase Storage")

class ProductUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Nama produk")
    description: Optional[str] = None
    price: Decimal = Field(..., ge=0, description="Harga harus >= 0")
    stock: int = Field(..., ge=0, description="Stok harus >= 0")
    category_id: int = Field(..., description="ID Kategori produk")

class SellerProductResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    price: Decimal
    stock: int
    category_name: str
    image_url: Optional[str] = None
    is_deleted: bool

    model_config = ConfigDict(from_attributes=True)

class CategoryResponse(BaseModel):
    id: int
    name: str
    slug: str

    model_config = ConfigDict(from_attributes=True)
