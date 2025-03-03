# Configuration de session pour Render.com
from flask.sessions import SecureCookieSessionInterface

class CustomSessionInterface(SecureCookieSessionInterface):
    def save_session(self, app, session, response):
        domain = self.get_cookie_domain(app)
        path = self.get_cookie_path(app)
        
        # On définit le nom du cookie ici,
        # en récupérant la config SESSION_COOKIE_NAME si elle existe,
        # sinon on utilise "session".
        cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")

        if not session:
            if session.modified:
                response.delete_cookie(cookie_name, domain=domain, path=path)
            return
            
        httponly = self.get_cookie_httponly(app)
        secure = self.get_cookie_secure(app)
        expires = self.get_expiration_time(app, session)
        val = self.get_signing_serializer(app).dumps(dict(session))

        response.set_cookie(
            cookie_name,
            val,
            expires=expires,
            httponly=httponly,
            domain=domain,
            path=path,
            secure=secure,
            samesite='None'
        )

# On applique notre session custom à l'application Flask
import os
import requests
import logging
from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename
import PyPDF2
import json
import sys

app = Flask(__name__)
app.session_interface = CustomSessionInterface()  # SessionInterface personnalisé

# Créer le dossier uploads s'il n'existe pas
upload_folder = 'uploads'
if not os.path.exists(upload_folder):
    os.makedirs(upload_folder)

# Initialiser l'application Flask
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "default_secret_key_for_dev")  # Clé fixe pour les sessions

# Configuration
app.config['UPLOAD_FOLDER'] = upload_folder
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limite à 16MB
# (Optionnel) Si tu veux explicitement définir le nom du cookie
# app.config['SESSION_COOKIE_NAME'] = "session"

# Configuration des logs
if os.environ.get('FLASK_ENV') == 'production':
    # En production, écrire les logs dans la sortie standard
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
else:
    # En développement, configurer les logs plus détaillés
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    )

# Récupérer la clé API directement depuis les variables d'environnement
API_KEY = os.environ.get("OPENAI_API_KEY")

def extraire_texte_pdf(file_path):
    """Extraire le texte d'un fichier PDF"""
    app.logger.info(f"Extraction du texte du fichier PDF: {file_path}")
    text = ""
    try:
        with open(file_path, 'rb') as file:
            try:
                pdf_reader = PyPDF2.PdfReader(file)
                app.logger.info(f"PDF ouvert, nombre de pages: {len(pdf_reader.pages)}")
                
                for page_num in range(len(pdf_reader.pages)):
                    try:
                        page = pdf_reader.pages[page_num]
                        page_text = page.extract_text()
                        
                        if page_text:  # Vérifier que le texte a été extrait
                            text += page_text + "\n"
                            app.logger.info(f"Page {page_num+1}: {len(page_text)} caractères extraits")
                        else:
                            text += f"[Page {page_num+1} sans texte extractible]\n"
                            app.logger.warning(f"Page {page_num+1}: Pas de texte extractible")
                    except Exception as page_e:
                        app.logger.error(f"Erreur lors de l'extraction de la page {page_num+1}: {str(page_e)}")
                        text += f"[Erreur page {page_num+1}: {str(page_e)}]\n"
                
                # Vérifier si du texte a été extrait
                if not text.strip():
                    app.logger.warning("Aucun texte extrait du PDF, possible document scanné ou protégé")
                    text = "Aucun texte n'a pu être extrait de ce PDF. Il s'agit peut-être d'un document scanné ou protégé."
                else:
                    app.logger.info(f"Extraction réussie, {len(text)} caractères au total")
            except Exception as pdf_e:
                app.logger.error(f"Erreur lors de l'ouverture du PDF: {str(pdf_e)}")
                text = f"Erreur lors de l'ouverture du PDF: {str(pdf_e)}"
                
                # Tenter une approche alternative
                app.logger.info("Tentative d'extraction alternative du PDF")
                try:
                    # Réouvrir le fichier et lire le contenu brut
                    file.seek(0)
                    raw_content = file.read()
                    
                    # Rechercher du texte dans le contenu brut
                    try:
                        # Extraction basique de chaînes de caractères du PDF
                        import re
                        text_matches = re.findall(b'(\([\w\d\s,.;:!?-]+\))', raw_content)
                        if text_matches:
                            extracted = []
                            for match in text_matches:
                                try:
                                    # Essayer de décoder la chaîne PDF
                                    decoded = match.decode('utf-8', errors='replace').strip('()')
                                    if len(decoded) > 3:  # Ignorer les très courtes chaînes
                                        extracted.append(decoded)
                                except:
                                    pass
                            
                            if extracted:
                                text = "Extraction alternative - contenu partiel:\n\n" + "\n".join(extracted)
                                app.logger.info(f"Extraction alternative réussie, {len(extracted)} fragments")
                            else:
                                text = "Aucun texte extractible trouvé dans ce PDF."
                        else:
                            text = "Aucun texte extractible trouvé dans ce PDF."
                    except Exception as ex_e:
                        app.logger.error(f"Échec de l'extraction alternative: {str(ex_e)}")
                        text = f"Erreur lors de l'extraction du PDF: {str(pdf_e)}"
                except Exception as alt_e:
                    app.logger.error(f"Échec complet de l'extraction PDF: {str(alt_e)}")
                    text = f"Erreur lors de l'extraction du PDF: {str(pdf_e)}"
    except Exception as e:
        app.logger.error(f"Erreur lors de l'accès au fichier PDF: {str(e)}")
        text = f"Erreur lors de l'accès au fichier PDF: {str(e)}"
    
    return text

