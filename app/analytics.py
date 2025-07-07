import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from collections import defaultdict

from google.oauth2.credentials import Credentials
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Metric, RunReportRequest
)

def _fetch_ga_data_for_property(
    data_client: BetaAnalyticsDataClient,
    property_id: str,
    dimensions: List[Dimension],
    metrics: List[Metric],
    start_date_str: str,
    end_date_str: str
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    property_data_rows = []
    error = None
    try:
        if not property_id.startswith("properties/"):
            return [], f"Ongeldig formaat property ID: {property_id}"

        response = data_client.run_report(RunReportRequest(
            property=property_id,
            dimensions=dimensions,
            metrics=metrics,
            date_ranges=[DateRange(start_date=start_date_str, end_date=end_date_str)],
            keep_empty_rows=True
        ))

        dimension_header_names = [header.name for header in response.dimension_headers]
        metric_header_names = [header.name for header in response.metric_headers]

        for api_row in response.rows:
            row_dict = {"dimensions": {}, "metrics": {}}
            for i, dim_value_obj in enumerate(api_row.dimension_values):
                dim_name_from_header = dimension_header_names[i]
                if dim_name_from_header == "date":
                    try:
                        dt_obj = datetime.strptime(dim_value_obj.value, "%Y%m%d")
                        row_dict["dimensions"][dim_name_from_header] = dt_obj
                    except ValueError:
                        row_dict["dimensions"][dim_name_from_header] = dim_value_obj.value
                else:
                    row_dict["dimensions"][dim_name_from_header] = dim_value_obj.value
            
            for i, metric_value_obj in enumerate(api_row.metric_values):
                metric_name_from_header = metric_header_names[i]
                try:
                    row_dict["metrics"][metric_name_from_header] = float(metric_value_obj.value)
                except ValueError:
                    row_dict["metrics"][metric_name_from_header] = 0.0
            property_data_rows.append(row_dict)
        
    except Exception as e:
        print(f"ERROR (analytics.py): Fout bij ophalen/verwerken rapport voor {property_id}: {e}")
        error = str(e)
    
    return property_data_rows, error


async def generate_benchmark_data_from_google(
    google_credentials: Credentials,
    client_a_property_id: str,
    benchmark_property_ids: List[str],
    selected_metric_api_names: List[str],
    selected_dimension_api_names: List[str],
    start_date_str: str,
    end_date_str: str
) -> List[Dict[str, Any]]:
    
    data_client = BetaAnalyticsDataClient(credentials=google_credentials)
    
    ga_query_dimension_names = ["date"] + selected_dimension_api_names
    
    final_ga_metrics = [Metric(name=m) for m in selected_metric_api_names]
    final_ga_dimensions = [Dimension(name=d) for d in ga_query_dimension_names]

    if not final_ga_metrics:
        raise ValueError("Geen metrics geselecteerd.")

    errors_dict: Dict[str, str] = {}
    
    processed_client_a_data: Dict[Tuple, Dict[str, Any]] = {}
    
    client_a_raw_rows, client_a_error = await asyncio.to_thread(
        _fetch_ga_data_for_property,
        data_client, client_a_property_id, final_ga_dimensions, final_ga_metrics, 
        start_date_str, end_date_str
    )
    if client_a_error:
        errors_dict[client_a_property_id] = client_a_error
    
    if client_a_raw_rows:
        for row_dict in client_a_raw_rows:
            key_dim_values_list = [row_dict["dimensions"].get("date")]
            for dim_name in selected_dimension_api_names: 
                key_dim_values_list.append(row_dict["dimensions"].get(dim_name, "(not set)"))
            
            key_tuple = tuple(key_dim_values_list)
            processed_client_a_data[key_tuple] = row_dict["metrics"]

    aggregated_benchmark_metrics: Dict[Tuple, Dict[str, Dict[str, float]]] = defaultdict(
        lambda: {m_api: {"sum": 0.0, "count_props": 0} for m_api in selected_metric_api_names}
    )
    successful_benchmark_prop_count = 0

    if benchmark_property_ids:
        for bench_prop_id in benchmark_property_ids:
            bench_raw_rows, bench_error = await asyncio.to_thread(
                _fetch_ga_data_for_property,
                data_client, bench_prop_id, final_ga_dimensions, final_ga_metrics,
                start_date_str, end_date_str
            )
            if bench_error:
                errors_dict[bench_prop_id] = bench_error
                continue
            if not bench_raw_rows:
                continue
            
            successful_benchmark_prop_count += 1
            for row_dict in bench_raw_rows:
                key_dim_values_list = [row_dict["dimensions"].get("date")]
                for dim_name in selected_dimension_api_names:
                    key_dim_values_list.append(row_dict["dimensions"].get(dim_name, "(not set)"))
                key_tuple = tuple(key_dim_values_list)

                for m_api, value in row_dict["metrics"].items():
                    if m_api in selected_metric_api_names:
                        aggregated_benchmark_metrics[key_tuple][m_api]["sum"] += value
    
    averaged_benchmark_data: Dict[Tuple, Dict[str, Any]] = {}
    if successful_benchmark_prop_count > 0:
        for key_tuple, metrics_sums_counts in aggregated_benchmark_metrics.items():
            averaged_benchmark_data[key_tuple] = {}
            for m_api, data in metrics_sums_counts.items():
                if m_api in ["averageSessionDuration", "engagementRate"]:
                    averaged_benchmark_data[key_tuple][m_api] = data["sum"] / successful_benchmark_prop_count
                else:
                    averaged_benchmark_data[key_tuple][m_api] = data["sum"] / successful_benchmark_prop_count

    final_wide_output: List[Dict[str, Any]] = []
    
    for key_tuple, metrics_values_dict in processed_client_a_data.items():
        output_row = {"group": client_a_property_id} 
        output_row["date"] = key_tuple[0] 
        
        for i, dim_name in enumerate(selected_dimension_api_names): 
            output_row[dim_name] = key_tuple[i + 1] 
            
        for metric_name, value in metrics_values_dict.items():
            if metric_name in selected_metric_api_names:
                output_row[metric_name] = round(value, 2) if isinstance(value, (int, float)) else value
        final_wide_output.append(output_row)

    for key_tuple, metrics_values_dict in averaged_benchmark_data.items():
        output_row = {"group": "Benchmark"}
        output_row["date"] = key_tuple[0]
        
        for i, dim_name in enumerate(selected_dimension_api_names):
            output_row[dim_name] = key_tuple[i + 1]
            
        for metric_name, value in metrics_values_dict.items():
            if metric_name in selected_metric_api_names:
                output_row[metric_name] = round(value, 2) if isinstance(value, (int, float)) else value
        final_wide_output.append(output_row)

    if not final_wide_output and errors_dict:
        error_summary = "; ".join([f"{prop}: {err}" for prop, err in errors_dict.items()])
        raise ValueError(f"Kon geen benchmark data genereren. Fouten: {error_summary}")
    elif not final_wide_output and not client_a_raw_rows and successful_benchmark_prop_count == 0 :
        pass

    return final_wide_output
