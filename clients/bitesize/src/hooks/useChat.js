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
  const { messages, retrievalBackend, sharedMemory } = session
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
          sharedMemory: sharedMemory && retrievalBackend === 'zep',
          threadUuid: session.threadUuid,
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
      }))
      return true
    } catch (requestError) {
      setError(errorMessage(requestError))
      return false
    } finally {
      setLoading(false)
    }
  }, [loading, messages, recipeSlug, retrievalBackend, sharedMemory, session.threadUuid])

  const reset = useCallback(() => {
    setSession((current) => newChatSession(current))
    setError(null)
  }, [])

  function changeRetrievalBackend(backend) {
    if (loading) return
    setSession((current) => newChatSession({ ...current, retrievalBackend: backend }))
    setError(null)
  }

  function changeSharedMemory(enabled) {
    if (loading) return
    setSession((current) => ({ ...current, sharedMemory: enabled, threadUuid: null }))
  }

  return {
    messages, loading, error, sendMessage, reset, retrievalBackend, changeRetrievalBackend,
    sharedMemory, changeSharedMemory, storageAvailable,
  }
}
