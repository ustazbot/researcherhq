// Primary: [[cite:N]] — Secondary fallback: (filename.pdf, ms. N)
const PRIMARY = /\[\[cite:(\d+)\]\]/g
const FALLBACK = /\(([^)]+?\.pdf),\s*ms\.\s*(\d+)\)/gi

export function parseCitation(text, sources = []) {
  if (!text) return [{ type: 'text', content: '' }]
  const segments = []
  let last = 0

  // Collect all matches (primary preferred; fallback only fills gaps)
  const matches = []
  let m
  PRIMARY.lastIndex = 0
  while ((m = PRIMARY.exec(text)) !== null) {
    matches.push({ start: m.index, end: m.index + m[0].length, index: parseInt(m[1], 10), raw: m[0] })
  }

  // If no primary tokens found, try fallback
  if (matches.length === 0) {
    FALLBACK.lastIndex = 0
    while ((m = FALLBACK.exec(text)) !== null) {
      // Find source by filename match
      const fname = m[1].trim().toLowerCase()
      const srcIdx = sources.findIndex(s => s.filename?.toLowerCase().includes(fname))
      matches.push({ start: m.index, end: m.index + m[0].length, index: srcIdx + 1, raw: m[0] })
    }
  }

  // Sort by position
  matches.sort((a, b) => a.start - b.start)

  for (const match of matches) {
    if (match.start > last) {
      segments.push({ type: 'text', content: text.slice(last, match.start) })
    }
    const src = sources[match.index - 1] ?? null
    segments.push({ type: 'cite', index: match.index, source: src })
    last = match.end
  }
  if (last < text.length) {
    segments.push({ type: 'text', content: text.slice(last) })
  }
  return segments.length ? segments : [{ type: 'text', content: text }]
}

// ponytail: self-check — run with `node src/utils/parseCitation.js`
if (typeof process !== 'undefined' && process.argv[1]?.includes('parseCitation')) {
  const src = [{ filename: 'kajian.pdf', page_number: 3 }]
  const r1 = parseCitation('Fakta ini [[cite:1]] disahkan.', src)
  console.assert(r1.length === 3, 'should have 3 segments')
  console.assert(r1[1].type === 'cite', 'middle should be cite')
  console.assert(r1[1].index === 1, 'cite index should be 1')
  const r2 = parseCitation('(kajian.pdf, ms. 3)', src)
  console.assert(r2[0].type === 'cite', 'fallback should parse cite')
  const r3 = parseCitation('plain text no citations', src)
  console.assert(r3[0].type === 'text', 'no tokens = pure text')
  console.log('parseCitation self-check PASS')
}
