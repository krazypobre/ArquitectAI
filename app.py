import hashlib
from flask import Flask, request, jsonify, send_from_directory
import requests
import os
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from psd_tools import PSDImage
from pdf2image import convert_from_path
from PIL import Image
import pytesseract
import docx
from pptx import Presentation
import ezdxf
import json

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {
    'pdf', 'dwg', 'dxf', 'png', 'jpg', 'jpeg', 'bmp',
    'svg', 'tiff', 'webp', 'heic', 'gif', 'docx', 'pptx',
    'ai', 'psd', 'indd'
}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
USERS_FILE = os.path.join(UPLOAD_FOLDER, 'users.json')
# Función auxiliar para cargar usuarios
def load_users():
    if not os.path.exists(USERS_FILE) or os.path.getsize(USERS_FILE) == 0:
        return []
    with open(USERS_FILE, 'r') as f:
        return json.load(f)
# Función auxiliar para guardar usuarios
def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4) # indent=4 para mejor legibilidad del JSON

# --------------------------
# Funciones auxiliares
# --------------------------

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def buscar_serper(query, api_key):
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": '3afe5888cc608256a0ae579173d4fb0c7186a9d0',
        "Content-Type": "application/json"
    }
    body = {"q": query}
    response = requests.post(url, headers=headers, json=body)
    print("Serper respuesta:", response.status_code, response.text)
    
    if response.status_code != 200:
        return None, f"Error HTTP: {response.status_code} - {response.text}"
    
    data = response.json()
    resultados = []
    organic = data.get("organic", [])
    
    if not organic:
        return None, "No se encontraron resultados en Serper."
    
    for r in organic:
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        link = r.get("link", "")
        resultados.append(f"Título: {title}\nResumen: {snippet}\nEnlace: {link}")
    
    return "\n\n".join(resultados), None

