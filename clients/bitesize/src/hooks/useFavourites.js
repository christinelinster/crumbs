import { useCallback, useState } from 'react'

const STORAGE_KEY = 'bitesize:favourites'

function loadStored() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveStored(ids) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
  } catch {
    // localStorage unavailable (private mode) — keep in memory only
  }
}

export default function useFavourites() {
  const [favouriteIds, setFavouriteIds] = useState(loadStored)

  const toggleFavourite = useCallback((id) => {
    setFavouriteIds((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
      saveStored(next)
      return next
    })
  }, [])

  const isFavourite = useCallback((id) => favouriteIds.includes(id), [favouriteIds])

  return { favouriteIds, isFavourite, toggleFavourite }
}
