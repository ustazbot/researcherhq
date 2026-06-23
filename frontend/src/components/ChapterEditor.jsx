import { useState, useEffect, useRef } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Highlight from '@tiptap/extension-highlight'
import Underline from '@tiptap/extension-underline'
import { mdToHtml } from '../utils/markdown'

const EDITOR_STYLES = `
.editor-paper {
  max-width: 700px;
  width: 100%;
  margin: 0 auto;
  padding: 32px 40px;
  box-sizing: border-box;
}
@media (max-width: 768px) {
  .editor-paper { padding: 16px 16px; }
}
.editor-paper .ProseMirror {
  font-family: 'Source Serif 4', Georgia, serif;
  font-size: 16px;
  line-height: 1.75;
  color: var(--ink);
  outline: none;
  min-height: 300px;
}
.editor-paper .ProseMirror h1 { font-size: 1.6em; font-weight: 600; margin: 1.4em 0 0.5em; }
.editor-paper .ProseMirror h2 { font-size: 1.3em; font-weight: 600; margin: 1.2em 0 0.4em; }
.editor-paper .ProseMirror h3 { font-size: 1.1em; font-weight: 600; margin: 1em 0 0.3em; }
.editor-paper .ProseMirror p { margin: 0 0 0.9em; }
.editor-paper .ProseMirror ul,
.editor-paper .ProseMirror ol { padding-left: 1.5em; margin-bottom: 0.9em; }
`

const TOOLTIP_KEY = 'rhq_suggestion_tooltip_seen'

// ponytail: inline toolbar — no separate component, only one editor instance
function ToolbarButton({ onClick, active, children, title }) {
  return (
    <button
      onMouseDown={e => { e.preventDefault(); onClick() }}
      title={title}
      style={{
        padding: '3px 8px', border: 'none', borderRadius: 3, cursor: 'pointer',
        background: active ? 'var(--accent-soft)' : 'transparent',
        color: active ? 'var(--ink)' : 'var(--ink-soft)',
        fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: active ? 700 : 400,
      }}
    >
      {children}
    </button>
  )
}

