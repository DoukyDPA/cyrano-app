import os
import sys
import requests
import logging
import PyPDF2
import re

from flask import Flask, render_template, request, jsonify, session
from flask.sessions import SecureCookieSessionInterface
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
#                           Configuration FLASK + Session
# ---------------------------------------------------------------------------
class CustomSessionInterface(SecureCookieSessionInterface):
    """
    Permet de configurer la cookie de session avec samesite='None' et secure,
    afin de la rendre compatible avec des déploiements cross-domain (Render, etc.).
    """
    def save_session(self, app, session, response):
        domain = self.get_cookie_domain(app)
        path = self.get_cookie_path(app)
        
        iif not session:
            if session.modified:
                cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
                response.delete_cookie(cookie_name, domain=domain, path=path)
            return
        
        httponly = self.get_cookie_httponly(app)
        secure = self.get_cookie_secure(app)
        expires = self.get_expiration_time(app, session)
        val = self.get_signing_serializer(app).dumps(dict(session))
        response.set_cookie(app.session_cookie_name, val,
                            expires=expires, httponly=httponly,
                            domain=domain, path=path, secure=secure, samesite='None')

# Initialisation de l’application Flask
app = Flask(__name__)
app.session_interface = CustomSessionInterface()

# Clé secrète pour la session (à adapter en production)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "secret_key_dev")

# Configuration d’un dossier où stocker les fichiers uploadés
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limite 16 MB

# Configuration des logs
if os.environ.get('FLASK_ENV') == 'production':
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
else:
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    )

# Récupération de la clé OpenAI (doit être configurée en variable d’env)
API_KEY = os.environ.get("OPENAI_API_KEY")

# ---------------------------------------------------------------------------
#                     Fonctions utilitaires d’extraction
# ---------------------------------------------------------------------------

def extraire_texte_pdf(file_path):
    """
    Extrait le texte d’un fichier PDF en essayant plusieurs méthodes.
    """
    app.logger.info(f"Extraction du texte du PDF: {file_path}")
    texte = ""
    try:
        with open(file_path, 'rb') as file:
            try:
                pdf_reader = PyPDF2.PdfReader(file)
                app.logger.info(f"PDF ouvert, {len(pdf_reader.pages)} pages détectées.")
                for page_num in range(len(pdf_reader.pages)):
                    try:
                        page = pdf_reader.pages[page_num]
                        page_text = page.extract_text()
                        if page_text:
                            texte += page_text + "\n"
                        else:
                            texte += f"[Page {page_num+1} sans texte]\n"
                    except Exception as e:
                        app.logger.error(f"Erreur extraction page {page_num+1}: {str(e)}")
                        texte += f"[Erreur page {page_num+1}: {str(e)}]\n"
                
                if not texte.strip():
                    # Possiblement un document scanné
                    texte = "Aucun texte n’a pu être extrait : document scanné ou protégé."
            
            except Exception as pdf_e:
                app.logger.error(f"Erreur lors de l’ouverture du PDF: {pdf_e}")
                texte = f"Erreur lors de l’ouverture du PDF: {pdf_e}"
                # Tentative d’approche alternative (brute) :
                file.seek(0)
                raw_content = file.read()
                # Chercher des chaînes de texte
                text_matches = re.findall(b'(\([\w\d\s,.;:!?-]+\))', raw_content)
                if text_matches:
                    extracted = []
                    for match in text_matches:
                        try:
                            decoded = match.decode('utf-8', errors='replace').strip('()')
                            if len(decoded) > 3:
                                extracted.append(decoded)
                        except:
                            pass
                    if extracted:
                        texte = "Extraction partielle brute:\n" + "\n".join(extracted)
                    else:
                        texte = "Aucun texte extractible trouvé (approche brute)."
    except Exception as e:
        texte = f"Erreur lecture PDF: {str(e)}"
    return texte

def extraire_texte_fichier(file_path):
    """
    Extrait le texte d’un fichier PDF ou TXT (retourne une chaîne).
    """
    if not os.path.exists(file_path):
        return f"Erreur: Le fichier {file_path} n’existe pas."
    
    extension = os.path.splitext(file_path)[1].lower()
    
    if extension == ".pdf":
        return extraire_texte_pdf(file_path)
    elif extension == ".txt":
        # Essayer d’ouvrir en plusieurs encodages
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    return f.read()
            except:
                pass
        # Dernière approche : lecture binaire + decode
        with open(file_path, 'rb') as f:
            raw = f.read()
        for enc in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
            try:
                return raw.decode(enc, errors='replace')
            except:
                continue
        return raw.decode('utf-8', errors='replace')
    else:
        return f"Ce format {extension} n’est pas supporté (PDF ou TXT uniquement)."

