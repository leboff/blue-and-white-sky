import { useEffect, useState } from 'react'
import { getSettings, saveSettings, type Settings } from '../api'

function escapeHtml(s: string): string {
  const div = document.createElement('div')
  div.textContent = s
  return div.innerHTML
}

export default function Admin() {
  const [state, setState] = useState<Settings>({ keywords: [], negative_keywords: [], authorities: [] })
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null)
  const [loading, setLoading] = useState(true)
  const [keywordInput, setKeywordInput] = useState('')
  const [negativeKeywordInput, setNegativeKeywordInput] = useState('')
  const [authorityDid, setAuthorityDid] = useState('')
  const [authorityLabel, setAuthorityLabel] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const data = await getSettings()
      setState(data)
    } catch (e) {
      setMessage({ text: (e as Error).message, error: true })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleSave = async () => {
    setMessage(null)
    try {
      await saveSettings(state)
      setMessage({ text: 'Saved.', error: false })
    } catch (e) {
      setMessage({ text: (e as Error).message, error: true })
    }
  }

  const addKeyword = () => {
    const v = keywordInput.trim()
    if (v) {
      setState((s) => ({ ...s, keywords: [...s.keywords, v] }))
      setKeywordInput('')
    }
  }

  const addNegativeKeyword = () => {
    const v = negativeKeywordInput.trim()
    if (v) {
      setState((s) => ({ ...s, negative_keywords: [...s.negative_keywords, v] }))
      setNegativeKeywordInput('')
    }
  }

  const addAuthority = () => {
    const did = authorityDid.trim()
    if (did && did.startsWith('did:')) {
      setState((s) => ({
        ...s,
        authorities: [...s.authorities, { did, label: authorityLabel.trim() || did }],
      }))
      setAuthorityDid('')
      setAuthorityLabel('')
    } else {
      setMessage({ text: 'DID must start with did:', error: true })
    }
  }

  if (loading) return <p>Loading…</p>

  return (
    <>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#1e293b', marginBottom: '0.5rem' }}>
        PSU Feed — Admin
      </h1>
      <p style={{ color: '#64748b', marginBottom: '1rem' }}>
        Manage keywords and authority accounts. Changes take effect after you click Save; the ingester picks them up within about 60 seconds.
      </p>

      {message && (
        <div
          style={{
            marginBottom: '1rem',
            padding: '0.5rem 1rem',
            borderRadius: '0.25rem',
            background: message.error ? '#fee2e2' : '#dcfce7',
            color: message.error ? '#991b1b' : '#166534',
          }}
        >
          {message.text}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <section style={{ background: '#fff', borderRadius: '0.5rem', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', padding: '1.25rem' }}>
          <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#1e293b', marginBottom: '0.75rem' }}>Keywords</h2>
          <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 0.75rem 0' }}>
            {state.keywords.length === 0 && <li style={{ color: '#64748b', fontSize: '0.875rem' }}>No keywords yet.</li>}
            {state.keywords.map((k, i) => (
              <li key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', padding: '0.25rem 0' }}>
                <code style={{ fontSize: '0.875rem', background: '#f1f5f9', padding: '0.125rem 0.5rem', borderRadius: '0.25rem', wordBreak: 'break-all' }}>
                  {escapeHtml(k)}
                </code>
                <button
                  type="button"
                  onClick={() => setState((s) => ({ ...s, keywords: s.keywords.filter((_, j) => j !== i) }))}
                  style={{ color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <input
              type="text"
              value={keywordInput}
              onChange={(e) => setKeywordInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addKeyword()}
              placeholder="Regex keyword (e.g. Nittany\s?Lions?)"
              style={{ flex: 1, minWidth: '200px', border: '1px solid #cbd5e1', borderRadius: '0.25rem', padding: '0.5rem 0.75rem' }}
            />
            <button type="button" onClick={addKeyword} style={{ background: '#2563eb', color: '#fff', padding: '0.5rem 1rem', borderRadius: '0.25rem', border: 'none', cursor: 'pointer' }}>
              Add
            </button>
          </div>
        </section>

        <section style={{ background: '#fff', borderRadius: '0.5rem', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', padding: '1.25rem' }}>
          <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#1e293b', marginBottom: '0.75rem' }}>Negative keywords</h2>
          <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 0.75rem 0' }}>
            {state.negative_keywords.length === 0 && <li style={{ color: '#64748b', fontSize: '0.875rem' }}>No negative keywords yet.</li>}
            {state.negative_keywords.map((k, i) => (
              <li key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', padding: '0.25rem 0' }}>
                <code style={{ fontSize: '0.875rem', background: '#f1f5f9', padding: '0.125rem 0.5rem', borderRadius: '0.25rem', wordBreak: 'break-all' }}>
                  {escapeHtml(k)}
                </code>
                <button
                  type="button"
                  onClick={() => setState((s) => ({ ...s, negative_keywords: s.negative_keywords.filter((_, j) => j !== i) }))}
                  style={{ color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <input
              type="text"
              value={negativeKeywordInput}
              onChange={(e) => setNegativeKeywordInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addNegativeKeyword()}
              placeholder="Regex (e.g. Power\s?Supply)"
              style={{ flex: 1, minWidth: '200px', border: '1px solid #cbd5e1', borderRadius: '0.25rem', padding: '0.5rem 0.75rem' }}
            />
            <button type="button" onClick={addNegativeKeyword} style={{ background: '#2563eb', color: '#fff', padding: '0.5rem 1rem', borderRadius: '0.25rem', border: 'none', cursor: 'pointer' }}>
              Add
            </button>
          </div>
        </section>

        <section style={{ background: '#fff', borderRadius: '0.5rem', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', padding: '1.25rem' }}>
          <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#1e293b', marginBottom: '0.75rem' }}>Authorities</h2>
          <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 0.75rem 0' }}>
            {state.authorities.length === 0 && <li style={{ color: '#64748b', fontSize: '0.875rem' }}>No authorities yet.</li>}
            {state.authorities.map((a, i) => (
              <li key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', padding: '0.25rem 0' }}>
                <span style={{ fontSize: '0.875rem' }}>
                  <code style={{ background: '#f1f5f9', padding: '0.125rem 0.25rem', borderRadius: '0.25rem' }}>{escapeHtml(a.did)}</code>{' '}
                  {escapeHtml(a.label || '')}
                </span>
                <button
                  type="button"
                  onClick={() => setState((s) => ({ ...s, authorities: s.authorities.filter((_, j) => j !== i) }))}
                  style={{ color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' }}>
            <input
              type="text"
              value={authorityDid}
              onChange={(e) => setAuthorityDid(e.target.value)}
              placeholder="DID (e.g. did:plc:...)"
              style={{ flex: 1, minWidth: '200px', border: '1px solid #cbd5e1', borderRadius: '0.25rem', padding: '0.5rem 0.75rem' }}
            />
            <input
              type="text"
              value={authorityLabel}
              onChange={(e) => setAuthorityLabel(e.target.value)}
              placeholder="Label"
              style={{ flex: 1, minWidth: '120px', border: '1px solid #cbd5e1', borderRadius: '0.25rem', padding: '0.5rem 0.75rem' }}
            />
            <button type="button" onClick={addAuthority} style={{ background: '#2563eb', color: '#fff', padding: '0.5rem 1rem', borderRadius: '0.25rem', border: 'none', cursor: 'pointer' }}>
              Add
            </button>
          </div>
        </section>
      </div>

      <div style={{ marginTop: '1.5rem', display: 'flex', gap: '0.75rem' }}>
        <button type="button" onClick={handleSave} style={{ background: '#16a34a', color: '#fff', padding: '0.5rem 1.25rem', borderRadius: '0.25rem', border: 'none', cursor: 'pointer' }}>
          Save changes
        </button>
        <button type="button" onClick={() => { load(); setMessage(null); }} style={{ background: '#64748b', color: '#fff', padding: '0.5rem 1.25rem', borderRadius: '0.25rem', border: 'none', cursor: 'pointer' }}>
          Reset
        </button>
      </div>
    </>
  )
}
