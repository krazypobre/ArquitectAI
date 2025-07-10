import hashlib
from flask import Flask, request, jsonify, send_from_directory, render_template, redirect
from flask_mail import Mail, Message 
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
from flask import Flask, session

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {
    'pdf', 'dwg', 'dxf', 'png', 'jpg', 'jpeg', 'bmp',
    'svg', 'tiff', 'webp', 'heic', 'gif', 'docx', 'pptx',
    'ai', 'psd', 'indd'
}

app = Flask(__name__)
app.secret_key = 'una_clave_super_secreta'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'tucorreo@gmail.com'
app.config['MAIL_PASSWORD'] = 'tu_contraseña_de_aplicacion'
app.config['MAIL_DEFAULT_SENDER'] = ('Tu App', 'tucorreo@gmail.com')

mail = Mail(app)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
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
        json.dump(users, f, indent=4)

# --------------------------
# Funciones auxiliares
# --------------------------

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def buscar_serper(query, api_key):
    """
    Busca en Google usando Serper API
    """
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    body = {"q": query}
    
    try:
        response = requests.post(url, headers=headers, json=body, timeout=10)
        print(f"🔍 Serper API - Status: {response.status_code}")
        print(f"🔍 Serper API - Response: {response.text[:200]}...")
        
        if response.status_code != 200:
            return None, f"Error HTTP: {response.status_code} - {response.text}"
        
        data = response.json()
        resultados = []
        organic = data.get("organic", [])
        
        if not organic:
            return None, "No se encontraron resultados en Serper."
        
        for r in organic[:5]:  # Limitar a 5 resultados
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            link = r.get("link", "")
            resultados.append(f"Título: {title}\nResumen: {snippet}\nEnlace: {link}")
        
        return "\n\n".join(resultados), None
        
    except Exception as e:
        print(f"❌ Error en Serper: {e}")
        return None, f"Error conectando con Serper: {e}"

