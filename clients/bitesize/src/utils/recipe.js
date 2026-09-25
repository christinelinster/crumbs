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

export function formatServings(value) {
  const count = Number(value)
  return `${value} ${count === 1 ? 'serving' : 'servings'}`
}

export function formatDuration(value) {
  const minutes = Math.floor(Number(value))
  if (!Number.isFinite(minutes) || minutes < 0) return ''

  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  if (hours === 0) return `${remainingMinutes} min`
  if (remainingMinutes === 0) return `${hours} hr`
  return `${hours} hr ${remainingMinutes} min`
}

export function categoryMatches(recipe, selectedCategory) {
  return facetMatches(recipe.category, selectedCategory)
}

function tagMatches(recipe, selectedTag) {
  return facetMatches(recipe.tags, selectedTag)
}

function facetMatches(values, selectedValue) {
  if (selectedValue === 'All') return true

  const wanted = normalizeKey(selectedValue)
  return normalizeArray(values).some((value) => normalizeKey(value) === wanted)
}

export function recipeMatchesSearch(recipe, searchTerm) {
  const query = normalizeKey(searchTerm)
  if (!query) return true

  const searchableText = normalizeKey(
    [
      recipe.title,
      recipe.slug,
      recipe.description,
      recipe.cuisine,
      ...normalizeArray(recipe.category),
      ...normalizeArray(recipe.tags),
    ]
      .filter(Boolean)
      .join(' '),
  )

  return query.split(' ').every((word) => searchableText.includes(word))
}

export function filterRecipes(
  recipes,
  {
    category = 'All',
    tag = 'All',
    searchTerm = '',
    calorieLimit = Number.POSITIVE_INFINITY,
    showFavourites = false,
    favouriteIds = [],
  } = {},
) {
  const limit = Number.isFinite(calorieLimit)
    ? calorieLimit
    : Number.POSITIVE_INFINITY

  return (recipes ?? []).filter(
    (recipe) =>
      categoryMatches(recipe, category) &&
      tagMatches(recipe, tag) &&
      recipeMatchesSearch(recipe, searchTerm) &&
      (recipe.calories == null || recipe.calories <= limit) &&
      (!showFavourites || favouriteIds.includes(recipe.slug)),
  )
}

function normalizeKey(value) {
  return String(value).trim().toLowerCase().replace(/[-_]+/g, ' ').replace(/\s+/g, ' ')
}

export function sectionItems(sections) {
  return normalizeArray(sections).flatMap((section) => normalizeArray(section?.items))
}

export function sectionHeading(section) {
  if (section?.kind !== 'group' || typeof section.name !== 'string') return ''
  return section.name.trim()
}
