from pypdf import PdfReader
import sys

def extract_text_from_pdf(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        return str(e)

if __name__ == "__main__":
    print("Reading PDF...")
    pdf_path = "grok_report.pdf"
    content = extract_text_from_pdf(pdf_path)
    print(f"Content length: {len(content)}")
    print(content[:2000]) # Print first 2000 chars

