# app/routes/ui.py
import json
from typing import List, Optional
from datetime import datetime, timedelta
import urllib.parse
from urllib.parse import unquote_plus # NIEUW

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
    if credentials and request.session.get("user_email"):
        return RedirectResponse(url=str(request.url_for("my_benchmarks_page")), status_code=302)
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
            id_info = google_id_token.verify_oauth2_token(flow.credentials.id_token, google_auth_requests.Request(), settings.GOOGLE_CLIENT_ID)
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
    
    # NIEUW: Decodeer het bericht uit de URL query
    decoded_message = unquote_plus(message) if message else None

    benchmarks = get_benchmark_reports_by_user_email(db, user_email)
    
    # AANGEPAST: Geef het gedecodeerde bericht door aan de template
    return templates.TemplateResponse(
        "my_benchmarks.html", 
        {"request": request, "benchmarks": benchmarks, "user_email": user_email, "message": decoded_message}
    )

@router.get("/benchmarks/new", response_class=HTMLResponse, name="select_benchmark_options_page")
async def select_benchmark_options_page(request: Request, error_message_form: Optional[str] = Query(None)):
    credentials = get_google_credentials_from_session(request)
    if not credentials: return RedirectResponse(url=str(request.url_for("home_route")), status_code=302)

    ga_properties, error_message_fetch = await _get_ga_properties(credentials)
    if error_message_fetch and any(keyword in error_message_fetch.upper() for keyword in ["INVALID_GRANT", "TOKEN HAS BEEN EXPIRED", "UNAUTHENTICATED", "PERMISSION_DENIED"]):
        request.session.clear()
        redirect_url = str(request.url_for("home_route").include_query_params(error="auth_failed_properties"))
        return RedirectResponse(url=redirect_url, status_code=302)

    user_email = request.session.get("user_email", "Onbekend")
    
    # Decodeer eventuele foutmeldingen die via de query worden meegegeven
    decoded_error_form = unquote_plus(error_message_form) if error_message_form else None

    context = {
        "request": request, "properties": ga_properties, "user_email": user_email,
        "available_metrics": settings.AVAILABLE_METRICS, "default_metrics": settings.DEFAULT_METRICS,
        "available_dimensions": settings.AVAILABLE_DIMENSIONS, "default_dimensions": settings.DEFAULT_DIMENSIONS,
        "default_start_date": (datetime.now() - timedelta(days=settings.DEFAULT_START_DAYS_AGO)).strftime("%Y-%m-%d"),
        "default_end_date": (datetime.now() - timedelta(days=settings.DEFAULT_END_DAYS_AGO)).strftime("%Y-%m-%d"),
        "error_message_fetch": error_message_fetch, 
        "error_message_form": decoded_error_form, # Gebruik de gedecodeerde melding
        "benchmark_title": "", "client_a_property_id_db": None, "benchmark_property_ids_db": [],
        "form_action_url": request.url_for('generate_and_save_benchmark_route'),
        "submit_button_text": "Genereer & Sla Nieuwe Benchmark Op", "report_uuid": None
    }
    return templates.TemplateResponse("select_options.html", context)

@router.post("/benchmarks/new", name="generate_and_save_benchmark_route")
async def generate_and_save_benchmark_endpoint(
    request: Request, benchmark_title: str = Form(...),
    client_a_property_id: Optional[str] = Form(None), # Maak optioneel voor validatie
    benchmark_property_ids: Optional[List[str]] = Form(None),
    selected_metrics: Optional[List[str]] = Form(None),
    selected_dimensions: Optional[List[str]] = Form(None),
    start_date: str = Form(...), end_date: str = Form(...),
    db: Session = Depends(get_db)
):
    credentials = get_google_credentials_from_session(request)
    user_email = request.session.get("user_email")
    if not credentials or not user_email:
        return RedirectResponse(str(request.url_for("home_route").include_query_params(error="not_logged_in")), status_code=302)

    actual_selected_dimensions = selected_dimensions if selected_dimensions else []
    
    # Server-side validatie
    error_form = None
    if not benchmark_title.strip(): error_form = "Benchmark titel mag niet leeg zijn."
    elif not client_a_property_id: error_form = "Selecteer a.u.b. een Klant A property."
    elif not benchmark_property_ids: error_form = "Selecteer a.u.b. ten minste één Benchmark property."
    elif client_a_property_id in benchmark_property_ids: error_form = "Klant A property mag niet ook een Benchmark property zijn."
    elif not selected_metrics: error_form = "Selecteer a.u.b. ten minste één metric."
    try:
        if start_date > end_date: raise ValueError("Startdatum mag niet na de einddatum liggen.")
    except (ValueError, TypeError): error_form = f"Ongeldige datums opgegeven."

    if error_form:
        redirect_url = str(request.url_for("select_benchmark_options_page").include_query_params(error_message_form=urllib.parse.quote_plus(error_form)))
        return RedirectResponse(url=redirect_url, status_code=303)

    try:
        benchmark_results_flat = await generate_benchmark_data_from_google(
            credentials, client_a_property_id, benchmark_property_ids,
            selected_metrics, actual_selected_dimensions, start_date, end_date
        )
    except ValueError as e:
        redirect_url = str(request.url_for("select_benchmark_options_page").include_query_params(error_message_form=urllib.parse.quote_plus(f"Fout bij genereren: {e}")))
        return RedirectResponse(url=redirect_url, status_code=303)
    except Exception as e:
        print(f"Onverwachte fout bij genereren benchmark data: {e}")
        redirect_url = str(request.url_for("select_benchmark_options_page").include_query_params(error_message_form=urllib.parse.quote_plus(f"Onverwachte serverfout: {e}")))
        return RedirectResponse(url=redirect_url, status_code=303)

    db_report_obj = create_benchmark_report(
        db=db, title=benchmark_title, client_a_property_id=client_a_property_id,
        benchmark_property_ids=benchmark_property_ids, metrics_used=selected_metrics,
        dimensions_used=actual_selected_dimensions, benchmark_results_flat_json=benchmark_results_flat,
        user_email=user_email
    )
    
    redirect_url = str(request.url_for("my_benchmarks_page").include_query_params(message=urllib.parse.quote_plus(f"Benchmark '{db_report_obj.title}' succesvol aangemaakt!")))
    return RedirectResponse(url=redirect_url, status_code=303)

