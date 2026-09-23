import { useState } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import ChatPanel from './components/ChatPanel'
import ChatLauncher from './components/ChatLauncher'
import NavBar from './components/NavBar'
import Home from './pages/Home'
import RecipeDetail from './pages/RecipeDetail'
import useChat from './hooks/useChat'
import useFavourites from './hooks/useFavourites'
import { RecipesProvider } from './hooks/useRecipes'

export default function App() {
  const { favouriteIds, isFavourite, toggleFavourite } = useFavourites()
  const chat = useChat()
  const [chatOpen, setChatOpen] = useState(false)

  return (
    <RecipesProvider>
      <BrowserRouter>
        <NavBar
          favouriteCount={favouriteIds.length}
        />
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
          {...chat}
        />
      </BrowserRouter>
    </RecipesProvider>
  )
}
