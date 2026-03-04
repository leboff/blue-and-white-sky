import { useCallback, useEffect, useState } from 'react'
import { classifyPost, deletePost, getDevFeed, type DevPost } from '../api'

export default function DevFeed() {
  const [data, setData] = useState<{ posts: DevPost[]; message?: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [limit, setLimit] = useState(20)
  const [gravity, setGravity] = useState<number | null>(null)
  const [lookbackHours, setLookbackHours] = useState<number | null>(null)
  const [showAll, setShowAll] = useState(true)
  const [classifyingUri, setClassifyingUri] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getDevFeed({
        limit: limit,
        gravity: gravity ?? undefined,
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
        Tuning:{' '}
        <a href="?" onClick={(e) => { e.preventDefault(); setGravity(1.5); }}>gravity=1.5</a>
        {' | '}
        <a href="?" onClick={(e) => { e.preventDefault(); setGravity(1.8); }}>1.8</a>
        {' | '}
        <a href="?" onClick={(e) => { e.preventDefault(); setLookbackHours(24); }}>lookback=24h</a>
        {' | '}
        <a href="?" onClick={(e) => { e.preventDefault(); setLookbackHours(48); }}>48h</a>
        {' | '}
        <a href="?" onClick={(e) => { e.preventDefault(); setLookbackHours(72); }}>72h</a>
        {' | '}
        <button type="button" onClick={() => setShowAll(true)} style={{ background: 'none', border: 'none', color: '#2563eb', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}>
          Show pending/rejected
        </button>
        {' | '}
        <button type="button" onClick={() => setShowAll(false)} style={{ background: 'none', border: 'none', color: '#2563eb', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}>
          Approved only
        </button>
      </p>

      {error && (
        <div style={{ marginBottom: '1rem', padding: '0.5rem 1rem', background: '#fee2e2', color: '#991b1b', borderRadius: '0.25rem' }}>
          {error}
        </div>
      )}

      {loading && <p>Loading…</p>}
      {!loading && data?.message && !data.posts?.length && <p>{data.message}</p>}
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
