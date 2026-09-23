import test from 'node:test'
import assert from 'node:assert/strict'
import { categories, tags } from '../data/categories.js'
import {
  categoryMatches,
  filterRecipes,
  formatDuration,
  formatServings,
  groupHeadingsAt,
  normalizeArray,
} from './recipe.js'

const FILTER_RECIPES = [
  {
    slug: 'sukiyaki-japanese-one-pot-meal',
    title: 'Sukiyaki: Japanese One Pot Meal',
    category: ['dinner'],
    tags: ['one-pot'],
    cuisine: 'Japanese',
    calories: 450,
  },
  {
    slug: 'taiwanese-beef-noodle-soup',
    title: 'Taiwanese Beef Noodle Soup',
    category: ['dinner'],
    tags: ['beef', 'soup'],
    cuisine: 'Taiwanese',
    calories: 650,
  },
  {
    slug: 'banana-oat-pancakes',
    title: 'Banana Oat Pancakes',
    category: ['breakfast'],
    tags: [],
    cuisine: 'American',
    calories: 300,
  },
]

test('normalizes canonical arrays without changing their values', () => {
  assert.deepEqual(normalizeArray(['dinner', 'one-pot']), ['dinner', 'one-pot'])
  assert.deepEqual(normalizeArray('dinner'), ['dinner'])
  assert.deepEqual(normalizeArray(null), [])
})

test('formats serving metadata clearly for singular and plural recipes', () => {
  assert.equal(formatServings(1), '1 serving')
  assert.equal(formatServings(4), '4 servings')
})

test('formats recipe durations as hours and minutes when needed', () => {
  assert.equal(formatDuration(25), '25 min')
  assert.equal(formatDuration(60), '1 hr')
  assert.equal(formatDuration(90), '1 hr 30 min')
  assert.equal(formatDuration(150), '2 hr 30 min')
})

test('keeps only the first named marker for each group', () => {
  const headings = groupHeadingsAt([
    { position: 1, group_position: 1, group_name: 'For the sauce' },
    { position: 2, group_position: 1, group_name: 'For the sauce' },
    { position: 3, group_position: 2, group_name: null },
  ])

  assert.deepEqual([...headings.entries()], [[1, 'For the sauce']])
})

test('matches a selected category against the canonical category array', () => {
  const recipe = { category: ['dinner'], tags: ['soup'] }

  assert.equal(categoryMatches(recipe, 'Dinner'), true)
  assert.equal(categoryMatches(recipe, 'Soup'), false)
})

test('uses the corpus taxonomy for category and tag filters', () => {
  assert.deepEqual(categories, [
    'All',
    'Appetizer',
    'Breakfast',
    'Dessert',
    'Dinner',
    'Drink',
    'Lunch',
    'Side',
    'Snack',
  ])
  assert.deepEqual(tags, [
    'All',
    'Beef',
    'Chicken',
    'No Cook',
    'One Pot',
    'Pork',
    'Soup',
  ])
})

test('filters category and tag facets independently and searches recipe summaries', () => {
  assert.deepEqual(
    filterRecipes(FILTER_RECIPES, {
      category: 'Dinner',
      tag: 'Soup',
      showFavourites: false,
      favouriteIds: [],
    }),
    [FILTER_RECIPES[1]],
  )

  assert.deepEqual(
    filterRecipes(FILTER_RECIPES, {
      category: 'Dinner',
      tag: 'One Pot',
      calorieLimit: 500,
      showFavourites: false,
      favouriteIds: [],
    }),
    [FILTER_RECIPES[0]],
  )

  assert.deepEqual(
    filterRecipes(FILTER_RECIPES, {
      searchTerm: 'japanese one pot',
    }),
    [FILTER_RECIPES[0]],
  )
})
