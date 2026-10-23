import { useCallback, useEffect, useState } from 'react'
import {
  appendAssistantMessage,
  appendUserMessage,
  buildChatRequest,
  loadChatSession,
  newChatSession,
  saveChatSession,
} from '../utils/chat'

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error)
}

export default function useChat(recipeSlug = null) {
  const [session, setSession] = useState(loadChatSession)
  const { messages, retrievalBackend } = session
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [storageAvailable, setStorageAvailable] = useState(true)

  useEffect(() => {
    setStorageAvailable(saveChatSession(session))
  }, [session])

  const sendMessage = useCallback(async (question) => {
    const content = question.trim()
    if (!content || loading) return false

    const lastMessage = messages.at(-1)
    const requestHistory =
      lastMessage?.role === 'user' && lastMessage.content === content
        ? messages.slice(0, -1)
        : messages

    setSession((current) => ({ ...current, messages: appendUserMessage(current.messages, content) }))
    setLoading(true)
    setError(null)

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildChatRequest(content, requestHistory, recipeSlug, retrievalBackend, {
          threadUuid: session.threadUuid,
          graphitiThreadUuid: session.graphitiThreadUuid,
        })),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || `Request failed with status ${response.status}`)
      }
      setSession((current) => ({
        ...current,
        messages: appendAssistantMessage(current.messages, data),
        threadUuid: data.thread_uuid ?? current.threadUuid,
        graphitiThreadUuid: data.graphiti_thread_uuid ?? current.graphitiThreadUuid,
      }))
      return true
    } catch (requestError) {
      setError(errorMessage(requestError))
      return false
    } finally {
      setLoading(false)
    }
  }, [loading, messages, recipeSlug, retrievalBackend, session.threadUuid, session.graphitiThreadUuid])

  const reset = useCallback(() => {
    setSession((current) => newChatSession(current))
    setError(null)
  }, [])

  function changeRetrievalBackend(backend) {
    if (loading) return
    setSession((current) => newChatSession({ ...current, retrievalBackend: backend }))
    setError(null)
  }

  return {
    messages, loading, error, sendMessage, reset, retrievalBackend, changeRetrievalBackend,
    storageAvailable,
  }
}
