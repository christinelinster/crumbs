import { Link } from 'react-router-dom'
import { RECIPE_ACCENT, RECIPE_ICON } from '../data/categories'
import FavButton from './FavButton'
import RecipeIcon from './RecipeIcon'
import { formatDuration, formatLabel, normalizeArray } from '../utils/recipe'

export default function RecipeCard({ recipe, isFavourite, toggleFavourite }) {
  const fav = isFavourite(recipe.slug)
  const categories = normalizeArray(recipe.category)
  const tags = normalizeArray(recipe.tags)
  const primaryCategory = categories[0]
  const visibleTags = tags.slice(0, 2)
  const macros = [
    ['calories', 'kcal', recipe.calories, 'macro--calories'],
    ['protein', 'protein', recipe.protein, 'macro--protein'],
    ['fat', 'fat', recipe.fat, 'macro--fat'],
    ['carbs', 'carbs', recipe.carbs, 'macro--carbs'],
  ]

  return (
    <div className="card" style={{ '--accent': RECIPE_ACCENT }}>
      <Link
        to={`/recipe/${encodeURIComponent(recipe.slug)}`}
        className="card-link"
        aria-label={recipe.title}
      >
        <div className="card-media">
          <div className="card-emoji">
            <RecipeIcon name={RECIPE_ICON} className="dish-icon" />
          </div>
          <div className="card-body">
            <div className="recipe-taxonomy">
              {primaryCategory && (
                <span className="recipe-category-label">{formatLabel(primaryCategory)}</span>
              )}
              {primaryCategory && visibleTags.length > 0 && (
                <span className="recipe-taxonomy-separator" aria-hidden="true">·</span>
              )}
              {visibleTags.length > 0 && (
                <span className="recipe-tag-text">
                  {visibleTags.map(formatLabel).join(' · ')}
                </span>
              )}
              {recipe.total_time_minutes != null && (
                <span className="card-time">⏱ {formatDuration(recipe.total_time_minutes)}</span>
              )}
            </div>
            <h3 className="card-name">{recipe.title}</h3>
            <ul className="macros">
              {macros.map(([key, label, value, macroClass]) => (
                <li key={key} className={`macro ${macroClass}`}>
                  <strong>{value == null ? '—' : value}</strong>
                  <span>{label}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Link>
      <FavButton
        isFavourite={fav}
        onToggle={() => toggleFavourite(recipe.slug)}
        label={fav ? `Remove ${recipe.title} from favourites` : `Add ${recipe.title} to favourites`}
      />
    </div>
  )
}
