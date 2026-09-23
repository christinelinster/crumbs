import { categories, tags } from '../data/categories'

export default function Filters({
  category,
  setCategory,
  tag,
  setTag,
  searchTerm,
  setSearchTerm,
  calorieLimit,
  setCalorieLimit,
  maxCalories,
  showFavourites,
  setShowFavourites,
  favouriteCount,
  resultCount,
}) {
  const sliderMax = Math.max(maxCalories, 100)
  const sliderValue = Math.min(calorieLimit, sliderMax)

  return (
    <div className="filters">
      <div className="filter-search">
        <label className="filter-label" htmlFor="recipe-search">
          Search recipes
        </label>
        <div className="search-field">
          <span className="search-icon" aria-hidden="true">⌕</span>
          <input
            id="recipe-search"
            type="search"
            placeholder="Search by recipe name, category, or tag"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          {searchTerm && (
            <button
              type="button"
              className="search-clear"
              aria-label="Clear recipe search"
              onClick={() => setSearchTerm('')}
            >
              ×
            </button>
          )}
      </div>
      </div>

      <div className="filter-taxonomy">
        <div className="filter-group filter-group--categories">
          <span className="filter-label">Categories</span>
          <div className="chips" role="group" aria-label="Filter by category">
            {categories.map((c) => (
              <button
                key={c}
                type="button"
                className={`chip chip--category-filter ${category === c && !showFavourites ? 'chip--active' : ''}`}
                onClick={() => {
                  setShowFavourites(false)
                  setCategory(c)
                }}
              >
                {c}
              </button>
            ))}
          </div>
        </div>

        <div className="filter-group filter-group--tags">
          <span className="filter-label">Tags</span>
          <div className="chips chips--compact" role="group" aria-label="Filter by tag">
            {tags.map((t) => (
              <button
                key={t}
                type="button"
                className={`chip chip--tag-filter ${tag === t && !showFavourites ? 'chip--active' : ''}`}
                onClick={() => {
                  setShowFavourites(false)
                  setTag(t)
                }}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <div className="filter-group filter-group--favourites">
          <span className="filter-label">Saved</span>
          <button
            type="button"
            className={`chip chip--fav filter-favourites ${showFavourites ? 'chip--active' : ''}`}
            aria-pressed={showFavourites}
            onClick={() => setShowFavourites((v) => !v)}
          >
            ♥ Favourites{favouriteCount > 0 ? ` (${favouriteCount})` : ''}
          </button>
        </div>

      </div>

      <div className="filter-controls">
        <div className="filter-group filter-group--slider">
          <label className="filter-label" htmlFor="calorie-slider">
            Max calories <span className="slider-value">{calorieLimit} kcal</span>
          </label>
          <input
            id="calorie-slider"
            className="slider"
            type="range"
            min="100"
            max={sliderMax}
            step="10"
            value={sliderValue}
            onChange={(e) => setCalorieLimit(Number(e.target.value))}
          />
        </div>
        <div className="filter-results" aria-live="polite">
          <span>Results</span>
          <span className="filter-results-dot" aria-hidden="true">·</span>
          <strong>{resultCount}</strong>
        </div>
      </div>
    </div>
  )
}
