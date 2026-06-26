"""
PDF and EPUB pack generator.
Takes a Forge Mint result dict and produces sellable output files.
"""
import json
import pathlib
import datetime


EXPORT_DIR = pathlib.Path.home() / "lousta-core" / "output" / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _build_pdf(book: dict, out_path: pathlib.Path) -> None:
    try:
        from fpdf import FPDF
    except ImportError:
        out_path.write_text(f"[PDF placeholder — install fpdf2]\n{book['title']}")
        return

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 24)
    pdf.cell(0, 20, book["title"], ln=True, align="C")
    pdf.set_font("Helvetica", "", 14)
    pdf.cell(0, 10, f"by {book['author']}", ln=True, align="C")
    pdf.ln(10)

    pdf.set_font("Helvetica", "", 11)
    for ch in book["chapters"]:
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 10, f"Chapter {ch['chapter']}", ln=True)
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 7, ch["text"])
        pdf.ln(5)

    pdf.output(str(out_path))


def _build_epub(book: dict, out_path: pathlib.Path) -> None:
    try:
        from ebooklib import epub
    except ImportError:
        out_path.write_text(f"[EPUB placeholder — install ebooklib]\n{book['title']}")
        return

    eb = epub.EpubBook()
    eb.set_identifier(f"lousta-{book['title'].lower().replace(' ', '-')}")
    eb.set_title(book["title"])
    eb.set_language("en")
    eb.add_author(book["author"])

    spine = ["nav"]
    for ch in book["chapters"]:
        c = epub.EpubHtml(
            title=f"Chapter {ch['chapter']}",
            file_name=f"chapter_{ch['chapter']:02d}.xhtml",
            lang="en",
        )
        c.content = (
            f"<h1>Chapter {ch['chapter']}</h1>"
            f"<p>{ch['text'].replace(chr(10), '</p><p>')}</p>"
        )
        eb.add_item(c)
        spine.append(c)

    eb.spine = spine
    eb.add_item(epub.EpubNcx())
    eb.add_item(epub.EpubNav())
    epub.write_epub(str(out_path), eb)


def generate_pack(book: dict) -> dict:
    """
    Accepts a forge_mint result dict and writes PDF + EPUB to the exports dir.
    Returns paths to the generated files.
    """
    slug = book["title"].lower().replace(" ", "_")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    pdf_path = EXPORT_DIR / f"{slug}_{ts}.pdf"
    epub_path = EXPORT_DIR / f"{slug}_{ts}.epub"

    _build_pdf(book, pdf_path)
    _build_epub(book, epub_path)

    return {
        "title": book["title"],
        "pdf": str(pdf_path),
        "epub": str(epub_path),
        "generated": datetime.datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_epub.py <forge_mint_result.json>")
        raise SystemExit(1)

    book = json.loads(pathlib.Path(sys.argv[1]).read_text())
    result = generate_pack(book)
    print(json.dumps(result, indent=2))
