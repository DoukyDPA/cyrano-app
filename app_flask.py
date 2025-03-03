import os
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Récupérer la clé API directement depuis les variables d'environnement
API_KEY = os.environ.get("OPENAI_API_KEY")

def chat_avec_cyrano(message_utilisateur):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    cyrano_system_prompt = """Vous êtes Cyrano de Bergerac, poète du XVIIe siècle, bretteur et cadet de Gascogne. Vous avez un nez proéminent dont vous êtes complexé. Vous êtes éloquent, fier, et répondez avec un style poétique riche en métaphores, parfois en alexandrins."""
    
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": cyrano_system_prompt},
            {"role": "user", "content": message_utilisateur}
        ],
        "max_tokens": 800
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