@router.get("/benchmarks/edit/{report_uuid}", response_class=HTMLResponse, name="edit_benchmark_page")
async def edit_benchmark_page(request: Request, report_uuid: str, db: Session = Depends(get_db), error_message_form: Optional[str] = Query(None)):
    credentials = get_google_credentials_from_session(request)
    user_email = request.session.get("user_email")
    if not credentials or not user_email:
        return RedirectResponse(str(request.url_for("home_route").include_query_params(error="not_logged_in")), status_code=302)

    benchmark = get_benchmark_report_by_uuid(db, report_uuid)
    if not benchmark or benchmark.generated_by_email != user_email:
        raise HTTPException(status_code=404, detail="Benchmark niet gevonden of geen eigenaar.")

    ga_properties, error_message_fetch = await _get_ga_properties(credentials)
    if error_message_fetch and any(keyword in error_message_fetch.upper() for keyword in ["INVALID_GRANT", "TOKEN HAS BEEN EXPIRED", "UNAUTHENTICATED", "PERMISSION_DENIED"]):
        request.session.clear()
        return RedirectResponse(str(request.url_for("home_route").include_query_params(error="auth_failed_properties_edit")), status_code=302)
    
    # Decodeer eventuele foutmeldingen
    decoded_error_form = unquote_plus(error_message_form) if error_message_form else None
    
    try:
        client_a_prop_db = benchmark.client_a_property_id
        benchmark_props_db = json.loads(benchmark.benchmark_property_ids_json) if benchmark.benchmark_property_ids_json else []
        metrics_db = json.loads(benchmark.metrics_used)
        dimensions_db = json.loads(benchmark.dimensions_used)
        opgeslagen_data = json.loads(benchmark.benchmark_data_json)
        start_date_db = (datetime.now() - timedelta(days=settings.DEFAULT_START_DAYS_AGO)).strftime("%Y-%m-%d")
        end_date_db = (datetime.now() - timedelta(days=settings.DEFAULT_END_DAYS_AGO)).strftime("%Y-%m-%d")
        if opgeslagen_data and isinstance(opgeslagen_data, list) and len(opgeslagen_data) > 0 and "date" in opgeslagen_data[0]:
            all_dates = sorted(list(set(item["date"] for item in opgeslagen_data if "date" in item and item["date"] is not None)))
            if all_dates:
                start_date_db = all_dates[0]
                end_date_db = all_dates[-1]
    except (json.JSONDecodeError, TypeError) as e:
        print(f"Error parsing data for edit page: {e}")
        return RedirectResponse(str(request.url_for("my_benchmarks_page").include_query_params(message=urllib.parse.quote_plus("Fout bij laden benchmark data voor bewerken."))), status_code=303)

    context = {
        "request": request, "properties": ga_properties, "user_email": user_email,
        "available_metrics": settings.AVAILABLE_METRICS, "default_metrics": metrics_db,
        "available_dimensions": settings.AVAILABLE_DIMENSIONS, "default_dimensions": dimensions_db,
        "default_start_date": start_date_db, "default_end_date": end_date_db,
        "error_message_fetch": error_message_fetch, 
        "error_message_form": decoded_error_form, # Gebruik gedecodeerde melding
        "benchmark_title": benchmark.title, "client_a_property_id_db": client_a_prop_db, 
        "benchmark_property_ids_db": benchmark_props_db, "report_uuid": report_uuid,
        "form_action_url": request.url_for('update_benchmark_endpoint', report_uuid=report_uuid),
        "submit_button_text": "Sla Wijzigingen Op"
    }
    return templates.TemplateResponse("select_options.html", context)

