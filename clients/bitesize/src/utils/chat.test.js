import test from 'node:test'
import assert from 'node:assert/strict'
import {
  appendAssistantMessage,
  appendChatExchange,
  appendUserMessage,
  buildChatRequest,
  parseInlineMarkdown,
  parseAssistantContent,
  scrollChatToLatest,
} from './chat.js'
import { CHAT_LAUNCHER_LABEL } from './chatLauncher.js'

test('uses the Ask Crumbs launcher label', () => {
  assert.equal(CHAT_LAUNCHER_LABEL, 'Ask Crumbs')
})

test('builds a chat request from completed messages without sending recipe cards', () => {
  const messages = [
    { role: 'user', content: 'I want breakfast.' },
    {
      role: 'assistant',
      content: 'Try steamed eggs.',
      recipeCards: [{ slug: 'steamed-eggs' }],
    },
  ]

  assert.deepEqual(buildChatRequest('  What can I make?  ', messages), {
    question: 'What can I make?',
    history: [
      { role: 'user', content: 'I want breakfast.' },
      { role: 'assistant', content: 'Try steamed eggs.' },
    ],
  })
})

test('includes the active recipe slug in a recipe-specific chat request', () => {
  assert.deepEqual(buildChatRequest('  How much water?  ', [], 'steamed-eggs'), {
    question: 'How much water?',
    history: [],
    recipe_slug: 'steamed-eggs',
  })
})

test('scrolls the chat container to its newest content', () => {
  const calls = []
  const container = {
    scrollHeight: 480,
    scrollTo(options) {
      calls.push(options)
    },
  }

  scrollChatToLatest(container)

  assert.deepEqual(calls, [{ top: 480, behavior: 'smooth' }])
})

test('does nothing when the chat container is not mounted', () => {
  assert.doesNotThrow(() => scrollChatToLatest(null))
})

test('appends a successful user and assistant exchange with recipe cards', () => {
  const messages = [{ role: 'user', content: 'I want breakfast.' }]
  const response = {
    answer: 'Try steamed eggs.',
    recipe_cards: [{
      slug: 'steamed-eggs',
      title: 'Steamed Eggs',
      similarity_score: 0.91,
    }],
  }

  assert.deepEqual(appendChatExchange(messages, 'What can I make?', response), [
    { role: 'user', content: 'I want breakfast.' },
    { role: 'user', content: 'What can I make?' },
    {
      role: 'assistant',
      content: 'Try steamed eggs.',
      recipeCards: [{
        slug: 'steamed-eggs',
        title: 'Steamed Eggs',
        similarity_score: 0.91,
      }],
    },
  ])
})

test('appends the user message before the assistant response exists', () => {
  assert.deepEqual(
    appendUserMessage([], 'What can I make?'),
    [{ role: 'user', content: 'What can I make?' }],
  )
})

test('parses assistant headings and lists into renderable blocks', () => {
  assert.deepEqual(
    parseAssistantContent(
      '### Ingredients\n- 2 eggs\n- 1 cup water\n\n### Method\n1. Whisk the eggs.',
    ),
    [
      { type: 'heading', level: 3, text: 'Ingredients' },
      { type: 'unordered-list', items: ['2 eggs', '1 cup water'] },
      { type: 'heading', level: 3, text: 'Method' },
      { type: 'ordered-list', items: ['Whisk the eggs.'] },
    ],
  )
})

test('parses walkthrough steps and their per-step ingredient lists', () => {
  assert.deepEqual(
    parseAssistantContent(
      '1. Whisk the eggs until smooth.\nIngredients for this step:\n- 2 eggs\n- 1 cup water',
    ),
    [
      { type: 'ordered-list', items: ['Whisk the eggs until smooth.'] },
      { type: 'paragraph', text: 'Ingredients for this step:' },
      { type: 'unordered-list', items: ['2 eggs', '1 cup water'] },
    ],
  )
})

test('keeps numbered recommendations in one list across blank lines', () => {
  assert.deepEqual(
    parseAssistantContent('1. Sukiyaki fits.\n\n2. Beef noodle soup fits.'),
    [
      {
        type: 'ordered-list',
        items: ['Sukiyaki fits.', 'Beef noodle soup fits.'],
      },
    ],
  )
})

test('parses bold inline Markdown without leaving marker characters', () => {
  assert.deepEqual(
    parseInlineMarkdown('**Steamed Eggs** are silky and quick.'),
    [
      { type: 'strong', text: 'Steamed Eggs' },
      { type: 'text', text: ' are silky and quick.' },
    ],
  )
})

test('appends the assistant response to an already-visible user message', () => {
  const messages = [{ role: 'user', content: 'What can I make?' }]
  const response = { answer: 'Try steamed eggs.', recipe_cards: [] }

  assert.deepEqual(appendAssistantMessage(messages, response), [
    { role: 'user', content: 'What can I make?' },
    { role: 'assistant', content: 'Try steamed eggs.', recipeCards: [] },
  ])
})
