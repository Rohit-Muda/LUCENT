import { formatDuration, formatTimestamp } from '../utils/formatters'

export default function TranscriptView({ transcript }) {
  return (
    <section className="transcript-panel" aria-label="Lecture transcript">
      <h2>Transcript</h2>
      <p className="transcript-metadata">
        Provider: {transcript.provider || 'Unavailable'}
        {transcript.detected_language && ` · Detected language: ${transcript.detected_language}`}
        {transcript.transcribed_duration_seconds != null &&
          ` · Duration: ${formatDuration(transcript.transcribed_duration_seconds)}`}
      </p>

      <div className="card-block">
        <h3>Cleaned transcript</h3>
        <p className="transcript-text mixed-script">{transcript.cleaned_text}</p>
      </div>

      <details className="transcript-original">
        <summary>Original transcript</summary>
        <p className="transcript-text mixed-script">{transcript.original_text}</p>
      </details>

      {transcript.segments?.length > 0 && (
        <div className="segments-block">
          <h3>Timestamped segments</h3>
          <ol className="transcript-segments">
            {transcript.segments.map((segment, index) => (
              <li key={`${segment.start}-${index}`}>
                <time>
                  {formatTimestamp(segment.start)}–{formatTimestamp(segment.end)}
                </time>
                <span className="mixed-script">{segment.text}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  )
}
