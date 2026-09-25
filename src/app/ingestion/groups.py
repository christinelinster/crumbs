"""Normalize raw recipe groups to canonical sections."""


def group_at(groups: list[dict], position: int) -> tuple[int | None, str | None]:
    """Resolve one-based item position to its optional group number and name."""
    result = (None, None)
    for number, group in enumerate(groups, 1):
        if group["start"] > position:
            break
        result = (number, group["name"])
    return result


def items_to_sections(
    items: list[str],
    groups: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Convert flat items and parser boundaries to ordered content sections."""
    sections: list[dict[str, object]] = []
    active_group_position = object()

    for position, item in enumerate(items, 1):
        group_position, group_name = group_at(groups, position)
        if not sections or group_position != active_group_position:
            if group_position is None:
                sections.append({
                    "kind": "ungrouped",
                    "name": None,
                    "items": [],
                })
            else:
                sections.append({
                    "kind": "group",
                    "name": group_name,
                    "items": [],
                })

        sections[-1]["items"].append(item)
        active_group_position = group_position

    return sections


def normalize_recipe_sections(recipe: dict[str, object]) -> dict[str, object]:
    """Return metadata and canonical sections, dropping parser-only flat fields."""
    parser_fields = {
        "ingredients", "instructions", "ingredient_groups", "instruction_groups",
    }
    normalized = {
        key: value for key, value in recipe.items() if key not in parser_fields
    }
    normalized["ingredient_sections"] = items_to_sections(
        recipe["ingredients"], recipe.get("ingredient_groups", [])
    )
    normalized["instruction_sections"] = items_to_sections(
        recipe["instructions"], recipe.get("instruction_groups", [])
    )
    return normalized