# ---------------------------------------------------------------------------
#                         Fonction de Chat unifiée
# ---------------------------------------------------------------------------
def chat_avec_ia(message_user):
    """
    Gère l’envoi d’un message à l’IA en conservant l’historique dans la session.
    Si message_user est vide, on considère qu’on a déjà ajouté
    un nouveau message 'user' dans l’historique (par exemple après upload).
    """
    if not API_KEY:
        return "Erreur: Clé API OpenAI non configurée."

    if 'chat_history' not in session:
        session['chat_history'] = []
    
    # Si un nouveau message utilisateur est fourni, on l’ajoute dans l’historique
    if message_user.strip():
        session['chat_history'].append({'role': 'user', 'content': message_user})
        session.modified = True

    # Prompt système
    system_prompt = (
        "Tu es un coach en insertion professionnelle expérimenté qui aide les demandeurs d’emploi. "
        "Analyse et réponds en te fondant sur l’historique (CV, dossier, offres, questions...). "
        "Ne fais pas de phrases creuses d’introduction ni de conclusion. "
        "Ne jamais employer le mot 'crucial'."
    )

    # Construction du message pour l’API
    messages_for_api = [{'role': 'system', 'content': system_prompt}]
    
    # On ajoute l’historique
    for hist_msg in session['chat_history']:
        messages_for_api.append(hist_msg)
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "gpt-4o",      # Adaptable (gpt-3.5-turbo, etc.)
        "messages": messages_for_api,
        "max_tokens": 1000
    }
    
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions",
                                 headers=headers, json=data, timeout=60)
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            # On ajoute la réponse dans l’historique
            session['chat_history'].append({"role": "assistant", "content": content})
            session.modified = True
            return content
        else:
            return f"Erreur API: {response.status_code} - {response.text[:300]}"
    except Exception as e:
        return f"Erreur durant l’appel API: {str(e)}"

# ---------------------------------------------------------------------------
#                             Routes Flask
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    """
    Page principale (HTML). Vous pouvez simplement rendre un template,
    ou renvoyer un petit message si vous n’avez pas de front spécial.
    """
    return render_template('index.html')  # Ou un simple "return 'Hello'"

@app.route('/debug', methods=['GET'])
def debug_info():
    """
    Endpoint pour debug : inspecter l’état de la session, etc.
    """
    debug_data = {
        'session_id': session.get('_id', 'non défini'),
        'chat_history_length': len(session.get('chat_history', [])),
        'api_key_ok': bool(API_KEY),
        'upload_folder': os.path.abspath(app.config['UPLOAD_FOLDER']),
        'uploaded_files': os.listdir(app.config['UPLOAD_FOLDER']),
    }
    return jsonify(debug_data)

@app.route('/session_status', methods=['GET'])
def session_status():
    """
    Par souci de compatibilité avec votre front existant,
    renvoie quelques infos (par ex. si on a déjà démarré la conversation ou pas).
    """
    has_history = 'chat_history' in session and len(session['chat_history']) > 0
    return jsonify({
        'session_active': has_history,
        'session_id': session.get('_id', 'none'),
    })

@app.route('/upload', methods=['POST'])
def upload_file():
    """
    Nouvelle approche : on n’appelle pas d’analyse séparée.
    On stocke le texte dans l’historique sous forme de message 'user',
    puis on appelle la même fonction de chat_avec_ia pour avoir la réponse IA.
    """
    try:
        if 'document' not in request.files:
            return jsonify({'response': "Aucun fichier téléchargé", 'success': False})
        
        file = request.files['document']
        document_type = request.form.get('document_type', 'document_general')

        if file.filename == '':
            return jsonify({'response': "Aucun fichier sélectionné", 'success': False})
        
        # Enregistrement du fichier
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file_content = file.read()
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        # Extraction du texte
        texte = extraire_texte_fichier(file_path)
        if not texte or texte.startswith("Erreur"):
            return jsonify({'response': texte, 'success': False})
        
        # Tronquer si trop long
        max_len = 3000
        texte_tronque = texte[:max_len]
        if len(texte) > max_len:
            texte_tronque += "\n[Document tronqué, trop volumineux…]"

        # Ajouter un message utilisateur dans l’historique
        if 'chat_history' not in session:
            session['chat_history'] = []
        
        session['chat_history'].append({
            'role': 'user',
            'content': (
                f"Je viens de télécharger un document de type {document_type}. "
                f"Voici son contenu:\n\n{texte_tronque}\n\n"
                "Peux-tu l’analyser ?"
            )
        })
        session.modified = True
        
        # Appeler la fonction de chat pour générer la réponse sur-le-champ
        reponse_ia = chat_avec_ia("")
        
        return jsonify({'response': reponse_ia, 'success': True})
    
    except Exception as e:
        return jsonify({'response': f"Erreur inattendue: {e}", 'success': False})

@app.route('/chat', methods=['POST'])
def chat():
    """
    Quand l’utilisateur envoie un message (simple texte).
    On appelle chat_avec_ia(message).
    """
    data = request.json or {}
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({'response': "Aucun message reçu."})
    
    # Appel à la fonction d’IA
    reponse_ia = chat_avec_ia(user_message)
    return jsonify({'response': reponse_ia})

@app.route('/test_api', methods=['GET'])
def test_api():
    """
    Permet de tester rapidement si la clé API est valide et si l’API OpenAI répond.
    """
    if not API_KEY:
        return jsonify({
            "success": False,
            "message": "Clé API absente ou invalide",
        })
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    test_messages = [
        {"role": "system", "content": "Tu es un assistant minimaliste."},
        {"role": "user", "content": "Réponds : 'La connexion à l’API fonctionne'."}
    ]
    data = {
        "model": "gpt-4o",
        "messages": test_messages,
        "max_tokens": 50
    }
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions",
                                 headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            return jsonify({
                "success": True,
                "message": "API OpenAI accessible",
                "response": content
            })
        else:
            return jsonify({
                "success": False,
                "message": f"Échec: {response.status_code}",
                "response": response.text
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Exception: {e}"
        })

# ---------------------------------------------------------------------------
#                         Lancement de l’application
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