def llamar_a_ollama(prompt):
    """
    Llama al modelo Ollama local
    """
    url = "http://127.0.0.1:11434/v1/chat/completions"
    system_message = {
        "role": "system",
        "content": "Eres un experto arquitecto y diseñador, pero también sabes sobre todos los temas del mundo. "
                   "Ayuda con preguntas técnicas y creativas. Habla como una persona normal, "
                   "responde en el idioma en que se te habla y no hagas saludos largos. "
                   "Si tienes información de búsqueda, úsala para dar respuestas actualizadas."
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
# Rutas principales
# --------------------------

@app.route('/')
def home():
    return render_template('index.html', username=session.get('username'))

@app.route('/preguntar', methods=['POST'])
def preguntar():
    """
    Ruta principal para preguntas con búsqueda automática en Serper
    """
    data = request.json
    pregunta = data.get('pregunta')
    usar_serper = data.get('usar_serper', True)  # 🔥 POR DEFECTO BUSCA EN SERPER
    
    if not pregunta:
        return jsonify({"error": "No se recibió pregunta"}), 400

    api_key = "3afe5888cc608256a0ae579173d4fb0c7186a9d0"
    print(f"🔍 Pregunta: {pregunta}")
    print(f"🔍 Usar Serper: {usar_serper}")

    # 🔥 SIEMPRE BUSCA EN SERPER (salvo que explícitamente se diga que no)
    if usar_serper:
        print("🔍 Buscando en Serper...")
        resultados, error = buscar_serper(pregunta, api_key)
        
        if resultados:
            print("✅ Resultados encontrados en Serper")
            prompt = f"""Información actualizada de Internet:
{resultados}

Pregunta del usuario: {pregunta}

Responde usando esta información actualizada. Si la información no es suficiente, 
combínala con tu conocimiento pero prioriza la información de Internet."""
        else:
            print(f"❌ No se encontraron resultados en Serper: {error}")
            prompt = f"""No se pudo obtener información actualizada de Internet.
Pregunta: {pregunta}
Responde con tu conocimiento, pero menciona que no tienes información actualizada."""
    else:
        print("🔍 Saltando búsqueda en Serper por solicitud del usuario")
        prompt = pregunta

    # Llamar a Ollama
    response_ollama = llamar_a_ollama(prompt)
    
    return jsonify({
        "respuesta": response_ollama,
        "busqueda_realizada": usar_serper,
        "serper_usado": usar_serper and resultados is not None
    })

@app.route('/api/generar-texto', methods=['POST'])
def generar_texto():
    """
    Ruta para generar texto con archivos y búsqueda opcional
    """
    # Manejar tanto JSON como form-data
    if request.is_json:
        data = request.get_json()
        prompt = data.get('prompt', '').strip()
        usar_serper = data.get('usar_serper', True)  # 🔥 POR DEFECTO BUSCA EN SERPER
    else:
        prompt = request.form.get('prompt', '').strip()
        usar_serper = request.form.get('usar_serper', 'true').lower() == 'true'

    if not prompt:
        return jsonify({"error": "No se recibió prompt"}), 400

    file = request.files.get('file')
    api_key = "3afe5888cc608256a0ae579173d4fb0c7186a9d0"
    
    print(f"🔍 Prompt: {prompt}")
    print(f"🔍 Usar Serper: {usar_serper}")
    print(f"🔍 Archivo: {file.filename if file else 'No'}")

    # 🔥 BUSCAR EN SERPER PRIMERO
    search_info = ""
    if usar_serper:
        print("🔍 Buscando en Serper...")
        resultados, error = buscar_serper(prompt, api_key)
        if resultados:
            print("✅ Resultados encontrados en Serper")
            search_info = f"Información actualizada de Internet:\n{resultados}\n\n"
        else:
            print(f"❌ Error en Serper: {error}")

    # Procesar archivo si existe
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

    # Combinar toda la información
    combined_prompt = f"{search_info}{file_text}\n\nUsuario pregunta: {prompt}" if (search_info or file_text) else prompt

    # Llamar a Ollama
    system_message = {
        "role": "system",
        "content": "Eres un experto arquitecto y diseñador, pero también sabes sobre todos los temas del mundo. "
                   "Ayuda con preguntas técnicas y creativas sobre arquitectura y otros temas. "
                   "Habla como una persona normal, responde en el idioma en que se te habla y no hagas saludos largos. "
                   "Si tienes información actualizada de Internet, úsala para dar respuestas precisas."
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

    return jsonify({
        'respuesta': respuesta,
        'busqueda_realizada': usar_serper,
        'archivo_procesado': bool(file_text)
    })

# --------------------------
# Rutas de archivos
# --------------------------

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

# --------------------------
# Rutas de autenticación
# --------------------------

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')

    if not name or not email or not password:
        return jsonify({"error": "Todos los campos son obligatorios."}), 400
    
    if len(password) < 6:
        return jsonify({"error": "La contraseña debe tener al menos 6 caracteres."}), 400

    users = load_users()

    if any(user['email'] == email for user in users):
        return jsonify({"error": "El correo ya está registrado."}), 409

    hashed_password = hashlib.sha256(password.encode('utf-8')).hexdigest()

    new_user = {
        "name": name,
        "email": email,
        "password": hashed_password
    }
    users.append(new_user)
    save_users(users)

    session['username'] = name

    # Enviar correo de bienvenida
    msg = Message(
        "Bienvenido a Nuestra Página",
        recipients=[email]
    )
    msg.body = f"Hola {name}, gracias por registrarte!"
    msg.html = f"<h1>Hola {name}</h1><p>Gracias por registrarte en nuestra página! ¿Estás preparad@ para comenzar a aprender con nuestra IA?</p>"

    try:
        mail.send(msg)
    except Exception as e:
        print(f"Error enviando correo: {e}")

    return jsonify({"message": "Usuario registrado correctamente."}), 201

@app.route('/login', methods=['POST'])
def login():
    if request.form:
        username = request.form.get('username')
        password = request.form.get('password')
    else:
        data = request.get_json()
        username = data.get('email')
        password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Usuario/Email y contraseña son obligatorios."}), 400

    users = load_users()

    user_found = None
    for user in users:
        if user['email'] == username or user['name'] == username:
            user_found = user
            break

    if not user_found:
        return jsonify({"error": "Credenciales inválidas."}), 401

    provided_password_hashed = hashlib.sha256(password.encode('utf-8')).hexdigest()

    if user_found['password'] == provided_password_hashed:
        session['username'] = user_found['name']

        if request.form:
            return redirect('/')
        else:
            return jsonify({
                "message": "Sesión iniciada.",
                "user": {
                    "name": user_found['name'],
                    "email": user_found['email']
                }
            }), 200
    else:
        return jsonify({"error": "Credenciales inválidas."}), 401

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect('/')

# --------------------------
# Ejecutar
# --------------------------

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5050)