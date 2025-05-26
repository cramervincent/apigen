# app/routes/ui.py
import json
from typing import List, Optional
from datetime import datetime, timedelta
import urllib.parse

from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.datastructures import URL

from ..dependencies import get_db
from ..auth import get_google_credentials_from_session, get_google_flow, store_credentials_in_session
from ..config import settings
from ..crud import (
    create_benchmark_report, 
    get_benchmark_report_by_uuid,
    get_benchmark_reports_by_user_email,
    update_benchmark_report,
    delete_benchmark_report
)
from ..analytics import generate_benchmark_data_from_google

from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
from google.analytics.admin_v1beta.types import ListAccountSummariesRequest
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_auth_requests

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# --- Hulpfunctie voor GA Properties ---
async def _get_ga_properties(credentials):
    ga_properties = []
    error_message = None
    try:
        admin_client = AnalyticsAdminServiceClient(credentials=credentials)
        summaries = admin_client.list_account_summaries(request=ListAccountSummariesRequest(page_size=200))
        for acc_sum in summaries:
            for prop_sum in getattr(acc_sum, 'property_summaries', []):
                if "properties/" in prop_sum.property:
                    ga_properties.append({
                        "id": prop_sum.property,
                        "name": f"{prop_sum.display_name or 'N/A'} (Account: {acc_sum.display_name or 'N/A'})"
                    })
    except Exception as e:
        print(f"Error fetching account summaries: {e}")
        error_message = f"Fout bij ophalen GA properties: {e}"
    return sorted(ga_properties, key=lambda p: p['name'].lower()), error_message

# --- Authenticatieroutes ---
@router.get("/", response_class=HTMLResponse, name="home_route")
async def home(request: Request, db: Session = Depends(get_db)):
    credentials = get_google_credentials_from_session(request)
    if credentials:
        user_email = request.session.get("user_email")
        if user_email:
            return RedirectResponse(url=str(request.url_for("my_benchmarks_page")), status_code=302)
        else:
            return RedirectResponse(url=str(request.url_for("select_benchmark_options_page")), status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/login", name="login_google_route")
async def login_google(request: Request):
    if settings.GOOGLE_CLIENT_ID == "YOUR_GOOGLE_CLIENT_ID" or settings.GOOGLE_CLIENT_SECRET == "YOUR_GOOGLE_CLIENT_SECRET":
        return HTMLResponse("<h1>Configuratie Fout</h1><p>Google Client ID/Secret niet ingesteld.</p>", status_code=500)
    flow = get_google_flow()
    authorization_url, state = flow.authorization_url(access_type="offline", prompt="consent")
    request.session["oauth_state"] = state
    return RedirectResponse(url=authorization_url)

@router.get("/auth/callback", name="auth_callback_route")
async def auth_callback_google(request: Request, code: str, state: str):
    session_state = request.session.pop("oauth_state", None)
    if not session_state or state != session_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")
    flow = get_google_flow()
    try:
        flow.fetch_token(code=code)
        store_credentials_in_session(request, flow.credentials)
        if flow.credentials and flow.credentials.id_token:
            id_info = google_id_token.verify_oauth2_token(
                flow.credentials.id_token,
                google_auth_requests.Request(),
                settings.GOOGLE_CLIENT_ID
            )
            request.session["user_email"] = id_info.get("email")
    except Exception as e:
        print(f"Error fetching token: {e}")
        raise HTTPException(status_code=500, detail=f"Kon token niet ophalen: {e}")
    return RedirectResponse(url=str(request.url_for("my_benchmarks_page")))

@router.get("/logout", name="logout_route")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url=str(request.url_for("home_route")))

# --- Benchmark Management Routes ---

@router.get("/benchmarks", response_class=HTMLResponse, name="my_benchmarks_page")
async def my_benchmarks_page(request: Request, db: Session = Depends(get_db), message: Optional[str] = Query(None)):
    credentials = get_google_credentials_from_session(request)
    user_email = request.session.get("user_email")
    if not credentials or not user_email:
        redirect_url = str(request.url_for("home_route").include_query_params(error="not_logged_in"))
        return RedirectResponse(url=redirect_url, status_code=302)

    benchmarks = get_benchmark_reports_by_user_email(db, user_email)
    return templates.TemplateResponse("my_benchmarks.html", {
        "request": request,
        "benchmarks": benchmarks,
        "user_email": user_email,
        "message": message
    })

