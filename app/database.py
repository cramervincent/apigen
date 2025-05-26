# app/database.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from .config import settings

DATABASE_URL = settings.DATABASE_URL

engine_args = {}
if DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class BenchmarkReportDB(Base):
    __tablename__ = "benchmark_reports"
    id = Column(Integer, primary_key=True, index=True)
    report_uuid = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, index=True, nullable=False, default="Naamloze Benchmark")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Nieuwe velden voor Klant A en Benchmark properties
    client_a_property_id = Column(String, nullable=True) 
    benchmark_property_ids_json = Column(Text, nullable=True) # JSON string lijst van benchmark property IDs

    # Oude velden (kunnen eventueel later opgeschoond worden of blijven voor legacy data)
    property_ids_used = Column(Text, nullable=True) # Comma-separated string (legacy)

    metrics_used = Column(Text) # JSON string lijst van metric API namen
    dimensions_used = Column(Text) # JSON string lijst van dimension API namen
    
    # benchmark_data_json zal nu de nieuwe platte structuur bevatten
    benchmark_data_json = Column(Text) 
    generated_by_email = Column(String, nullable=True, index=True)

def create_db_and_tables():
    Base.metadata.create_all(bind=engine)
