# app/main.py
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from .database import create_db_and_tables # Functie om tabellen te maken
from .config import settings # Importeer settings
from .routes import ui, api # Importeer de routers

# Maak database tabellen aan bij opstarten (indien ze niet bestaan)
# In een productie-setup zou je Alembic migrations gebruiken.
create_db_and_tables() 

app = FastAPI(
    title="Google Analytics Benchmark Tool",
    description="Een tool om benchmarks te genereren en op te slaan van Google Analytics data.",
    version="1.0.0"
)

# Middleware
app.add_middleware(
    SessionMiddleware, 
    secret_key=settings.SESSION_SECRET_KEY # Gebruik de key uit settings
)

# Routers
app.include_router(ui.router, tags=["User Interface"])
app.include_router(api.router, tags=["API"])

# Optioneel: een simpele root endpoint voor de API
@app.get("/api/health", tags=["API Health"])
async def health_check():
    return {"status": "ok"}

# Voor lokaal draaien met `python app/main.py` (niet ideaal voor productie)
if __name__ == "__main__":
    import uvicorn
    print(f"Starting Uvicorn server. Loaded settings: SESSION_SECRET_KEY='{settings.SESSION_SECRET_KEY[:5]}...'")
    print(f"DATABASE_URL: {settings.DATABASE_URL}")
    uvicorn.run(app, host="0.0.0.0", port=8000)