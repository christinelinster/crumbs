export function normalizeArray(value) {
  if (Array.isArray(value)) return value
  if (typeof value === 'string' && value.trim()) return [value]
  return []
}

export function formatLabel(value) {
  return String(value)
    .replace(/[-_]+/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => `${word[0].toUpperCase()}${word.slice(1).toLowerCase()}`)
    .join(' ')
}

export function categoryMatches(recipe, selectedCategory) {
  if (selectedCategory === 'All') return true

  const wanted = normalizeKey(selectedCategory)
  return [...normalizeArray(recipe.category), ...normalizeArray(recipe.tags)].some(
    (value) => normalizeKey(value) === wanted,
  )
}

function normalizeKey(value) {
  return String(value).trim().toLowerCase().replace(/[-_]+/g, ' ').replace(/\s+/g, ' ')
}

export function groupHeadingsAt(markers) {
  const headings = new Map()
  const seenGroups = new Set()

  for (const marker of normalizeArray(markers)) {
    if (
      !marker ||
      !Number.isInteger(marker.position) ||
      !Number.isInteger(marker.group_position) ||
      seenGroups.has(marker.group_position)
    ) {
      continue
    }

    seenGroups.add(marker.group_position)
    const name = typeof marker.group_name === 'string' ? marker.group_name.trim() : ''
    if (name) headings.set(marker.position, name)
  }

  return headings
}
