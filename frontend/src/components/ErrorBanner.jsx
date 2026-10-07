// Prominent, dismissible error message (announced to screen readers).
export default function ErrorBanner({ message, onDismiss }) {
  if (!message) return null
  return (
    <div className="error-banner" role="alert">
      <span className="error-icon" aria-hidden="true">!</span>
      <span className="error-text">{message}</span>
      {onDismiss && (
        <button type="button" className="icon-button" onClick={onDismiss} aria-label="Dismiss error">
          ×
        </button>
      )}
    </div>
  )
}
