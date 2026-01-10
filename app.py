import os
import uuid
import threading
import time
import zipfile
from io import BytesIO

import cv2
from rembg import remove
from PIL import Image

from flask import Flask, render_template, request, jsonify, send_file, url_for, redirect
from werkzeug.utils import secure_filename

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 256  # 256 MB limit

# Assurer l'existence des dossiers
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Dictionnaire pour suivre la progression des tâches
# {video_id: {'status': 'pending'/'processing'/'completed'/'error', 'progress': 0-100, 'frames_count': 0, 'total_frames': 0, 'output_dir': None, 'error_message': None, 'params': {}}}
processing_tasks = {}

def unsharp_mask(image):
    """Applique un masque de netteté (Unsharp Mask) à l'image OpenCV."""
    # Flou gaussien (sigma=5 est un bon point de départ)
    blurred = cv2.GaussianBlur(image, (0, 0), 5)
    # Calcul de l'image nette: Original + (Original - Blurred) * amount
    # addWeighted fait: src1 * alpha + src2 * beta + gamma
    # Ici: image * 1.5 + blurred * -0.5 + 0
    sharpened = cv2.addWeighted(image, 1.5, blurred, -0.5, 0)
    return sharpened

def process_video(video_id, video_path, params):
    """Fonction de traitement vidéo asynchrone."""
    task = processing_tasks[video_id]
    
    try:
        task['status'] = 'processing'
        task['message'] = 'Initialisation du traitement vidéo...'
        
        # 1. Initialisation OpenCV
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise Exception("Impossible d'ouvrir le fichier vidéo.")
            
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Calcul de l'intervalle en nombre de frames à sauter
        interval_sec = params['interval']
        frame_skip = max(1, int(fps * interval_sec))
        
        task['total_frames'] = total_frames
        task['message'] = f"Vidéo: {total_frames} frames à {fps:.2f} FPS. Extraction toutes les {interval_sec}s ({frame_skip} frames)."
        
        # Préparation du dossier de sortie
        output_dir = os.path.join(app.config['OUTPUT_FOLDER'], video_id)
        os.makedirs(output_dir, exist_ok=True)
        task['output_dir'] = output_dir
        
        frame_count = 0
        extracted_count = 0
        
        while cap.isOpened():
            ret, frame = cap.read()
            
            if not ret:
                break
            
            # Mise à jour de la progression basée sur le nombre total de frames lues
            progress = int((frame_count / total_frames) * 100)
            task['progress'] = progress
            task['frames_count'] = extracted_count
            task['message'] = f"Extraction: {extracted_count} frames générées. Progression: {progress}%"
            
            # Extraction selon l'intervalle
            if frame_count % frame_skip == 0:
                
                # 2. Option "unblur" (Amélioration de netteté)
                if params['unblur_option']:
                    frame = unsharp_mask(frame)
                
                # 3. Redimensionnement proportionnel
                target_width = params['target_width']
                height, width, _ = frame.shape
                
                if width > target_width:
                    ratio = target_width / width
                    target_height = int(height * ratio)
                    frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
                
                # 4. Conversion en image PIL (BGR -> RGB)
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(rgb_image)
                
                # 5. Suppression automatique de l'arrière-plan avec rembg
                # rembg gère la conversion en RGBA pour la transparence
                result_image = remove(pil_image)
                
                # 6. Sauvegarde de l'image dans le format de sortie
                output_format = params['output_format']
                filename = f"frame_{extracted_count:05d}.{output_format}"
                output_path = os.path.join(output_dir, filename)
                
                if output_format == 'png':
                    # PNG: qualité maximale avec transparence (par défaut avec rembg)
                    result_image.save(output_path, format='PNG')
                elif output_format == 'jpg':
                    # JPG: conversion RGB, compression contrôlée (pas de transparence)
                    # Convertir en RGB avant de sauvegarder en JPG
                    if result_image.mode == 'RGBA':
                        result_image = result_image.convert('RGB')
                    result_image.save(output_path, format='JPEG', quality=95)
                elif output_format == 'webp':
                    # WEBP: format optimisé web avec transparence
                    result_image.save(output_path, format='WEBP', lossless=True) # Lossless pour meilleure qualité avec transparence
                
                extracted_count += 1
            
            frame_count += 1
            
        cap.release()
        
        # Finalisation
        task['progress'] = 100
        task['frames_count'] = extracted_count
        task['status'] = 'completed'
        task['message'] = f"Traitement terminé. {extracted_count} frames générées."
        
    except Exception as e:
        error_msg = f"Erreur de traitement: {e}"
        task['status'] = 'error'
        task['error_message'] = error_msg
        task['message'] = error_msg
        app.logger.error(f"Erreur dans le traitement pour {video_id}: {e}")
        
    finally:
        # Nettoyage du fichier vidéo original
        if os.path.exists(video_path):
            os.remove(video_path)
            
        # S'assurer que la progression est à 100% même en cas d'erreur
        if task['progress'] < 100:
            task['progress'] = 100

