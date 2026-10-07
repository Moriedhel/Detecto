import { SAMPLES, sampleUrl } from '../samples'

// Grid of demo images; clicking one loads it as if it had been uploaded.
export default function SampleGallery({ onSelect, selected, disabled = false }) {
  return (
    <div className="samples">
      <h2>Sample images</h2>
      <ul className="sample-grid">
        {SAMPLES.map((s) => (
          <li key={s.file}>
            <button
              type="button"
              className={`sample${selected === s.file ? ' selected' : ''}`}
              onClick={() => onSelect(s.file)}
              disabled={disabled}
              title={`${s.label}: ${s.people} ${s.people === 1 ? 'person' : 'people'} (hand count)`}
            >
              <img src={sampleUrl(s.file)} alt="" loading="lazy" />
              <span>{s.label}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
