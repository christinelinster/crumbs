import { Fragment, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import useRecipe from '../hooks/useRecipe'
import { RECIPE_ACCENT, RECIPE_ICON } from '../data/categories'
import { matchedIngredientIndexes, stepSegments } from '../utils/ingredients'
import { formatLabel, groupHeadingsAt, normalizeArray } from '../utils/recipe'
import FavButton from '../components/FavButton'
import RecipeIcon from '../components/RecipeIcon'

const EMPTY_LIST = []

export default function RecipeDetail({ isFavourite, toggleFavourite }) {
  const { slug } = useParams()
  const { recipe, loading, error, retry } = useRecipe(slug)
  const [hoveredStep, setHoveredStep] = useState(null)
  const ingredients = recipe?.ingredients ?? EMPTY_LIST
  const instructions = recipe?.instructions ?? EMPTY_LIST
  const categories = normalizeArray(recipe?.category)
  const tags = normalizeArray(recipe?.tags)

  const ingredientGroupHeadings = useMemo(
    () => groupHeadingsAt(recipe?.ingredient_groups),
    [recipe],
  )
  const instructionGroupHeadings = useMemo(
    () => groupHeadingsAt(recipe?.instruction_groups),
    [recipe],
  )

  const stepMatches = useMemo(
    () => instructions.map((step) => matchedIngredientIndexes(ingredients, step)),
    [ingredients, instructions],
  )

  if (loading && !recipe) {
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

  if (error && !recipe) {
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
                {categories.map((value) => (
                  <span key={`category-${value}`} className="chip chip--static">
                    {formatLabel(value)}
                  </span>
                ))}
                {tags.map((value) => (
                  <span key={`tag-${value}`} className="chip chip--static chip--tag">
                    {formatLabel(value)}
                  </span>
                ))}
                {recipe.cuisine && (
                  <span className="chip chip--static">{formatLabel(recipe.cuisine)}</span>
                )}
                {recipe.total_time_minutes != null && (
                  <span className="chip chip--static chip--time">
                    ⏱ {recipe.total_time_minutes} min
                  </span>
                )}
                {recipe.servings != null && (
                  <span className="chip chip--static">👥 {recipe.servings} servings</span>
                )}
              </div>
              <FavButton
                isFavourite={isFavourite(recipe.slug)}
                onToggle={() => toggleFavourite(recipe.slug)}
                label={isFavourite(recipe.slug) ? `Remove ${recipe.title} from favourites` : `Add ${recipe.title} to favourites`}
              />
            </div>
            <h1 className="detail-title">{recipe.title}</h1>
            {recipe.description && <p className="detail-description">{recipe.description}</p>}
          </div>
        </div>

        <div className="macro-bar">
          <div className="macro">
            <strong>{recipe.calories == null ? '—' : recipe.calories}</strong>
            <span>kcal</span>
          </div>
          <div className="macro">
            <strong>{recipe.protein == null ? '—' : `${recipe.protein}g`}</strong>
            <span>protein</span>
          </div>
          <div className="macro">
            <strong>{recipe.fat == null ? '—' : `${recipe.fat}g`}</strong>
            <span>fat</span>
          </div>
          <div className="macro">
            <strong>{recipe.carbs == null ? '—' : `${recipe.carbs}g`}</strong>
            <span>carbs</span>
          </div>
        </div>

        <div className="detail-grid">
          <section className="panel">
            <h2 className="panel-title">Ingredients</h2>
            <p className="panel-hint">Hover a step to see what it uses.</p>
            <ul className="ingredients">
              {ingredients.map((item, i) => {
                const position = i + 1
                const groupName = ingredientGroupHeadings.get(position)
                return (
                  <Fragment key={`ingredient-${position}-${item}`}>
                    {groupName && <li className="group-heading">{groupName}</li>}
                    <li className={activeIngredients.includes(i) ? 'is-active' : ''}>
                      {item}
                    </li>
                  </Fragment>
                )
              })}
            </ul>
          </section>

          <section className="panel">
            <h2 className="panel-title">Instructions</h2>
            <ol className="steps">
              {instructions.map((step, i) => {
                const position = i + 1
                const groupName = instructionGroupHeadings.get(position)
                return (
                  <Fragment key={`instruction-${position}-${step}`}>
                    {groupName && <li className="group-heading">{groupName}</li>}
                    <li
                      className={hoveredStep === i ? 'is-hovered' : ''}
                      onMouseEnter={() => setHoveredStep(i)}
                      onMouseLeave={() => setHoveredStep(null)}
                    >
                      <span className="step-num">{position}</span>
                      <p>
                        {stepSegments(step, stepMatches[i], ingredients).map((seg, j) =>
                          seg.ingredient ? (
                            <mark key={j} className="step-ingredient">{seg.text}</mark>
                          ) : (
                            <span key={j}>{seg.text}</span>
                          ),
                        )}
                      </p>
                    </li>
                  </Fragment>
                )
              })}
            </ol>
          </section>
        </div>

        {(recipe.notes || recipe.source_url) && (
          <footer className="detail-meta">
            {recipe.notes && (
              <div>
                <h2 className="panel-title">Notes</h2>
                <p>{recipe.notes}</p>
              </div>
            )}
            {recipe.source_url && (
              <a href={recipe.source_url} target="_blank" rel="noreferrer">
                {recipe.source_label || 'View source recipe'} ↗
              </a>
            )}
          </footer>
        )}
      </article>
    </main>
  )
}
