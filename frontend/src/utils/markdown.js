import { marked } from 'marked'
import DOMPurify from 'dompurify'

// ponytail: minimal config — only what TipTap StarterKit renders
marked.setOptions({ breaks: true, gfm: true })

const ALLOWED_TAGS = [
  'h1','h2','h3','p','br','strong','em','u','s',
  'ul','ol','li','blockquote','code','pre','sup','a',
]
const ALLOWED_ATTR = ['href','class','data-index','data-cite']

export function mdToHtml(text) {
  if (!text) return ''
  const raw = marked.parse(text)
  return DOMPurify.sanitize(raw, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
  })
}
