import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

const HELP_SECTIONS = [
  {
    id: 'bermula',
    icon: '🚀',
    title: 'Bermula',
    items: [
      { q: 'Cara daftar dan log masuk', a: 'Pergi ke researcherhq.com → klik Daftar → masukkan emel. Kata laluan akan dihantar ke emel anda. Log masuk menggunakan kata laluan tersebut, kemudian tukar dalam Account Settings.' },
      { q: 'Cipta projek pertama', a: 'Selepas log masuk, klik [+ Projek Baru] dalam dashboard. Isi nama projek, pilih bidang kajian, dan tahap pengajian.' },
      { q: 'Muat naik dokumen', a: 'Dalam workspace projek, panel kiri (Sources) → klik [+ Tambah Sumber] → pilih fail (PDF, DOCX, XLSX, PPTX, max 20MB) → pilih kategori dokumen.' },
      { q: 'Hantar soalan pertama', a: 'Selepas dokumen diproses, taip soalan dalam panel Chat (tengah) → tekan Enter atau klik butang hantar.' },
    ]
  },
  {
    id: 'dokumen',
    icon: '📄',
    title: 'Urus Dokumen (Sources)',
    items: [
      { q: 'Jenis fail yang disokong', a: 'PDF, DOCX, XLSX, PPTX — maksimum 20MB sesatu fail.' },
      { q: 'Kategori dokumen', a: 'Artikel Rujukan (jurnal/buku), Catatan SV (nota penyelia), Draf Sendiri (draf tesis), Data & Transkrip (data kajian), Panduan Format (garis panduan fakulti).' },
      { q: 'Cari artikel dari Search Panel', a: 'Klik [🔍 Cari Artikel] dalam panel Sources → taip kata kunci → hasil dari OpenAlex dan Semantic Scholar dipaparkan → klik artikel untuk baca abstract → [+ Tambah ke Sources] (Pro sahaja).' },
      { q: 'Open Access vs Paywalled', a: '🔓 Open Access: AI dapat baca kandungan penuh artikel. 🔒 Paywalled: AI hanya ada abstract. Muat naik PDF penuh untuk analisis mendalam.' },
    ]
  },
  {
    id: 'chat',
    icon: '💬',
    title: 'Chat dengan AI',
    items: [
      { q: 'Mod RAG vs Jawapan Umum vs Web', a: 'RAG (📄 Dokumen): AI jawab dari dokumen awak — tepat, ada citation. Jawapan Umum (💬): AI jawab dari pengetahuan umum apabila tiada dokumen atau soalan umum. Web (🔍): AI cari maklumat terkini dari internet — Pro sahaja, 5 kredit/carian.' },
      { q: 'Output Modes', a: 'Soal-Jawab (1–3 kredit), Key Findings (3 kredit), Executive Summary (5 kredit), Literature Review (10 kredit). Pilih mode mengikut keperluan output yang dikehendaki.' },
      { q: 'Toggle Web Search', a: 'Klik butang [📄 Dokumen] dalam input bar untuk tukar ke [🔍 Web]. Pro sahaja. Setiap carian web = 5 kredit. Toggle kembali ke Dokumen secara automatik selepas setiap soalan.' },
      { q: 'Citation dalam jawapan AI', a: 'AI guna format [[cite:N]] untuk rujuk sumber. N = nombor sumber dalam senarai di bawah jawapan. Klik sumber untuk lihat petikan asal dari dokumen.' },
    ]
  },
  {
    id: 'editor',
    icon: '✍️',
    title: 'Editor & Struktur Thesis',
    items: [
      { q: 'Cara guna editor', a: 'Panel kanan (Struktur Thesis) → klik nama bab → editor TipTap terbuka di panel tengah. Sokongan teks bold, italic, highlight.' },
      { q: 'Terima dan Tolak cadangan AI', a: '[Terima]: kandungan cadangan AI dimasukkan ke dalam bab awak. [Tolak]: cadangan dibuang, teks asal kekal.' },
      { q: 'Export bab ke .docx', a: 'Panel Struktur Thesis → klik [Export] atau ikon .docx sebelah nama bab → fail .docx dimuat turun.' },
      { q: 'Semak SV Alignment', a: 'Dalam editor → klik [Semak SV Alignment] → AI bandingkan kandungan bab dengan maklum balas penyelia yang diupload dan kesan item yang belum diambil tindakan.' },
    ]
  },
  {
    id: 'style',
    icon: '🎨',
    title: 'Style Profile',
    items: [
      { q: 'Apa itu Style Profile', a: 'Tetapan gaya penulisan yang membantu AI ikut cara awak menulis — pilihan perkataan, panjang ayat, nada akademik.' },
      { q: 'Cara tetapkan', a: 'Dua cara: (1) Isi borang manual dalam Style Profile modal, atau (2) Upload contoh penulisan awak → AI akan analyse dan extract gaya penulisan secara automatik.' },
      { q: 'Di mana Style Profile', a: 'Dalam workspace projek → panel Chat → ikon Style Profile (Pro sahaja).' },
    ]
  },
  {
    id: 'sv',
    icon: '👨‍🏫',
    title: 'Maklum Balas Penyelia',
    items: [
      { q: 'Upload nota penyelia', a: 'Sources panel → [+ Tambah Sumber] → pilih fail → kategori: Catatan SV → AI akan extract item maklum balas secara automatik.' },
      { q: 'Semak alignment', a: 'Dalam editor → klik [Semak SV Alignment] → AI compare bab awak dengan maklum balas SV dan highlight item yang belum diambil tindakan.' },
    ]
  },
  {
    id: 'kredit',
    icon: '💳',
    title: 'Kredit & Pelan',
    items: [
      { q: 'Apa itu Research Credits', a: 'Unit yang digunakan setiap kali AI jana respons. Free: 50 kredit/bulan. Pro: 500 kredit/bulan + boleh topup.' },
      { q: 'Kadar kredit', a: 'Soal-Jawab biasa: 1 kredit. Soal-Jawab mendalam: 3 kredit. Key Findings: 3 kredit. Executive Summary: 5 kredit. Literature Review: 10 kredit. Carian Web: 5 kredit (Pro).' },
      { q: 'Topup kredit', a: 'RM10 = +200 kredit tambahan. Kredit topup tidak reset bulanan — kekal sehingga digunakan. Mesti pengguna Pro untuk topup.' },
      { q: 'Semak baki kredit', a: 'Klik nama awak (atas kanan) → Account Settings → bahagian Kredit. Atau lihat indikator kredit dalam workspace.' },
    ]
  },
  {
    id: 'soal-selidik',
    icon: '📋',
    title: 'Soal Selidik (Pro sahaja)',
    items: [
      { q: 'Apa itu Modul Soal Selidik?', a: 'Alat (Pro sahaja) untuk bina draf instrumen dari dokumen projek, kumpul respons melalui link awam, dan export data. Lokasi: ikon [Survey] dalam icon rail panel Sources.' },
      { q: 'Cara jana draf dengan AI', a: 'Buka Soal Selidik → klik [Jana dengan AI]. AI baca dokumen projek awak (objektif, kerangka konsep, pemboleh ubah) dan jana draf bahagian + soalan. Kos: 10 kredit untuk jana penuh.' },
      { q: 'Edit dan susun soalan', a: 'Semua soalan boleh diedit — teks, jenis (Likert/MCQ/terbuka/demografi), pilihan jawapan, dan susunan. Edit manual percuma. Nota: struktur dikunci semasa kutipan respons aktif.' },
      { q: 'Mod Pilot vs Actual', a: 'Pilot = kutipan percubaan (had 50 respons) yang boleh dibuka semula untuk membaiki instrumen selepas pilot study; respons pilot disimpan untuk analisis kebolehpercayaan nanti. Actual = kutipan sebenar (had sehingga 1,000 respons).' },
      { q: 'Cara kumpul respons', a: 'Klik Terbitkan → pilih mod → dapat link awam. Kongsi link; responden isi tanpa akaun. Owner nampak bilangan respons dan boleh Export CSV.' },
      { q: 'Export data respons', a: 'Dalam dashboard Kumpul, klik Export CSV (pilih pilot atau actual) — satu baris per respons, satu kolum per soalan, termasuk kolum is_pilot.' },
      { q: 'Adakah instrumen ini sah (valid)?', a: 'TIDAK secara automatik. Output adalah DRAF — kesahan instrumen memerlukan semakan penyelia, expert review dan pilot study di luar sistem.' },
    ]
  },
  {
    id: 'faq',
    icon: '❓',
    title: 'Soalan Lazim',
    items: [
      { q: 'Adakah dokumen saya selamat?', a: 'Ya. Dokumen awak hanya digunakan dalam projek awak sendiri. Kami tidak kongsikan kandungan dokumen awak dengan pengguna lain atau pihak ketiga.' },
      { q: 'Boleh AI reka maklumat (hallucinate)?', a: 'ResearcherHQ direka untuk mengurangkan hallucination — AI hanya jawab dari dokumen awak (mod RAG). Untuk mod Jawapan Umum, AI mungkin ada had pengetahuan. Sentiasa semak citation yang diberikan.' },
      { q: 'Kenapa AI kata "abstract sahaja"?', a: 'Artikel yang ditambah dari Search Panel mungkin paywalled — ResearcherHQ hanya dapat abstract awam. Muat naik PDF penuh artikel tersebut untuk analisis mendalam.' },
      { q: 'Cara hubungi sokongan', a: 'Menu → Sokongan, atau emel support@researcherhq.com.' },
    ]
  },
]

