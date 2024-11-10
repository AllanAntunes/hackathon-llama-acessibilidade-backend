from flask import Flask, request, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv
from groq import Groq
from agent import run_conversation
import uuid
import os
import subprocess
import shlex

load_dotenv()
API_KEY = os.getenv('API_KEY')

app = Flask(__name__)
CORS(app, origins='*')

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('MYSQL_CONNECTION')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

def require_api_key(func):
    def wrapper(*args, **kwargs):
        api_key = request.headers.get('Authorization')
        if api_key and api_key == API_KEY:
            return func(*args, **kwargs)
        else:
            return jsonify({"error": "Unauthorized"}), 401
    wrapper.__name__ = func.__name__
    return wrapper

class Message(db.Model):
    __tablename__ = 'message'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sessionId = db.Column(db.Integer, nullable=False)
    role = db.Column(db.Integer, nullable=False, comment='1 - User / 2 - Assistant')
    message = db.Column(db.Text, nullable=True)
    audioFilename = db.Column(db.Text, nullable=True)
    datetime = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())

class Space(db.Model):
    __tablename__ = 'space'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    thumbnailUrl = db.Column(db.Text)

class SpaceItem(db.Model):
    __tablename__ = 'space_item'
    id = db.Column(db.Integer, primary_key=True)
    spaceId = db.Column(db.Integer, db.ForeignKey('space.id'))
    step = db.Column(db.Integer, nullable=False)
    name = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    aiDescription = db.Column(db.Text)
    imageUrl = db.Column(db.Text)
    authorName = db.Column(db.Text)
    authorDescription = db.Column(db.Text)

@app.route('/conversation/session', methods=['GET'])
@require_api_key
def conversation_session():
    response = {
        "sessionId": str(uuid.uuid4()),
    }
    return jsonify(response)

@app.route('/conversation/message', methods=['POST'])
@require_api_key
def conversation_message():
    session_id = request.form.get('sessionId')
    space_id = request.form.get('spaceId')
    audio_file = request.files.get('audioFile')

    if not audio_file:
        return jsonify({"error": "Audio file is required"}), 400

    audio_filename = f"{uuid.uuid4()}.mp3"
    audio_path = os.path.join('audio', audio_filename)
    audio_file.save(audio_path)

    # Transcrição de áudio para texto
    groq_client = Groq(
        api_key=os.environ.get("GROQ_API_KEY")
    )

    with open(audio_path, "rb") as file:
        transcription = groq_client.audio.transcriptions.create(
            file=(audio_path, file.read()),
            model="whisper-large-v3-turbo",
            prompt="Specify context or spelling",
            response_format="json",
            language="pt",
            temperature=0.0
        )

    transcripted_audio = transcription.text

    # Insere mensagem enviada pelo usuário na tabela "message"
    new_message = Message(
        sessionId = session_id,
        role = 'user',
        message = transcripted_audio,
        audioFilename = audio_filename
    )
    db.session.add(new_message)
    db.session.commit()

    # Pegar transcrição e obter resposta do Groq/Llama
    agent_response = run_conversation(transcripted_audio, groq_client)
    
    # Pegar resposta e passar no Piper para virar áudio .mp3
    response_audio = f"{uuid.uuid4()}.mp3"
    response_audio_path = os.path.join('audio', response_audio)

    safe_text = shlex.quote(agent_response)
    command = f"echo {safe_text} | piper --model pt_BR-faber-medium --output_file {response_audio_path}"

    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        abort(500, description=f"Failed to generate audio: {str(e)}")

    if not os.path.exists(response_audio_path):
        abort(500, description="Audio file not found.")

    # Insere mensagem gerada pela LLM na tabela "message"
    new_message = Message(
        sessionId = session_id,
        role = 'assistant',
        message = agent_response,
        audioFilename = response_audio
    )
    db.session.add(new_message)
    db.session.commit()

    # Enviar JSON de resposta
    response = {
        "sessionId": session_id,
        "audioUrl": f"https://api.acessibilidade.tec.br/audio/{response_audio}",
        "transcription": agent_response
    }
    return jsonify(response)

