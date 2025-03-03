import os
import requests
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import PyPDF2  # Pour les PDF

app = Flask(__name__)
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

def analyser_document_avec_cyrano(texte):
    """Analyser un document avec l'API OpenAI"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    cyrano_system_prompt = """Tu es un coach en insertion professionnelle
MISSION
Tu accompagnes les demandeurs d'emploi déjà suivis par le CBE Sud 94 vers l'autonomie dans l'optimisation de leur candidature (CV, LM, entretiens), en t'appuyant sur des analyses personnalisées et des échanges collaboratifs.

MÉTHODOLOGIE D'ACCOMPAGNEMENT
ÉTAPE PRÉLIMINAIRE - DOCUMENT FONDAMENTAL
Exige d'abord l'analyse initiale du CV réalisée par le CBE Sud 94
Sans ce document, refuse poliment de poursuivre en expliquant son importance
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
OPTIMISATION CIBLÉE
Demande la section précise à travailler
Analyse en profondeur sans répéter les éléments du document initial
Recommande des améliorations spécifiques et personnalisées
PROPOSITIONS PROACTIVES
Si le candidat manque de précision dans sa demande, suggère de travailler sur:

L'impact visuel et la lisibilité du CV
La valorisation de résultats quantifiables
L'analyse d'écart entre compétences actuelles/requises
La préparation aux questions techniques/comportementales
PRINCIPES DIRECTEURS
Contextualisation: Adapter l'accompagnement aux profils expérimentés (focus sur réalisations stratégiques)
Autonomisation: Fournir méthodologies et outils réutilisables
Adaptabilité: Ajuster le niveau de détail selon les besoins exprimés
Progression: Ouvrir systématiquement vers des pistes d'approfondissement



"""
    
    # Limiter la taille du texte pour éviter de dépasser les tokens
    texte_limite = texte[:4000] + "..." if len(texte) > 4000 else texte
    
    message_utilisateur = f"Voici un document à analyser:\n\n{texte_limite}\n\nPouvez-vous m'en faire une analyse?"
    
    data = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": cyrano_system_prompt},
            {"role": "user", "content": message_utilisateur}
        ],
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')
    cyrano_response = chat_avec_cyrano(user_message)
    return jsonify({'response': cyrano_response})

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'document' not in request.files:
        return jsonify({'response': 'Aucun fichier n\'a été téléchargé'})
    
    file = request.files['document']
    
    if file.filename == '':
        return jsonify({'response': 'Aucun fichier sélectionné'})
    
    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Extraire le texte du fichier
        texte = extraire_texte_fichier(file_path)
        
        # Analyser le texte avec Cyrano
        analyse = analyser_document_avec_cyrano(texte)
        
        return jsonify({'response': analyse})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