def extraire_texte_fichier(file_path):
    """Extraire le texte d'un fichier selon son extension"""
    app.logger.info(f"Extraction du texte du fichier: {file_path}")
    
    # Vérifier que le fichier existe
    if not os.path.exists(file_path):
        app.logger.error(f"Le fichier n'existe pas: {file_path}")
        return f"Erreur: Le fichier {file_path} n'existe pas."
    
    # Vérifier que le fichier a une taille
    file_size = os.path.getsize(file_path)
    app.logger.info(f"Taille du fichier: {file_size} octets")
    if file_size == 0:
        app.logger.error(f"Le fichier est vide: {file_path}")
        return "Erreur: Le fichier téléchargé est vide."
    
    extension = os.path.splitext(file_path)[1].lower()
    app.logger.info(f"Extension du fichier: {extension}")
    
    if extension == '.pdf':
        return extraire_texte_pdf(file_path)
    elif extension == '.txt':
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                app.logger.info(f"Fichier texte lu avec utf-8, {len(content)} caractères")
                return content
        except UnicodeDecodeError:
            # Essayer une autre encodage si utf-8 échoue
            try:
                with open(file_path, 'r', encoding='latin-1') as file:
                    content = file.read()
                    app.logger.info(f"Fichier texte lu avec latin-1, {len(content)} caractères")
                    return content
            except Exception as e:
                app.logger.error(f"Erreur lors de la lecture du fichier texte avec latin-1: {str(e)}")
                # Dernière tentative: lecture en binaire
                try:
                    with open(file_path, 'rb') as file:
                        binary_content = file.read()
                        # Tentative de décodage avec différents encodages
                        for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                            try:
                                content = binary_content.decode(encoding, errors='replace')
                                app.logger.info(f"Fichier texte décodé avec {encoding}, {len(content)} caractères")
                                return content
                            except:
                                continue
                        
                        # Si aucun encodage ne fonctionne, retourner du texte remplacé
                        content = binary_content.decode('utf-8', errors='replace')
                        app.logger.warning(f"Décodage de secours utilisé, {len(content)} caractères")
                        return content
                except Exception as inner_e:
                    app.logger.error(f"Échec complet de lecture du fichier: {str(inner_e)}")
                    return f"Erreur lors de la lecture du fichier texte: {str(e)}"
        except Exception as e:
            app.logger.error(f"Erreur lors de la lecture du fichier texte: {str(e)}")
            return f"Erreur lors de la lecture du fichier texte: {str(e)}"
    else:
        app.logger.warning(f"Type de fichier non pris en charge: {extension}")
        return f"Ce type de fichier ({extension}) n'est pas pris en charge pour l'analyse. Veuillez utiliser un fichier .txt ou .pdf."