@router.get("/benchmarks/new", response_class=HTMLResponse, name="select_benchmark_options_page")
async def select_benchmark_options_page(request: Request, error_message_form: Optional[str] = Query(None)):
    credentials = get_google_credentials_from_session(request)
    if not credentials:
        return RedirectResponse(url=str(request.url_for("home_route")), status_code=302)

    ga_properties, error_message_fetch = await _get_ga_properties(credentials)
    if error_message_fetch and any(keyword in error_message_fetch.upper() for keyword in ["INVALID_GRANT", "TOKEN HAS BEEN EXPIRED", "UNAUTHENTICATED", "PERMISSION_DENIED"]):
        request.session.clear()
        redirect_url = str(request.url_for("home_route").include_query_params(error="auth_failed_properties"))
        return RedirectResponse(url=redirect_url, status_code=302)

    user_email = request.session.get("user_email", "Onbekend")
    default_start_date_val = (datetime.now() - timedelta(days=settings.DEFAULT_START_DAYS_AGO)).strftime("%Y-%m-%d")
    default_end_date_val = (datetime.now() - timedelta(days=settings.DEFAULT_END_DAYS_AGO)).strftime("%Y-%m-%d")

    context = {
        "request": request,
        "properties": ga_properties,
        "user_email": user_email,
        "available_metrics": settings.AVAILABLE_METRICS,
        "default_metrics": settings.DEFAULT_METRICS,
        "available_dimensions": settings.AVAILABLE_DIMENSIONS,
        "default_dimensions": settings.DEFAULT_DIMENSIONS,
        "default_start_date": default_start_date_val,
        "default_end_date": default_end_date_val,
        "error_message_fetch": error_message_fetch,
        "error_message_form": error_message_form,
        "benchmark_title": "",
        "form_action_url": request.url_for('generate_and_save_benchmark_route'),
        "submit_button_text": "Genereer & Sla Nieuwe Benchmark Op"
    }
    return templates.TemplateResponse("select_options.html", context)


@router.post("/benchmarks/new", name="generate_and_save_benchmark_route")
async def generate_and_save_benchmark_endpoint(
    request: Request,
    benchmark_title: str = Form(...),
    property_ids: Optional[List[str]] = Form(None),
    selected_metrics: List[str] = Form(...),
    selected_dimensions: List[str] = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    db: Session = Depends(get_db)
):
    credentials = get_google_credentials_from_session(request)
    user_email = request.session.get("user_email")
    if not credentials or not user_email:
        redirect_url = str(request.url_for("home_route").include_query_params(error="not_logged_in"))
        return RedirectResponse(url=redirect_url, status_code=302)

    error_form = None
    # ... (Validatie blijft hetzelfde)
    if not benchmark_title.strip(): error_form = "Benchmark titel mag niet leeg zijn."
    elif not property_ids: error_form = "Selecteer ten minste één GA4 property."
    elif not selected_metrics or not selected_dimensions: error_form = "Selecteer ten minste één metric en één dimensie."
    try:
        if start_date > end_date: raise ValueError("Startdatum mag niet na de einddatum liggen.")
    except ValueError as ve: error_form = f"Ongeldige datums: {ve}"

    if error_form:
        safe_error_message = urllib.parse.quote_plus(error_form)
        redirect_url = str(request.url_for("select_benchmark_options_page").include_query_params(error_message_form=safe_error_message))
        return RedirectResponse(url=redirect_url, status_code=303)

    try:
        benchmark_results = await generate_benchmark_data_from_google(
            credentials, property_ids, selected_metrics, selected_dimensions, start_date, end_date
        )
    except ValueError as e:
        safe_error_message = urllib.parse.quote_plus(f"Fout bij genereren: {e}")
        redirect_url = str(request.url_for("select_benchmark_options_page").include_query_params(error_message_form=safe_error_message))
        return RedirectResponse(url=redirect_url, status_code=303)
    except Exception as e:
        print(f"Onverwachte fout bij genereren benchmark data: {e}")
        safe_error_message = urllib.parse.quote_plus(f"Onverwachte fout: {e}")
        redirect_url = str(request.url_for("select_benchmark_options_page").include_query_params(error_message_form=safe_error_message))
        return RedirectResponse(url=redirect_url, status_code=303)

    db_report_obj = create_benchmark_report(
        db=db, title=benchmark_title, property_ids=property_ids, metrics_used=selected_metrics,
        dimensions_used=selected_dimensions, benchmark_results=benchmark_results, user_email=user_email
    )
    
    success_message = urllib.parse.quote_plus(f"Benchmark '{db_report_obj.title}' succesvol aangemaakt!")
    redirect_url = str(request.url_for("my_benchmarks_page").include_query_params(message=success_message))
    return RedirectResponse(url=redirect_url, status_code=303)

