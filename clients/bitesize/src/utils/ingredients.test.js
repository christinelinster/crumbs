import test from 'node:test'
import assert from 'node:assert/strict'
import {
  ingredientKeywords,
  matchedIngredientIndexes,
  stepSegments,
} from './ingredients.js'

test('ignores parenthetical procedural notes when extracting ingredient keywords', () => {
  assert.deepEqual(
    ingredientKeywords('2 tablespoons oil (you can use any neutral oil)'),
    ['oil'],
  )
})

test('calls out a real ingredient in every step where it is used', () => {
  const ingredients = [
    '1 onion',
    '2 tablespoons oil (you can use any neutral oil)',
  ]

  assert.deepEqual(
    matchedIngredientIndexes(ingredients, 'Cook the onion in the oil.'),
    [0, 1],
  )
  assert.deepEqual(
    matchedIngredientIndexes(ingredients, 'Add the oil and stir until fragrant.'),
    [1],
  )

  assert.ok(
    stepSegments('Add the oil and stir until fragrant.', [1], ingredients).some(
      (segment) => segment.text.toLowerCase() === 'oil' && segment.ingredient,
    ),
  )
})

test('does not mark procedural words as inline ingredients', () => {
  const ingredients = ['2 tablespoons oil (you can use any neutral oil)']
  const segments = stepSegments('Stir until you are ready.', [0], ingredients)

  assert.equal(segments.some((segment) => segment.ingredient), false)
})