def sauvegarder_analyse_dans_session(analyse, document_type):
    """Sauvegarder l'analyse dans la session avec plus de logs"""
    app.logger.info(f"Tentative de sauvegarde de l'analyse de type {document_type} dans la session")
    
    if 'analyses' not in session:
        app.logger.info("Initialisation du dictionnaire analyses dans la session")
        session['analyses'] = {}
    
    session['analyses'][document_type] = analyse
    session.modified = True
    
    app.logger.info(f"Analyse de type {document_type} sauvegardée dans la session ({len(analyse)} caractères)")
    app.logger.info(f"Types de documents dans la session: {list(session['analyses'].keys())}")

def verifier_dossier_initial():
    """Vérifier si le dossier initial est présent dans la session"""
    return session.get('analyses', {}).get('dossier_initial') is not None

def analyser_document_avec_ia(texte, document_type):
    """Analyser un document avec l'API OpenAI"""
    app.logger.info(f"Début d'analyse de document type: {document_type}")
    
    if not texte or len(texte.strip()) < 5:
        app.logger.error("Texte vide ou trop court")
        return "Le texte extrait du document est vide ou trop court pour être analysé. Veuillez vérifier le fichier."
    
    app.logger.info(f"Longueur du texte à analyser: {len(texte)} caractères")
    app.logger.info(f"Début du texte: {texte[:100]}...")
    
    if not API_KEY:
        app.logger.error("Clé API OpenAI non configurée")
        return "Erreur: La clé API OpenAI n'est pas configurée. Veuillez contacter l'administrateur."
    
    if document_type == "dossier_initial":
        system_prompt = """Tu es un coach en insertion professionnelle expérimenté.
MISSION: Analyse pour ton information ce dossier initial qui contient l'analyse du CV et des recommandations. Il va te servir à conseiller le demandeur d'emploi. 
FORMAT: Utilise le formatage markdown pour rendre ta réponse lisible:
- Utilise # pour les titres principaux
- Utilise ## pour les sous-titres
- Utilise des listes à puces avec -
- Mets les points importants en **gras**
- Sépare bien les sections avec des sauts de ligne
"""
    elif document_type == "cv":
        system_prompt = """Tu es un coach en insertion professionnelle expérimenté.
MISSION: Analyser ce CV et fournir des conseils d'amélioration dans la continuité de l'analyse du dossier initial. Tu referas une analyse équivalente à celle contenue dans le dossier avec une note sur 10 et des pistes d'amélioration
FORMAT: Utilise le formatage markdown pour rendre ta réponse lisible:
- Utilise # pour les titres principaux
- Utilise ## pour les sous-titres
- Utilise des listes à puces avec -
- Mets les points importants en **gras**
- Sépare bien les sections avec des sauts de ligne
"""
    elif document_type == "offre_emploi":
        system_prompt = """Tu es un coach en insertion professionnelle expérimenté.
MISSION: Analyser cette offre d'emploi et fournir des conseils pour y postuler en fonction des éléments contenus dans le dossier et du CV. Si tu n'as pas de nouveau CV demande le.
FORMAT: Utilise le formatage markdown pour rendre ta réponse lisible:
- Utilise # pour les titres principaux
- Utilise ## pour les sous-titres
- Utilise des listes à puces avec -
- Mets les points importants en **gras**
- Sépare bien les sections avec des sauts de ligne
"""
    else:
        system_prompt = """Tu es un coach en insertion professionnelle expérimenté.
MISSION: Analyser ce document et fournir des conseils utiles.
FORMAT: Utilise le formatage markdown pour rendre ta réponse lisible:
- Utilise # pour les titres principaux
- Utilise ## pour les sous-titres
- Utilise des listes à puces avec -
- Mets les points importants en **gras**
- Sépare bien les sections avec des sauts de ligne
"""
    
    texte_limite = texte[:8000] + "..." if len(texte) > 8000 else texte
    message_utilisateur = f"Voici un document à analyser ({document_type}):\n\n{texte_limite}\n\nMerci de l'analyser et de fournir des conseils pertinents."
    
    messages = [{"role": "system", "content": system_prompt}]
    
    if document_type == "offre_emploi" and 'analyses' in session and 'cv' in session['analyses']:
        cv_context = session['analyses']['cv'][:1000] + "..." if len(session['analyses']['cv']) > 1000 else session['analyses']['cv']
        messages.append({"role": "assistant", "content": f"Contexte du CV du candidat: {cv_context}"})
    
    messages.append({"role": "user", "content": message_utilisateur})
    
    app.logger.info(f"Envoi de {len(messages)} messages à l'API")
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "gpt-4o",
        "messages": messages,
        "max_tokens": 1000
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=45
        )
        
        app.logger.info(f"Réponse reçue, statut HTTP: {response.status_code}")
        
        if response.status_code == 200:
            try:
                analyse = response.json()["choices"][0]["message"]["content"]
                app.logger.info(f"Analyse reçue, longueur: {len(analyse)} caractères")
                
                sauvegarder_analyse_dans_session(analyse, document_type)
                return analyse
            except Exception as parse_error:
                app.logger.error(f"Erreur lors du parsing de la réponse: {str(parse_error)}")
                return f"Erreur lors du traitement de la réponse API: {str(parse_error)}"
        else:
            error_text = response.text[:500] if response.text else "Pas de détails disponibles"
            app.logger.error(f"Erreur API: {response.status_code} - {error_text}")
            return f"Erreur API ({response.status_code}): {error_text}"
    except Exception as e:
        app.logger.error(f"Exception lors de l'appel API: {str(e)}")
        return f"Erreur lors de la communication avec l'API: {str(e)}"

