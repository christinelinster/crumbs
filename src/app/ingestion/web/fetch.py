import httpx

async def fetch_page(url: str) -> str:
    """Download HTML for recipe extraction, propagating HTTP and network errors."""
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=10.0,
    ) as client:
        response = await client.get(
            url,
            headers={"User-Agent": "RecipeImporter/1.0"},
        )
        response.raise_for_status()
        return response.text
