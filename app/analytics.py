# app/analytics.py
import asyncio # <--- TOEGEVOEGD
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
    dimensions: List[Dimension], # GA Dimension objecten
    metrics: List[Metric],       # GA Metric objecten
    start_date_str: str,
    end_date_str: str
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Hulpfunctie om data voor één property op te halen.
    Retourneert een lijst van dictionaries, waarbij elke dict een rij uit GA vertegenwoordigt.
    Elke dict heeft keys 'dimensions' (een dict van dim_name: dim_value) en 
    'metrics' (een dict van metric_name: metric_value).
    """
    property_data_rows = []
    error = None
    try:
        if not property_id.startswith("properties/"):
            return [], f"Ongeldig formaat property ID: {property_id}"

        # print(f"DEBUG (analytics.py): Requesting report for {property_id} with dims: {[d.name for d in dimensions]}, metrics: {[m.name for m in metrics]}")
        response = data_client.run_report(RunReportRequest(
            property=property_id,
            dimensions=dimensions,
            metrics=metrics,
            date_ranges=[DateRange(start_date=start_date_str, end_date=end_date_str)],
            keep_empty_rows=True # Belangrijk voor consistente aggregatie
        ))

        dimension_header_names = [header.name for header in response.dimension_headers]
        metric_header_names = [header.name for header in response.metric_headers]

        for api_row in response.rows:
            row_dict = {"dimensions": {}, "metrics": {}}
            for i, dim_value_obj in enumerate(api_row.dimension_values):
                dim_name_from_header = dimension_header_names[i]
                # Converteer GA datumformaat YYYYMMDD naar een datetime-object
                if dim_name_from_header == "date":
                    try:
                        # Behoud het als een datetime object
                        dt_obj = datetime.strptime(dim_value_obj.value, "%Y%m%d")
                        row_dict["dimensions"][dim_name_from_header] = dt_obj
                    except ValueError:
                        # Fallback als de conversie mislukt
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
    selected_metric_api_names: List[str],    # API namen van geselecteerde metrics
    selected_dimension_api_names: List[str], # API namen van geselecteerde NIET-DATUM dimensies
    start_date_str: str,
    end_date_str: str
) -> List[Dict[str, Any]]: # Returnwaarde is nu de lijst van "brede" dictionaries
    
    data_client = BetaAnalyticsDataClient(credentials=google_credentials)
    
    # Dimensies voor de GA API call: 'date' + geselecteerde niet-datum dimensies
    ga_query_dimension_names = ["date"] + selected_dimension_api_names
    
    final_ga_metrics = [Metric(name=m) for m in selected_metric_api_names]
    final_ga_dimensions = [Dimension(name=d) for d in ga_query_dimension_names]

    if not final_ga_metrics:
        raise ValueError("Geen metrics geselecteerd.")

    errors_dict: Dict[str, str] = {}
    
    # --- Data verwerking voor Klant A ---
    processed_client_a_data: Dict[Tuple, Dict[str, Any]] = {} # Key: (date, dim_val1,...), Value: {metric1: val1,...}
    
    # Gebruik asyncio.to_thread om de synchrone GA client call in een aparte thread uit te voeren
    client_a_raw_rows, client_a_error = await asyncio.to_thread(
        _fetch_ga_data_for_property, # De functie zelf (zonder haakjes)
        data_client, client_a_property_id, final_ga_dimensions, final_ga_metrics, 
        start_date_str, end_date_str
    )
    if client_a_error:
        errors_dict[client_a_property_id] = client_a_error
    
    if client_a_raw_rows:
        for row_dict in client_a_raw_rows:
            # De 'date' key in row_dict["dimensions"] is nu een datetime object
            key_dim_values_list = [row_dict["dimensions"].get("date")] # Kan None zijn als 'date' niet aanwezig is
            for dim_name in selected_dimension_api_names: 
                key_dim_values_list.append(row_dict["dimensions"].get(dim_name, "(not set)"))
            
            key_tuple = tuple(key_dim_values_list)
            processed_client_a_data[key_tuple] = row_dict["metrics"]

    # --- Data verwerking voor Benchmark ---
    aggregated_benchmark_metrics: Dict[Tuple, Dict[str, Dict[str, float]]] = defaultdict(
        lambda: {m_api: {"sum": 0.0, "count_props": 0} for m_api in selected_metric_api_names}
    )
    successful_benchmark_prop_count = 0

    if benchmark_property_ids:
        for bench_prop_id in benchmark_property_ids:
            bench_raw_rows, bench_error = await asyncio.to_thread(
                _fetch_ga_data_for_property, # De functie zelf
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
                # Speciale behandeling voor 'averageSessionDuration' en 'engagementRate'
                if m_api in ["averageSessionDuration", "engagementRate"]:
                     # Voor deze metrics willen we het gemiddelde van de gemiddelden nemen,
                     # wat neerkomt op de som delen door het aantal properties dat data heeft geleverd.
                    averaged_benchmark_data[key_tuple][m_api] = data["sum"] / successful_benchmark_prop_count
                else:
                    # Voor andere metrics, neem de som (of pas logica aan indien nodig)
                    # Hier gaan we uit van een gemiddelde over de properties.
                    averaged_benchmark_data[key_tuple][m_api] = data["sum"] / successful_benchmark_prop_count


    # --- Samenstellen van de uiteindelijke "brede" output ---
    final_wide_output: List[Dict[str, Any]] = []
    
    # Verwerk Klant A data
    for key_tuple, metrics_values_dict in processed_client_a_data.items():
        output_row = {"group": client_a_property_id} 
        # key_tuple[0] is het datetime object voor de datum
        output_row["date"] = key_tuple[0] 
        
        for i, dim_name in enumerate(selected_dimension_api_names): 
            output_row[dim_name] = key_tuple[i + 1] 
            
        for metric_name, value in metrics_values_dict.items():
            if metric_name in selected_metric_api_names:
                output_row[metric_name] = round(value, 2) if isinstance(value, (int, float)) else value
        final_wide_output.append(output_row)

    # Verwerk Benchmark data
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
        pass # Geen data en geen errors, retourneer lege lijst

    return final_wide_output
