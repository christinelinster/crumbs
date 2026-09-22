import { Link } from 'react-router-dom'
import { RECIPE_ACCENT, RECIPE_ICON } from '../data/categories'
import FavButton from './FavButton'
import RecipeIcon from './RecipeIcon'
import { formatLabel, normalizeArray } from '../utils/recipe'

export default function RecipeCard({ recipe, isFavourite, toggleFavourite }) {
  const fav = isFavourite(recipe.slug)
  const categories = normalizeArray(recipe.category)
  const tags = normalizeArray(recipe.tags)
  const macros = [
    ['calories', 'kcal', recipe.calories],
    ['protein', 'protein', recipe.protein],
    ['fat', 'fat', recipe.fat],
    ['carbs', 'carbs', recipe.carbs],
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
              {recipe.total_time_minutes != null && (
                <span className="chip chip--static chip--time">
                  ⏱ {recipe.total_time_minutes} min
                </span>
              )}
            </div>
            <h3 className="card-name">{recipe.title}</h3>
            <ul className="macros">
              {macros.map(([key, label, value]) => (
                <li key={key} className="macro">
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
