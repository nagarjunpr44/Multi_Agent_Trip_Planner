from __future__ import annotations

import json
from langchain_core.tools import tool
from config.settings import get_settings

try:
    from firecrawl import FirecrawlApp
except ImportError:
    FirecrawlApp = None

@tool
async def search_tripadvisor_tool(destination: str, category: str = "geos") -> str:
    """Search for destination details, ratings, and top attractions using Firecrawl.
    
    Args:
        destination: City or place name (e.g. "Tokyo", "Paris", "Kyoto")
        category: "geos" for destination overview | "attractions" | "hotels" | "restaurants"
    
    Returns:
        JSON with location details, rating, review count, and top nearby attractions
    """
    s = get_settings()
    if not s.apis.firecrawl_api_key:
        return json.dumps({"error": "FIRECRAWL_API_KEY is not configured. Cannot perform Firecrawl search."})
        
    if FirecrawlApp is None:
        return json.dumps({"error": "Firecrawl SDK is not installed. Run: uv pip install firecrawl-py"})

    try:
        app = FirecrawlApp(api_key=s.apis.firecrawl_api_key)
        
        # We perform a Google search via Firecrawl tailored to TripAdvisor and Lonely Planet
        search_query = f"{destination} top {category} site:tripadvisor.com OR site:lonelyplanet.com"
        
        # We can use the simple search endpoint first
        response = app.search(search_query)
        
        # Firecrawl native search endpoint returns {'data': [{url, title, description, content}, ...], 'success': True}
        data = response.get('data', [])
        
        snippets = []
        for d in data[:5]:
            snippets.append({
                "title": d.get("title", ""),
                "description": d.get("description", ""),
                "url": d.get("url", "")
            })
            
        return json.dumps({
            "destination": destination,
            "category": category,
            "results": snippets,
            "source": "firecrawl_search"
        })
    except Exception as e:
        return json.dumps({"error": f"Firecrawl request failed: {str(e)}"})