@router.post("/benchmarks/edit/{report_uuid}", name="update_benchmark_endpoint")
async def update_benchmark_endpoint(
    request: Request, report_uuid: str, benchmark_title: str = Form(...),
    client_a_property_id: Optional[str] = Form(None),
    benchmark_property_ids: Optional[List[str]] = Form(None),
    selected_metrics: Optional[List[str]] = Form(None),
    selected_dimensions: Optional[List[str]] = Form(None),
    start_date: str = Form(...), end_date: str = Form(...),
    db: Session = Depends(get_db)
):
    credentials = get_google_credentials_from_session(request)
    user_email = request.session.get("user_email")
    if not credentials or not user_email:
        return RedirectResponse(str(request.url_for("home_route").include_query_params(error="not_logged_in")), status_code=302)

    benchmark_to_update = get_benchmark_report_by_uuid(db, report_uuid)
    if not benchmark_to_update or benchmark_to_update.generated_by_email != user_email:
        raise HTTPException(status_code=404, detail="Benchmark niet gevonden of geen eigenaar voor update.")

    actual_selected_dimensions = selected_dimensions if selected_dimensions else []
    error_form = None
    if not benchmark_title.strip(): error_form = "Benchmark titel mag niet leeg zijn."
    elif not client_a_property_id: error_form = "Selecteer a.u.b. een Klant A property."
    elif not benchmark_property_ids: error_form = "Selecteer a.u.b. ten minste één Benchmark property."
    elif client_a_property_id in benchmark_property_ids: error_form = "Klant A property mag niet ook een Benchmark property zijn."
    elif not selected_metrics: error_form = "Selecteer a.u.b. ten minste één metric."
    try:
        if start_date > end_date: raise ValueError("Startdatum mag niet na de einddatum liggen.")
    except (ValueError, TypeError): error_form = f"Ongeldige datums opgegeven."
    
    if error_form:
        redirect_url = str(request.url_for("edit_benchmark_page", report_uuid=report_uuid).include_query_params(error_message_form=urllib.parse.quote_plus(error_form)))
        return RedirectResponse(url=redirect_url, status_code=303)

    try:
        new_benchmark_results_flat = await generate_benchmark_data_from_google(
            credentials, client_a_property_id, benchmark_property_ids,
            selected_metrics, actual_selected_dimensions, start_date, end_date
        )
    except ValueError as e:
        redirect_url = str(request.url_for("edit_benchmark_page", report_uuid=report_uuid).include_query_params(error_message_form=urllib.parse.quote_plus(f"Fout bij hergenereren data: {e}")))
        return RedirectResponse(url=redirect_url, status_code=303)
    except Exception as e:
        print(f"Onverwachte fout bij hergenereren data voor update: {e}")
        redirect_url = str(request.url_for("edit_benchmark_page", report_uuid=report_uuid).include_query_params(error_message_form=urllib.parse.quote_plus(f"Onverwachte serverfout bij update: {e}")))
        return RedirectResponse(url=redirect_url, status_code=303)
    
    updated_report = update_benchmark_report(
        db=db, report_uuid=report_uuid, user_email=user_email, title=benchmark_title,
        client_a_property_id=client_a_property_id, benchmark_property_ids=benchmark_property_ids,
        metrics_used=selected_metrics, dimensions_used=actual_selected_dimensions,
        benchmark_results_flat_json=new_benchmark_results_flat
    )

    if updated_report:
        redirect_url = str(request.url_for("my_benchmarks_page").include_query_params(message=urllib.parse.quote_plus(f"Benchmark '{updated_report.title}' succesvol bijgewerkt!")))
        return RedirectResponse(url=redirect_url, status_code=303)
    else:
        redirect_url = str(request.url_for("my_benchmarks_page").include_query_params(message=urllib.parse.quote_plus("Fout bij bijwerken benchmark in database.")))
        return RedirectResponse(url=redirect_url, status_code=303)

@router.post("/benchmarks/delete/{report_uuid}", name="delete_benchmark_endpoint")
async def delete_benchmark_endpoint(request: Request, report_uuid: str, db: Session = Depends(get_db)):
    credentials = get_google_credentials_from_session(request)
    user_email = request.session.get("user_email")
    if not credentials or not user_email:
        return RedirectResponse(str(request.url_for("home_route").include_query_params(error="not_logged_in")), status_code=302)

    benchmark_to_delete = get_benchmark_report_by_uuid(db, report_uuid)
    if not benchmark_to_delete or benchmark_to_delete.generated_by_email != user_email:
        redirect_url = str(request.url_for("my_benchmarks_page").include_query_params(message=urllib.parse.quote_plus("Kon benchmark niet verwijderen.")))
        return RedirectResponse(url=redirect_url, status_code=303)
    
    title_deleted = benchmark_to_delete.title
    deleted = delete_benchmark_report(db, report_uuid, user_email)

    if deleted:
        redirect_url = str(request.url_for("my_benchmarks_page").include_query_params(message=urllib.parse.quote_plus(f"Benchmark '{title_deleted}' succesvol verwijderd!")))
        return RedirectResponse(url=redirect_url, status_code=303)
    else:
        redirect_url = str(request.url_for("my_benchmarks_page").include_query_params(message=urllib.parse.quote_plus("Fout bij verwijderen benchmark.")))
        return RedirectResponse(url=redirect_url, status_code=303)