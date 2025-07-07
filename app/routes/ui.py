import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import urllib.parse
from urllib.parse import unquote_plus 

from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.datastructures import URL
import pandas as pd

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
    
    decoded_message = unquote_plus(message) if message else None

    benchmarks = get_benchmark_reports_by_user_email(db, user_email)
    
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
    
    decoded_error_form = unquote_plus(error_message_form) if error_message_form else None

    context = {
        "request": request, "properties": ga_properties, "user_email": user_email,
        "available_metrics": settings.AVAILABLE_METRICS, "default_metrics": settings.DEFAULT_METRICS,
        "available_dimensions": settings.AVAILABLE_DIMENSIONS, "default_dimensions": settings.DEFAULT_DIMENSIONS,
        "default_start_date": (datetime.now() - timedelta(days=settings.DEFAULT_START_DAYS_AGO)).strftime("%Y-%m-%d"),
        "default_end_date": (datetime.now() - timedelta(days=settings.DEFAULT_END_DAYS_AGO)).strftime("%Y-%m-%d"),
        "error_message_fetch": error_message_fetch, 
        "error_message_form": decoded_error_form,
        "benchmark_title": "", "client_a_property_id_db": None, "benchmark_property_ids_db": [],
        "form_action_url": request.url_for('generate_and_save_benchmark_route'),
        "submit_button_text": "Genereer & Sla Nieuwe Benchmark Op", "report_uuid": None
    }
    return templates.TemplateResponse("select_options.html", context)

