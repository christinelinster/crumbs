function statusError(response) {
  return `Request failed with status ${response.status}`
}

async function requestJson(path, options, errorMessage) {
  const response = await fetch(path, options)
  if (!response.ok && !errorMessage) {
    throw new Error(statusError(response))
  }
  const data = await response.json()
  if (!response.ok) throw new Error(errorMessage(response, data))
  return data
}

export function getRecipes() {
  return requestJson('/api/recipes')
}

export function getRecipe(slug) {
  return requestJson(`/api/recipes/${encodeURIComponent(slug)}`)
}

export function sendChatMessage(request) {
  return requestJson('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  }, (response, data) => data.detail || statusError(response))
}
