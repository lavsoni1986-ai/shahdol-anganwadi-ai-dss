import PyPDF2
with open("test_v4.pdf", "rb") as f:
    reader = PyPDF2.PdfReader(f)
    print(f"Total pages: {len(reader.pages)}")
    for i, page in enumerate(reader.pages):
        print(f"--- Page {i+1} ---")
        text = page.extract_text()
        # Print first 200 chars and look for key strings
        print(text[:200].replace('\n', ' '))