export default function HelpPage() {
  const [openSection, setOpenSection] = useState(null)
  const [openItem, setOpenItem] = useState(null)
  const navigate = useNavigate()

  return (
    <div style={{ maxWidth: 760, margin: '0 auto', padding: '32px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 32 }}>
        <button onClick={() => navigate(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6B7280', fontSize: 14 }}>← Balik</button>
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>Pusat Bantuan</h1>
      </div>

      {HELP_SECTIONS.map(section => (
        <div key={section.id} style={{ marginBottom: 12, border: '1px solid #E5E7EB', borderRadius: 8, overflow: 'hidden' }}>
          <button
            onClick={() => setOpenSection(openSection === section.id ? null : section.id)}
            style={{
              width: '100%', padding: '14px 16px',
              background: openSection === section.id ? '#F9FAFB' : 'white',
              border: 'none', cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              fontSize: 15, fontWeight: 600, textAlign: 'left',
            }}
          >
            <span>{section.icon} {section.title}</span>
            <span style={{ color: '#9CA3AF' }}>{openSection === section.id ? '▲' : '▼'}</span>
          </button>

          {openSection === section.id && (
            <div style={{ borderTop: '1px solid #E5E7EB' }}>
              {section.items.map((item, i) => (
                <div key={i} style={{ borderBottom: i < section.items.length - 1 ? '1px solid #F3F4F6' : 'none' }}>
                  <button
                    onClick={() => setOpenItem(openItem === `${section.id}-${i}` ? null : `${section.id}-${i}`)}
                    style={{
                      width: '100%', padding: '12px 16px', background: 'none', border: 'none',
                      cursor: 'pointer', display: 'flex', justifyContent: 'space-between',
                      fontSize: 14, color: '#374151', textAlign: 'left',
                    }}
                  >
                    <span>{item.q}</span>
                    <span style={{ color: '#9CA3AF', flexShrink: 0, marginLeft: 8 }}>
                      {openItem === `${section.id}-${i}` ? '−' : '+'}
                    </span>
                  </button>
                  {openItem === `${section.id}-${i}` && (
                    <div style={{ padding: '0 16px 14px 16px', fontSize: 14, color: '#6B7280', lineHeight: 1.6 }}>
                      {item.a}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
