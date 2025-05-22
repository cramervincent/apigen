# app/crud.py
import json
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from .database import BenchmarkReportDB # Importeer het DB model

def create_benchmark_report(
    db: Session, 
    property_ids: List[str],
    metrics_used: List[str], # API namen
    dimensions_used: List[str], # API namen
    benchmark_results: Dict[str, Any], # Het volledige resultaat dict
    user_email: Optional[str]
) -> BenchmarkReportDB:
    db_report = BenchmarkReportDB(
        property_ids_used=",".join(property_ids),
        metrics_used=json.dumps(metrics_used),
        dimensions_used=json.dumps(dimensions_used),
        benchmark_data_json=json.dumps(benchmark_results), # Sla volledige resultaten op
        generated_by_email=user_email
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report

def get_benchmark_report_by_uuid(db: Session, report_uuid: str) -> Optional[BenchmarkReportDB]:
    return db.query(BenchmarkReportDB).filter(BenchmarkReportDB.report_uuid == report_uuid).first()