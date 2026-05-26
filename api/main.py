# api/main.py

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from api.routers import cars, costs, reports, predictions

app = FastAPI(
    title="Japan Car Import Calculator",
    description="Compare the cost and expensees of importing cars from Japan vs buying locally in Kenya. Get insights on top deals and market trends.",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Include routers
app.include_router(cars.router, prefix="/api")
app.include_router(costs.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(predictions.router, prefix="/api")


@app.get("/")
def root():
    return {"message": "Japan Car Import Calculator API", "docs": "/docs"}


@app.get("/health")
def health_check():
    return {"status": "ok"}