export function ChapterEditor({ chapter, content, pendingSuggestion, onAccept, onReject, onSave, saving }) {
  const [tooltipDismissed, setTooltipDismissed] = useState(false)
  const saveTimer = useRef(null)
  const lastSavedContent = useRef(content || '')

  const editor = useEditor({
    extensions: [StarterKit, Highlight, Underline],
    content: content || '',
    editable: !pendingSuggestion,
    onUpdate: ({ editor }) => {
      if (pendingSuggestion) return
      clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(() => {
        const html = editor.getHTML()
        if (html !== lastSavedContent.current) {
          lastSavedContent.current = html
          onSave(html)
        }
      }, 2000)
    },
  })

  // Sync content when chapter changes or content loads from API
  useEffect(() => {
    if (!editor) return
    if (!pendingSuggestion) {
      editor.commands.setContent(content || '')
      lastSavedContent.current = content || ''
    }
  }, [content, chapter?.id, pendingSuggestion, editor])

  // Toggle editable bila pendingSuggestion berubah
  useEffect(() => {
    if (!editor) return
    editor.setEditable(!pendingSuggestion)
  }, [pendingSuggestion, editor])

  // Cleanup saveTimer on unmount
  useEffect(() => {
    return () => clearTimeout(saveTimer.current)
  }, [])

  if (!chapter) {
    return (
      <div style={{
        flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'var(--bg)', color: 'var(--ink-soft)',
        fontFamily: 'var(--font-body)', fontSize: 15, padding: 40, textAlign: 'center',
      }}>
        <div>
          <p style={{ marginBottom: 8, fontWeight: 500 }}>Pilih bab dari panel Struktur Tesis.</p>
          <p style={{ fontSize: 13 }}>Atau tambah bab baru untuk mula menulis.</p>
        </div>
      </div>
    )
  }

  function handleManualSave() {
    if (!editor) return
    clearTimeout(saveTimer.current)
    const html = editor.getHTML()
    lastSavedContent.current = html
    onSave(html)
  }

  function handleAccept() {
    if (!editor) return
    editor.commands.setContent(mdToHtml(pendingSuggestion.text))
    onAccept(editor.getHTML())
  }

  const hasChanges = editor ? editor.getHTML() !== lastSavedContent.current : false

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg)' }}>
      {/* Header */}
      <div style={{
        padding: '12px 24px', borderBottom: '1px solid var(--line)',
        background: 'var(--card)', display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', flexShrink: 0,
      }}>
        <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 16, color: 'var(--ink)' }}>
          {chapter.title}
        </span>
        {!pendingSuggestion && (
          <button
            onClick={handleManualSave}
            disabled={saving || !hasChanges}
            style={{
              padding: '6px 16px', background: 'var(--accent)', border: 'none',
              borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)',
              fontWeight: 700, fontSize: 13, cursor: saving ? 'wait' : 'pointer',
              opacity: (saving || !hasChanges) ? 0.5 : 1,
            }}
          >
            {saving ? 'Menyimpan...' : 'Simpan'}
          </button>
        )}
      </div>

      {/* Toolbar — only when not in suggestion mode */}
      {!pendingSuggestion && editor && (
        <div style={{
          display: 'flex', gap: 2, padding: '6px 12px',
          borderBottom: '1px solid var(--line)', background: 'var(--card)',
          flexShrink: 0, flexWrap: 'wrap',
        }}>
          <ToolbarButton onClick={() => editor.chain().focus().toggleBold().run()} active={editor.isActive('bold')} title="Bold">B</ToolbarButton>
          <ToolbarButton onClick={() => editor.chain().focus().toggleItalic().run()} active={editor.isActive('italic')} title="Italic"><em>I</em></ToolbarButton>
          <ToolbarButton onClick={() => editor.chain().focus().toggleUnderline().run()} active={editor.isActive('underline')} title="Underline"><u>U</u></ToolbarButton>
          <ToolbarButton onClick={() => editor.chain().focus().toggleHighlight().run()} active={editor.isActive('highlight')} title="Highlight">H</ToolbarButton>
          <span style={{ width: 1, background: 'var(--line)', margin: '0 4px' }} />
          <ToolbarButton onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} active={editor.isActive('heading', { level: 1 })} title="Heading 1">H1</ToolbarButton>
          <ToolbarButton onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} active={editor.isActive('heading', { level: 2 })} title="Heading 2">H2</ToolbarButton>
        </div>
      )}

      {/* Suggestion mode */}
      {pendingSuggestion ? (
        <div style={{ flex: 1, overflow: 'auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* First-time tooltip */}
          {!tooltipDismissed && !localStorage.getItem(TOOLTIP_KEY) && (
            <div style={{
              padding: '12px 16px', background: 'var(--accent-soft)', border: '1px solid var(--accent)',
              borderRadius: 'var(--radius-sm)', display: 'flex', alignItems: 'flex-start', gap: 12,
            }}>
              <span style={{ fontSize: 18 }}>💡</span>
              <div style={{ flex: 1 }}>
                <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)' }}>
                  Ni cadangan AI{pendingSuggestion.stageLabel ? ` — ${pendingSuggestion.stageLabel}` : ''} — klik <strong>Terima</strong> untuk masuk ke bab, atau <strong>Tolak</strong> untuk buang.
                </p>
              </div>
              <button onClick={() => { localStorage.setItem(TOOLTIP_KEY, '1'); setTooltipDismissed(true) }} style={{
                background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 16, flexShrink: 0, padding: 0,
              }}>×</button>
            </div>
          )}

          {/* Suggestion banner */}
          <div style={{
            borderLeft: '4px solid var(--accent)', paddingLeft: 16,
            background: 'var(--accent-soft)', borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
            padding: '16px 16px 16px 20px',
          }}>
            <p style={{
              fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase',
              letterSpacing: '0.08em', color: 'var(--ink-soft)', margin: '0 0 8px',
            }}>
              Cadangan AI{pendingSuggestion.stageLabel ? ` — ${pendingSuggestion.stageLabel}` : ''}
            </p>
            <p style={{ fontFamily: 'var(--font-body)', fontSize: 15, lineHeight: 1.7, color: 'var(--ink)', margin: 0, whiteSpace: 'pre-wrap' }}>
              {pendingSuggestion.text}
            </p>
          </div>

          {/* Terima / Tolak */}
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={handleAccept} disabled={saving} style={{
              padding: '10px 24px', background: 'var(--accent)', border: 'none',
              borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)',
              fontWeight: 700, fontSize: 14, cursor: saving ? 'wait' : 'pointer',
              opacity: saving ? 0.6 : 1,
            }}>
              {saving ? 'Menyimpan...' : 'Terima'}
            </button>
            <button onClick={onReject} disabled={saving} style={{
              padding: '10px 24px', background: 'transparent',
              border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
              fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14,
              cursor: 'pointer', color: 'var(--ink-soft)',
            }}>
              Tolak
            </button>
          </div>

          {/* Current content (read-only, muted) */}
          {(content || '').trim() && (
            <div>
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-soft)', margin: '0 0 8px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Kandungan semasa (tidak berubah jika Tolak)
              </p>
              <div
                dangerouslySetInnerHTML={{ __html: content }}
                style={{ fontFamily: 'var(--font-body)', fontSize: 14, lineHeight: 1.7, color: 'var(--ink-soft)' }}
              />
            </div>
          )}
        </div>
      ) : (
        /* Edit mode — TipTap editor */
        <div style={{ flex: 1, overflow: 'auto' }}>
          <style>{EDITOR_STYLES}</style>
          <div className="editor-paper">
            <EditorContent editor={editor} />
          </div>
        </div>
      )}
    </div>
  )
}
