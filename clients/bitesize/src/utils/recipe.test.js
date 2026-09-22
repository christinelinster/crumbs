import test from 'node:test'
import assert from 'node:assert/strict'
import { categoryMatches, groupHeadingsAt, normalizeArray } from './recipe.js'

test('normalizes canonical arrays without changing their values', () => {
  assert.deepEqual(normalizeArray(['dinner', 'one-pot']), ['dinner', 'one-pot'])
  assert.deepEqual(normalizeArray('dinner'), ['dinner'])
  assert.deepEqual(normalizeArray(null), [])
})

test('keeps only the first named marker for each group', () => {
  const headings = groupHeadingsAt([
    { position: 1, group_position: 1, group_name: 'For the sauce' },
    { position: 2, group_position: 1, group_name: 'For the sauce' },
    { position: 3, group_position: 2, group_name: null },
  ])

  assert.deepEqual([...headings.entries()], [[1, 'For the sauce']])
})

test('matches a selected category against canonical category or tag arrays', () => {
  const recipe = { category: ['dinner'], tags: ['high-protein'] }

  assert.equal(categoryMatches(recipe, 'Dinner'), true)
  assert.equal(categoryMatches(recipe, 'High Protein'), true)
  assert.equal(categoryMatches(recipe, 'Dessert'), false)
})
