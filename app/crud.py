# app/crud.py
import json
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc # Importeer desc voor sorteren
from .database import BenchmarkReportDB

def create_benchmark_report(
    db: Session, 
    title: str, # NIEUW
    property_ids: List[str],
    metrics_used: List[str],
    dimensions_used: List[str],
    benchmark_results: Dict[str, Any],
    user_email: Optional[str]
) -> BenchmarkReportDB:
    db_report = BenchmarkReportDB(
        title=title, # NIEUW
        property_ids_used=",".join(property_ids),
        metrics_used=json.dumps(metrics_used),
        dimensions_used=json.dumps(dimensions_used),
        benchmark_data_json=json.dumps(benchmark_results),
        generated_by_email=user_email
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report

def get_benchmark_report_by_uuid(db: Session, report_uuid: str) -> Optional[BenchmarkReportDB]:
    return db.query(BenchmarkReportDB).filter(BenchmarkReportDB.report_uuid == report_uuid).first()

# NIEUW: Haal alle benchmarks op voor een specifieke gebruiker
def get_benchmark_reports_by_user_email(db: Session, user_email: str) -> List[BenchmarkReportDB]:
    return db.query(BenchmarkReportDB).filter(BenchmarkReportDB.generated_by_email == user_email).order_by(desc(BenchmarkReportDB.updated_at)).all()

# NIEUW: Update een bestaande benchmark
def update_benchmark_report(
    db: Session,
    report_uuid: str,
    user_email: str, # Om eigendom te verifiëren
    title: Optional[str] = None,
    property_ids: Optional[List[str]] = None,
    metrics_used: Optional[List[str]] = None,
    dimensions_used: Optional[List[str]] = None,
    benchmark_results: Optional[Dict[str, Any]] = None # Dit zou opnieuw gegenereerd moeten worden als selecties wijzigen
) -> Optional[BenchmarkReportDB]:
    db_report = db.query(BenchmarkReportDB).filter(
        BenchmarkReportDB.report_uuid == report_uuid,
        BenchmarkReportDB.generated_by_email == user_email # Eigenaar check
    ).first()

    if not db_report:
        return None

    if title is not None:
        db_report.title = title
    if property_ids is not None:
        db_report.property_ids_used = ",".join(property_ids)
    if metrics_used is not None:
        db_report.metrics_used = json.dumps(metrics_used)
    if dimensions_used is not None:
        db_report.dimensions_used = json.dumps(dimensions_used)
    if benchmark_results is not None: # Als de data zelf ook geüpdatet wordt
        db_report.benchmark_data_json = json.dumps(benchmark_results)
    
    # updated_at wordt automatisch bijgewerkt door de onupdate in het model
    db.commit()
    db.refresh(db_report)
    return db_report

# NIEUW: Verwijder een benchmark
def delete_benchmark_report(db: Session, report_uuid: str, user_email: str) -> bool:
    db_report = db.query(BenchmarkReportDB).filter(
        BenchmarkReportDB.report_uuid == report_uuid,
        BenchmarkReportDB.generated_by_email == user_email # Eigenaar check
    ).first()

    if db_report:
        db.delete(db_report)
        db.commit()
        return True
    return False
