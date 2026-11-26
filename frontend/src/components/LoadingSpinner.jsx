export default function LoadingSpinner({ message = 'Loading...' }) {
  return (
    <div className="loading-spinner" role="status">
      <div className="spinner" aria-hidden="true" />
      <p>{message}</p>
    </div>
  )
}
