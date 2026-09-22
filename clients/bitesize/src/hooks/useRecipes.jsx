import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

const RecipesContext = createContext(null)

let cachedRecipes = null
let inFlight = null

function fetchRecipes() {
  if (cachedRecipes) return Promise.resolve(cachedRecipes)
  if (!inFlight) {
    inFlight = fetch('/api/recipes')
      .then((res) => {
        if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
        return res.json()
      })
      .then((data) => {
        cachedRecipes = data
        return data
      })
      .finally(() => {
        inFlight = null
      })
  }
  return inFlight
}

export function RecipesProvider({ children }) {
  const [recipes, setRecipes] = useState(cachedRecipes)
  const [loading, setLoading] = useState(!cachedRecipes)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (cachedRecipes) return
    let active = true
    fetchRecipes()
      .then((data) => {
        if (active) setRecipes(data)
      })
      .catch((err) => {
        if (active) setError(err.message)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  const retry = useCallback(() => {
    setLoading(true)
    setError(null)
    fetchRecipes()
      .then((data) => setRecipes(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const value = useMemo(
    () => {
      const calorieValues = (recipes ?? [])
        .map((recipe) => recipe.calories)
        .filter((calories) => Number.isFinite(calories))
      const maxCalories = calorieValues.length ? Math.max(...calorieValues) : 0
      return { recipes, maxCalories, loading, error, retry }
    },
    [recipes, loading, error, retry],
  )

  return <RecipesContext.Provider value={value}>{children}</RecipesContext.Provider>
}

export default function useRecipes() {
  return useContext(RecipesContext)
}
