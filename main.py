import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

from app.database import init_db
from app.routers import recipes, shopping, discover


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="Recipe Shopping List",
    description="Family recipe management and shopping list generator",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(recipes.router)
app.include_router(shopping.router)
app.include_router(discover.router)

# Templates
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page."""
    return templates.TemplateResponse("index.html", {"request": request})


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