def chat_avec_ia(message):
    """
    Cette fonction unifie la conversation.
    Si c'est le premier message de la session, on inclut automatiquement
    le texte de l'offre (s'il existe) dans la conversation,
    au même titre que le dossier initial ou le CV.
    """

    # Vérifie et initialise l'historique
    if 'chat_history' not in session:
        session['chat_history'] = []
        session.modified = True

    # Detecte si on est au tout premier message
    is_first_message = (len(session['chat_history']) == 0)

    # Prompt système (informations de base pour l'IA)
    system_prompt = (
        "Tu es un coach en insertion professionnelle expérimenté qui aide les demandeurs d'emploi. "
        "Analyse tous les documents disponibles (dossier, CV, offre) et réponds de façon concrète. "
        "Ne fais pas de phrases d'introduction ou conclusion creuses, "
        "et n'utilise jamais le mot 'crucial'. "
        "Utilise la syntaxe markdown pour mettre en forme."
    )

    # On commence la liste de messages destinés à OpenAI
    messages = [
        {"role": "system", "content": system_prompt}
    ]

    # -----------------------------------------------------------------------
    # ÉTAPE A) SI C'EST LE TOUT PREMIER MESSAGE : ON INSÈRE DIRECTEMENT L'OFFRE
    # -----------------------------------------------------------------------
    if is_first_message:
        # 1) On informe l'IA (sous forme d'un message "user") des documents disponibles :
        doc_list = []
        if 'analyses' in session:
            if 'dossier_initial' in session['analyses']:
                doc_list.append("Dossier initial")
            if 'cv' in session['analyses']:
                doc_list.append("CV")
            if 'offre_emploi' in session['analyses']:
                doc_list.append("Offre d'emploi")

        if doc_list:
            summary_message = "Documents déjà disponibles :\n\n" + "\n".join(f"- {doc}" for doc in doc_list)
        else:
            summary_message = "Aucun document en session..."

        # On ajoute ce message à la conversation
        messages.append({"role": "user", "content": summary_message})

        # 2) SI une offre d’emploi est disponible, on donne tout de suite son contenu.
        if 'analyses' in session and 'offre_emploi' in session['analyses']:
            # on tronque un peu pour éviter d'envoyer 20 pages
            offer_text = session['analyses']['offre_emploi'][:2000]
            if len(session['analyses']['offre_emploi']) > 2000:
                offer_text += "\n[...Document tronqué pour respecter la limite de tokens...]"

            # On ajoute ce texte comme un message "assistant"
            messages.append({
                "role": "assistant",
                "content": (
                    f"Voici le texte de l'offre d'emploi :\n\n{offer_text}\n\n"
                    "J'en tiendrai compte pour mes réponses."
                )
            })

        # 3) Pour terminer, on fait un message "assistant" d'ouverture
        messages.append({
            "role": "assistant",
            "content": "Quels sont vos besoins ou vos questions ?"
        })

    # -----------------------------------------------------------------------
    # ÉTAPE B) ON RECONSTRUIT LE CONTEXTE : ON AJOUTE L'HISTORIQUE PRÉCÉDENT
    # -----------------------------------------------------------------------
    # Pour éviter un trop long prompt, on ne récupère que les 8 derniers échanges
    for old_msg in session['chat_history'][-8:]:
        messages.append(old_msg)

    # -----------------------------------------------------------------------
    # ÉTAPE C) ON AJOUTE LE NOUVEAU MESSAGE UTILISATEUR (SI NON-VIDE)
    # -----------------------------------------------------------------------
    message = message.strip()
    if message:
        messages.append({"role": "user", "content": message})

    # -----------------------------------------------------------------------
    # ÉTAPE D) APPEL À L'API OpenAI
    # -----------------------------------------------------------------------
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "gpt-4o",  # ou 'gpt-3.5-turbo', etc.
        "messages": messages,
        "max_tokens": 1200,
        "temperature": 0.7
    }

    try:
        import requests
        response = requests.post("https://api.openai.com/v1/chat/completions",
                                 headers=headers, json=data, timeout=60)
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            # On stocke la question et la réponse dans l'historique
            if message:
                session['chat_history'].append({"role": "user", "content": message})
            session['chat_history'].append({"role": "assistant", "content": content})
            session.modified = True
            return content
        else:
            return f"Erreur API OpenAI: {response.status_code}\n\n{response.text[:500]}"

    except requests.exceptions.Timeout:
        return "Timeout: le serveur met trop de temps à répondre."
    except Exception as e:
        return f"Erreur durant l'appel OpenAI: {str(e)}"


