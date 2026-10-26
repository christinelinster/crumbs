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

test('builds a chat request with compact recipe references', () => {
  const messages = [
    { role: 'user', content: 'I want breakfast.' },
    {
      role: 'assistant',
      content: 'Try steamed eggs.',
      recipeCards: [{ title: 'Steamed Eggs', slug: 'steamed-eggs', calories: 180 }],
    },
  ]

  assert.deepEqual(buildChatRequest('  What can I make?  ', messages), {
    question: 'What can I make?',
    history: [
      { role: 'user', content: 'I want breakfast.' },
      {
        role: 'assistant',
        content: 'Try steamed eggs.',
        recipe_references: [{ title: 'Steamed Eggs', slug: 'steamed-eggs' }],
      },
    ],
  })
})

test('sends ordered title and slug references from earlier assistant cards', () => {
  const request = buildChatRequest('More like these?', [
    { role: 'user', content: 'I want breakfast.' },
    {
      role: 'assistant',
      content: 'Here are two.',
      recipeCards: [
        { title: 'Egg Pancakes', slug: 'egg-pancakes', calories: 300 },
        { title: 'Turkey Bowl', slug: 'turkey-bowl', similarity_score: 0.4 },
      ],
    },
    { role: 'assistant', content: 'Anything else?' },
  ])

  assert.deepEqual(request.history, [
    { role: 'user', content: 'I want breakfast.' },
    {
      role: 'assistant',
      content: 'Here are two.',
      recipe_references: [
        { title: 'Egg Pancakes', slug: 'egg-pancakes' },
        { title: 'Turkey Bowl', slug: 'turkey-bowl' },
      ],
    },
    { role: 'assistant', content: 'Anything else?' },
  ])
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
      { type: 'ordered-list', start: 1, items: ['Whisk the eggs.'] },
    ],
  )
})

test('parses level-four headings used for recipe ingredient groups', () => {
  assert.deepEqual(
    parseAssistantContent('#### For the sauce\n- 2 tablespoons soy sauce'),
    [
      { type: 'heading', level: 4, text: 'For the sauce' },
      { type: 'unordered-list', items: ['2 tablespoons soy sauce'] },
    ],
  )
})

test('parses walkthrough steps and their per-step ingredient lists', () => {
  assert.deepEqual(
    parseAssistantContent(
      '1. Whisk the eggs until smooth.\nIngredients for this step:\n- 2 eggs\n- 1 cup water',
    ),
    [
      { type: 'ordered-list', start: 1, items: ['Whisk the eggs until smooth.'] },
      { type: 'paragraph', text: 'Ingredients for this step:' },
      { type: 'unordered-list', items: ['2 eggs', '1 cup water'] },
    ],
  )
})

test('preserves the step number when ingredient bullets split ordered lists', () => {
  assert.deepEqual(
    parseAssistantContent(
      '1. Whisk the eggs.\nIngredients for this step:\n- 2 eggs\n\n2. Steam until set.\nIngredients for this step:\n- 1 cup water',
    ),
    [
      { type: 'ordered-list', start: 1, items: ['Whisk the eggs.'] },
      { type: 'paragraph', text: 'Ingredients for this step:' },
      { type: 'unordered-list', items: ['2 eggs'] },
      { type: 'ordered-list', start: 2, items: ['Steam until set.'] },
      { type: 'paragraph', text: 'Ingredients for this step:' },
      { type: 'unordered-list', items: ['1 cup water'] },
    ],
  )
})

