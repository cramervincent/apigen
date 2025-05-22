# app/routes/api.py
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..crud import get_benchmark_report_by_uuid

router = APIRouter(prefix="/api/v1") # Prefix voor API routes

@router.get("/report/{report_uuid}", name="get_saved_report_api")
async def get_saved_report_api(report_uuid: str, db: Session = Depends(get_db)):
    db_report = get_benchmark_report_by_uuid(db=db, report_uuid=report_uuid)
    if not db_report: 
        raise HTTPException(status_code=404, detail="Benchmark rapport niet gevonden.")
    
    try:
        report_data_from_db = json.loads(db_report.benchmark_data_json)
        metrics_used = json.loads(db_report.metrics_used)
        dimensions_used = json.loads(db_report.dimensions_used)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Fout bij het parsen van opgeslagen rapportdata.")

    response_data = {
        "report_uuid": db_report.report_uuid,
        "created_at": db_report.created_at.isoformat() if db_report.created_at else None,
        "property_ids_used_in_generation": db_report.property_ids_used.split(',') if db_report.property_ids_used else [],
        "metrics_used_in_generation_api_names": metrics_used,
        "dimensions_used_in_generation_api_names": dimensions_used,
        "generated_by_email": db_report.generated_by_email,
        "benchmark_data": report_data_from_db 
    }
    return response_data