@app.route('/process', methods=['POST'])
def process():
    if 'video_file' not in request.files:
        return jsonify({'error': 'Aucun fichier vidéo fourni'}), 400
    
    file = request.files['video_file']
    
    if file.filename == '':
        return jsonify({'error': 'Nom de fichier vide'}), 400
    
    if file and allowed_file(file.filename):
        try:
            # 1. Validation et récupération des paramètres
            target_width = int(request.form.get('target_width', 512))
            interval = float(request.form.get('interval', 1.0))
            output_format = request.form.get('output_format', 'png').lower()
            unblur_option = request.form.get('unblur_option') == 'on'

            if output_format not in ['png', 'jpg', 'webp']:
                return jsonify({'error': 'Format de sortie non supporté'}), 400
            
            if target_width <= 0 or interval <= 0:
                return jsonify({'error': 'Paramètres de traitement invalides'}), 400

            # 2. Préparation des chemins et ID
            video_id = str(uuid.uuid4())
            filename = secure_filename(file.filename)
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_id + '_' + filename)
            output_dir = os.path.join(app.config['OUTPUT_FOLDER'], video_id)
            
            # 3. Sauvegarde du fichier
            file.save(video_path)
            
            # 4. Initialisation de la tâche
            params = {
                'target_width': target_width,
                'interval': interval,
                'output_format': output_format,
                'unblur_option': unblur_option
            }
            
            processing_tasks[video_id] = {
                'status': 'pending',
                'progress': 0,
                'frames_count': 0,
                'total_frames': 0,
                'output_dir': output_dir,
                'error_message': None,
                'params': params,
                'video_path': video_path
            }
            
            # 5. Lancement du traitement asynchrone
            thread = threading.Thread(target=process_video, args=(video_id, video_path, params))
            thread.start()
            
            return jsonify({'video_id': video_id, 'message': 'Traitement lancé avec succès'}), 202
            
        except Exception as e:
            app.logger.error(f"Erreur lors du traitement de l'upload: {e}")
            return jsonify({'error': f'Erreur interne du serveur: {e}'}), 500
    
    return jsonify({'error': 'Type de fichier non autorisé'}), 400

@app.route('/progress/<video_id>')
def progress(video_id):
    task = processing_tasks.get(video_id)
    if not task:
        return jsonify({'error': 'ID de vidéo non trouvé'}), 404
    
    # Retourne l'état actuel de la tâche
    return jsonify({
        'status': task['status'],
        'progress': task['progress'],
        'message': task.get('message', 'En cours...'),
        'frames_count': task['frames_count'],
        'total_frames': task['total_frames']
    })

@app.route('/frames/<video_id>')
def frames(video_id):
    task = processing_tasks.get(video_id)
    if not task or task['status'] != 'completed':
        return jsonify({'error': 'Traitement non terminé ou ID invalide'}), 404
    
    output_dir = task['output_dir']
    
    try:
        # Liste tous les fichiers dans le dossier de sortie
        frames_list = [f for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
        return jsonify({'frames': frames_list})
    except Exception as e:
        app.logger.error(f"Erreur lors de la liste des frames pour {video_id}: {e}")
        return jsonify({'error': 'Erreur lors de la récupération des frames'}), 500

@app.route('/outputs/<video_id>/<filename>')
def serve_frame(video_id, filename):
    task = processing_tasks.get(video_id)
    if not task or task['status'] not in ['processing', 'completed']:
        return jsonify({'error': 'Ressource non disponible'}), 404
    
    output_dir = task['output_dir']
    
    # Sécurité: s'assurer que le fichier demandé est bien dans le dossier de sortie
    return send_file(os.path.join(output_dir, filename))

@app.route('/download/<video_id>')
def download_zip(video_id):
    task = processing_tasks.get(video_id)
    if not task or task['status'] != 'completed':
        return jsonify({'error': 'Traitement non terminé ou ID invalide'}), 404
    
    output_dir = task['output_dir']
    
    # Création de l'archive ZIP en mémoire
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                # Ajout du fichier à l'archive, en utilisant un chemin relatif
                zf.write(file_path, os.path.relpath(file_path, output_dir))
    
    memory_file.seek(0)
    
    # Envoi du fichier ZIP
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'frames_{video_id}.zip'
    )

# Nettoyage des routes non utilisées
# Les autres routes seront implémentées dans les phases suivantes:
# /process
# /progress/<video_id>
# /frames/<video_id>
# /outputs/<video_id>/<filename>

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

# Les autres routes seront implémentées dans les phases suivantes:
# /process
# /progress/<video_id>
# /frames/<video_id>
# /outputs/<video_id>/<filename>

if __name__ == '__main__':
    # Pour le développement local, Replit utilisera gunicorn
    app.run(debug=True)
