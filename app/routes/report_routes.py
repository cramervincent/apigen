
import json
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import pandas as pd

from ..dependencies import get_db
from ..auth import get_google_credentials_from_session
from ..config import settings
from ..crud import get_benchmark_report_by_uuid
from .utils import _get_ga_properties

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

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

        trend_data = {}
        if 'date' in df.columns:
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

        start_date = df['date'].min().strftime('%d %b %Y')
        end_date = df['date'].max().strftime('%d %b %Y')

        ga_properties, _ = await _get_ga_properties(get_google_credentials_from_session(request))
        client_name = next((prop['name'] for prop in ga_properties if prop['id'] == client_id), client_id)

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
