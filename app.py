from flask import Flask, request, jsonify, send_from_directory
import requests
import os
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from PIL import Image
import pytesseract
import docx
from pptx import Presentation
import ezdxf

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'dwg', 'dxf', 'png', 'jpg', 'jpeg', 'bmp', 'svg', 'tiff', 'webp', 'heic', 'gif', 'docx', 'pptx'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def home():
    return send_from_directory('.', 'index.html')

@app.route('/api/generar-texto', methods=['POST'])
def generar_texto():
    prompt = request.form.get('prompt', '').strip()
    file = request.files.get('file')

    file_text = ""

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        ext = filename.rsplit('.', 1)[1].lower()

        try:
            if ext == 'pdf':
                reader = PdfReader(filepath)
                for page in reader.pages[:3]:
                    page_text = page.extract_text()
                    if page_text:
                        file_text += page_text + "\n"

            elif ext in ('png', 'jpg', 'jpeg', 'bmp', 'gif', 'tiff', 'webp', 'heic', 'dxf'):
                img = Image.open(filepath)
                text = pytesseract.image_to_string(img, lang='spa')
                file_text += text

            elif ext == 'docx':
                doc = docx.Document(filepath)
                for para in doc.paragraphs:
                    file_text += para.text + "\n"

            elif ext == 'pptx':
                ppt = Presentation(filepath)
                for slide in ppt.slides:
                    for shape in slide.shapes:
                        if hasattr(shape, "text"):
                            file_text += shape.text + "\n"

            elif ext in ('dwg', 'dxf'):
                doc = ezdxf.readfile(filepath)
                msp = doc.modelspace()
                for entity in msp:
                    tipo = entity.dxftype()
                    if tipo == "LINE":
                        start = entity.dxf.start
                        end = entity.dxf.end
                        length = ((end[0] - start[0])**2 + (end[1] - start[1])**2)**0.5
                        file_text += f"Línea de {start} a {end} con longitud aproximada de {round(length, 2)} unidades.\n"
                    elif tipo == "TEXT":
                        file_text += f"Texto: {entity.dxf.text}\n"
                    elif tipo == "MTEXT":
                        file_text += f"Texto: {entity.text}\n"


            else:
                file_text += f"[Archivo '{filename}' recibido, pero sin extracción automática de texto.]"

        except Exception as e:
            file_text += f"[Error procesando archivo '{filename}': {e}]"

        os.remove(filepath)

    combined_prompt = f"{file_text}\n\nUsuario pregunta: {prompt}" if file_text else prompt

    system_message = {
        "role": "system",
        "content": "Eres un experto arquitecto y diseñador, ayuda con preguntas técnicas y creativas sobre arquitectura, no hagas respuestas demasiado largas en los saludos, habla como si fueses una persona normal."
    }
    user_message = {
        "role": "user",
        "content": combined_prompt
    }
    print("Prompt combinado enviado al modelo:\n", combined_prompt)

    response = requests.post(
        'http://127.0.0.1:11434/v1/chat/completions',
        json={
            "model": "llama3",
            "messages": [system_message, user_message]
        }
    )

    if response.status_code == 200:
        respuesta = response.json()['choices'][0]['message']['content']
    else:
        respuesta = "Error al generar respuesta"

    return jsonify({'respuesta': respuesta})

@app.route("/upload", methods=["POST"])
def upload_file():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No se envió ningún archivo."}), 400

    filename = file.filename
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    if filename.lower().endswith(".dxf"):
        try:
            doc = ezdxf.readfile(filepath)
            msp = doc.modelspace()
            entidades = []

            for entity in msp:
                tipo = entity.dxftype()
                if tipo == "LINE":
                    start = entity.dxf.start
                    end = entity.dxf.end
                    length = ((end[0] - start[0])**2 + (end[1] - start[1])**2)**0.5
                    entidades.append({
                        "tipo": "línea",
                        "inicio": [round(start[0],2), round(start[1],2)],
                        "fin": [round(end[0],2), round(end[1],2)],
                        "longitud": round(length, 2)
                    })
                elif tipo in ("TEXT", "MTEXT"):
                    if tipo == "TEXT":
                         texto = entity.dxf.text
                    elif tipo == "MTEXT":
                        texto = entity.text
                        entidades.append({
                        "tipo": "texto",
                        "contenido": texto
        
                    })

            return jsonify({"resultado": entidades})
        except Exception as e:
            return jsonify({"error": f"No se pudo leer el archivo DXF: {str(e)}"}), 500

    return jsonify({"mensaje": "Archivo recibido pero no es DXF."})


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5050)








