from flask import Flask, request, jsonify, send_from_directory
import requests
import os
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from psd_tools import PSDImage
import pikepdf
from pdf2image import convert_from_path
from PIL import Image
import pytesseract
import docx
from pptx import Presentation
import ezdxf

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'dwg', 'dxf', 'png', 'jpg', 'jpeg', 'bmp', 'svg', 'tiff', 'webp', 'heic', 'gif', 'docx', 'pptx', 'ai', 'psd', 'indd'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def buscar_serper(query, api_key):
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    body = {
        "q": query
    }
    response = requests.post(url, headers=headers, json=playload)  # ✅ JSON en body
    print("Serper respuesta:", response.status_code, response.text)
    if response.status_code != 200:
        return None, response.text
    data = response.json()
    resultados = []
    for r in data.get("organic", []):
        title = r.get("title")
        snippet = r.get("snippet")
        link = r.get("link")
        resultados.append(f"{title}\n{snippet}\n{link}")
    return "\n\n".join(resultados), None

# Ruta para recibir preguntas desde el frontend y responder con info de búsqueda + Ollama
@app.route('/preguntar', methods=['POST'])
def preguntar():
    data = request.json
    pregunta = data.get('pregunta')
    if not pregunta:
        return jsonify({"error": "No se recibió pregunta"}), 400

    api_key = "3afe5888cc608256a0ae579173d4fb0c7186a9d0"  # Pon aquí tu API Key de Serper.dev

    # Buscar en Serper.dev
    resultados, error = buscar_serper(pregunta, api_key)
    if error:
        return jsonify({"error": f"Error en búsqueda: {error}"}), 500

    # Construir prompt para Ollama (aquí debes poner tu llamada a Ollama)
    prompt = f"Información relevante para la pregunta:\n{resultados}\n\nResponde usando esta información: {pregunta}"

    # --- Aquí llamas a Ollama con el prompt y obtienes la respuesta ---
    # response_ollama = llamar_a_ollama(prompt)  # Implementa esta función según tu código actual

    response_ollama = llamar_a_ollama(prompt)  # Placeholder

    return jsonify({"respuesta": response_ollama})

def llamar_a_ollama(prompt):
    url = "http://127.0.0.1:11434/v1/chat/completions"
    system_message = {
        "role": "system",
        "content": "Responde exactamente lo que te pida el usuario, si es necesario buscalo en google, si la información proporcionada no contiene respuesta, di: ‘No encontré respuesta en la búsqueda."
    }
    user_message = {
        "role": "user",
        "content": prompt
    }
    payload = {
        "model": "llama3",
        "messages": [system_message, user_message]
    }
    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return f"Error del servidor del modelo: {response.status_code}"
    except Exception as e:
        return f"Error llamando al modelo: {e}"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_file(filepath, ext):
    """Extrae texto de diferentes tipos de archivo"""
    file_text = ""
    
    try:
        if ext == 'pdf':
            reader = PdfReader(filepath)
            for page in reader.pages[:3]:  # Solo primeras 3 páginas
                page_text = page.extract_text()
                if page_text:
                    file_text += page_text + "\n"
        
        elif ext in ('png', 'jpg', 'jpeg', 'bmp', 'gif', 'tiff', 'webp', 'heic'):
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
        
        elif ext == 'psd':
            psd = PSDImage.open(filepath)
            img = psd.composite()
            text = pytesseract.image_to_string(img, lang='spa')
            file_text += text
        
        elif ext == 'ai':
            # Illustrator a PDF -> Imagen -> OCR
            try:
                images = convert_from_path(filepath)
                for img in images:
                    text = pytesseract.image_to_string(img, lang='spa')
                    file_text += text + "\n"
            except Exception as ai_error:
                print(f"Error procesando archivo AI: {ai_error}")
                file_text += f"[Error procesando archivo AI: {ai_error}]"
        
        elif ext == 'indd':
            # InDesign no se puede procesar directamente
            file_text += "[Archivo InDesign detectado. Por favor, exporta el archivo a PDF para procesarlo.]"
        
        elif ext == 'svg':
            # SVG es un formato vectorial, se puede intentar OCR si se convierte a imagen
            try:
                img = Image.open(filepath)
                text = pytesseract.image_to_string(img, lang='spa')
                file_text += text
            except Exception as svg_error:
                file_text += f"[Archivo SVG recibido, conversión no disponible: {svg_error}]"
        
        else:
            file_text += f"[Archivo recibido pero formato '{ext}' no soportado para extracción de texto.]"
    
    except Exception as e:
        print(f"Error procesando archivo {ext}: {e}")
        file_text += f"[Error procesando archivo: {e}]"
    
    return file_text

@app.route("/")
def home():
    return send_from_directory('.', 'index.html')

@app.route('/api/generar-texto', methods=['POST'])
def generar_texto():
    prompt = request.form.get('prompt', '').strip()
    file = request.files.get('file')
    
    file_text = ""
    
    # Procesar archivo si existe
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        ext = filename.rsplit('.', 1)[1].lower()
        file_text = extract_text_from_file(filepath, ext)
        
        # Limpiar archivo temporal
        try:
            os.remove(filepath)
        except Exception as e:
            print(f"Error eliminando archivo temporal: {e}")
    
    # Combinar texto del archivo con el prompt del usuario
    combined_prompt = f"{file_text}\n\nUsuario pregunta: {prompt}" if file_text else prompt
    
    # Configurar mensajes para el modelo
    system_message = {
        "role": "system",
        "content": "Eres un experto arquitecto y diseñador, pero también sabes sobre todos los temas del mundo, si el usuario pide otro tema que no es sobre arquitectura o algo parecido, respondele con toda la información que sepas, o búscala en internet, ayuda con preguntas técnicas y creativas sobre arquitectura, no hagas respuestas demasiado largas en los saludos, habla como si fueses una persona normal, responde siempre en el idioma en el que te hable, no cambies de idioma si no lo pide el usuario, si te pide hablar sobre otros temas que no son de arquitectura o algo relacionado con eso ayúdalo también."
    }
    user_message = {
        "role": "user",
        "content": combined_prompt
    }
    
    print("Prompt combinado enviado al modelo:\n", combined_prompt)
    
    # Llamada al modelo
    try:
        response = requests.post(
            'http://127.0.0.1:11434/v1/chat/completions',
            json={
                "model": "llama3",
                "messages": [system_message, user_message]
            },
            timeout=30  # Añadir timeout
        )
        
        if response.status_code == 200:
            respuesta = response.json()['choices'][0]['message']['content']
        else:
            respuesta = f"Error del servidor del modelo: {response.status_code}"
    
    except Exception as e:
        print(f"Error llamando al modelo: {e}")
        respuesta = "Error al generar respuesta del modelo"
    
    return jsonify({'respuesta': respuesta})

@app.route("/upload", methods=["POST"])
def upload_file():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No se envió ningún archivo."}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    try:
        if filename.lower().endswith(".dxf"):
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
                        "inicio": [round(start[0], 2), round(start[1], 2)],
                        "fin": [round(end[0], 2), round(end[1], 2)],
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
        else:
            return jsonify({"mensaje": "Archivo recibido pero no es DXF."})
    
    except Exception as e:
        return jsonify({"error": f"No se pudo procesar el archivo: {str(e)}"}), 500
    
    finally:
        # Limpiar archivo temporal
        try:
            os.remove(filepath)
        except Exception as e:
            print(f"Error eliminando archivo temporal: {e}")

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5050)