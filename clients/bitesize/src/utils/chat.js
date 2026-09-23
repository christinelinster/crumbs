export function buildChatRequest(question, messages, recipeSlug = null) {
  const request = {
    question: question.trim(),
    history: messages.map(({ role, content }) => ({ role, content })),
  }

  if (recipeSlug) request.recipe_slug = recipeSlug
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
  const pattern = /\*\*(.+?)\*\*|__(.+?)__/g
  let lastIndex = 0

  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0
    if (start > lastIndex) {
      tokens.push({ type: 'text', text: text.slice(lastIndex, start) })
    }
    tokens.push({ type: 'strong', text: match[1] ?? match[2] })
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

  function flushParagraph() {
    if (paragraphLines.length === 0) return
    blocks.push({ type: 'paragraph', text: paragraphLines.join('\n') })
    paragraphLines = []
  }

  function flushList() {
    if (listItems.length === 0) return
    blocks.push({ type: listType, items: listItems })
    listType = null
    listItems = []
  }

  function flushBlocks() {
    flushParagraph()
    flushList()
  }

  for (const line of String(content ?? '').split(/\r?\n/)) {
    const heading = line.match(/^\s*(#{1,3})\s+(.+?)\s*#*\s*$/)
    const unorderedItem = line.match(/^\s*[-*]\s+(.+)$/)
    const orderedItem = line.match(/^\s*\d+[.)]\s+(.+)$/)

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
      if (listType !== nextListType) flushList()
      listType = nextListType
      listItems.push((unorderedItem || orderedItem)[1])
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
