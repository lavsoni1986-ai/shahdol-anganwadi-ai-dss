import fitz
import sys

def pdf_to_images(pdf_path):
    doc = fitz.open(pdf_path)
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=150)
        output_path = f"page_{page_num + 1}.png"
        pix.save(output_path)
        print(f"Saved {output_path}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        pdf_to_images(sys.argv[1])
    else:
        print("Provide PDF path")
