# app/web.py
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="RT-AI QA UI (primer paso)")

# Servir archivos estáticos (CSS, imágenes, etc.)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Carpeta donde estarán las plantillas HTML
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """
    Ruta principal: solo muestra una página sencilla.
    """
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "message": "Hola Paola, FastAPI ya está vivo 🚀",
            "result": None,
            "error": None,
        },
    )
