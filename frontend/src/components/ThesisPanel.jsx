import { useState } from 'react'
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react'
import api from '../api/client'

const STATUS_LABEL = { draft: 'Draft', dalam_proses: 'In Progress', siap: 'Done' }
const STATUS_COLOR = { draft: 'var(--line)', dalam_proses: 'var(--accent-soft)', siap: 'var(--success-soft)' }

export function ThesisPanel({ chapters, onExport, exportingChapterId, tier, projectId, activeChapterId, onSetActive, onAddChapter, onDeleteChapter, onReorderChapter, onRenameChapter, collapsed, onToggleCollapse, onCompile, compiling, compileError, compileWarning, onDismissError }) {
  const [upgrading, setUpgrading] = useState(false)
  const [addMode, setAddMode] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [editingChapterId, setEditingChapterId] = useState(null)
  const [editingTitle, setEditingTitle] = useState('')
  const [hoveredChapterId, setHoveredChapterId] = useState(null)

  const done = (chapters || []).filter(c => c.status === 'siap').length
  const total = (chapters || []).length

  if (collapsed) {
    return (
      <div style={{
        width: 36, flexShrink: 0, borderLeft: '1px solid var(--line)',
        background: 'var(--card)', display: 'flex', flexDirection: 'column', alignItems: 'center',
        paddingTop: 12, position: 'relative',
      }}>
        {/* Floating pill on left divider */}
        <button
          onClick={onToggleCollapse}
          title="Expand thesis structure panel"
          style={{
            position: 'absolute', left: -10, top: '50%', transform: 'translateY(-50%)',
            width: 20, height: 36,
            background: 'var(--accent-soft)', border: '1px solid var(--accent)', borderRadius: 10,
            boxShadow: '0 1px 2px rgba(0,0,0,0.06)',
            cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 2, padding: 0, color: 'var(--accent)',
          }}
          onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 2px 4px rgba(0,0,0,0.1)' }}
          onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 1px 2px rgba(0,0,0,0.06)' }}
        >
          <IconChevronLeft size={13} stroke={1.5} />
        </button>
      </div>
    )
  }

  function handleAdd(e) {
    e.preventDefault()
    if (!newTitle.trim()) return
    onAddChapter(newTitle.trim())
    setNewTitle('')
    setAddMode(false)
  }

  function handleDelete(e, chap) {
    e.stopPropagation()
    const message = chap.has_content
      ? `⚠️ Chapter "${chap.title}" has unsaved content.\n\nDeleting this chapter will permanently remove ALL content.\n\nContinue?`
      : `Delete "${chap.title}"?`
    if (window.confirm(message)) {
      onDeleteChapter(chap.id)
    }
  }

  async function handleRenameChapterLocal(chapterId, currentTitle, newTitle) {
    const trimmed = newTitle.trim()
    setEditingChapterId(null)
    setEditingTitle('')
    if (!trimmed || trimmed === currentTitle) return
    await onRenameChapter(chapterId, trimmed)
  }

  return (
    <div id="rhq-tour-thesis" style={{
      width: 264, flexShrink: 0, borderLeft: '1px solid var(--line)',
      display: 'flex', flexDirection: 'column', background: 'var(--card)',
      position: 'relative',
    }}>
      {/* Floating pill on left divider */}
      <button
        onClick={onToggleCollapse}
        title="Collapse thesis structure panel"
        style={{
          position: 'absolute', left: -10, top: '50%', transform: 'translateY(-50%)',
          width: 20, height: 36,
          background: 'var(--accent-soft)', border: '1px solid var(--accent)', borderRadius: 10,
          boxShadow: '0 1px 2px rgba(0,0,0,0.06)',
          cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 2, padding: 0, color: 'var(--accent)',
        }}
        onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 2px 4px rgba(0,0,0,0.1)' }}
        onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 1px 2px rgba(0,0,0,0.06)' }}
      >
        <IconChevronRight size={13} stroke={1.5} />
      </button>
      {tier !== 'pro' && (
        <div style={{
          position: 'absolute', inset: 0,
          background: 'rgba(248,246,241,0.88)',
          backdropFilter: 'blur(2px)',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          zIndex: 10, padding: 24, textAlign: 'center',
        }}>
          <span style={{ fontSize: 32, marginBottom: 12 }}>🔒</span>
          <p style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 16, margin: '0 0 8px' }}>
            Thesis Workspace
          </p>
          <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-soft)', margin: '0 0 16px' }}>
            Manage chapters, assign AI output, and export .docx — Pro only.
          </p>
          <button
            onClick={async () => {
              setUpgrading(true)
              try {
                const { data } = await api.post('/billing/upgrade/initiate')
                window.location.href = data.payment_url
              } catch {
                alert('Failed to initiate payment. Please try again.')
                setUpgrading(false)
              }
            }}
            disabled={upgrading}
            style={{
              padding: '10px 20px', background: 'var(--accent)', border: 'none',
              borderRadius: 'var(--radius-sm)', fontWeight: 700, cursor: upgrading ? 'wait' : 'pointer',
              fontFamily: 'var(--font-heading)', fontSize: 14, opacity: upgrading ? 0.7 : 1,
            }}
          >
            {upgrading ? 'Processing...' : 'Upgrade to Pro — RM39/month'}
          </button>
        </div>
      )}

      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)' }}>
            Thesis Structure
          </span>
        </div>
        {total > 0 && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: done === total ? 'var(--success)' : 'var(--ink-soft)' }}>
            {done}/{total} done
          </span>
        )}
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
        {total === 0 && !addMode && (
          <p style={{ padding: '16px', color: 'var(--ink-soft)', fontSize: 13 }}>
            No chapters yet. Add your first chapter.
          </p>
        )}

        {(chapters || []).map((chap, idx) => {
          const isActive = chap.id === activeChapterId
          return (
            <div
              key={chap.id}
              onClick={() => onSetActive(chap.id)}
              onMouseEnter={() => setHoveredChapterId(chap.id)}
              onMouseLeave={() => setHoveredChapterId(null)}
              style={{
                padding: '8px 12px',
                borderBottom: '1px solid var(--line)',
                background: isActive ? 'var(--accent-soft)' : 'transparent',
                borderLeft: isActive ? '3px solid var(--accent)' : '3px solid transparent',
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 4 }}>
                {editingChapterId === chap.id ? (
                  <input
                    autoFocus
                    value={editingTitle}
                    onChange={e => setEditingTitle(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') handleRenameChapterLocal(chap.id, chap.title, editingTitle)
                      if (e.key === 'Escape') { setEditingChapterId(null); setEditingTitle('') }
                    }}
                    onBlur={() => handleRenameChapterLocal(chap.id, chap.title, editingTitle)}
                    onClick={e => e.stopPropagation()}
                    style={{
                      flex: 1, padding: '2px 4px',
                      border: '1px solid var(--accent)', borderRadius: 3,
                      fontFamily: 'var(--font-body)', fontSize: 13,
                      background: 'var(--bg)', outline: 'none', minWidth: 0,
                    }}
                  />
                ) : (
                  <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)', flex: 1, wordBreak: 'break-word' }}>
                    {isActive && <span style={{ color: 'var(--accent)', marginRight: 4 }}>●</span>}
                    {chap.title}
                  </span>
                )}
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 10, padding: '2px 5px', borderRadius: 3,
                  background: STATUS_COLOR[chap.status] || 'var(--line)', color: 'var(--ink)',
                  flexShrink: 0,
                }}>
                  {STATUS_LABEL[chap.status] || chap.status}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 6 }} onClick={e => e.stopPropagation()}>
                {/* Rename */}
                {editingChapterId !== chap.id && (
                  <button
                    onClick={e => { e.stopPropagation(); setEditingChapterId(chap.id); setEditingTitle(chap.title) }}
                    title="Rename chapter"
                    style={{ background: 'none', border: '1px solid var(--line)', borderRadius: 3, cursor: 'pointer', padding: '1px 5px', fontSize: 11, opacity: 0.7 }}
                  >✏</button>
                )}
                {/* Reorder butang */}
                {(hoveredChapterId === chap.id || window.innerWidth < 768) && (
                  <>
                    <button
                      onClick={() => onReorderChapter(chap.id, 'up')}
                      disabled={idx === 0}
                      title="Move up"
                      style={{ background: 'none', border: '1px solid var(--line)', borderRadius: 3, cursor: idx === 0 ? 'default' : 'pointer', padding: '1px 5px', fontSize: 11, opacity: idx === 0 ? 0.3 : 0.7 }}
                    >↑</button>
                    <button
                      onClick={() => onReorderChapter(chap.id, 'down')}
                      disabled={idx === chapters.length - 1}
                      title="Move down"
                      style={{ background: 'none', border: '1px solid var(--line)', borderRadius: 3, cursor: idx === chapters.length - 1 ? 'default' : 'pointer', padding: '1px 5px', fontSize: 11, opacity: idx === chapters.length - 1 ? 0.3 : 0.7 }}
                    >↓</button>
                  </>
                )}

                {/* Export */}
                {tier === 'pro' && (
                  <button
                    onClick={() => onExport(chap.id)}
                    disabled={exportingChapterId === chap.id}
                    style={{
                      padding: '2px 7px', fontSize: 10,
                      background: 'transparent', border: '1px solid var(--line)',
                      borderRadius: 3, cursor: exportingChapterId === chap.id ? 'wait' : 'pointer',
                      fontFamily: 'var(--font-mono)',
                      opacity: exportingChapterId === chap.id ? 0.6 : 1,
                    }}
                  >
                    {exportingChapterId === chap.id ? 'Generating...' : '.docx'}
                  </button>
                )}

                {/* Padam */}
                <button
                  onClick={e => handleDelete(e, chap)}
                  style={{
                    marginLeft: 'auto', background: 'none', border: 'none',
                    cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 14, padding: '1px 4px',
                  }}
                >×</button>
              </div>
            </div>
          )
        })}

        {/* Form tambah bab baru */}
        {addMode && (
          <form onSubmit={handleAdd} style={{ padding: '8px 12px', borderTop: '1px solid var(--line)' }}>
            <input
              autoFocus
              value={newTitle}
              onChange={e => setNewTitle(e.target.value)}
              placeholder="Chapter name (e.g. Chapter 1: Introduction)"
              style={{
                width: '100%', padding: '6px 8px', boxSizing: 'border-box',
                border: '1px solid var(--accent)', borderRadius: 4,
                fontFamily: 'var(--font-body)', fontSize: 13, outline: 'none',
                background: 'var(--bg)',
              }}
            />
            <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
              <button type="submit" disabled={!newTitle.trim()} style={{
                flex: 1, padding: '5px 0', background: 'var(--accent)', border: 'none',
                borderRadius: 4, fontFamily: 'var(--font-body)', fontSize: 12, cursor: 'pointer',
              }}>Add</button>
              <button type="button" onClick={() => { setAddMode(false); setNewTitle('') }} style={{
                padding: '5px 10px', background: 'transparent', border: '1px solid var(--line)',
                borderRadius: 4, fontFamily: 'var(--font-body)', fontSize: 12, cursor: 'pointer',
              }}>Cancel</button>
            </div>
          </form>
        )}
      </div>

      {!addMode && (
        <div style={{ padding: 12, borderTop: '1px solid var(--line)' }}>
          <button
            onClick={() => setAddMode(true)}
            style={{
              width: '100%', padding: '7px 0',
              background: 'var(--accent-soft)', border: '1px solid var(--accent)',
              borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)',
              fontSize: 13, cursor: 'pointer', color: 'var(--ink)',
            }}
          >+ Add Chapter</button>
          {tier === 'pro' && (
            <>
              {compileError && (
                <div style={{
                  margin: '6px 0',
                  padding: '8px 12px',
                  background: 'var(--danger-soft)',
                  border: '1px solid var(--danger)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 12,
                  color: 'var(--danger)',
                  lineHeight: 1.5,
                }}>
                  {compileError}
                  <button
                    onClick={onDismissError}
                    style={{ float: 'right', background: 'none', border: 'none', cursor: 'pointer', fontSize: 12, color: 'var(--danger)' }}
                  >✕</button>
                </div>
              )}
              {compileWarning && (
                <div style={{
                  margin: '6px 0',
                  padding: '8px 12px',
                  background: 'var(--warning-soft)',
                  border: '1px solid var(--warning)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 12,
                  color: 'var(--warning)',
                  lineHeight: 1.5,
                }}>
                  ⚠ {compileWarning}
                </div>
              )}
              <button
                onClick={onCompile}
                disabled={compiling}
                style={{
                  width: '100%', marginTop: 6, padding: '7px 0',
                  background: compiling ? 'var(--line)' : 'var(--accent)',
                  border: 'none', borderRadius: 'var(--radius-sm)',
                  fontFamily: 'var(--font-heading)', fontSize: 13,
                  fontWeight: 700, cursor: compiling ? 'wait' : 'pointer',
                }}
              >
                {compiling ? 'Generating...' : '⬇ Compile Full Thesis'}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