@router.get("/benchmarks/edit/{report_uuid}", response_class=HTMLResponse, name="edit_benchmark_page")
async def edit_benchmark_page(request: Request, report_uuid: str, db: Session = Depends(get_db), error_message_form: Optional[str] = Query(None)):
    credentials = get_google_credentials_from_session(request)
    user_email = request.session.get("user_email")
    if not credentials or not user_email:
        redirect_url = str(request.url_for("home_route").include_query_params(error="not_logged_in"))
        return RedirectResponse(url=redirect_url, status_code=302)

    benchmark = get_benchmark_report_by_uuid(db, report_uuid)
    if not benchmark or benchmark.generated_by_email != user_email:
        raise HTTPException(status_code=404, detail="Benchmark niet gevonden of geen eigenaar.")

    ga_properties, error_message_fetch = await _get_ga_properties(credentials)
    if error_message_fetch and any(keyword in error_message_fetch.upper() for keyword in ["INVALID_GRANT", "TOKEN HAS BEEN EXPIRED", "UNAUTHENTICATED", "PERMISSION_DENIED"]):
        request.session.clear()
        redirect_url = str(request.url_for("home_route").include_query_params(error="auth_failed_properties_edit"))
        return RedirectResponse(url=redirect_url, status_code=302)
    
    try:
        benchmark_data = json.loads(benchmark.benchmark_data_json)
        selected_prop_ids = benchmark.property_ids_used.split(',') if benchmark.property_ids_used else []
        selected_metrics_db = json.loads(benchmark.metrics_used)
        selected_dimensions_db = json.loads(benchmark.dimensions_used)
        period = benchmark_data.get("period", {})
        start_date_db = period.get("start_date")
        end_date_db = period.get("end_date")
    except (json.JSONDecodeError, KeyError):
        error_msg = urllib.parse.quote_plus("Fout bij laden benchmark data.")
        redirect_url = str(request.url_for("my_benchmarks_page").include_query_params(message=error_msg))
        return RedirectResponse(url=redirect_url, status_code=303)

    context = {
        "request": request, "properties": ga_properties, "user_email": user_email,
        "available_metrics": settings.AVAILABLE_METRICS, "default_metrics": selected_metrics_db,
        "available_dimensions": settings.AVAILABLE_DIMENSIONS, "default_dimensions": selected_dimensions_db,
        "default_start_date": start_date_db, "default_end_date": end_date_db,
        "error_message_fetch": error_message_fetch, "error_message_form": error_message_form,
        "benchmark_title": benchmark.title, "selected_property_ids_db": selected_prop_ids,
        "report_uuid": report_uuid,
        "form_action_url": request.url_for('update_benchmark_endpoint', report_uuid=report_uuid),
        "submit_button_text": "Sla Wijzigingen Op"
    }
    return templates.TemplateResponse("select_options.html", context)

