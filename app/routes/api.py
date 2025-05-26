# app/routes/api.py
import json
from typing import List # Nodig voor List type hint
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..crud import get_benchmark_report_by_uuid

router = APIRouter(prefix="/api/v1")

@router.get("/report/{report_uuid}", name="get_saved_report_api")
async def get_saved_report_api(report_uuid: str, db: Session = Depends(get_db)):
    db_report = get_benchmark_report_by_uuid(db=db, report_uuid=report_uuid)
    if not db_report: 
        raise HTTPException(status_code=404, detail="Benchmark rapport niet gevonden.")
    
    try:
        # benchmark_data_json bevat nu de platte lijst direct
        report_data_from_db: List[dict] = json.loads(db_report.benchmark_data_json)
        metrics_used = json.loads(db_report.metrics_used)
        dimensions_used = json.loads(db_report.dimensions_used) # Dit zijn de niet-datum dimensies
        client_a_prop = db_report.client_a_property_id
        benchmark_props = json.loads(db_report.benchmark_property_ids_json) if db_report.benchmark_property_ids_json else []

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Fout bij het parsen van opgeslagen rapportdata.")

    # De response geeft nu direct de platte data terug zoals opgeslagen.
    # Je kunt hier overwegen om de 'period' expliciet terug te geven als je die apart opslaat,
    # of afleidt uit de data (min/max date).
    
    # Probeer periode af te leiden uit de data
    min_date, max_date = None, None
    if report_data_from_db and isinstance(report_data_from_db, list) and len(report_data_from_db) > 0:
        all_dates = sorted(list(set(item["date"] for item in report_data_from_db if "date" in item and item["date"] is not None)))
        if all_dates:
            min_date = all_dates[0]
            max_date = all_dates[-1]

    response_data = {
        "report_uuid": db_report.report_uuid,
        "title": db_report.title,
        "created_at": db_report.created_at.isoformat() if db_report.created_at else None,
        "updated_at": db_report.updated_at.isoformat() if db_report.updated_at else None,
        "generated_by_email": db_report.generated_by_email,
        "client_a_property_id": client_a_prop,
        "benchmark_property_ids": benchmark_props,
        "metrics_used_api_names": metrics_used,
        "dimensions_used_api_names": dimensions_used, # Excl. 'date'
        "period_in_data": {"start_date": min_date, "end_date": max_date} if min_date and max_date else None,
        "benchmark_data": report_data_from_db 
    }
    return response_data