test('keeps numbered recommendations in one list across blank lines', () => {
  assert.deepEqual(
    parseAssistantContent('1. Sukiyaki fits.\n\n2. Beef noodle soup fits.'),
    [
      {
        type: 'ordered-list',
        start: 1,
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

test('parses Markdown source links into link tokens', () => {
  assert.deepEqual(
    parseInlineMarkdown('Source: [Recipe site](https://example.com/recipe) 🍲'),
    [
      { type: 'text', text: 'Source: ' },
      { type: 'link', text: 'Recipe site', href: 'https://example.com/recipe' },
      { type: 'text', text: ' 🍲' },
    ],
  )
})

test('leaves unsafe Markdown destinations as plain text', () => {
  assert.deepEqual(
    parseInlineMarkdown('[unsafe](javascript:alert(1))'),
    [{ type: 'text', text: '[unsafe](javascript:alert(1))' }],
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


test('sends the selected retrieval backend for Bitesize chat', () => {
  assert.equal(buildChatRequest('dinner', [], null, 'zep').retrieval_backend, 'zep')
  assert.equal(buildChatRequest('dinner', [], null, 'vector').retrieval_backend, 'vector')
  assert.equal(buildChatRequest('dinner', [], null, 'graphiti').retrieval_backend, 'graphiti')
})

test('reload preserves Graphiti as the selected retrieval backend', async () => {
  const { loadChatSession } = await import('./chat.js')
  const session = loadChatSession({ getItem: () => JSON.stringify({
    messages: [], retrievalBackend: 'graphiti',
  }) })
  assert.equal(session.retrievalBackend, 'graphiti')
})

test('reload restores transcript, backend, and graph thread IDs', async () => {
  const { loadChatSession, saveChatSession } = await import('./chat.js')
  let value = null
  const storage = { getItem: () => value, setItem: (key, data) => { value = data } }
  const session = {
    messages: [
      { role: 'user', content: 'I avoid onions.' },
      { role: 'assistant', content: 'Try tofu.', recipeCards: [{ slug: 'tofu' }], memoryStatus: 'saved' },
    ],
    threadUuid: 'thread-1', retrievalBackend: 'zep',
    graphitiThreadUuid: 'graphiti-thread-1',
  }
  assert.equal(saveChatSession(session, storage), true)
  assert.deepEqual(loadChatSession(storage), { ...session, conversations: {} })
})

test('new chat clears transcript and graph threads while keeping the backend', async () => {
  const { newChatSession } = await import('./chat.js')
  const next = newChatSession({
    messages: [{ role: 'user', content: 'Old chat' }],
    threadUuid: 'old-thread', graphitiThreadUuid: 'old-graphiti-thread', retrievalBackend: 'zep',
  })
  assert.deepEqual(next.messages, [])
  assert.equal(next.threadUuid, null)
  assert.equal(next.graphitiThreadUuid, null)
  assert.equal(next.retrievalBackend, 'zep')
})

test('blocked or corrupt storage leaves chat usable without claiming persistence', async () => {
  const { loadChatSession, saveChatSession } = await import('./chat.js')
  const storage = { getItem: () => '{invalid', setItem: () => { throw new Error('full') } }
  assert.deepEqual(loadChatSession(storage).messages, [])
  assert.equal(saveChatSession({ messages: [] }, storage), false)
})

test('Zep selection automatically saves only to Zep and reuses its thread', () => {
  const request = buildChatRequest('dinner', [], null, 'zep', {
    sharedMemory: false, graphitiMemory: true,
    threadUuid: 'zep-thread', graphitiThreadUuid: 'graphiti-thread',
  })
  assert.equal(request.shared_memory, undefined)
  assert.equal(request.thread_uuid, 'zep-thread')
  assert.equal(request.graphiti_memory, undefined)
  assert.equal(request.graphiti_thread_uuid, undefined)
})

test('Graphiti selection automatically saves only to Graphiti and reuses its thread', () => {
  const request = buildChatRequest('dinner', [], null, 'graphiti', {
    sharedMemory: true, graphitiMemory: false,
    threadUuid: 'zep-thread', graphitiThreadUuid: 'graphiti-thread',
  })
  assert.equal(request.graphiti_memory, true)
  assert.equal(request.graphiti_thread_uuid, 'graphiti-thread')
  assert.equal(request.shared_memory, undefined)
  assert.equal(request.thread_uuid, undefined)
  assert.equal(request.history, undefined)
})

test('first graph turns enable saving without supplying a thread ID', () => {
  const zep = buildChatRequest('dinner', [], null, 'zep')
  assert.equal(zep.shared_memory, undefined)
  assert.equal(zep.thread_uuid, undefined)
  const graphiti = buildChatRequest('dinner', [], null, 'graphiti')
  assert.equal(graphiti.graphiti_memory, true)
  assert.equal(graphiti.graphiti_thread_uuid, undefined)
  assert.equal(graphiti.history, undefined)
})

test('vector selection never saves to graph backends despite old saved choices', () => {
  const request = buildChatRequest('dinner', [], null, 'vector', {
    sharedMemory: true, graphitiMemory: true,
    threadUuid: 'zep-thread', graphitiThreadUuid: 'graphiti-thread',
  })
  for (const key of ['shared_memory', 'graphiti_memory', 'thread_uuid', 'graphiti_thread_uuid']) {
    assert.equal(request[key], undefined)
  }
})

test('reload drops retired memory choices and saves to the selected graph', async () => {
  const { loadChatSession, newChatSession } = await import('./chat.js')
  const saved = { messages: [], retrievalBackend: 'graphiti', sharedMemory: true, graphitiMemory: false }
  const session = loadChatSession({ getItem: () => JSON.stringify(saved) })
  assert.equal(session.sharedMemory, undefined)
  assert.equal(session.graphitiMemory, undefined)
  assert.equal(buildChatRequest('dinner', [], null, session.retrievalBackend, session).graphiti_memory, true)
  const reset = newChatSession(saved)
  assert.equal(reset.retrievalBackend, 'graphiti')
  assert.equal(reset.sharedMemory, undefined)
  assert.equal(reset.graphitiMemory, undefined)
})

test('Graphiti save status is preserved on assistant messages', () => {
  const messages = appendAssistantMessage([], {
    answer: 'Try tofu.', graphiti_memory_status: 'error',
  })
  assert.equal(messages[0].graphitiMemoryStatus, 'error')
})

test('switching back restores each backend transcript and thread IDs without mixing history', async () => {
  const { newChatSession, switchChatBackend } = await import('./chat.js')
  let session = {
    ...newChatSession({ retrievalBackend: 'graphiti' }),
    messages: [{ role: 'user', content: 'Graphiti question' }, { role: 'assistant', content: 'Graphiti answer', recipeCards: [] }],
    graphitiThreadUuid: 'graphiti-thread',
  }
  session = switchChatBackend(session, 'zep')
  assert.deepEqual(session.messages, [])
  assert.equal(session.threadUuid, null)
  session = { ...session, messages: [{ role: 'user', content: 'Zep question' }, { role: 'assistant', content: 'Zep answer', recipeCards: [] }], threadUuid: 'zep-thread' }
  session = switchChatBackend(session, 'vector')
  assert.deepEqual(session.messages, [])
  session = { ...session, messages: [{ role: 'user', content: 'Vector question' }] }
  session = switchChatBackend(session, 'graphiti')
  assert.equal(session.messages[1].content, 'Graphiti answer')
  assert.equal(session.graphitiThreadUuid, 'graphiti-thread')
  const request = buildChatRequest('Follow-up', session.messages, null, session.retrievalBackend, session)
  assert.equal(request.graphiti_thread_uuid, 'graphiti-thread')
  assert.equal(request.history, undefined)
  session = switchChatBackend(session, 'zep')
  assert.equal(session.messages[1].content, 'Zep answer')
  assert.equal(session.threadUuid, 'zep-thread')
  assert.equal(switchChatBackend(session, 'vector').messages[0].content, 'Vector question')
  assert.equal(switchChatBackend(session, 'zep'), session)
})

test('reload preserves inactive backend conversations and their threads', async () => {
  const { loadChatSession, saveChatSession, newChatSession, switchChatBackend } = await import('./chat.js')
  let stored
  const storage = { getItem: () => stored, setItem: (_, value) => { stored = value } }
  const graphiti = { ...newChatSession({ retrievalBackend: 'graphiti' }), messages: [{ role: 'user', content: 'Saved question' }], graphitiThreadUuid: 'saved-thread' }
  const zep = switchChatBackend(graphiti, 'zep')
  assert.equal(saveChatSession(zep, storage), true)
  const restored = switchChatBackend(loadChatSession(storage), 'graphiti')
  assert.deepEqual(restored.messages, graphiti.messages)
  assert.equal(restored.graphitiThreadUuid, 'saved-thread')
})

test('New chat resets only the selected backend and does not resurrect its old chat', async () => {
  const { newChatSession, switchChatBackend } = await import('./chat.js')
  let session = { ...newChatSession(), messages: [{ role: 'user', content: 'Old Zep' }], threadUuid: 'old-zep-thread' }
  session = switchChatBackend(session, 'graphiti')
  session = { ...session, messages: [{ role: 'user', content: 'Keep Graphiti' }], graphitiThreadUuid: 'keep-thread' }
  session = newChatSession(switchChatBackend(session, 'zep'))
  assert.deepEqual(session.messages, [])
  assert.equal(session.threadUuid, null)
  session = switchChatBackend(session, 'graphiti')
  assert.equal(session.messages[0].content, 'Keep Graphiti')
  assert.equal(session.graphitiThreadUuid, 'keep-thread')
  session = switchChatBackend(session, 'zep')
  assert.deepEqual(session.messages, [])
  assert.equal(session.threadUuid, null)
})

test('legacy saved chat is preserved under its selected backend on first switch', async () => {
  const { loadChatSession, switchChatBackend } = await import('./chat.js')
  const legacy = { messages: [{ role: 'user', content: 'Existing chat' }], retrievalBackend: 'graphiti', graphitiThreadUuid: 'existing-thread' }
  const loaded = loadChatSession({ getItem: () => JSON.stringify(legacy) })
  const restored = switchChatBackend(switchChatBackend(loaded, 'zep'), 'graphiti')
  assert.deepEqual(restored.messages, legacy.messages)
  assert.equal(restored.graphitiThreadUuid, 'existing-thread')
})

test('malformed inactive saved conversations do not discard the valid active chat', async () => {
  const { loadChatSession, switchChatBackend } = await import('./chat.js')
  const saved = {
    messages: [{ role: 'user', content: 'Keep active' }], retrievalBackend: 'zep',
    conversations: {
      graphiti: { messages: 'invalid' },
      vector: { messages: [null, { role: 'system', content: 'invalid' }, { role: 'assistant', content: 'Keep answer', recipeCards: null }], threadUuid: 123 },
    },
  }
  const session = loadChatSession({ getItem: () => JSON.stringify(saved) })
  assert.equal(session.messages[0].content, 'Keep active')
  assert.deepEqual(switchChatBackend(session, 'graphiti').messages, [])
  const vector = switchChatBackend(session, 'vector')
  assert.deepEqual(vector.messages, [{ role: 'assistant', content: 'Keep answer', recipeCards: [] }])
  assert.equal(vector.threadUuid, null)
})