@router.post("/benchmarks/edit/{report_uuid}", name="update_benchmark_endpoint")
async def update_benchmark_endpoint(
    request: Request, report_uuid: str, benchmark_title: str = Form(...),
    property_ids: Optional[List[str]] = Form(None), selected_metrics: List[str] = Form(...),
    selected_dimensions: List[str] = Form(...), start_date: str = Form(...), end_date: str = Form(...),
    db: Session = Depends(get_db)
):
    credentials = get_google_credentials_from_session(request)
    user_email = request.session.get("user_email")
    if not credentials or not user_email:
        redirect_url = str(request.url_for("home_route").include_query_params(error="not_logged_in"))
        return RedirectResponse(url=redirect_url, status_code=302)

    if not get_benchmark_report_by_uuid(db, report_uuid) or get_benchmark_report_by_uuid(db, report_uuid).generated_by_email != user_email:
        raise HTTPException(status_code=404, detail="Benchmark niet gevonden of geen eigenaar voor update.")

    error_form = None
    # ... (Validatie blijft hetzelfde)
    if not benchmark_title.strip(): error_form = "Benchmark titel mag niet leeg zijn."
    elif not property_ids: error_form = "Selecteer ten minste één GA4 property."
    try:
        if start_date > end_date: raise ValueError("Startdatum mag niet na de einddatum liggen.")
    except ValueError as ve: error_form = f"Ongeldige datums: {ve}"
    
    if error_form:
        safe_error_message = urllib.parse.quote_plus(error_form)
        redirect_url = str(request.url_for("edit_benchmark_page", report_uuid=report_uuid).include_query_params(error_message_form=safe_error_message))
        return RedirectResponse(url=redirect_url, status_code=303)

    try:
        new_benchmark_results = await generate_benchmark_data_from_google(
            credentials, property_ids, selected_metrics, selected_dimensions, start_date, end_date
        )
    except ValueError as e:
        safe_error_message = urllib.parse.quote_plus(f"Fout bij hergenereren data: {e}")
        redirect_url = str(request.url_for("edit_benchmark_page", report_uuid=report_uuid).include_query_params(error_message_form=safe_error_message))
        return RedirectResponse(url=redirect_url, status_code=303)
    
    updated_report = update_benchmark_report(
        db=db, report_uuid=report_uuid, user_email=user_email, title=benchmark_title,
        property_ids=property_ids, metrics_used=selected_metrics,
        dimensions_used=selected_dimensions, benchmark_results=new_benchmark_results
    )

    if updated_report:
        success_message = urllib.parse.quote_plus(f"Benchmark '{updated_report.title}' succesvol bijgewerkt!")
        redirect_url = str(request.url_for("my_benchmarks_page").include_query_params(message=success_message))
        return RedirectResponse(url=redirect_url, status_code=303)
    else:
        error_msg = urllib.parse.quote_plus("Fout bij bijwerken benchmark.")
        redirect_url = str(request.url_for("my_benchmarks_page").include_query_params(message=error_msg))
        return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/benchmarks/delete/{report_uuid}", name="delete_benchmark_endpoint")
async def delete_benchmark_endpoint(request: Request, report_uuid: str, db: Session = Depends(get_db)):
    credentials = get_google_credentials_from_session(request)
    user_email = request.session.get("user_email")
    if not credentials or not user_email:
        redirect_url = str(request.url_for("home_route").include_query_params(error="not_logged_in"))
        return RedirectResponse(url=redirect_url, status_code=302)

    benchmark_to_delete = get_benchmark_report_by_uuid(db, report_uuid)
    if not benchmark_to_delete or benchmark_to_delete.generated_by_email != user_email:
        error_msg = urllib.parse.quote_plus("Kon benchmark niet verwijderen.")
        redirect_url = str(request.url_for("my_benchmarks_page").include_query_params(message=error_msg))
        return RedirectResponse(url=redirect_url, status_code=303)
    
    title_deleted = benchmark_to_delete.title
    deleted = delete_benchmark_report(db, report_uuid, user_email)

    if deleted:
        success_message = urllib.parse.quote_plus(f"Benchmark '{title_deleted}' succesvol verwijderd!")
        redirect_url = str(request.url_for("my_benchmarks_page").include_query_params(message=success_message))
        return RedirectResponse(url=redirect_url, status_code=303)
    else:
        error_msg = urllib.parse.quote_plus("Fout bij verwijderen benchmark.")
        redirect_url = str(request.url_for("my_benchmarks_page").include_query_params(message=error_msg))
        return RedirectResponse(url=redirect_url, status_code=303)

@router.get("/report-generated", response_class=HTMLResponse, name="report_generated_page_legacy")
async def report_generated_page_legacy(request: Request, report_url: str = Query(...)):
    return templates.TemplateResponse("report_generated.html", {"request": request, "report_url": report_url})
