import { useCallback, useEffect, useState } from 'react'

const cachedRecipes = new Map()
const inFlight = new Map()

function fetchRecipe(slug) {
  if (cachedRecipes.has(slug)) return Promise.resolve(cachedRecipes.get(slug))

  if (!inFlight.has(slug)) {
    const request = fetch(`/api/recipes/${encodeURIComponent(slug)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
        return res.json()
      })
      .then((data) => {
        cachedRecipes.set(slug, data)
        return data
      })
      .finally(() => {
        inFlight.delete(slug)
      })

    inFlight.set(slug, request)
  }

  return inFlight.get(slug)
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error)
}

export default function useRecipe(slug) {
  const [recipe, setRecipe] = useState(() => cachedRecipes.get(slug) ?? null)
  const [loading, setLoading] = useState(() => Boolean(slug && !cachedRecipes.has(slug)))
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    const cached = slug ? cachedRecipes.get(slug) : null

    setRecipe(cached ?? null)
    setError(null)

    if (!slug || cached) {
      setLoading(false)
      return () => {
        active = false
      }
    }

    setLoading(true)
    fetchRecipe(slug)
      .then((data) => {
        if (active) setRecipe(data)
      })
      .catch((err) => {
        if (active) setError(errorMessage(err))
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [slug])

  const retry = useCallback(() => {
    if (!slug) return

    setLoading(true)
    setError(null)
    fetchRecipe(slug)
      .then((data) => setRecipe(data))
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false))
  }, [slug])

  return { recipe, loading, error, retry }
}
