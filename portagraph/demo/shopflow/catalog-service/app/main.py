"""HTTP API каталога товаров."""
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Product

app = FastAPI(title="ShopFlow Catalog")


@app.get("/api/v1/products")
def list_products(session: Session = Depends(get_session)):
    return [p.__dict__ for p in session.query(Product).filter(Product.stock > 0).limit(100)]


@app.get("/api/v1/products/{sku}")
def get_product(sku: str, session: Session = Depends(get_session)):
    product = session.query(Product).filter_by(sku=sku).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return product.__dict__


@app.post("/api/v1/products/{sku}/reserve")
def reserve(sku: str, quantity: int, session: Session = Depends(get_session)):
    product = session.query(Product).filter_by(sku=sku).with_for_update().first()
    if product is None or product.stock < quantity:
        raise HTTPException(status_code=409, detail="Недостаточно товара")
    product.stock -= quantity
    session.commit()
    return {"sku": sku, "left": product.stock}
