from flask import Flask, render_template, request, jsonify
import requests
import os
from dotenv import load_dotenv

# Charger variables d'environnement
load_dotenv()
API_KEY = os.getenv("ANTHROPIC_API_KEY")

app = Flask(__name__)

def chat_avec_cyrano(message_utilisateur):
    headers = {
        "x-api-key": API_KEY,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01"
    }
    
    # Définition du personnage de Cyrano
    cyrano_system_prompt = """Vous êtes Cyrano de Bergerac, poète, bretteur et cadet de Gascogne avec un nez proéminent dont vous êtes complexé.

PERSONNALITÉ:
- Extrêmement fier et susceptible, surtout concernant votre nez
- Éloquent, capable d'improviser des tirades poétiques éblouissantes
- Romantique passionné mais timide dans l'expression directe de vos sentiments amoureux
- Courageux jusqu'à la témérité, prêt à défier quiconque vous manque de respect
- Spirituel, vif d'esprit, maniant l'ironie et les jeux de mots avec brio
- Généreux et loyal en amitié, capable de sacrifice pour ceux que vous aimez

STYLE D'EXPRESSION:
- Utilisez un langage riche en métaphores et images poétiques
- Employez un vocabulaire précieux du XVIIe siècle français
- Exprimez-vous en alexandrins 
- Répondez aux provocations par des réparties cinglantes et spirituelles
- Ponctuez vos phrases d'expressions gasconnes comme 'Cadédis!' ou 'Sandious!'"""
    
    data = {
        "model": "claude-3-7-sonnet-20250219",
        "max_tokens": 1000,
        "system": cyrano_system_prompt,
        "messages": [
            {
                "role": "user",
                "content": message_utilisateur
            }
        ]
    }
    
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=data
    )
    
    if response.status_code == 200:
        return response.json()["content"][0]["text"]
    else:
        return f"Erreur: {response.status_code} - {response.text}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')
    cyrano_response = chat_avec_cyrano(user_message)
    return jsonify({'response': cyrano_response})

# Point d'entrée pour Gunicorn
if __name__ == '__main__':
    # Pour le développement local
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
