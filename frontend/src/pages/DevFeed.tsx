import { useCallback, useEffect, useState } from 'react'
import { classifyPost, deletePost, getDevFeed, type DevPost } from '../api'

export default function DevFeed() {
  const [data, setData] = useState<{ posts: DevPost[]; message?: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [limit, setLimit] = useState(20)
  const [gravity, setGravity] = useState<number>(1.5)
  const [lookbackHours, setLookbackHours] = useState<number | null>(null)
  const [showAll, setShowAll] = useState(true)
  const [classifyingUri, setClassifyingUri] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getDevFeed({
        limit: limit,
        gravity,
        lookback_hours: lookbackHours ?? undefined,
        show_all: showAll,
      })
      setData(res)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [limit, gravity, lookbackHours, showAll])

  useEffect(() => {
    load()
  }, [load])

  const handleDelete = async (uri: string) => {
    if (!confirm('Delete this post from the DB?')) return
    try {
      await deletePost(uri)
      setData((d) => d ? { ...d, posts: d.posts.filter((p) => p.uri !== uri) } : d)
    } catch (e) {
      alert((e as Error).message)
    }
  }

  const handleClassify = async (post: DevPost) => {
    setClassifyingUri(post.uri)
    try {
      const res = await classifyPost(post.uri, post.text, post.quoted_text || undefined)
      const newStatus = res.relevant ? 'approved' : 'rejected'
      setData((d) => {
        if (!d) return d
        return {
          ...d,
          posts: d.posts.map((p) =>
            p.uri === post.uri ? { ...p, llm_status: newStatus } : p
          ),
        }
      })
    } catch (e) {
      alert((e as Error).message)
    } finally {
      setClassifyingUri(null)
    }
  }

  return (
    <>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#1e293b', marginBottom: '0.5rem' }}>
        Penn State Feed — Preview
      </h1>

      <p style={{ marginBottom: '1rem', color: '#64748b' }}>
        Limit:{' '}
        <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} style={{ marginRight: '1rem' }}>
          <option value={10}>10</option>
          <option value={20}>20</option>
          <option value={50}>50</option>
        </select>
        {' '}
        Gravity:{' '}
        <input
          type="range"
          min={1}
          max={5}
          step={0.1}
          value={gravity}
          onChange={(e) => setGravity(Number(e.target.value))}
          style={{ verticalAlign: 'middle', marginRight: '0.5rem' }}
        />
        <span style={{ minWidth: '2.5rem', display: 'inline-block' }}>{gravity.toFixed(1)}</span>
        {' '}
        Lookback:{' '}
        <button type="button" onClick={() => setLookbackHours(24)} style={{ marginRight: '0.25rem', padding: '0.2rem 0.5rem', borderRadius: '0.25rem', border: '1px solid #cbd5e1', cursor: 'pointer', background: lookbackHours === 24 ? '#e0f2fe' : undefined }}>24h</button>
        <button type="button" onClick={() => setLookbackHours(48)} style={{ marginRight: '0.25rem', padding: '0.2rem 0.5rem', borderRadius: '0.25rem', border: '1px solid #cbd5e1', cursor: 'pointer', background: lookbackHours === 48 ? '#e0f2fe' : undefined }}>48h</button>
        <button type="button" onClick={() => setLookbackHours(72)} style={{ marginRight: '0.5rem', padding: '0.2rem 0.5rem', borderRadius: '0.25rem', border: '1px solid #cbd5e1', cursor: 'pointer', background: lookbackHours === 72 ? '#e0f2fe' : undefined }}>72h</button>
        <button type="button" onClick={() => setLookbackHours(null)} style={{ padding: '0.2rem 0.5rem', borderRadius: '0.25rem', border: '1px solid #cbd5e1', cursor: 'pointer', background: lookbackHours === null ? '#e0f2fe' : undefined }}>default</button>
        {' '}
        Status:{' '}
        <button type="button" onClick={() => setShowAll(true)} style={{ marginRight: '0.25rem', padding: '0.2rem 0.5rem', borderRadius: '0.25rem', border: '1px solid #cbd5e1', cursor: 'pointer', background: showAll ? '#e0f2fe' : undefined }}>
          Show pending/rejected
        </button>
        <button type="button" onClick={() => setShowAll(false)} style={{ padding: '0.2rem 0.5rem', borderRadius: '0.25rem', border: '1px solid #cbd5e1', cursor: 'pointer', background: !showAll ? '#e0f2fe' : undefined }}>
          Approved only
        </button>
      </p>

      {error && (
        <div style={{ marginBottom: '1rem', padding: '0.5rem 1rem', background: '#fee2e2', color: '#991b1b', borderRadius: '0.25rem' }}>
          {error}
        </div>
      )}

      {loading && <p>Loading…</p>}
      {!loading && data?.message && !data.posts?.length && (
        <p>
          {data.message}
          {!showAll && ' Try “Show pending/rejected” to see unclassified posts.'}
        </p>
      )}
      {!loading && data && data.posts.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', background: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', borderRadius: '0.5rem' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
                <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left' }}>#</th>
                <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left' }}>Author</th>
                <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left' }}>Text</th>
                <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left' }}>L/R/R</th>
                <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left' }}>Score</th>
                <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left' }}>Created</th>
                <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left' }}>Status</th>
                <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left' }}>Link</th>
                <th style={{ padding: '0.5rem 0.75rem' }}></th>
                <th style={{ padding: '0.5rem 0.75rem' }}></th>
              </tr>
            </thead>
            <tbody>
              {data.posts.map((post, i) => (
                <tr key={post.uri} style={{ borderBottom: '1px solid #e2e8f0' }}>
                  <td style={{ padding: '0.5rem 0.75rem' }}>{i + 1}</td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>
                    <strong>{post.display_name}</strong> @{post.handle}
                  </td>
                  <td style={{ padding: '0.5rem 0.75rem', maxWidth: '20rem' }}>
                    {post.text.slice(0, 200)}{post.text.length > 200 ? '…' : ''}
                  </td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>{post.like_count} / {post.repost_count} / {post.reply_count}</td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>{post.score.toFixed(4)}</td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>{post.created.slice(0, 19)}</td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>
                    <span style={{
                      padding: '0.125rem 0.375rem',
                      borderRadius: '0.25rem',
                      fontSize: '0.875rem',
                      background: post.llm_status === 'approved' ? '#dcfce7' : post.llm_status === 'rejected' ? '#fee2e2' : '#fef3c7',
                      color: post.llm_status === 'approved' ? '#166534' : post.llm_status === 'rejected' ? '#991b1b' : '#92400e',
                    }}>
                      {post.llm_status}
                    </span>
                  </td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>
                    <a href={post.link} target="_blank" rel="noreferrer">Open</a>
                  </td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>
                    <button
                      type="button"
                      disabled={classifyingUri === post.uri}
                      onClick={() => handleClassify(post)}
                      style={{ padding: '0.25rem 0.5rem', borderRadius: '0.25rem', border: '1px solid #cbd5e1', cursor: classifyingUri === post.uri ? 'wait' : 'pointer' }}
                    >
                      {classifyingUri === post.uri ? '…' : 'Classify'}
                    </button>
                  </td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>
                    <button
                      type="button"
                      onClick={() => handleDelete(post.uri)}
                      style={{ padding: '0.25rem 0.5rem', borderRadius: '0.25rem', border: '1px solid #cbd5e1', cursor: 'pointer' }}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
