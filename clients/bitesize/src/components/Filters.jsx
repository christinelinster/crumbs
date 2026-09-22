import { categories } from '../data/categories'

export default function Filters({
  category,
  setCategory,
  calorieLimit,
  setCalorieLimit,
  maxCalories,
  showFavourites,
  setShowFavourites,
  favouriteCount,
}) {
  return (
    <div className="filters">
      <div className="filter-group">
        <span className="filter-label">Type</span>
        <div className="chips" role="group" aria-label="Filter by category">
          {categories.map((c) => (
            <button
              key={c}
              type="button"
              className={`chip ${category === c && !showFavourites ? 'chip--active' : ''}`}
              onClick={() => {
                setShowFavourites(false)
                setCategory(c)
              }}
            >
              {c}
            </button>
          ))}
          <button
            type="button"
            className={`chip chip--fav ${showFavourites ? 'chip--active' : ''}`}
            aria-pressed={showFavourites}
            onClick={() => setShowFavourites((v) => !v)}
          >
            ♥ Favourites{favouriteCount > 0 ? ` (${favouriteCount})` : ''}
          </button>
        </div>
      </div>
      <div className="filter-group filter-group--slider">
        <label className="filter-label" htmlFor="calorie-slider">
          Max calories <span className="slider-value">{calorieLimit} kcal</span>
        </label>
        <input
          id="calorie-slider"
          className="slider"
          type="range"
          min="100"
          max={maxCalories}
          step="10"
          value={calorieLimit}
          onChange={(e) => setCalorieLimit(Number(e.target.value))}
        />
      </div>
    </div>
  )
}