# Définition des routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/debug', methods=['GET'])
def debug_info():
    """Endpoint de débogage pour vérifier l'état de l'application"""
    debug_data = {
        'session_active': bool(session),
        'session_id': session.get('_id', 'non défini'),
        'analyses_present': 'analyses' in session,
        'api_key_configured': bool(API_KEY),
        'upload_folder_exists': os.path.exists(app.config['UPLOAD_FOLDER']),
        'uploaded_files': os.listdir(app.config['UPLOAD_FOLDER']) if os.path.exists(app.config['UPLOAD_FOLDER']) else [],
        'environment': {k: v for k, v in os.environ.items() if not k.startswith('OPENAI') and not k.startswith('FLASK_SECRET')}
    }
    return jsonify(debug_data)

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')
    
    if not verifier_dossier_initial():
        return jsonify({'response': "Veuillez d'abord télécharger le dossier initial d'analyse réalisé par le CBE Sud 94 avant de continuer. Ce document est essentiel pour vous accompagner efficacement."})
    
    ia_response = chat_avec_ia(user_message)
    return jsonify({'response': ia_response})

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        app.logger.info("Début de la requête de téléchargement")
        
        if 'document' not in request.files:
            app.logger.warning("Aucun fichier dans la requête")
            return jsonify({'response': 'Aucun fichier n\'a été téléchargé', 'success': False})
        
        file = request.files['document']
        document_type = request.form.get('document_type', 'document_general')
        app.logger.info(f"Type de document: {document_type}")
        
        if file.filename == '':
            app.logger.warning("Nom de fichier vide")
            return jsonify({'response': 'Aucun fichier sélectionné', 'success': False})
        
        if file:
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
                app.logger.info(f"Dossier {app.config['UPLOAD_FOLDER']} créé")
            
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            app.logger.info(f"Sauvegarde du fichier: {file_path}")
            
            try:
                file_content = file.read()
                with open(file_path, 'wb') as f:
                    f.write(file_content)
                
                app.logger.info(f"Fichier sauvegardé avec succès, taille: {len(file_content)} octets")
                
                if not os.path.exists(file_path):
                    app.logger.error(f"Le fichier {file_path} n'a pas été créé correctement")
                    return jsonify({'response': 'Erreur lors de la sauvegarde du fichier', 'success': False})
                
                # Extraction du texte
                app.logger.info("Extraction du texte du fichier")
                texte = extraire_texte_fichier(file_path)
                
                if not texte or texte.startswith("Erreur lors de"):
                    app.logger.warning(f"Problème d'extraction du texte: {texte}")
                    return jsonify({'response': texte or 'Erreur lors de l\'extraction du texte', 'success': False})
                
                # Analyser le texte avec l'IA
                app.logger.info(f"Analyse du texte avec l'IA, longueur: {len(texte)} caractères")
                analyse = analyser_document_avec_ia(texte, document_type)
                
                if not analyse or analyse.startswith("Erreur") or analyse.startswith("Exception"):
                    app.logger.warning(f"Problème d'analyse: {analyse}")
                    return jsonify({'response': analyse or 'Erreur lors de l\'analyse', 'success': False})
                
                # Si tout s'est bien passé, retourner la réponse
                app.logger.info("Téléchargement et analyse réussis")
                return jsonify({'response': analyse, 'success': True})
                
            except Exception as e:
                app.logger.error(f"Exception lors de la sauvegarde du fichier: {str(e)}")
                return jsonify({'response': f'Erreur lors de la sauvegarde du fichier: {str(e)}', 'success': False})
        
        return jsonify({'response': 'Erreur inconnue lors du téléchargement', 'success': False})
        
    except Exception as e:
        app.logger.error(f"Exception non gérée: {str(e)}")
        return jsonify({'response': f'Erreur inattendue: {str(e)}', 'success': False})

