# app/database.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base # Gebruik declarative_base voor oudere SQLAlchemy versies
# Voor SQLAlchemy 2.0 zou je from sqlalchemy.orm import DeclarativeBase gebruiken
# en class Base(DeclarativeBase): pass

from .config import settings # Importeer settings

DATABASE_URL = settings.DATABASE_URL

# Voor SQLite, specifieke connect_args
engine_args = {}
if DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base() # of Base = DeclarativeBase() voor SQLAlchemy 2.0

class BenchmarkReportDB(Base):
    __tablename__ = "benchmark_reports"
    id = Column(Integer, primary_key=True, index=True)
    report_uuid = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    property_ids_used = Column(Text) 
    metrics_used = Column(Text) 
    dimensions_used = Column(Text) 
    benchmark_data_json = Column(Text) 
    generated_by_email = Column(String, nullable=True)

def create_db_and_tables():
    Base.metadata.create_all(bind=engine)