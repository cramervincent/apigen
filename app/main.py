# app/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware # NIEUW & CORRECT

from .database import create_db_and_tables
from .config import settings
from .routes import ui, api
from .styling import compile_scss

# Imports voor Alembic
from alembic.config import Config
from alembic import command
import traceback

# Compileer SCSS naar CSS bij opstarten
compile_scss()

# Database migraties uitvoeren met duidelijke logging
print("="*50)
print("CONTROLEREN EN UITVOEREN DATABASE MIGRATIES")
print("="*50)
try:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    command.upgrade(alembic_cfg, "head")
    print("✅ Migraties succesvol gecontroleerd en uitgevoerd.")
except Exception as e:
    print("❌ FOUT TIJDENS UITVOEREN VAN DATABASE MIGRATIES:")
    print(traceback.format_exc())
finally:
    print("="*50)
    print("Applicatie wordt nu verder opgestart...")


app = FastAPI(
    title="Google Analytics Benchmark Tool",
    description="Een tool om benchmarks te genereren en op te slaan van Google Analytics data.",
    version="1.0.0"
)

# Middleware
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY
)

# Mount static files directory
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Routers
app.include_router(ui.router, tags=["User Interface"])
app.include_router(api.router, tags=["API"])

@app.get("/api/health", tags=["API Health"])
async def health_check():
    return {"status": "ok"}

# Voor lokaal draaien
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)