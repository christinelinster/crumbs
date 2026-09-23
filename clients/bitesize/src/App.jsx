import { useEffect, useState } from 'react'
import { BrowserRouter, Route, Routes, useMatch } from 'react-router-dom'
import ChatPanel from './components/ChatPanel'
import ChatLauncher from './components/ChatLauncher'
import NavBar from './components/NavBar'
import Home from './pages/Home'
import RecipeDetail from './pages/RecipeDetail'
import useChat from './hooks/useChat'
import useFavourites from './hooks/useFavourites'
import useRecipe from './hooks/useRecipe'
import { RecipesProvider } from './hooks/useRecipes'

function AppShell() {
  const { favouriteIds, isFavourite, toggleFavourite } = useFavourites()
  const recipeMatch = useMatch('/recipe/:slug')
  const recipeSlug = recipeMatch?.params.slug ?? null
  const { recipe: selectedRecipe } = useRecipe(recipeSlug)
  const [recipeContextEnabled, setRecipeContextEnabled] = useState(
    () => Boolean(recipeSlug),
  )
  const [chatOpen, setChatOpen] = useState(false)
  const activeRecipeSlug = recipeContextEnabled ? recipeSlug : null
  const recipeContext = activeRecipeSlug
    ? {
        slug: activeRecipeSlug,
        title: selectedRecipe?.title ?? 'Current recipe',
      }
    : null
  const chat = useChat(activeRecipeSlug)

  useEffect(() => {
    setRecipeContextEnabled(Boolean(recipeSlug))
  }, [recipeSlug])

  return (
    <>
      <NavBar favouriteCount={favouriteIds.length} />
      <Routes>
        <Route
          path="/"
          element={
            <Home
              favouriteIds={favouriteIds}
              isFavourite={isFavourite}
              toggleFavourite={toggleFavourite}
            />
          }
        />
        <Route
          path="/recipe/:slug"
          element={
            <RecipeDetail
              isFavourite={isFavourite}
              toggleFavourite={toggleFavourite}
              onDiscussRecipe={() => {
                setRecipeContextEnabled(true)
                setChatOpen(true)
              }}
            />
          }
        />
      </Routes>
      <ChatLauncher
        isOpen={chatOpen}
        onClick={() => setChatOpen(true)}
      />
      <ChatPanel
        isOpen={chatOpen}
        onClose={() => setChatOpen(false)}
        onNewChat={chat.reset}
        recipeContext={recipeContext}
        onClearRecipeContext={() => setRecipeContextEnabled(false)}
        {...chat}
      />
    </>
  )
}

export default function App() {
  return (
    <RecipesProvider>
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    </RecipesProvider>
  )
}
