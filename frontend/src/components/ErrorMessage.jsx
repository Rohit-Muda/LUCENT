export default function ErrorMessage({ message, onRetry }) {
  return (
    <div className="notice notice-error" role="alert">
      <p>{message}</p>
      {onRetry && (
        <button className="button button-small" type="button" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}
