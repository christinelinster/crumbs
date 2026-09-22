const UNITS = new Set([
  'cup', 'cups', 'tbsp', 'tablespoon', 'tablespoons', 'tsp', 'teaspoon', 'teaspoons',
  'oz', 'ounce', 'ounces', 'lb', 'pound', 'pounds', 'g', 'ml', 'l', 'kg',
  'clove', 'cloves', 'handful', 'handfuls', 'pinch', 'pinches', 'scoop', 'scoops',
  'can', 'cans', 'bunch', 'bunches', 'stalk', 'stalks', 'head', 'heads',
  'piece', 'pieces', 'large', 'small', 'medium', 'extra', 'virgin', 'frozen',
])

const STOPWORDS = new Set([
  'of', 'and', 'to', 'for', 'with', 'fresh', 'plus', 'serving', 'serve', 'chopped',
  'diced', 'sliced', 'grated', 'minced', 'melted', 'softened', 'rinsed', 'drained',
  'toasted', 'roasted', 'cooked', 'crushed', 'into', 'the', 'your', 'leaf', 'leaves',
  'mixed', 'warm', 'cubed', 'halved', 'cloves',
])

const QUANTITY = /^\d/

export function ingredientKeywords(ingredient) {
  return ingredient
    .toLowerCase()
    .split(/[\s,()]+/)
    .filter(Boolean)
    .filter(
      (token) =>
        !QUANTITY.test(token) &&
        !UNITS.has(token) &&
        !STOPWORDS.has(token) &&
        token.length >= 3,
    )
}

export function matchedIngredientIndexes(ingredients, step) {
  const text = ` ${step.toLowerCase()} `
  const indexes = []
  ingredients.forEach((ingredient, i) => {
    const hit = ingredientKeywords(ingredient).some((keyword) =>
      new RegExp(`\\b${keyword}s?\\b`).test(text),
    )
    if (hit) indexes.push(i)
  })
  return indexes
}

export function stepSegments(step, ingredientIndexes, ingredients) {
  const keywordRegexes = ingredientIndexes.flatMap((i) =>
    ingredientKeywords(ingredients[i]).map((keyword) => new RegExp(`^${keyword}s?$`, 'i')),
  )
  if (keywordRegexes.length === 0) return [{ text: step, ingredient: false }]

  return step.split(/([A-Za-z']+)/).filter(Boolean).map((part) => {
    const isWord = /^[A-Za-z']+$/.test(part)
    return {
      text: part,
      ingredient: isWord && keywordRegexes.some((re) => re.test(part)),
    }
  })
}
