
from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
from google.analytics.admin_v1beta.types import ListAccountSummariesRequest

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
