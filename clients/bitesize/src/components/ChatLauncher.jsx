import { CHAT_LAUNCHER_LABEL } from '../utils/chatLauncher.js'

export default function ChatLauncher({ isOpen, onClick }) {
  if (isOpen) return null

  return (
    <button
      type="button"
      className="chat-launcher"
      onClick={onClick}
      aria-label="Open Crumbs chat"
      aria-controls="chat-panel"
      aria-expanded="false"
      title={CHAT_LAUNCHER_LABEL}
    >
      <span className="chat-launcher-mark" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span className="chat-launcher-label">{CHAT_LAUNCHER_LABEL}</span>
    </button>
  )
}