def llamar_a_ollama(prompt):
    url = "http://127.0.0.1:11434/v1/chat/completions"
    system_message = {
        "role": "system",
        "content": "Responde exactamente lo que te pida el usuario, si es necesario búscalo en Google. "
                   "Si la información proporcionada no contiene respuesta, di: 'No encontré respuesta en la búsqueda.'"
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

def extract_text_from_file(filepath, ext):
    file_text = ""
    try:
        if ext == 'pdf':
            reader = PdfReader(filepath)
            for page in reader.pages[:3]:
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
                    length = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
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
            try:
                images = convert_from_path(filepath)
                for img in images:
                    text = pytesseract.image_to_string(img, lang='spa')
                    file_text += text + "\n"
            except Exception as ai_error:
                file_text += f"[Error procesando archivo AI: {ai_error}]"

        elif ext == 'indd':
            file_text += "[Archivo InDesign detectado. Por favor, exporta el archivo a PDF para procesarlo.]"

        elif ext == 'svg':
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

# --------------------------
# Rutas
# --------------------------

@app.route("/")
def home():
    return send_from_directory('.', 'index.html')

@app.route('/preguntar', methods=['POST'])
def preguntar():
    data = request.json
    pregunta = data.get('pregunta')
    if not pregunta:
        return jsonify({"error": "No se recibió pregunta"}), 400

    api_key = "3afe5888cc608256a0ae579173d4fb0c7186a9d0"
    resultados, error = buscar_serper(pregunta, api_key)

    if resultados:
        prompt = f"Información de búsqueda:\n{resultados}\n\nPregunta del usuario: {pregunta}\nResponde usando SOLO esta información. Si no está, di: 'No encontré respuesta en la búsqueda.'"
    else:
        prompt = f"No hubo resultados de búsqueda. Responde con lo que sepas o di: 'No encontré respuesta en la búsqueda.' Pregunta: {pregunta}"

    response_ollama = llamar_a_ollama(prompt)

    return jsonify({"respuesta": response_ollama})

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
        file_text = extract_text_from_file(filepath, ext)

        try:
            os.remove(filepath)
        except Exception as e:
            print(f"Error eliminando archivo temporal: {e}")

    combined_prompt = f"{file_text}\n\nUsuario pregunta: {prompt}" if file_text else prompt

    system_message = {
        "role": "system",
        "content": "Eres un experto arquitecto y diseñador, pero también sabes sobre todos los temas del mundo. "
                   "Ayuda con preguntas técnicas y creativas sobre arquitectura y otros temas. "
                   "Habla como una persona normal, responde en el idioma en que se te habla y no hagas saludos largos."
    }
    user_message = {
        "role": "user",
        "content": combined_prompt
    }

    try:
        response = requests.post(
            'http://127.0.0.1:11434/v1/chat/completions',
            json={
                "model": "llama3",
                "messages": [system_message, user_message]
            },
            timeout=30
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
                    length = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
                    entidades.append({
                        "tipo": "línea",
                        "inicio": [round(start[0], 2), round(start[1], 2)],
                        "fin": [round(end[0], 2), round(end[1], 2)],
                        "longitud": round(length, 2)
                    })
                elif tipo in ("TEXT", "MTEXT"):
                    texto = entity.dxf.text if tipo == "TEXT" else entity.text
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
        try:
            os.remove(filepath)
        except Exception as e:
            print(f"Error eliminando archivo temporal: {e}")

    email = data.get('email')
    password = data.get('password')
    if not email or not password: # Solo necesitamos email y password para login
        return jsonify({"error": "Faltan datos."}), 400
    if not os.path.exists('users.json'):
        return jsonify({"error": "No hay usuarios registrados."}), 401 # O un mensaje más genérico
    with open('users.json', 'r') as f: # Abrir en modo lectura
        users = json.load(f)
    # Buscar al usuario por email
    user_found = None
    for user in users:
        if user['email'] == email:
            user_found = user
            break
    if user_found:
        # Hashear la contraseña proporcionada para compararla con la almacenada
        provided_password_hashed = hashlib.sha256(password.encode()).hexdigest()
        
        # Comparar la contraseña hasheada
        if user_found['password'] == provided_password_hashed:
            # Inicio de sesión exitoso
            return jsonify({"message": "Sesión iniciada.", "user": {"name": user_found['name'], "email": user_found['email']}}), 200
        else:
            # Contraseña incorrecta
            return jsonify({"error": "Credenciales inválidas."}), 401
    else:
        # Usuario no encontrado
        return jsonify({"error": "Credenciales inválidas."}), 40

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')

    # Validación básica de entrada
    if not name or not email or not password:
        return jsonify({"error": "Todos los campos son obligatorios."}), 400
    
    if len(password) < 6: # Ejemplo de validación de longitud mínima
        return jsonify({"error": "La contraseña debe tener al menos 6 caracteres."}), 400

    users = load_users()

    # Verificar si el correo ya está registrado
    if any(user['email'] == email for user in users):
        return jsonify({"error": "El correo ya está registrado."}), 409 # 409 Conflict

    # Hashear la contraseña antes de guardarla
    hashed_password = hashlib.sha256(password.encode('utf-8')).hexdigest()

    new_user = {
        "name": name,
        "email": email,
        "password": hashed_password # Guardar la contraseña hasheada
    }
    users.append(new_user)
    save_users(users)

    return jsonify({"message": "Usuario registrado correctamente."}), 201 # 201 Created

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    # Validación básica de entrada
    if not email or not password:
        return jsonify({"error": "Email y contraseña son obligatorios."}), 400

    users = load_users()

    # Buscar al usuario por email
    user_found = None
    for user in users:
        if user['email'] == email:
            user_found = user
            break

    # Si el usuario no se encuentra o la contraseña no coincide
    if not user_found:
        # Mensaje genérico para seguridad: no revelar si el email existe o no
        return jsonify({"error": "Credenciales inválidas."}), 401

    # Hashear la contraseña proporcionada por el usuario para la comparación
    provided_password_hashed = hashlib.sha256(password.encode('utf-8')).hexdigest()

    # Comparar el hash de la contraseña proporcionada con el hash almacenado
    if user_found['password'] == provided_password_hashed:
        # Inicio de sesión exitoso
        # Puedes devolver información del usuario (sin la contraseña)
        return jsonify({
            "message": "Sesión iniciada.",
            "user": {
                "name": user_found['name'],
                "email": user_found['email']
            }
        }), 200
    else:
        # Contraseña incorrecta
        return jsonify({"error": "Credenciales inválidas."}), 401


# --------------------------
# Ejecutar
# --------------------------

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5050)
