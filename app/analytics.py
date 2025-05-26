# app/analytics.py
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from collections import defaultdict
import copy # Voor deepcopy

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
    """Hulpfunctie om data voor één property op te halen en te structureren."""
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
            keep_empty_rows=True # Belangrijk voor correcte aggregatie later
        ))

        dimension_header_names = [header.name for header in response.dimension_headers]
        metric_header_names = [header.name for header in response.metric_headers]

        for api_row in response.rows:
            row_dict = {"dimensions": {}, "metrics": {}}
            for i, dim_value_obj in enumerate(api_row.dimension_values):
                dim_name_from_header = dimension_header_names[i]
                row_dict["dimensions"][dim_name_from_header] = dim_value_obj.value
            
            for i, metric_value_obj in enumerate(api_row.metric_values):
                metric_name_from_header = metric_header_names[i]
                try:
                    row_dict["metrics"][metric_name_from_header] = float(metric_value_obj.value)
                except ValueError:
                    row_dict["metrics"][metric_name_from_header] = 0.0 # Of None, afhankelijk van hoe je het wilt
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
    selected_dimension_api_names: List[str], # Dit zijn de API namen
    start_date_str: str,
    end_date_str: str
) -> List[Dict[str, Any]]: # Returnwaarde is nu de platte lijst
    
    data_client = BetaAnalyticsDataClient(credentials=google_credentials)
    
    # Zorg dat 'date' altijd een dimensie is, als die niet is geselecteerd, voeg hem toe.
    # De outputstructuur vereist een 'date' veld.
    final_dimension_api_names = list(selected_dimension_api_names) # Kopie
    if "date" not in final_dimension_api_names:
        final_dimension_api_names.insert(0, "date") # Voeg 'date' vooraan toe voor consistentie

    final_ga_metrics = [Metric(name=m) for m in selected_metric_api_names]
    final_ga_dimensions = [Dimension(name=d) for d in final_dimension_api_names]

    if not final_ga_metrics:
        raise ValueError("Geen metrics geselecteerd.")
    if not final_ga_dimensions: # 'date' is nu altijd aanwezig
        raise ValueError("Geen dimensies geselecteerd (minimaal 'date' is nodig).")

    flat_report_data: List[Dict[str, Any]] = []
    errors_dict: Dict[str, str] = {}

    # 1. Data ophalen voor Klant A
    # print(f"Fetching data for Klant A: {client_a_property_id}")
    client_a_raw_data, client_a_error = _fetch_ga_data_for_property(
        data_client, client_a_property_id, final_ga_dimensions, final_ga_metrics, start_date_str, end_date_str
    )
    if client_a_error:
        errors_dict[client_a_property_id] = client_a_error
    # Zelfs met een error, gaan we door als er benchmark properties zijn, anders is er geen data.
    # Als Klant A faalt en er zijn geen benchmark properties, dan is er een groter probleem.
    if not client_a_raw_data and not benchmark_property_ids and client_a_error:
         raise ValueError(f"Kon geen data ophalen voor Klant A ({client_a_property_id}): {client_a_error} en geen benchmark properties geselecteerd.")


    # 2. Data ophalen en aggregeren voor Benchmark Properties
    benchmark_aggregated_data = defaultdict(lambda: {
        metric_name: {"sum": 0.0, "count": 0} for metric_name in selected_metric_api_names
    })
    # Key voor benchmark_aggregated_data: tuple(dimension_values_in_ga_order_excluding_date, date_value)
    # Dit is om de sommen per unieke combinatie van dimensies (en datum) bij te houden.

    successful_benchmark_properties_count = 0
    if benchmark_property_ids:
        for bench_prop_id in benchmark_property_ids:
            # print(f"Fetching data for Benchmark property: {bench_prop_id}")
            bench_raw_data, bench_error = _fetch_ga_data_for_property(
                data_client, bench_prop_id, final_ga_dimensions, final_ga_metrics, start_date_str, end_date_str
            )
            if bench_error:
                errors_dict[bench_prop_id] = bench_error
                continue # Ga naar volgende benchmark property bij fout
            
            if not bench_raw_data: # Geen data voor deze property, telt niet mee voor gemiddelde
                continue

            successful_benchmark_properties_count += 1
            for row in bench_raw_data:
                # Maak een key op basis van alle dimensiewaarden in de volgorde van final_dimension_api_names
                # De 'date' dimensie moet hierin zitten.
                dim_values_tuple = tuple(row["dimensions"].get(dim_api_name, "(not set)") for dim_api_name in final_dimension_api_names)
                
                for metric_api_name, value in row["metrics"].items():
                    benchmark_aggregated_data[dim_values_tuple][metric_api_name]["sum"] += value
                    benchmark_aggregated_data[dim_values_tuple][metric_api_name]["count"] += 1 # Telt hoe vaak deze metric voor deze dim-combo is gezien over properties

    # Als er errors zijn, kunnen we die eventueel teruggeven. Voor nu focussen we op de data.
    if errors_dict:
        print(f"WARNING (analytics.py): Errors occurred during data fetching: {errors_dict}")
        # Je zou kunnen kiezen om hier een exception te raisen als *alle* fetches falen.
        if not client_a_raw_data and successful_benchmark_properties_count == 0:
            raise ValueError(f"Kon voor geen enkele property data ophalen. Fouten: {errors_dict}")


    # 3. Transformeer Klant A data naar platte structuur
    # print("Transforming Klant A data...")
    for client_row in client_a_raw_data:
        date_value = client_row["dimensions"].get("date", "N/A") # 'date' moet er zijn
        
        # Itereer over de *geselecteerde* niet-datum dimensies voor de output structuur
        for dim_api_name_selected in selected_dimension_api_names: # Gebruik originele selectie
            if dim_api_name_selected == "date": # 'date' wordt al apart behandeld
                continue

            dim_value_for_output = client_row["dimensions"].get(dim_api_name_selected, "(not set)")
            
            for metric_api_name, value in client_row["metrics"].items():
                if metric_api_name not in selected_metric_api_names: continue # Alleen geselecteerde metrics

                flat_report_data.append({
                    "group": client_a_property_id, # Of een alias "Klant A"
                    "date": date_value,
                    "dimension_type": dim_api_name_selected, # De API naam van de dimensie
                    "dimension_value": dim_value_for_output,
                    "metric": metric_api_name, # De API naam van de metric
                    "value": round(value, 2)
                })
        
        # Als er GEEN andere dimensies dan 'date' zijn geselecteerd,
        # maak dan toch entries voor de metrics met een placeholder dimensie.
        if all(d == "date" for d in selected_dimension_api_names) or not any(d != "date" for d in selected_dimension_api_names) :
            for metric_api_name, value in client_row["metrics"].items():
                if metric_api_name not in selected_metric_api_names: continue
                flat_report_data.append({
                    "group": client_a_property_id,
                    "date": date_value,
                    "dimension_type": "N/A", # Geen andere dimensie
                    "dimension_value": "N/A",
                    "metric": metric_api_name,
                    "value": round(value, 2)
                })


    # 4. Transformeer Benchmark data naar platte structuur
    # print("Transforming Benchmark data...")
    if successful_benchmark_properties_count > 0:
        for dim_values_tuple, metrics_agg in benchmark_aggregated_data.items():
            # Haal de date_value uit de dim_values_tuple.
            # We weten dat 'date' de eerste is in final_dimension_api_names.
            date_idx = final_dimension_api_names.index("date")
            date_value = dim_values_tuple[date_idx]

            # Maak een dictionary van de dimensiewaarden voor makkelijke lookup
            current_row_dims_dict = {final_dimension_api_names[i]: dim_values_tuple[i] for i in range(len(final_dimension_api_names))}

            for dim_api_name_selected in selected_dimension_api_names: # Gebruik originele selectie
                if dim_api_name_selected == "date":
                    continue
                
                dim_value_for_output = current_row_dims_dict.get(dim_api_name_selected, "(not set)")

                for metric_api_name, agg_values in metrics_agg.items():
                    if metric_api_name not in selected_metric_api_names: continue

                    # Gemiddelde berekenen. De 'count' hier is het aantal keren dat een waarde voor deze metric
                    # is bijgedragen aan de som *voor deze specifieke dimensie combinatie*.
                    # Voor het benchmark gemiddelde willen we delen door successful_benchmark_properties_count.
                    # Echter, als een property geen data had voor een *specifieke dimensie combinatie*, dan
                    # mag die niet meetellen voor het gemiddelde van *die specifieke combinatie*.
                    # De huidige `agg_values["count"]` is niet per se `successful_benchmark_properties_count`.
                    # Het is het aantal properties dat data had voor *deze specifieke rij*.
                    
                    # Correctie: Het gemiddelde moet over het aantal properties dat *überhaupt* data heeft geleverd.
                    # Als een property voor een bepaalde dim-combo geen data heeft, is de som 0 en telt het niet mee.
                    # Dus delen door successful_benchmark_properties_count is correct.
                    
                    avg_value = 0
                    # De agg_values["count"] is hier het aantal properties dat data had voor deze specifieke dimensie-combinatie
                    # Dit is niet per se gelijk aan successful_benchmark_properties_count.
                    # We moeten de totale som delen door het aantal properties dat uberhaupt data heeft geleverd.
                    if successful_benchmark_properties_count > 0: # Voorkom ZeroDivisionError
                         avg_value = agg_values["sum"] / successful_benchmark_properties_count
                    else: # Zou niet moeten gebeuren als we hier komen
                        avg_value = 0


                    flat_report_data.append({
                        "group": "Benchmark",
                        "date": date_value,
                        "dimension_type": dim_api_name_selected,
                        "dimension_value": dim_value_for_output,
                        "metric": metric_api_name,
                        "value": round(avg_value, 2)
                    })
            
            # Als er GEEN andere dimensies dan 'date' zijn geselecteerd
            if all(d == "date" for d in selected_dimension_api_names) or not any(d != "date" for d in selected_dimension_api_names):
                for metric_api_name, agg_values in metrics_agg.items():
                    if metric_api_name not in selected_metric_api_names: continue
                    avg_value = 0
                    if successful_benchmark_properties_count > 0:
                        avg_value = agg_values["sum"] / successful_benchmark_properties_count
                    
                    flat_report_data.append({
                        "group": "Benchmark",
                        "date": date_value,
                        "dimension_type": "N/A",
                        "dimension_value": "N/A",
                        "metric": metric_api_name,
                        "value": round(avg_value, 2)
                    })
    
    # Sorteer de uiteindelijke data voor consistentie (optioneel maar aanbevolen)
    # Sorteer op group, dan date, dan dimension_type, dan dimension_value, dan metric
    # flat_report_data.sort(key=lambda x: (x["group"], x["date"], x["dimension_type"], str(x["dimension_value"]), x["metric"]))

    if not flat_report_data and errors_dict:
         # Als er helemaal geen data is en wel errors, geef een meer specifieke melding.
        # De eerdere check was alleen als Klant A faalde en er geen benchmark props waren.
        raise ValueError(f"Kon geen benchmark data genereren. Fouten opgetreden: {errors_dict}")
    elif not flat_report_data:
        # Geen errors, maar ook geen data (bijv. geselecteerde periode heeft geen data)
        # Dit is geen ValueError, maar de UI moet dit kunnen tonen.
        # De lege lijst wordt geretourneerd.
        pass


    return flat_report_data
