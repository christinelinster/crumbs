import { Link } from 'react-router-dom'
import { RECIPE_ACCENT, RECIPE_ICON } from '../data/categories'
import FavButton from './FavButton'
import RecipeIcon from './RecipeIcon'

export default function RecipeCard({ recipe, isFavourite, toggleFavourite }) {
  const fav = isFavourite(recipe.id)

  return (
    <div className="card" style={{ '--accent': RECIPE_ACCENT }}>
      <Link
        to={`/recipe/${recipe.id}`}
        className="card-link"
        aria-label={recipe.name}
      >
        <div className="card-media">
          <div className="card-emoji">
            <RecipeIcon name={RECIPE_ICON} className="dish-icon" />
          </div>
          <div className="card-body">
            <div className="card-tags">
              <span className="chip chip--static">{recipe.category}</span>
              <span className="chip chip--static chip--time">⏱ {recipe.time} min</span>
            </div>
            <h3 className="card-name">{recipe.name}</h3>
            <ul className="macros">
              <li className="macro">
                <strong>{recipe.calories}</strong>
                <span>kcal</span>
              </li>
              <li className="macro">
                <strong>{recipe.protein}g</strong>
                <span>protein</span>
              </li>
              <li className="macro">
                <strong>{recipe.fat}g</strong>
                <span>fat</span>
              </li>
              <li className="macro">
                <strong>{recipe.carbs}g</strong>
                <span>carbs</span>
              </li>
            </ul>
          </div>
        </div>
      </Link>
      <FavButton
        isFavourite={fav}
        onToggle={() => toggleFavourite(recipe.id)}
        label={fav ? `Remove ${recipe.name} from favourites` : `Add ${recipe.name} to favourites`}
      />
    </div>
  )
}
