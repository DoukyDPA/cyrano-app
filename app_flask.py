import os
import requests
from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename
import PyPDF2
import json

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Nécessaire pour utiliser les sessions
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limite à 16MB

# Créer le dossier uploads s'il n'existe pas
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Récupérer la clé API directement depuis les variables d'environnement
API_KEY = os.environ.get("OPENAI_API_KEY")

def extraire_texte_pdf(file_path):
    """Extraire le texte d'un fichier PDF"""
    text = ""
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page_num in range(len(pdf_reader.pages)):
                page_text = pdf_reader.pages[page_num].extract_text()
                if page_text:  # Vérifier que le texte a été extrait
                    text += page_text + "\n"
                else:
                    text += "[Page sans texte extractible]\n"
    except Exception as e:
        text = f"Erreur lors de l'extraction du PDF: {str(e)}"
    return text

def extraire_texte_fichier(file_path):
    """Extraire le texte d'un fichier selon son extension"""
    extension = os.path.splitext(file_path)[1].lower()
    
    if extension == '.pdf':
        return extraire_texte_pdf(file_path)
    elif extension == '.txt':
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except UnicodeDecodeError:
            # Essayer une autre encodage si utf-8 échoue
            try:
                with open(file_path, 'r', encoding='latin-1') as file:
                    return file.read()
            except Exception as e:
                return f"Erreur lors de la lecture du fichier texte: {str(e)}"
    else:
        return "Ce type de fichier n'est pas pris en charge pour l'analyse."

def sauvegarder_analyse_dans_session(analyse, document_type):
    """Sauvegarder l'analyse dans la session"""
    if 'analyses' not in session:
        session['analyses'] = {}
    
    session['analyses'][document_type] = analyse
    session.modified = True

def verifier_dossier_initial():
    """Vérifier si le dossier initial est présent dans la session"""
    return session.get('analyses', {}).get('dossier_initial') is not None

def analyser_document_avec_ia(texte, document_type):
    """Analyser un document avec l'API OpenAI"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Adapter le prompt système selon le type de document
    if document_type == "dossier_initial":
        system_prompt = """Tu es un coach en insertion professionnelle expérimenté.
MISSION
Analyser ce dossier initial qui contient l'analyse du CV et des recommandations faites par le CBE Sud 94. 
Extraire et mémoriser les informations clés sur le candidat, ses compétences, son parcours, et les recommandations déjà formulées.
Ces informations serviront de base pour l'accompagnement futur du candidat.
"""
    elif document_type == "cv":
        system_prompt = """Tu es un coach en insertion professionnelle expérimenté.
MISSION
Analyser ce CV en te basant sur le dossier initial déjà fourni.
Comparer avec les versions précédentes si disponibles.
Évaluer les améliorations réalisées et celles restant à faire.
Noter précisément le CV (/10) avec justification détaillée.
"""
    elif document_type == "offre_emploi":
        system_prompt = """Tu es un coach en insertion professionnelle expérimenté.
MISSION
Analyser cette offre d'emploi en relation avec le profil du candidat.
Extraire les exigences-clés (compétences, qualifications, mots-clés).
Évaluer la compatibilité avec le profil du candidat.
Proposer des adaptations du CV pour cette offre spécifique.
Ébaucher les points clés d'une lettre de motivation.
Préparer aux questions probables en entretien.
"""
    else:  # document_general
        system_prompt = """Tu es un coach en insertion professionnelle expérimenté.
MISSION
Tu accompagnes les demandeurs d'emploi déjà suivis par le CBE Sud 94 vers l'autonomie dans l'optimisation de leur candidature (CV, LM, entretiens), en t'appuyant sur des analyses personnalisées et des échanges collaboratifs.

MÉTHODOLOGIE D'ACCOMPAGNEMENT
ÉTAPE PRÉLIMINAIRE - DOCUMENT FONDAMENTAL
Tu travailles sur la base du dossier initial réalisé par le CBE Sud 94.
Sans ce document, tu refuses poliment de poursuivre en expliquant son importance.

ANALYSE PROGRESSIVE DU CV
Compare systématiquement chaque nouvelle version avec:
Le CV initial et ses lacunes identifiées
Les améliorations réalisées/restantes
Évalue précisément avec une note justifiée (/10)
Formule des axes d'amélioration actionnables et concrets

ADAPTATION AUX OFFRES D'EMPLOI
Extrais les exigences-clés (compétences, qualifications, mots-clés)
Propose une personnalisation ciblée du CV mettant en valeur les correspondances
Ébauche une lettre de motivation stratégique spécifique à l'offre
Prépare aux questions probables en entretien pour cette offre

