import { Fragment, useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import useRecipe from '../hooks/useRecipe'
import { RECIPE_ACCENT, RECIPE_ICON } from '../data/categories'
import { matchedIngredientIndexes, stepSegments } from '../utils/ingredients'
import {
  formatDuration,
  formatLabel,
  formatServings,
  normalizeArray,
  sectionHeading,
  sectionItems,
} from '../utils/recipe'
import FavButton from '../components/FavButton'
import RecipeIcon from '../components/RecipeIcon'

const EMPTY_LIST = []

export default function RecipeDetail({ isFavourite, toggleFavourite, onDiscussRecipe }) {
  const { slug } = useParams()
  const { recipe, loading, error, retry } = useRecipe(slug)
  const ingredientSections = recipe?.ingredient_sections ?? EMPTY_LIST
  const instructionSections = recipe?.instruction_sections ?? EMPTY_LIST
  const ingredients = useMemo(() => sectionItems(ingredientSections), [ingredientSections])
  const instructions = useMemo(() => sectionItems(instructionSections), [instructionSections])
  const categories = normalizeArray(recipe?.category)
  const tags = normalizeArray(recipe?.tags)

  const stepMatches = useMemo(
    () => instructions.map((step) => matchedIngredientIndexes(ingredients, step)),
    [ingredients, instructions],
  )
  const numberedInstructionSections = useMemo(() => {
    let position = 0
    return instructionSections.map((section) => ({
      section,
      items: section.items.map((step) => ({
        step,
        index: position,
        number: ++position,
      })),
    }))
  }, [instructionSections])

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

  return (
    <main className="page">
      <div className="detail-nav">
        <Link to="/" className="back-link">← All Recipes</Link>
        <button
          type="button"
          className="detail-discuss"
          onClick={onDiscussRecipe}
          aria-label={`Discuss ${recipe.title} with Crumbs`}
        >
          Discuss with Crumbs
        </button>
      </div>

      <article className="detail" style={{ '--accent': RECIPE_ACCENT }}>
        <div className="detail-hero">
          <div className="detail-emoji" aria-hidden="true">
            <RecipeIcon name={RECIPE_ICON} className="dish-icon" />
          </div>
          <div className="detail-head">
            <div className="detail-head-top">
              <div className="recipe-taxonomy">
                {categories[0] && (
                  <span className="recipe-category-label">{formatLabel(categories[0])}</span>
                )}
                {categories[0] && tags.length > 0 && (
                  <span className="recipe-taxonomy-separator" aria-hidden="true">·</span>
                )}
                {tags.length > 0 && (
                  <span className="recipe-tag-text">
                    {tags.slice(0, 2).map(formatLabel).join(' · ')}
                  </span>
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
            {(recipe.cuisine || recipe.total_time_minutes != null || recipe.servings != null) && (
              <div className="detail-facts" aria-label="Recipe details">
                {recipe.cuisine && (
                  <div className="detail-fact">
                    <span className="detail-fact-label">Cuisine</span>
                    <strong>{formatLabel(recipe.cuisine)}</strong>
                  </div>
                )}
                {recipe.total_time_minutes != null && (
                  <div className="detail-fact">
                    <span className="detail-fact-label">Total time</span>
                    <strong>{formatDuration(recipe.total_time_minutes)}</strong>
                  </div>
                )}
                {recipe.servings != null && (
                  <div className="detail-fact detail-fact--servings">
                    <span className="detail-fact-label">Serves</span>
                    <strong>{formatServings(recipe.servings)}</strong>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="macro-bar">
          <div className="macro macro--calories">
            <strong>{recipe.calories == null ? '—' : recipe.calories}</strong>
            <span>kcal</span>
          </div>
          <div className="macro macro--protein">
            <strong>{recipe.protein == null ? '—' : `${recipe.protein}g`}</strong>
            <span>protein</span>
          </div>
          <div className="macro macro--fat">
            <strong>{recipe.fat == null ? '—' : `${recipe.fat}g`}</strong>
            <span>fat</span>
          </div>
          <div className="macro macro--carbs">
            <strong>{recipe.carbs == null ? '—' : `${recipe.carbs}g`}</strong>
            <span>carbs</span>
          </div>
        </div>

        <div className="detail-grid">
          <section className="panel">
            <h2 className="panel-title">Ingredients</h2>
            <p className="panel-hint">Ingredients are called out in the instructions.</p>
            <ul className="ingredients">
              {ingredientSections.map((section, sectionIndex) => {
                const heading = sectionHeading(section)
                return (
                  <Fragment key={`ingredient-section-${sectionIndex}`}>
                    {heading && <li className="group-heading">{heading}</li>}
                    {section.items.map((item, itemIndex) => (
                      <li key={`ingredient-${sectionIndex}-${itemIndex}`}>{item}</li>
                    ))}
                  </Fragment>
                )
              })}
            </ul>
          </section>

          <section className="panel">
            <h2 className="panel-title">Instructions</h2>
            <ol className="steps">
              {numberedInstructionSections.map(({ section, items }, sectionIndex) => {
                const heading = sectionHeading(section)
                return (
                  <Fragment key={`instruction-section-${sectionIndex}`}>
                    {heading && <li className="group-heading">{heading}</li>}
                    {items.map(({ step, index, number }, itemIndex) => (
                      <li key={`instruction-${sectionIndex}-${itemIndex}`}>
                        <span className="step-num">{number}</span>
                        <p>
                          {stepSegments(step, stepMatches[index], ingredients).map((seg, j) =>
                            seg.ingredient ? (
                              <mark key={j} className="step-ingredient">{seg.text}</mark>
                            ) : (
                              <span key={j}>{seg.text}</span>
                            ),
                          )}
                        </p>
                      </li>
                    ))}
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
