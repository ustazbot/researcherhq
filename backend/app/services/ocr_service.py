import asyncio
from PIL import Image
import pytesseract


async def ocr_pdf_pages(pdf_bytes: bytes) -> list:
    def _run_ocr():
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img, lang="eng+msa")
            pages.append({"page_number": page_num + 1, "text": text})
        return pages

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_ocr)


def is_scanned_pdf(pages: list) -> bool:
    if not pages:
        return False
    avg_tokens = sum(len(p.get("text", "").split()) for p in pages) / len(pages)
    return avg_tokens < 50