@app.route('/space', methods=['GET'])
@require_api_key
def get_spaces():
    spaces = Space.query.all()
    return jsonify([{
        'spaceId': space.id,
        'name': space.name,
        'description': space.description,
        'thumbnailUrl': space.thumbnailUrl
    } for space in spaces])

@app.route('/space/<int:space_id>', methods=['GET'])
@require_api_key
def get_space(space_id):
    space = Space.query.get(space_id)
    return jsonify({
        'spaceId': space.id,
        'name': space.name,
        'description': space.description,
        'thumbnailUrl': space.thumbnailUrl
    }) if space else ('', 404)

@app.route('/space', methods=['POST'])
@require_api_key
def create_space():
    data = request.json
    new_space = Space(
        name=data['name'],
        description=data['description'],
        thumbnailUrl=data['thumbnailUrl']
    )
    db.session.add(new_space)
    db.session.commit()
    return jsonify({"success": True, "spaceId": new_space.id})

@app.route('/space', methods=['PUT'])
@require_api_key
def update_space():
    data = request.json
    space = Space.query.get(data['spaceId'])
    if space:
        space.name = data['name']
        space.description = data['description']
        space.thumbnailUrl = data['thumbnailUrl']
        db.session.commit()
        return jsonify({"success": True, "spaceId": space.id})
    return jsonify({"success": False, "spaceId": data['spaceId']}), 404

@app.route('/space', methods=['DELETE'])
@require_api_key
def delete_space():
    data = request.json
    space = Space.query.get(data['spaceId'])
    if space:
        db.session.delete(space)
        db.session.commit()
        return jsonify({"success": True, "spaceId": data['spaceId']})
    return jsonify({"success": False, "spaceId": data['spaceId']}), 404

@app.route('/space/<int:space_id>/item', methods=['GET'])
@require_api_key
def get_items(space_id):
    items = SpaceItem.query.filter_by(spaceId=space_id).all()
    return jsonify([{
        'itemId': item.id,
        'step': item.step,
        'name': item.name,
        'description': item.description,
        'aiDescription': item.aiDescription,
        'authorName': item.authorName,
        'authorDescription': item.authorDescription,
        'imageUrl': item.imageUrl
    } for item in items])

@app.route('/space/<int:space_id>/item/<int:item_id>', methods=['GET'])
@require_api_key
def get_item(space_id, item_id):
    item = SpaceItem.query.filter_by(spaceId=space_id, id=item_id).first()
    return jsonify({
        'itemId': item.id,
        'step': item.step,
        'name': item.name,
        'description': item.description,
        'aiDescription': item.aiDescription,
        'authorName': item.authorName,
        'authorDescription': item.authorDescription,
        'imageUrl': item.imageUrl
    }) if item else ('', 404)

@app.route('/space/<int:space_id>/item', methods=['POST'])
@require_api_key
def create_item(space_id):
    data = request.json
    new_item = SpaceItem(
        spaceId=space_id,
        step=data['step'],
        name=data['name'],
        description=data['description'],
        authorName=data['authorName'],
        authorDescription=data['authorDescription'],
        imageUrl=data['imageUrl']
    )
    db.session.add(new_item)
    db.session.commit()
    return jsonify({"success": True, "itemId": new_item.id})

@app.route('/space/<int:space_id>/item', methods=['PUT'])
@require_api_key
def update_item(space_id):
    data = request.json
    item = SpaceItem.query.filter_by(spaceId=space_id, id=data['itemId']).first()
    if item:
        item.step = data['step']
        item.name = data['name']
        item.description = data['description']
        item.authorName = data['authorName']
        item.authorDescription = data['authorDescription']
        item.imageUrl = data['imageUrl']
        db.session.commit()
        return jsonify({"success": True, "itemId": item.id})
    return jsonify({"success": False, "itemId": data['itemId']}), 404

@app.route('/space/<int:space_id>/item', methods=['DELETE'])
@require_api_key
def delete_item(space_id):
    data = request.json
    item = SpaceItem.query.filter_by(spaceId=space_id, id=data['itemId']).first()
    if item:
        db.session.delete(item)
        db.session.commit()
        return jsonify({"success": True, "itemId": data['itemId']})
    return jsonify({"success": False, "itemId": data['itemId']}), 404

if __name__ == '__main__':
    app.run(debug=True)