@router.post("/benchmarks/new", name="generate_and_save_benchmark_route")
async def generate_and_save_benchmark_endpoint(
    request: Request, benchmark_title: str = Form(...),
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
        "error_message_form": decoded_error_form,
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
    user_email = request.session.get("user_email")
    # Check ingelogde status (dit kan aan het begin)
    if not user_email or not get_google_credentials_from_session(request):
        return RedirectResponse(str(request.url_for("home_route").include_query_params(error="not_logged_in")), status_code=302)

    try:
        # 1. Haal de benchmark op die verwijderd moet worden
        benchmark_to_delete = get_benchmark_report_by_uuid(db, report_uuid)

        # 2. Controleer of de benchmark bestaat en of de gebruiker de eigenaar is
        if not benchmark_to_delete or benchmark_to_delete.generated_by_email != user_email:
            error_message = urllib.parse.quote_plus("Verwijderen mislukt: Benchmark niet gevonden of geen eigenaar.")
            redirect_url = str(request.url_for("my_benchmarks_page")) + f"?message={error_message}"
            return RedirectResponse(url=redirect_url, status_code=303)
        
        title_deleted = benchmark_to_delete.title
        
        # 3. Voer de verwijder-actie uit
        deleted = delete_benchmark_report(db, report_uuid, user_email)

        # 4. Bepaal de boodschap voor de gebruiker
        if deleted:
            message = urllib.parse.quote_plus(f"Benchmark '{title_deleted}' succesvol verwijderd!")
        else:
            # Dit gebeurt als de delete-functie False teruggeeft zonder een error
            message = urllib.parse.quote_plus(f"Fout bij verwijderen van benchmark '{title_deleted}'.")

        redirect_url = str(request.url_for("my_benchmarks_page")) + f"?message={message}"
        return RedirectResponse(url=redirect_url, status_code=303)

    except Exception as e:
        # 5. VANG ALLE ANDERE FOUTEN OP (DE FIX VOOR DE 500 ERROR)
        print(f"--- FATAL ERROR during benchmark deletion: {e} ---") # Log de fout nu wel!
        
        error_message = urllib.parse.quote_plus(f"Interne serverfout bij verwijderen. Details: {e}")
        redirect_url = str(request.url_for("my_benchmarks_page")) + f"?message={error_message}"
        return RedirectResponse(url=redirect_url, status_code=303)


# --- INTERACTIVE REPORT ROUTE WITH TIME AGGREGATION ---
@router.get("/benchmarks/report/{report_uuid}", response_class=HTMLResponse, name="interactive_report_page")
async def interactive_report_page(request: Request, report_uuid: str, db: Session = Depends(get_db)):
    user_email = request.session.get("user_email")
    if not user_email:
        return RedirectResponse(str(request.url_for("home_route").include_query_params(error="not_logged_in")), status_code=302)

    report = get_benchmark_report_by_uuid(db, report_uuid)
    if not report or report.generated_by_email != user_email:
        raise HTTPException(status_code=404, detail="Benchmark niet gevonden of geen eigenaar.")

    try:
        data = json.loads(report.benchmark_data_json)
        if not data:
            return templates.TemplateResponse("error.html", {"request": request, "message": "Dit rapport bevat geen data."}, status_code=404)
        
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])

        client_id = report.client_a_property_id
        benchmark_ids = json.loads(report.benchmark_property_ids_json)
        num_benchmark_properties = len(benchmark_ids) if benchmark_ids else 1

        client_df = df[df['group'] == client_id].copy()
        benchmark_df = df[df['group'] == 'Benchmark'].copy()
        
        metrics = json.loads(report.metrics_used)
        
        # --- Bereken KPIs (met gemiddelde voor benchmark) ---
        kpis = {}
        for metric in metrics:
            client_total = client_df[metric].sum()
            bench_total_sum = benchmark_df[metric].sum()
            bench_average = bench_total_sum / num_benchmark_properties
            
            diff = ((client_total - bench_average) / bench_average * 100) if bench_average > 0 else 0
            
            kpis[metric] = {
                "client_value": client_total,
                "bench_value": bench_average,
                "diff_percentage": round(diff, 1)
            }

        # --- Data voor Trend grafieken (Dag, Week, Maand) ---
        trend_data = {}
        if 'date' in df.columns:
            # Set date as index for resampling
            client_df_resample = client_df.set_index('date')
            benchmark_df_resample = benchmark_df.set_index('date')

            for metric in metrics:
                trend_data[metric] = {}
                for period, period_name in [('D', 'day'), ('W', 'week'), ('M', 'month')]:
                    client_resampled = client_df_resample[metric].resample(period).sum().reset_index()
                    benchmark_resampled_sum = benchmark_df_resample[metric].resample(period).sum().reset_index()
                    
                    benchmark_resampled_avg = benchmark_resampled_sum.copy()
                    benchmark_resampled_avg[metric] = benchmark_resampled_avg[metric] / num_benchmark_properties
                    
                    trend_data[metric][period_name] = {
                        "labels": client_resampled['date'].dt.strftime('%Y-%m-%d').tolist(),
                        "client_data": client_resampled[metric].tolist(),
                        "benchmark_data": benchmark_resampled_avg[metric].tolist()
                    }

        # --- Data voor Dimensie grafieken (met gemiddelde voor benchmark) ---
        dimension_data = {}
        dimensions_in_report = [d for d in json.loads(report.dimensions_used) if d != 'date']
        for dim in dimensions_in_report:
            if dim in df.columns:
                for metric in metrics:
                    client_dim = client_df.groupby(dim)[metric].sum().reset_index()
                    bench_dim_sum = benchmark_df.groupby(dim)[metric].sum().reset_index()
                    
                    merged_df = pd.merge(client_dim, bench_dim_sum, on=dim, how='outer', suffixes=('_client', '_bench_sum')).fillna(0)
                    
                    merged_df[metric + '_bench_avg'] = merged_df[metric + '_bench_sum'] / num_benchmark_properties

                    chart_key = f"{dim}_{metric}"
                    dimension_data[chart_key] = {
                        "metric_title": settings.AVAILABLE_METRICS.get(metric, metric),
                        "dimension_title": settings.AVAILABLE_DIMENSIONS.get(dim, dim),
                        "labels": merged_df[dim].tolist(),
                        "client_data": merged_df[metric + '_client'].tolist(),
                        "benchmark_data": merged_df[metric + '_bench_avg'].tolist()
                    }

        # --- Periode en Client naam bepalen ---
        start_date = df['date'].min().strftime('%d %b %Y')
        end_date = df['date'].max().strftime('%d %b %Y')
        
        ga_properties, _ = await _get_ga_properties(get_google_credentials_from_session(request))
        client_name = next((prop['name'] for prop in ga_properties if prop['id'] == client_id), client_id)

        # --- Context voor de template ---
        context = {
            "request": request,
            "report_title": report.title,
            "client_name": client_name.split(' (Account:')[0],
            "period": f"{start_date} - {end_date}",
            "kpis": kpis,
            "available_metrics_map": settings.AVAILABLE_METRICS,
            "trend_data_json": json.dumps(trend_data),
            "dimension_data_json": json.dumps(dimension_data),
            "json_loads": json.loads
        }
        return templates.TemplateResponse("interactive_report.html", context)
        
    except Exception as e:
        print(f"Error generating interactive report: {e}")
        return templates.TemplateResponse("error.html", {"request": request, "message": f"Fout bij genereren van rapport: {e}"}, status_code=500)