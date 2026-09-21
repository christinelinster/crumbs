"""Ordered section boundaries shared by Markdown loading and persistence."""


def group_at(groups: list[dict], position: int) -> tuple[int | None, str | None]:
    """Resolve one-based item position to its optional group number and name."""
    result = (None, None)
    for number, group in enumerate(groups, 1):
        if group["start"] > position:
            break
        result = (number, group["name"])
    return result
