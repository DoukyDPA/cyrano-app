import os
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Récupérer la clé API directement
API_KEY = os.environ.get("OPENAI_API_KEY")

def chat_avec_cyrano(message_utilisateur):
    if not API_KEY:
        return "Erreur: Clé API non configurée"
        
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Version enrichie du prompt Cyrano
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
- Exprimez-vous en alexandrins quand vous êtes particulièrement inspiré
- Répondez aux provocations par des réparties cinglantes et spirituelles
- Ponctuez vos phrases d'expressions gasconnes comme 'Cadédis!' ou 'Sandious!'

EXTRAITS CARACTÉRISTIQUES:
- 'C'est un roc! C'est un pic! C'est un cap! Que dis-je, c'est un cap? C'est une péninsule!' (à propos de votre propre nez)
- 'Non, merci! [...] Être aimé? Non, aimer? Oui! J'aime mieux mon tourment, c'est plus pur!'"""
    
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": cyrano_system_prompt},
            {"role": "user", "content": message_utilisateur}
        ],
        "max_tokens": 800,
        "temperature": 0.7
    }
    
    # Le reste du code reste identique

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
