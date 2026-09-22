import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import useRecipes from '../hooks/useRecipes'
import { RECIPE_ACCENT, RECIPE_ICON } from '../data/categories'
import { matchedIngredientIndexes, stepSegments } from '../utils/ingredients'
import FavButton from '../components/FavButton'
import RecipeIcon from '../components/RecipeIcon'

export default function RecipeDetail({ isFavourite, toggleFavourite }) {
  const { id } = useParams()
  const { recipes, loading, error, retry } = useRecipes()
  const recipe = (recipes ?? []).find((r) => r.id === id)
  const [hoveredStep, setHoveredStep] = useState(null)

  const stepMatches = useMemo(
    () =>
      recipe
        ? recipe.instructions.map((step) => matchedIngredientIndexes(recipe.ingredients, step))
        : [],
    [recipe],
  )

  if (loading && !recipes) {
    return (
      <main className="page">
        <div className="empty">
          <span className="empty-emoji" aria-hidden="true">
            ⏳
          </span>
          <p className="empty-title">Loading recipe…</p>
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

  if (!recipe) {
    return (
      <main className="page">
        <div className="empty">
          <span className="empty-emoji" aria-hidden="true">🤔</span>
          <p className="empty-title">Not in the archive</p>
          <Link to="/" className="btn">
            Back to All Recipes
          </Link>
        </div>
      </main>
    )
  }

  const activeIngredients = hoveredStep !== null ? stepMatches[hoveredStep] : []

  return (
    <main className="page">
      <Link to="/" className="back-link">← All Recipes</Link>

      <article className="detail" style={{ '--accent': RECIPE_ACCENT }}>
        <div className="detail-hero">
          <div className="detail-emoji" aria-hidden="true">
            <RecipeIcon name={RECIPE_ICON} className="dish-icon" />
          </div>
          <div className="detail-head">
            <div className="detail-head-top">
              <div className="card-tags">
                <span className="chip chip--static">{recipe.category}</span>
                <span className="chip chip--static chip--time">⏱ {recipe.time} min</span>
                <span className="chip chip--static">👥 {recipe.servings} servings</span>
              </div>
              <FavButton
                isFavourite={isFavourite(recipe.id)}
                onToggle={() => toggleFavourite(recipe.id)}
                label={isFavourite(recipe.id) ? `Remove ${recipe.name} from favourites` : `Add ${recipe.name} to favourites`}
              />
            </div>
            <h1 className="detail-title">{recipe.name}</h1>
          </div>
        </div>

        <div className="macro-bar">
          <div className="macro">
            <strong>{recipe.calories}</strong>
            <span>kcal</span>
          </div>
          <div className="macro">
            <strong>{recipe.protein}g</strong>
            <span>protein</span>
          </div>
          <div className="macro">
            <strong>{recipe.fat}g</strong>
            <span>fat</span>
          </div>
          <div className="macro">
            <strong>{recipe.carbs}g</strong>
            <span>carbs</span>
          </div>
        </div>

        <div className="detail-grid">
          <section className="panel">
            <h2 className="panel-title">Ingredients</h2>
            <p className="panel-hint">Hover a step to see what it uses.</p>
            <ul className="ingredients">
              {recipe.ingredients.map((item, i) => (
                <li
                  key={item}
                  className={activeIngredients.includes(i) ? 'is-active' : ''}
                >
                  {item}
                </li>
              ))}
            </ul>
          </section>

          <section className="panel">
            <h2 className="panel-title">Instructions</h2>
            <ol className="steps">
              {recipe.instructions.map((step, i) => (
                <li
                  key={step}
                  className={hoveredStep === i ? 'is-hovered' : ''}
                  onMouseEnter={() => setHoveredStep(i)}
                  onMouseLeave={() => setHoveredStep(null)}
                >
                  <span className="step-num">{i + 1}</span>
                  <p>
                    {stepSegments(step, stepMatches[i], recipe.ingredients).map((seg, j) =>
                      seg.ingredient ? (
                        <mark key={j} className="step-ingredient">{seg.text}</mark>
                      ) : (
                        <span key={j}>{seg.text}</span>
                      ),
                    )}
                  </p>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </article>
    </main>
  )
}
