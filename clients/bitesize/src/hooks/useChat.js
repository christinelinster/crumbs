import { useCallback, useState } from 'react'
import {
  appendAssistantMessage,
  appendUserMessage,
  buildChatRequest,
} from '../utils/chat'

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error)
}

export default function useChat(recipeSlug = null) {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const sendMessage = useCallback(async (question) => {
    const content = question.trim()
    if (!content || loading) return false

    const lastMessage = messages.at(-1)
    const requestHistory =
      lastMessage?.role === 'user' && lastMessage.content === content
        ? messages.slice(0, -1)
        : messages

    setMessages((current) => appendUserMessage(current, content))
    setLoading(true)
    setError(null)

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildChatRequest(content, requestHistory, recipeSlug)),
      })
      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || `Request failed with status ${response.status}`)
      }

      setMessages((current) => appendAssistantMessage(current, data))
      return true
    } catch (requestError) {
      setError(errorMessage(requestError))
      return false
    } finally {
      setLoading(false)
    }
  }, [loading, messages, recipeSlug])

  const reset = useCallback(() => {
    setMessages([])
    setError(null)
  }, [])

  return { messages, loading, error, sendMessage, reset }
}
