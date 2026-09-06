from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO, StringIO
from typing import Annotated

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from database import create_db_and_tables, engine
from models import Product
from schemas import ProductCreate


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)

templates = Jinja2Templates(directory="templates")

ingredientes = ["arroz", "papas", "pollo", "pezcado", "tomates"]


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    client_ip = request.client.host
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "titulo": "Página de Inicio",
            "fecha_actual": datetime.now().strftime("%d-%m-%Y"),  # noqa: DTZ005
            "ingredientes": ingredientes,
            "client_ip": client_ip,
        },
    )


@app.post("/contestar", response_class=HTMLResponse)
async def saludar(nombre: Annotated[str, Form()], edad: Annotated[int, Form()]):
    return f"<p>Hola, {nombre}, tu edad es {edad}</p>"


@app.get("/hola", response_class=HTMLResponse)
async def hola():
    return "<p class='text-center'>Hola</p>"


from fastapi.responses import HTMLResponse


@app.post("/products", response_class=HTMLResponse)
def create_product(
    name: str = Form(...),
    price: float = Form(...),
):
    product_data = ProductCreate(
        name=name,
        price=price,
    )

    product = Product(
        name=product_data.name,
        price=product_data.price,
    )

    with Session(engine) as session:
        session.add(product)
        session.commit()
        session.refresh(product)

    return "Producto creado correctamente"


@app.get("/products/{product_id}", response_class=HTMLResponse)
def get_product(request: Request, product_id: int):
    with Session(engine) as session:
        product = session.get(Product, product_id)

        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")

        return templates.TemplateResponse(
            request=request,
            name="components/fila_producto.html",
            context={"product": product},
        )


@app.get("/products", response_class=HTMLResponse)
def get_products(request: Request, q: str = ""):
    """
    Cuando evolucione a filtros, utilizar esta clase de filtros.
        statement = select(Product)

    if q:
        statement = statement.where(Product.name.contains(q))

    if precio_min:
        statement = statement.where(Product.price >= precio_min)

    if precio_max:
        statement = statement.where(Product.price <= precio_max)

    products = session.exec(statement).all()
    """
    with Session(engine) as session:
        statement = select(Product)

        if q:
            statement = statement.where(Product.name.contains(q))

        products = session.exec(statement).all()

        return templates.TemplateResponse(
            request=request,
            name="components/listar_productos.html",
            context={"products": products},
        )


@app.get("/products/{product_id}/edit", response_class=HTMLResponse)
def edit_product_form(request: Request, product_id: int):
    with Session(engine) as session:
        product = session.get(Product, product_id)

        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")

        return templates.TemplateResponse(
            request=request,
            name="components/editar_producto.html",
            context={"product": product},
        )


@app.post("/products/{product_id}", response_class=HTMLResponse)
def update_product(
    request: Request,
    product_id: int,
    name: str = Form(...),
    price: float = Form(...),
):
    with Session(engine) as session:
        product = session.get(Product, product_id)

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Producto no encontrado"
            )

        product.name = name
        product.price = price

        session.add(product)
        session.commit()
        session.refresh(product)

        return templates.TemplateResponse(
            request=request,
            name="components/fila_producto.html",
            context={"product": product},
        )


@app.delete("/products/{product_id}")
def delete_product(product_id: int):
    with Session(engine) as session:
        product = session.get(Product, product_id)

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Producto no encontrado"
            )

        session.delete(product)
        session.commit()

    return Response(status_code=200)


# Crear endpoint para recibir y procesar archivos csv, excel y retornar texto
@app.post("/procesar", response_class=HTMLResponse)
async def procesar(file: UploadFile = File(...)):  # noqa: B008
    contenido = await file.read()

    if file.filename.endswith(".csv"):
        try:
            df = pd.read_csv(BytesIO(contenido), encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(BytesIO(contenido), encoding="cp1252")

    elif file.filename.endswith(".xlsx"):
        df = pd.read_excel(BytesIO(contenido))

    else:
        raise HTTPException(400, "Formato no soportado")

    # texto = df.to_string(index=False)
    texto = df.shape

    return f"""
    <pre class="rounded bg-gray-100 p-4 overflow-auto">{texto}</pre>
    """


# Crear endpoint para recibir archivo csv, excel y retornar archivo .xlsx
@app.post("/procesar_retornar")
async def procesar_retornar(file: UploadFile = File(...)):
    contenido = await file.read()

    if file.filename.endswith(".csv"):
        try:
            df = pd.read_csv(BytesIO(contenido), encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(BytesIO(contenido), encoding="cp1252")

    elif file.filename.endswith(".xlsx"):
        df = pd.read_excel(BytesIO(contenido))

    else:
        raise HTTPException(400, "Formato no soportado")

    # Procesar DataFrame
    df["procesado"] = True

    # Crear archivo Excel en memoria
    archivo = BytesIO()

    with pd.ExcelWriter(archivo, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)

    archivo.seek(0)

    return StreamingResponse(
        archivo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=resultado.xlsx"},
    )


# Crear endpoint para recibir archivo csv, excel y retornar archivo .csv
@app.post("/procesar_csv")
async def procesar_csv(file: UploadFile = File(...)):
    contenido = await file.read()

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Solo se aceptan archivos CSV")

    try:
        df = pd.read_csv(BytesIO(contenido), encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(BytesIO(contenido), encoding="cp1252")

    # Procesar DataFrame
    df["procesado"] = True

    # Crear CSV en memoria
    archivo = BytesIO()
    df.to_csv(archivo, index=False, encoding="utf-8")
    archivo.seek(0)

    return StreamingResponse(
        archivo,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=resultado.csv"},
    )
