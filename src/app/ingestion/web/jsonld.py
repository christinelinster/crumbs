async def get_recipe_json_ld(url: str) -> dict | None:
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=10.0,
    ) as client:
        response = await client.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 RecipeImporter/1.0"
            },
        )
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    scripts = soup.find_all(
        "script",
        attrs={"type": "application/ld+json"},
    )

    for script in scripts:
        if not script.string:
            continue

        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue

        recipe = find_recipe(data)

        if recipe:
            return recipe

    return None

def find_recipe(data) -> dict | None:
    if isinstance(data, list):
        for item in data:
            recipe = find_recipe(item)

            if recipe:
                return recipe

    if isinstance(data, dict):
        type_value = data.get("@type")

        if type_value == "Recipe":
            return data

        if (
            isinstance(type_value, list)
            and "Recipe" in type_value
        ):
            return data

        for value in data.values():
            recipe = find_recipe(value)

            if recipe:
                return recipe

    return None

