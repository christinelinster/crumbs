import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { formatDuration, formatLabel, normalizeArray } from '../utils/recipe'
import {
  parseAssistantContent,
  parseInlineMarkdown,
  scrollChatToLatest,
} from '../utils/chat'

function ChatMark() {
  return (
    <span className="chat-mark" aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  )
}

function RecipeReference({ recipe }) {
  const labels = [
    ...normalizeArray(recipe.category),
    ...normalizeArray(recipe.tags),
  ].slice(0, 2)

  return (
    <Link
      to={`/recipe/${encodeURIComponent(recipe.slug)}`}
      className="chat-recipe-card"
    >
      <span className="chat-recipe-kicker">Recipe reference</span>
      <strong>{recipe.title}</strong>
      <span className="chat-recipe-meta">
        {labels.map(formatLabel).join(' · ')}
        {recipe.total_time_minutes != null && ` · ${formatDuration(recipe.total_time_minutes)}`}
      </span>
      {typeof recipe.similarity_score === 'number' && (
        <span className="chat-card-score">
          similarity_score: {recipe.similarity_score.toFixed(2)}
        </span>
      )}
      <span className="chat-recipe-arrow" aria-hidden="true">↗</span>
    </Link>
  )
}

function InlineMarkdown({ text }) {
  return parseInlineMarkdown(text).map((token, index) => {
    if (token.type === 'strong') {
      return <strong key={`strong-${index}`}>{token.text}</strong>
    }

    return <span key={`text-${index}`}>{token.text}</span>
  })
}

function AssistantAnswer({ content }) {
  const blocks = parseAssistantContent(content)

  return (
    <div className="chat-answer">
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          const Heading = `h${Math.min(Math.max(block.level, 2), 4)}`
          return (
            <Heading className="chat-answer-heading" key={`heading-${index}`}>
              <InlineMarkdown text={block.text} />
            </Heading>
          )
        }

        if (block.type === 'unordered-list' || block.type === 'ordered-list') {
          const List = block.type === 'ordered-list' ? 'ol' : 'ul'
          return (
            <List
              className={`chat-answer-list chat-answer-list--${block.type}`}
              key={`list-${index}`}
            >
              {block.items.map((item, itemIndex) => (
                <li key={`${index}-${itemIndex}`}>
                  <InlineMarkdown text={item} />
                </li>
              ))}
            </List>
          )
        }

        return (
          <p className="chat-answer-paragraph" key={`paragraph-${index}`}>
            <InlineMarkdown text={block.text} />
          </p>
        )
      })}
    </div>
  )
}

function ChatMessage({ message }) {
  if (message.role === 'user') {
    return (
      <div className="chat-message chat-message--user">
        <span className="chat-message-label">You</span>
        <p>{message.content}</p>
      </div>
    )
  }

  return (
    <div className="chat-message chat-message--assistant">
      <span className="chat-message-label"><ChatMark /> Crumbs</span>
      <AssistantAnswer content={message.content} />
      {message.recipeCards?.length > 0 && (
        <div className="chat-references">
          <span className="chat-references-label">Recipes used for this answer</span>
          {message.recipeCards.map((recipe) => (
            <RecipeReference
              key={recipe.slug}
              recipe={recipe}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default function ChatPanel({
  isOpen,
  onClose,
  onNewChat,
  messages,
  loading,
  error,
  sendMessage,
  recipeContext,
  onClearRecipeContext,
}) {
  const [draft, setDraft] = useState('')
  const messagesRef = useRef(null)

  useEffect(() => {
    if (isOpen) scrollChatToLatest(messagesRef.current)
  }, [error, isOpen, loading, messages])

  if (!isOpen) return null

  async function handleSubmit(event) {
    event.preventDefault()
    const sent = await sendMessage(draft)
    if (sent) setDraft('')
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  function handleNewChat() {
    onNewChat()
    setDraft('')
  }

  return (
    <>
      <button
        type="button"
        className="chat-backdrop"
        aria-label="Close Crumbs chat"
        onClick={onClose}
      />
      <aside
        id="chat-panel"
        className="chat-panel"
        aria-label="Crumbs recipe chat"
        role="dialog"
        aria-modal="true"
      >
        <header className="chat-panel-header">
          <div>
            <span className="chat-panel-kicker"><ChatMark /> Crumbs kitchen companion</span>
            <h2>What are you hungry for?</h2>
            <p>Ask for a recipe, an idea, or a way through dinner.</p>
          </div>
          <div className="chat-panel-actions">
            <button type="button" className="chat-icon-button" onClick={handleNewChat}>
              New chat
            </button>
            <button type="button" className="chat-close" onClick={onClose} aria-label="Close chat">
              ×
            </button>
          </div>
        </header>

        {recipeContext && (
          <div className="chat-context" role="status">
            <div className="chat-context-copy">
              <span className="chat-context-label">Discussing</span>
              <strong>{recipeContext.title}</strong>
            </div>
            <button
              type="button"
              className="chat-context-clear"
              onClick={onClearRecipeContext}
            >
              Clear
            </button>
          </div>
        )}

        <div ref={messagesRef} className="chat-messages" aria-live="polite">
          {messages.length === 0 && !loading && (
            <div className="chat-empty">
              <span className="chat-empty-mark"><ChatMark /></span>
              <p className="chat-empty-title">A little help from the archive.</p>
              <p>Try “something quick with eggs” or “what can I make for dinner?”</p>
            </div>
          )}

          {messages.map((message, index) => (
            <ChatMessage
              key={`${message.role}-${index}`}
              message={message}
            />
          ))}

          {loading && (
            <div className="chat-message chat-message--assistant chat-message--loading">
              <span className="chat-message-label"><ChatMark /> Crumbs</span>
              <span className="chat-loading-dots" aria-label="Crumbs is thinking">
                <i />
                <i />
                <i />
              </span>
            </div>
          )}

          {error && (
            <div className="chat-error" role="alert">
              <strong>That didn’t come through.</strong>
              <span>{error}</span>
              <small>Your question is still in the box. Try sending it again.</small>
            </div>
          )}
        </div>

        <form className="chat-composer" onSubmit={handleSubmit}>
          <label className="sr-only" htmlFor="chat-question">Ask Crumbs a question</label>
          <textarea
            id="chat-question"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask what to make…"
            rows={2}
            disabled={loading}
          />
          <div className="chat-composer-footer">
            <span>Enter to send · Shift + Enter for a new line</span>
            <button type="submit" className="chat-send" disabled={loading || !draft.trim()}>
              {loading ? 'Thinking…' : 'Send'}
            </button>
          </div>
        </form>
      </aside>
    </>
  )
}
