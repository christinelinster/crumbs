import { Link } from 'react-router-dom'
import RecipeIcon from './RecipeIcon'

export default function NavBar({ favouriteCount }) {
  return (
    <header className="nav">
      <Link to="/" className="nav-brand">
        <span className="nav-badge">
          <RecipeIcon name="logo" className="nav-logo" />
        </span>
        <span className="nav-name">
          <span className="nav-bite">bite</span>
          <span className="nav-size">size</span>
        </span>
      </Link>
      <aside className="nav-masthead">
        <span className="masthead-kicker">The Edit</span>
        <span className="masthead-line">eat well.</span>
        <span className="masthead-line">stay lean.</span>
        <span className="masthead-issue">Vol. 01 — Nourishment</span>
      </aside>
      <span className="nav-count" aria-label={`${favouriteCount} favourites`}>
        ♥ {favouriteCount}
      </span>
    </header>
  )
}
