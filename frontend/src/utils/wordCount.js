// §6J — client-side word count. Zero backend round-trips, zero LLM cost.
// Chapter content is TipTap HTML, so tags must be stripped and entities
// decoded before counting. DOMParser handles both (nested tags, &nbsp;,
// &amp;, …); the regex path is only a fallback for non-browser runtimes.

export function stripHtmlAndCount(html) {
  if (!html) return 0
  let text
  if (typeof DOMParser !== 'undefined') {
    text = new DOMParser().parseFromString(html, 'text/html').body.textContent || ''
  } else {
    text = html
      .replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/gi, ' ')
      .replace(/&amp;/gi, '&')
      .replace(/&lt;/gi, '<')
      .replace(/&gt;/gi, '>')
  }
  const tokens = text.split(/\s+/).filter(Boolean)
  return tokens.length
}
