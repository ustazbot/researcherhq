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
  // Convert [[cite:N]] to superscript before sanitizing
  const withChips = raw.replace(/\[\[cite:(\d+)\]\]/g,
    (_, n) => `<sup class="cite-chip" data-index="${n}">[${n}]</sup>`)
  return DOMPurify.sanitize(withChips, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
  })
}