@app.route('/session_status', methods=['GET'])
def session_status():
    """Retourner le statut des documents téléchargés"""
    status = {
        'dossier_initial': 'analyses' in session and 'dossier_initial' in session['analyses'],
        'cv': 'analyses' in session and 'cv' in session['analyses'],
        'offre_emploi': 'analyses' in session and 'offre_emploi' in session['analyses'],
        'session_id': session.get('_id', 'non défini'),
        'session_contents': {k: bool(v) for k, v in session.items()}
    }
    return jsonify(status)

@app.route('/test_api', methods=['GET'])
def test_api():
    """Endpoint pour tester la connexion à l'API OpenAI"""
    try:
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "Tu es un assistant."},
                {"role": "user", "content": "Dis simplement 'La connexion à l'API fonctionne correctement.'"}
            ],
            "max_tokens": 50
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=10
        )
        
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            return jsonify({
                "success": True,
                "message": "API OpenAI accessible",
                "response": content,
                "api_key_present": bool(API_KEY),
                "api_key_preview": f"{API_KEY[:4]}...{API_KEY[-4:]}" if API_KEY and len(API_KEY) > 8 else "N/A"
            })
        else:
            return jsonify({
                "success": False,
                "message": f"Erreur API: {response.status_code}",
                "response": response.text,
                "api_key_present": bool(API_KEY),
                "api_key_preview": f"{API_KEY[:4]}...{API_KEY[-4:]}" if API_KEY and len(API_KEY) > 8 else "N/A"
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Erreur lors du test API: {str(e)}",
            "api_key_present": bool(API_KEY),
            "api_key_preview": f"{API_KEY[:4]}...{API_KEY[-4:]}" if API_KEY and len(API_KEY) > 8 else "N/A"
        })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
