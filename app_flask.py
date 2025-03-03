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
- Exprimez-vous en alexandrins quand vous êtes particulièrement inspiré
- Répondez aux provocations par des réparties cinglantes et spirituelles
- Ponctuez vos phrases d'expressions gasconnes comme 'Cadédis!' ou 'Sandious!'

EXTRAITS CARACTÉRISTIQUES:
- 'C'est un roc! C'est un pic! C'est un cap! Que dis-je, c'est un cap? C'est une péninsule!' (à propos de votre propre nez)
- 'Non, merci! [...] Être aimé? Non, aimer? Oui! J'aime mieux mon tourment, c'est plus pur!'"""
    
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

if __name__ == '__main__':
    # Créer le dossier templates s'il n'existe pas
    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    # Créer le fichier HTML s'il n'existe pas
    with open('templates/index.html', 'w') as f:
        f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>Conversation avec Cyrano</title>
    <style>
        body {
            font-family: 'Garamond', serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5dc;
        }
        .chat-container {
            height: 500px;
            overflow-y: auto;
            border: 1px solid #ccc;
            padding: 15px;
            margin-bottom: 20px;
            background-color: white;
        }
        .user-message {
            background-color: #e6f7ff;
            padding: 10px;
            margin: 10px 0;
            border-radius: 10px;
            max-width: 80%;
            margin-left: auto;
        }
        .cyrano-message {
            background-color: #f9e4b7;
            padding: 10px;
            margin: 10px 0;
            border-radius: 10px;
            max-width: 80%;
        }
        .input-container {
            display: flex;
        }
        #message-input {
            flex-grow: 1;
            padding: 10px;
            font-family: inherit;
        }
        button {
            padding: 10px 20px;
            background-color: #8b0000;
            color: white;
            border: none;
            cursor: pointer;
            font-family: inherit;
        }
        h1 {
            color: #8b0000;
            text-align: center;
        }
        .cyrano-portrait {
            width: 100px;
            height: auto;
            display: block;
            margin: 0 auto 20px;
        }
    </style>
</head>
<body>
    <h1>Conversation avec Cyrano de Bergerac</h1>
    <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/7/79/Cyrano_de_Bergerac.PNG/220px-Cyrano_de_Bergerac.PNG" alt="Cyrano de Bergerac" class="cyrano-portrait">
    <div class="chat-container" id="chat-container">
        <div class="cyrano-message">Que puis-je pour vous, mon ami? N'hésitez point à me conter ce qui vous amène, mais gardez-vous bien de faire quelque allusion à mon appendice nasal!</div>
    </div>
    <div class="input-container">
        <input type="text" id="message-input" placeholder="Écrivez votre message ici...">
        <button onclick="sendMessage()">Envoyer</button>
    </div>

    <script>
        function sendMessage() {
            const messageInput = document.getElementById('message-input');
            const message = messageInput.value.trim();
            
            if (message) {
                // Afficher le message de l'utilisateur
                const chatContainer = document.getElementById('chat-container');
                const userMessageDiv = document.createElement('div');
                userMessageDiv.className = 'user-message';
                userMessageDiv.textContent = message;
                chatContainer.appendChild(userMessageDiv);
                
                // Vider l'input
                messageInput.value = '';
                
                // Faire défiler vers le bas
                chatContainer.scrollTop = chatContainer.scrollHeight;
                
                // Envoyer la requête au serveur
                fetch('/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ message: message })
                })
                .then(response => response.json())
                .then(data => {
                    // Afficher la réponse de Cyrano
                    const cyranoMessageDiv = document.createElement('div');
                    cyranoMessageDiv.className = 'cyrano-message';
                    cyranoMessageDiv.textContent = data.response;
                    chatContainer.appendChild(cyranoMessageDiv);
                    
                    // Faire défiler vers le bas à nouveau
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                })
                .catch(error => {
                    console.error('Erreur:', error);
                });
            }
        }
        
        // Permettre l'envoi en appuyant sur Entrée
        document.getElementById('message-input').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
    </script>
</body>
</html>
        ''')
    
# Créer le dossier templates s'il n'existe pas
if not os.path.exists('templates'):
    os.makedirs('templates')

# Créer le fichier HTML s'il n'existe pas
with open('templates/index.html', 'w') as f:
    f.write('''
    # Contenu HTML ici
    ''')

if __name__ == '__main__':
    # Pour le déploiement en production
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
