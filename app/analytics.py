# app/analytics.py
from typing import List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict

from google.oauth2.credentials import Credentials
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Metric, RunReportRequest, DimensionHeader, MetricHeader
)
# from .config import settings # settings wordt niet direct hier gebruikt, maar via parameters

async def generate_benchmark_data_from_google(
    google_credentials: Credentials,
    selected_property_ids: List[str],
    selected_metric_api_names: List[str],
    selected_dimension_api_names: List[str],
    start_date_str: str,
    end_date_str: str
) -> Dict[str, Any]:
    data_client = BetaAnalyticsDataClient(credentials=google_credentials)
    final_metrics = [Metric(name=m) for m in selected_metric_api_names]
    final_dimensions = [Dimension(name=d) for d in selected_dimension_api_names]

    if not final_metrics:
        raise ValueError("Geen metrics geselecteerd voor de API aanroep.")
    if not final_dimensions: # Een dimensie is meestal nodig, 'date' is een veilige default
        final_dimensions.append(Dimension(name="date"))

    # Initialiseer structuren voor data aggregatie
    overall_aggregated_metrics = {name: 0.0 for name in selected_metric_api_names}
    properties_data_summary = []
    properties_with_errors = {}
    successful_property_count = 0

    # Voor gemiddelden per *combinatie* van alle geselecteerde dimensies
    dimension_combo_sums = defaultdict(lambda: {
        **{metric_name: 0.0 for metric_name in selected_metric_api_names},
        '_properties_contributed_combo': set()
    })

    # NIEUW: Voor gemiddelden per *individuele* dimensiewaarde
    # Key: dimensie_api_naam (bv "date", "country")
    # Value: defaultdict(lambda: { 'metric_name': sum, '_properties_contributed_individual': set() })
    individual_dimension_value_sums = {
        dim_api_name: defaultdict(lambda: {
            **{metric_name: 0.0 for metric_name in selected_metric_api_names},
            '_properties_contributed_individual': set()
        }) for dim_api_name in selected_dimension_api_names
    }

    for prop_id in selected_property_ids:
        if not prop_id.startswith("properties/"):
            properties_with_errors[prop_id] = "Ongeldig formaat property ID."
            properties_data_summary.append({
                "id": prop_id, "error": "Ongeldig formaat", "data_rows": [],
                "property_total_metrics": {m: 0.0 for m in selected_metric_api_names}
            })
            continue

        property_specific_data_rows = []
        property_specific_total_metrics = {name: 0.0 for name in selected_metric_api_names}
        rows_processed_for_property = 0
        property_had_data_for_query = False # Vlag om te zien of deze property überhaupt data had voor de query

        try:
            print(f"DEBUG (analytics.py): Requesting report for {prop_id} with dims: {[d.name for d in final_dimensions]}, metrics: {[m.name for m in final_metrics]}")
            response = data_client.run_report(RunReportRequest(
                property=prop_id,
                dimensions=final_dimensions,
                metrics=final_metrics,
                date_ranges=[DateRange(start_date=start_date_str, end_date=end_date_str)],
            ))

            dimension_header_names = [header.name for header in response.dimension_headers]
            metric_header_names = [header.name for header in response.metric_headers]

            if response.rows: # Alleen als er rijen zijn, heeft de property data voor deze query
                property_had_data_for_query = True


            for api_row in response.rows:
                rows_processed_for_property += 1
                current_row_dimensions_dict = {}
                for i, dim_value_obj in enumerate(api_row.dimension_values):
                    dim_name_from_header = dimension_header_names[i]
                    current_row_dimensions_dict[dim_name_from_header] = dim_value_obj.value
                
                # Key voor dimension_combo_sums (alle geselecteerde dimensies)
                dim_key_tuple_combo = tuple(current_row_dimensions_dict.get(d_name, "(not set)") for d_name in selected_dimension_api_names)

                current_row_metrics_dict = {}
                for i, metric_value_obj in enumerate(api_row.metric_values):
                    metric_name_from_header = metric_header_names[i] # Dit is de API naam
                    try:
                        val = float(metric_value_obj.value)
                        current_row_metrics_dict[metric_name_from_header] = val
                        
                        # Update totalen
                        property_specific_total_metrics[metric_name_from_header] += val
                        overall_aggregated_metrics[metric_name_from_header] += val
                        
                        # Update sums voor de specifieke dimensie combinatie
                        dimension_combo_sums[dim_key_tuple_combo][metric_name_from_header] += val
                        dimension_combo_sums[dim_key_tuple_combo]['_properties_contributed_combo'].add(prop_id)

                        # NIEUW: Update sums voor elke individuele dimensiewaarde
                        for selected_dim_api_name in selected_dimension_api_names:
                            # De waarde van deze specifieke dimensie in de huidige rij
                            # We moeten de header naam gebruiken die overeenkomt met de geselecteerde API naam
                            if selected_dim_api_name in current_row_dimensions_dict:
                                individual_dim_value = current_row_dimensions_dict[selected_dim_api_name]
                                individual_dimension_value_sums[selected_dim_api_name][individual_dim_value][metric_name_from_header] += val
                                individual_dimension_value_sums[selected_dim_api_name][individual_dim_value]['_properties_contributed_individual'].add(prop_id)
                            # else:
                                # Dit zou niet moeten gebeuren als selected_dimension_api_names overeenkomen met wat in de query zit
                                # print(f"WARN: Geselecteerde dimensie {selected_dim_api_name} niet gevonden in rij dimensies: {current_row_dimensions_dict.keys()}")


                    except ValueError:
                        current_row_metrics_dict[metric_name_from_header] = 0.0
                
                property_specific_data_rows.append({
                    "dimensions": current_row_dimensions_dict,
                    "metrics": current_row_metrics_dict
                })
            
            if property_had_data_for_query: # Tel alleen mee als er data was
                successful_property_count += 1
            
            properties_data_summary.append({
                "id": prop_id,
                "data_rows": property_specific_data_rows,
                "property_total_metrics": property_specific_total_metrics,
                "rows_processed": rows_processed_for_property
            })

        except Exception as e:
            print(f"ERROR (analytics.py): Fout bij ophalen/verwerken rapport voor {prop_id}: {e}")
            properties_with_errors[prop_id] = str(e)
            properties_data_summary.append({
                "id": prop_id, "error": str(e), "data_rows": [],
                "property_total_metrics": {m: 0.0 for m in selected_metric_api_names}
            })
            continue # Ga naar de volgende property
    
    if successful_property_count == 0 and selected_property_ids:
        error_msg = f"Geen data succesvol opgehaald voor de geselecteerde properties. Fouten: {properties_with_errors}"
        # Als er geen properties waren geselecteerd, is dit geen error van deze functie
        if not selected_property_ids:
             error_msg = "Geen properties geselecteerd om data voor op te halen."
        raise ValueError(error_msg)

    # Bereken gemiddelden per *combinatie* van alle geselecteerde dimensies
    average_metrics_per_dimension_combination = []
    for dim_key_tuple, sums_and_meta in dimension_combo_sums.items():
        dim_values_dict = {selected_dimension_api_names[i]: dim_key_tuple[i] for i in range(len(dim_key_tuple))}
        avg_metrics = {
            m: round(sums_and_meta[m] / successful_property_count, 2) if successful_property_count > 0 else 0.0
            for m in selected_metric_api_names
        }
        average_metrics_per_dimension_combination.append({
            "dimensions": dim_values_dict,
            "average_metrics": avg_metrics
        })
        
    # NIEUW: Bereken gemiddelden per *individuele* dimensiewaarde
    average_metrics_per_individual_dimension_value = {}
    for dim_api_name, value_sums_dict in individual_dimension_value_sums.items():
        averages_for_this_dim = []
        for dim_value, sums_and_meta_individual in value_sums_dict.items():
            avg_metrics_individual = {
                m: round(sums_and_meta_individual[m] / successful_property_count, 2) if successful_property_count > 0 else 0.0
                for m in selected_metric_api_names
            }
            averages_for_this_dim.append({
                "value": dim_value, # De specifieke waarde van deze dimensie (bv. 'Organic Search')
                "average_metrics": avg_metrics_individual
            })
        # Sorteer de resultaten voor deze dimensie op de waarde voor consistentie
        average_metrics_per_individual_dimension_value[dim_api_name] = sorted(averages_for_this_dim, key=lambda x: str(x['value']))


    # Algemene gemiddelden en afgeleide metrics
    avg_overall_metrics_prop = {
        m: round(overall_aggregated_metrics[m] / successful_property_count, 2) if successful_property_count > 0 else 0.0 
        for m in selected_metric_api_names
    }
    
    derived_metrics = {}
    sessions_total = overall_aggregated_metrics.get("sessions", 0.0)
    if "engagedSessions" in overall_aggregated_metrics and sessions_total > 0:
        derived_metrics["overall_engagement_rate"] = round((overall_aggregated_metrics["engagedSessions"] / sessions_total) * 100, 2)
    if "screenPageViews" in overall_aggregated_metrics and sessions_total > 0:
        derived_metrics["overall_views_per_session"] = round(overall_aggregated_metrics["screenPageViews"] / sessions_total, 2)

    return {
        "requested_properties_count": len(selected_property_ids),
        "successful_properties_count": successful_property_count,
        "period": {"start_date": start_date_str, "end_date": end_date_str},
        "selected_metrics_api_names": selected_metric_api_names,
        "selected_dimensions_api_names": selected_dimension_api_names,
        "total_metrics_across_selection": overall_aggregated_metrics,
        "average_overall_metrics_per_property": avg_overall_metrics_prop,
        "average_metrics_per_dimension_combination": average_metrics_per_dimension_combination,
        "average_metrics_per_individual_dimension_value": average_metrics_per_individual_dimension_value, 
        "data_summary_per_property": properties_data_summary, 
        "errors_per_property": properties_with_errors
    }
