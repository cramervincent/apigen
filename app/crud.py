import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from .database import BenchmarkReportDB

def json_serializer(obj: Any) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def create_benchmark_report(
    db: Session,
    title: str,
    client_a_property_id: Optional[str],
    benchmark_property_ids: Optional[List[str]],
    metrics_used: List[str],
    dimensions_used: List[str],
    benchmark_results_flat_json: List[Dict[str, Any]],
    user_email: Optional[str]
) -> BenchmarkReportDB:

    benchmark_ids_json_str = json.dumps(benchmark_property_ids) if benchmark_property_ids else None

    all_props = []
    if client_a_property_id:
        all_props.append(client_a_property_id)
    if benchmark_property_ids:
        all_props.extend(benchmark_property_ids)
    legacy_property_ids_used = ",".join(all_props) if all_props else None

    db_report = BenchmarkReportDB(
        title=title,
        client_a_property_id=client_a_property_id,
        benchmark_property_ids_json=benchmark_ids_json_str,
        property_ids_used=legacy_property_ids_used,
        metrics_used=json.dumps(metrics_used),
        dimensions_used=json.dumps(dimensions_used),
        benchmark_data_json=json.dumps(benchmark_results_flat_json, default=json_serializer),
        generated_by_email=user_email
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report

def get_benchmark_report_by_uuid(db: Session, report_uuid: str) -> Optional[BenchmarkReportDB]:
    return db.query(BenchmarkReportDB).filter(BenchmarkReportDB.report_uuid == report_uuid).first()

def get_benchmark_reports_by_user_email(db: Session, user_email: str) -> List[BenchmarkReportDB]:
    return db.query(BenchmarkReportDB).filter(BenchmarkReportDB.generated_by_email == user_email).order_by(desc(BenchmarkReportDB.updated_at)).all()

def update_benchmark_report(
    db: Session,
    report_uuid: str,
    user_email: str,
    title: Optional[str] = None,
    client_a_property_id: Optional[str] = None,
    benchmark_property_ids: Optional[List[str]] = None,
    metrics_used: Optional[List[str]] = None,
    dimensions_used: Optional[List[str]] = None,
    benchmark_results_flat_json: Optional[List[Dict[str, Any]]] = None
) -> Optional[BenchmarkReportDB]:
    db_report = db.query(BenchmarkReportDB).filter(
        BenchmarkReportDB.report_uuid == report_uuid,
        BenchmarkReportDB.generated_by_email == user_email
    ).first()

    if not db_report:
        return None

    if title is not None:
        db_report.title = title

    if client_a_property_id is not None:
        db_report.client_a_property_id = client_a_property_id
    if benchmark_property_ids is not None:
        db_report.benchmark_property_ids_json = json.dumps(benchmark_property_ids)

    all_props_update = []
    current_client_a = client_a_property_id if client_a_property_id is not None else db_report.client_a_property_id
    current_benchmark_list = benchmark_property_ids if benchmark_property_ids is not None else (json.loads(db_report.benchmark_property_ids_json) if db_report.benchmark_property_ids_json else [])

    if current_client_a:
        all_props_update.append(current_client_a)
    if current_benchmark_list:
        all_props_update.extend(current_benchmark_list)
    db_report.property_ids_used = ",".join(all_props_update) if all_props_update else None

    if metrics_used is not None:
        db_report.metrics_used = json.dumps(metrics_used)
    if dimensions_used is not None:
        db_report.dimensions_used = json.dumps(dimensions_used)
    if benchmark_results_flat_json is not None:
        db_report.benchmark_data_json = json.dumps(benchmark_results_flat_json, default=json_serializer)

    db.commit()
    db.refresh(db_report)
    return db_report

def delete_benchmark_report(db: Session, report_uuid: str, user_email: str) -> bool:
    db_report = db.query(BenchmarkReportDB).filter(
        BenchmarkReportDB.report_uuid == report_uuid,
        BenchmarkReportDB.generated_by_email == user_email
    ).first()

    if db_report:
        db.delete(db_report)
        db.commit()
        return True
    return False
