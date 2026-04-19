import os
import io
import PyPDF2
from docx import Document

def extract_text_from_pdf(file_stream):
    """Extracts text from a PDF file stream."""
    try:
        reader = PyPDF2.PdfReader(file_stream)
        text = ""
        for page in reader.pages:
            content = page.extract_text()
            if content:
                text += content + "\n"
        return text.strip()
    except Exception as e:
        print(f"Error extracting PDF: {e}")
        return ""

def extract_text_from_docx(file_stream):
    """Extracts text from a DOCX file stream."""
    try:
        doc = Document(file_stream)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text.strip()
    except Exception as e:
        print(f"Error extracting DOCX: {e}")
        return ""

def extract_text_from_txt(file_stream):
    """Extracts text from a TXT file stream."""
    try:
        return file_stream.read().decode('utf-8', errors='ignore').strip()
    except Exception as e:
        print(f"Error extracting TXT: {e}")
        return ""

def get_document_content(files):
    """
    Takes a list of uploaded files (Werkzeug FileStorage)
    and returns a combined string of their contents.
    """
    combined_content = ""
    for file in files:
        filename = file.filename.lower()
        file.seek(0) # Ensure we are at the start of the stream
        
        if filename.endswith('.pdf'):
            content = extract_text_from_pdf(file)
        elif filename.endswith('.docx'):
            content = extract_text_from_docx(file)
        elif filename.endswith('.txt'):
            content = extract_text_from_txt(file)
        else:
            content = ""
            
        if content:
            combined_content += f"\n--- DOCUMENT: {file.filename} ---\n{content}\n"
            
    return combined_content.strip()
