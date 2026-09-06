from sqlmodel import SQLModel


class ProductCreate(SQLModel):
    name: str
    price: float
