function buildHistory(messages) {
  return messages.map(({ role, content, recipeCards }) => {
    const message = { role, content }
    const recipeReferences = role === 'assistant' && Array.isArray(recipeCards)
      ? recipeCards
        .filter(card => (
          typeof card?.title === 'string'
          && card.title.trim()
          && typeof card?.slug === 'string'
          && card.slug.trim()
        ))
        .map(({ title, slug }) => ({ title, slug }))
      : []

    if (recipeReferences.length > 0) message.recipe_references = recipeReferences
    return message
  })
}

const CHAT_BACKENDS = {
  vector: ({ messages }) => ({ history: buildHistory(messages) }),
  zep: ({ threads }) => ({
    ...(threads.threadUuid ? { thread_uuid: threads.threadUuid } : {}),
  }),
  graphiti: ({ threads }) => ({
    graphiti_memory: true,
    ...(threads.graphitiThreadUuid ? { graphiti_thread_uuid: threads.graphitiThreadUuid } : {}),
  }),
}

const CHAT_BACKEND_NAMES = Object.keys(CHAT_BACKENDS)

export function buildChatRequest(question, messages, recipeSlug = null, retrievalBackend = null, threads = {}) {
  const backendFields = (CHAT_BACKENDS[retrievalBackend] ?? CHAT_BACKENDS.vector)({ messages, threads })
  const request = { question: question.trim(), ...backendFields }
  if (recipeSlug) request.recipe_slug = recipeSlug
  if (retrievalBackend) request.retrieval_backend = retrievalBackend
  return request
}

export function scrollChatToLatest(container) {
  if (!container) return

  if (typeof container.scrollTo === 'function') {
    container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' })
    return
  }

  container.scrollTop = container.scrollHeight
}

export function appendUserMessage(messages, question) {
  const lastMessage = messages.at(-1)
  if (lastMessage?.role === 'user' && lastMessage.content === question) {
    return messages
  }

  return [...messages, { role: 'user', content: question }]
}

export function appendAssistantMessage(messages, response) {
  return [
    ...messages,
    {
      role: 'assistant',
      content: response.answer,
      recipeCards: response.recipe_cards ?? [],
      ...(response.memory_status ? { memoryStatus: response.memory_status } : {}),
      ...(response.graphiti_memory_status ? { graphitiMemoryStatus: response.graphiti_memory_status } : {}),
    },
  ]
}

export function appendChatExchange(messages, question, response) {
  return appendAssistantMessage(
    appendUserMessage(messages, question),
    response,
  )
}

export function parseInlineMarkdown(value) {
  const text = String(value ?? '')
  const tokens = []
  const pattern = /\*\*(.+?)\*\*|__(.+?)__|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g
  let lastIndex = 0

  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0
    if (start > lastIndex) {
      tokens.push({ type: 'text', text: text.slice(lastIndex, start) })
    }
    if (match[3] && match[4]) {
      tokens.push({ type: 'link', text: match[3], href: match[4] })
    } else {
      tokens.push({ type: 'strong', text: match[1] ?? match[2] })
    }
    lastIndex = start + match[0].length
  }

  if (lastIndex < text.length) {
    tokens.push({ type: 'text', text: text.slice(lastIndex) })
  }

  return tokens
}

export function parseAssistantContent(content) {
  const blocks = []
  let paragraphLines = []
  let listType = null
  let listItems = []
  let listStart = null

  function flushParagraph() {
    if (paragraphLines.length === 0) return
    blocks.push({ type: 'paragraph', text: paragraphLines.join('\n') })
    paragraphLines = []
  }

  function flushList() {
    if (listItems.length === 0) return
    const block = { type: listType, items: listItems }
    if (listType === 'ordered-list') block.start = listStart
    blocks.push(block)
    listType = null
    listItems = []
    listStart = null
  }

  function flushBlocks() {
    flushParagraph()
    flushList()
  }

  for (const line of String(content ?? '').split(/\r?\n/)) {
    const heading = line.match(/^\s*(#{1,6})\s+(.+?)\s*#*\s*$/)
    const unorderedItem = line.match(/^\s*[-*]\s+(.+)$/)
    const orderedItem = line.match(/^\s*(\d+)[.)]\s+(.+)$/)

    if (heading) {
      flushBlocks()
      blocks.push({
        type: 'heading',
        level: heading[1].length,
        text: heading[2],
      })
      continue
    }

    if (unorderedItem || orderedItem) {
      flushParagraph()
      const nextListType = unorderedItem ? 'unordered-list' : 'ordered-list'
      if (listType !== nextListType) {
        flushList()
        listType = nextListType
        if (nextListType === 'ordered-list') listStart = Number(orderedItem[1])
      }
      listItems.push(unorderedItem ? unorderedItem[1] : orderedItem[2])
      continue
    }

    if (!line.trim()) {
      flushParagraph()
      continue
    }

    flushList()
    paragraphLines.push(line)
  }

  flushBlocks()
  return blocks
}


const CHAT_SESSION_KEY = 'crumbs-chat-v1'

export function newChatSession(previous = {}) {
  return {
    retrievalBackend: previous.retrievalBackend ?? 'zep',
    messages: [], threadUuid: null, graphitiThreadUuid: null,
    conversations: previous.conversations ?? {},
  }
}

export function switchChatBackend(session, backend) {
  if (backend === session.retrievalBackend || !CHAT_BACKEND_NAMES.includes(backend)) return session
  const conversations = {
    ...session.conversations,
    [session.retrievalBackend]: {
      messages: session.messages,
      threadUuid: session.threadUuid,
      graphitiThreadUuid: session.graphitiThreadUuid,
    },
  }
  const next = conversations[backend] ?? newChatSession()
  delete conversations[backend]
  return { ...next, retrievalBackend: backend, conversations }
}

function restoreConversation(saved) {
  return {
    messages: saved.messages.filter(message => (
      ['user', 'assistant'].includes(message?.role) && typeof message.content === 'string'
    )).map(message => message.role === 'assistant'
      ? { ...message, recipeCards: Array.isArray(message.recipeCards) ? message.recipeCards : [] }
      : message),
    threadUuid: typeof saved.threadUuid === 'string' ? saved.threadUuid : null,
    graphitiThreadUuid: typeof saved.graphitiThreadUuid === 'string' ? saved.graphitiThreadUuid : null,
  }
}

export function loadChatSession(storage) {
  try {
    const saved = JSON.parse((storage ?? globalThis.localStorage).getItem(CHAT_SESSION_KEY))
    if (saved && Array.isArray(saved.messages)) {
      const backend = CHAT_BACKEND_NAMES.includes(saved.retrievalBackend) ? saved.retrievalBackend : 'zep'
      const conversations = Object.fromEntries(CHAT_BACKEND_NAMES
        .filter(name => name !== backend && Array.isArray(saved.conversations?.[name]?.messages))
        .map(name => [name, restoreConversation(saved.conversations[name])]))
      return { ...restoreConversation(saved), retrievalBackend: backend, conversations }
    }
  } catch { /* Missing or blocked storage leaves chat usable. */ }
  return newChatSession()
}

export function saveChatSession(session, storage) {
  try {
    (storage ?? globalThis.localStorage).setItem(CHAT_SESSION_KEY, JSON.stringify(session))
    return true
  } catch {
    return false
  }
}
