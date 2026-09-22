import { useMemo, useState } from 'react'
import { categories } from '../data/categories'
import useRecipes from '../hooks/useRecipes'
import Filters from '../components/Filters'
import RecipeCard from '../components/RecipeCard'

export default function Home({ favouriteIds, isFavourite, toggleFavourite }) {
  const { recipes, maxCalories, loading, error, retry } = useRecipes()
  const [category, setCategory] = useState(categories[0])
  const [calorieLimit, setCalorieLimit] = useState(null)
  const [showFavourites, setShowFavourites] = useState(false)

  const effectiveLimit = calorieLimit ?? maxCalories

  const visible = useMemo(
    () =>
      (recipes ?? []).filter(
        (r) =>
          (category === 'All' || r.category === category) &&
          r.calories <= effectiveLimit &&
          (!showFavourites || favouriteIds.includes(r.id)),
      ),
    [recipes, category, effectiveLimit, showFavourites, favouriteIds],
  )

  if (loading && !recipes) {
    return (
      <main className="page">
        <div className="empty">
          <span className="empty-emoji" aria-hidden="true">
            ⏳
          </span>
          <p className="empty-title">Loading recipes…</p>
        </div>
      </main>
    )
  }

  if (error && !recipes) {
    return (
      <main className="page">
        <div className="empty">
          <span className="empty-emoji" aria-hidden="true">
            ⚠️
          </span>
          <p className="empty-title">Couldn't load recipes</p>
          <p className="empty-sub">{error}</p>
          <button type="button" className="btn" onClick={retry}>
            Try again
          </button>
        </div>
      </main>
    )
  }

  return (
    <main className="page">
      <section className="hero">
        <p className="hero-eyebrow">Considered Cooking</p>
        <h1 className="hero-title">
          recipes with <span className="accent">intention</span>
        </h1>
        <p className="hero-sub">
          Macro-friendly recipes that still satisfy your taste buds.
        </p>
      </section>

      <Filters
        category={category}
        setCategory={setCategory}
        calorieLimit={effectiveLimit}
        setCalorieLimit={setCalorieLimit}
        maxCalories={maxCalories}
        showFavourites={showFavourites}
        setShowFavourites={setShowFavourites}
        favouriteCount={favouriteIds.length}
      />

      {visible.length > 0 ? (
        <div className="grid">
          {visible.map((recipe) => (
            <RecipeCard
              key={recipe.id}
              recipe={recipe}
              isFavourite={isFavourite}
              toggleFavourite={toggleFavourite}
            />
          ))}
        </div>
      ) : (
        <div className="empty">
          <span className="empty-emoji" aria-hidden="true">
            {showFavourites ? '💛' : '🍽️'}
          </span>
          <p className="empty-title">
            {showFavourites ? 'No favourites yet' : 'Nothing to be found'}
          </p>
          <p className="empty-sub">
            {showFavourites
              ? 'Tap the heart on any recipe to save it here.'
              : 'Adjust the calorie limit or choose another type.'}
          </p>
        </div>
      )}
    </main>
  )
}