PRINCIPES DIRECTEURS
Contextualisation: Adapter l'accompagnement au profil spécifique
Autonomisation: Fournir méthodologies et outils réutilisables
Progressivité: Guider par étapes vers l'amélioration
"""
    
    # Vérifier si le dossier initial est requis
    if document_type != "dossier_initial" and not verifier_dossier_initial():
        return "Veuillez d'abord télécharger le dossier initial d'analyse réalisé par le CBE Sud 94 avant de continuer. Ce document est essentiel pour vous accompagner efficacement."
    
    # Limiter la taille du texte pour éviter de dépasser les tokens
    texte_limite = texte[:4000] + "..." if len(texte) > 4000 else texte
    
    message_utilisateur = f"Voici un document à analyser ({document_type}):\n\n{texte_limite}\n\nMerci de l'analyser selon les directives."
    
    # Ajouter les analyses précédentes au contexte si disponibles
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": message_utilisateur}]
    
    # Ajouter le contexte du dossier initial si disponible et si ce n'est pas l'analyse du dossier initial
    if document_type != "dossier_initial" and 'analyses' in session and 'dossier_initial' in session['analyses']:
        messages.insert(1, {"role": "assistant", "content": "Contexte du dossier initial: " + session['analyses']['dossier_initial']})
    
    # Ajouter le CV si disponible et si on analyse une offre d'emploi
    if document_type == "offre_emploi" and 'analyses' in session and 'cv' in session['analyses']:
        messages.insert(1, {"role": "assistant", "content": "Contexte du CV du candidat: " + session['analyses']['cv']})
    
    data = {
        "model": "gpt-4o",
        "messages": messages,
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            analyse = response.json()["choices"][0]["message"]["content"]
            # Sauvegarder l'analyse dans la session
            sauvegarder_analyse_dans_session(analyse, document_type)
            return analyse
        else:
            return f"Erreur API: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Exception: {str(e)}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')
    
    # Vérifier si le dossier initial est présent
    if not verifier_dossier_initial():
        return jsonify({'response': "Veuillez d'abord télécharger le dossier initial d'analyse réalisé par le CBE Sud 94 avant de continuer. Ce document est essentiel pour vous accompagner efficacement."})
    
    ia_response = chat_avec_ia(user_message)
    return jsonify({'response': ia_response})

def chat_avec_ia(message):
    """Fonction pour discuter avec le coach IA"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = """Tu es un coach en insertion professionnelle expérimenté.
MISSION
Tu accompagnes les demandeurs d'emploi sur la base du dossier initial réalisé par le CBE Sud 94.
Tu aides à optimiser les candidatures (CV, lettres de motivation, préparation aux entretiens).
Tu t'appuies sur les analyses précédentes pour offrir un accompagnement personnalisé et progressif.

APPROCHE
- Adapter tes conseils au profil spécifique du candidat
- Fournir des retours constructifs et actionnables
- Aider à faire le lien entre le profil du candidat et les offres d'emploi
- Encourager l'autonomie tout en apportant un soutien expert

IMPORTANT
Tu n'as accès qu'aux documents qui ont été téléchargés. Si le candidat mentionne un document que tu n'as pas vu, demande-lui de le télécharger.
"""
    
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": message}]
    
    # Ajouter le contexte des analyses précédentes
    if 'analyses' in session:
        context = "Contexte des analyses précédentes:\n"
        for doc_type, analyse in session['analyses'].items():
            # Limiter la taille pour éviter de dépasser les tokens
            resume = analyse[:500] + "..." if len(analyse) > 500 else analyse
            context += f"\n--- {doc_type} ---\n{resume}\n"
        
        messages.insert(1, {"role": "assistant", "content": context})
    
    data = {
        "model": "gpt-4o",
        "messages": messages,
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"Erreur API: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Exception: {str(e)}"

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'document' not in request.files:
        return jsonify({'response': 'Aucun fichier n\'a été téléchargé'})
    
    file = request.files['document']
    document_type = request.form.get('document_type', 'document_general')
    
    if file.filename == '':
        return jsonify({'response': 'Aucun fichier sélectionné'})
    
    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Extraire le texte du fichier
        texte = extraire_texte_fichier(file_path)
        
        # Analyser le texte avec l'IA
        analyse = analyser_document_avec_ia(texte, document_type)
        
        return jsonify({'response': analyse})

@app.route('/session_status', methods=['GET'])
def session_status():
    """Retourner le statut des documents téléchargés"""
    status = {
        'dossier_initial': 'analyses' in session and 'dossier_initial' in session['analyses'],
        'cv': 'analyses' in session and 'cv' in session['analyses'],
        'offre_emploi': 'analyses' in session and 'offre_emploi' in session['analyses']
    }
    return jsonify(status)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
