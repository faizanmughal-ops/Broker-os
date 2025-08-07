from fastapi import FastAPI, UploadFile, File, Query
from fastapi.responses import JSONResponse
import docx
import PyPDF2
from PIL import Image
import pytesseract
import io
import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Tesseract path for macOS
pytesseract.pytesseract.tesseract_cmd = os.getenv('TESSERACT_CMD', '/usr/local/bin/tesseract')

app = FastAPI()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Global variable to store extraction type
extraction_type = None

def extract_text(file: UploadFile):
    content = ""
    file_extension = file.filename.split('.')[-1].lower()
    try:
        if file_extension == 'docx':
            doc = docx.Document(io.BytesIO(file.file.read()))
            content = "\n".join([para.text for para in doc.paragraphs])
        elif file_extension == 'pdf':
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file.file.read()))
            content = "\n".join([page.extract_text() for page in pdf_reader.pages])
        elif file_extension in ['jpg', 'jpeg', 'png']:
            image = Image.open(io.BytesIO(file.file.read()))
            content = pytesseract.image_to_string(image)
        else:
            raise ValueError(f"Unsupported file type: {file_extension}")
    except Exception as e:
        print(f"Error reading file {file.filename}: {str(e)}")
        raise e
    return content

def send_to_openai(text, extraction_type):
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    if extraction_type == 1:
        # Vehicle fields
        prompt = f"Extract the following fields from this text and return them as a JSON object: Vehicle Make, Vehicle Model, Vehicle Year, Vehicle VIN, Primary Use. If any field is not found, set it to null. Text: {text}"
    else:
        # Personal information fields
        prompt = f"Extract the following fields from this text and return them as a JSON object: First Name, Last Name, Email, Phone No., Address, City, State, Zip Code, Create Client Web Portal. For Create Client Web Portal, return 'true' if enabled or 'false' if not mentioned or disabled. If any field is not found, set it to null. Text: {text}"
    
    data = {
        "model": "gpt-3.5-turbo-0125",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200
    }
    response = requests.post("https://api.openai.com/v1/chat/completions", json=data, headers=headers, timeout=30)
    result = response.json()
    return result['choices'][0]['message']['content']

@app.post("/upload-file")
async def upload_file(file: UploadFile = File(...)):
    try:
        if extraction_type is None:
            return JSONResponse(content={"error": "Please set extraction type first. Use /set-type endpoint."}, status_code=400)
        
        print(f"Processing file: {file.filename}")
        extracted_text = extract_text(file)
        print(f"Extracted text length: {len(extracted_text)}")
        
        if not extracted_text:
            return JSONResponse(content={"error": "No text extracted from the file"}, status_code=400)
        
        print("Sending to OpenAI...")
        openai_response = send_to_openai(extracted_text, extraction_type)
        print(f"OpenAI response: {openai_response}")
        
        fields = json.loads(openai_response)
        return JSONResponse(content=fields)
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {str(e)}")
        return JSONResponse(content={"error": f"Failed to parse OpenAI response: {str(e)}"}, status_code=500)
    except Exception as e:
        print(f"Exception: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/set-type")
async def set_extraction_type(type_id: int = Query(...)):
    global extraction_type
    if type_id not in [1, 2]:
        return JSONResponse(content={"error": "Type must be 1 or 2"}, status_code=400)
    
    extraction_type = type_id
    type_name = "Vehicle Information" if type_id == 1 else "Personal Information"
    return JSONResponse(content={"message": f"Extraction type set to: {type_name}", "type": type_id})

if __name__ == "__main__":
    import uvicorn
    print("Starting FastAPI server...")
    print("Available endpoints:")
    print("- POST /set-type - Set extraction type (1 for Vehicle, 2 for Personal Info)")
    print("- POST /upload-file - Upload file for extraction")
    
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 8001))
    print(f"Server running on http://localhost:{port}")
    uvicorn.run(app, host=host, port=port)
