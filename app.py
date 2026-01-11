import os
import uuid
import threading
import zipfile
from io import BytesIO

import cv2
from rembg import remove
from PIL import Image

from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

# =========================
# CONFIGURATION
# =========================

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"
ALLOWED_EXTENSIONS = {"mp4", "mov", "avi"}

MAX_UPLOAD_SIZE = 256 * 1024 * 1024  # 256 MB

app = Flask(__name__)
app.config.update(
    UPLOAD_FOLDER=UPLOAD_FOLDER,
    OUTPUT_FOLDER=OUTPUT_FOLDER,
    MAX_CONTENT_LENGTH=MAX_UPLOAD_SIZE
)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# =========================
# STATE (THREAD-SAFE)
# =========================

processing_tasks = {}
tasks_lock = threading.Lock()

# =========================
# UTILS
# =========================

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def unsharp_mask(image):
    blurred = cv2.GaussianBlur(image, (0, 0), 5)
    return cv2.addWeighted(image, 1.5, blurred, -0.5, 0)


# =========================
# CORE PROCESSING
# =========================

def process_video(video_id: str, video_path: str, params: dict):
    with tasks_lock:
        task = processing_tasks[video_id]
        task["status"] = "processing"
        task["message"] = "Initialisation du traitement vidéo..."

    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError("Impossible d'ouvrir la vidéo")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_skip = max(1, int(fps * params["interval"]))

        output_dir = os.path.join(app.config["OUTPUT_FOLDER"], video_id)
        os.makedirs(output_dir, exist_ok=True)

        with tasks_lock:
            task["total_frames"] = total_frames
            task["output_dir"] = output_dir

        frame_index = 0
        extracted = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_index % frame_skip == 0:
                if params["unblur"]:
                    frame = unsharp_mask(frame)

                h, w, _ = frame.shape
                if w > params["target_width"]:
                    ratio = params["target_width"] / w
                    frame = cv2.resize(
                        frame,
                        (params["target_width"], int(h * ratio)),
                        interpolation=cv2.INTER_AREA
                    )

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)

                result = remove(pil_img)

                filename = f"frame_{extracted:05d}.{params['format']}"
                out_path = os.path.join(output_dir, filename)

                if params["format"] == "jpg":
                    if result.mode == "RGBA":
                        result = result.convert("RGB")
                    result.save(out_path, "JPEG", quality=95)
                elif params["format"] == "webp":
                    result.save(out_path, "WEBP", lossless=True)
                else:
                    result.save(out_path, "PNG")

                extracted += 1

            frame_index += 1

            with tasks_lock:
                task["frames_count"] = extracted
                task["progress"] = int((frame_index / total_frames) * 100)
                task["message"] = f"{extracted} frames générées"

        cap.release()

        with tasks_lock:
            task["status"] = "completed"
            task["progress"] = 100
            task["message"] = f"Terminé. {extracted} frames générées."

    except Exception as e:
        with tasks_lock:
            task["status"] = "error"
            task["error_message"] = str(e)
            task["message"] = f"Erreur: {e}"
            task["progress"] = 100

    finally:
        if os.path.exists(video_path):
            os.remove(video_path)


# =========================
# ROUTES
# =========================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
    if "video_file" not in request.files:
        return jsonify(error="Aucun fichier vidéo"), 400

    file = request.files["video_file"]
    if file.filename == "" or not allowed_file(file.filename):
        return jsonify(error="Fichier invalide"), 400

    try:
        params = {
            "target_width": int(request.form.get("target_width", 512)),
            "interval": float(request.form.get("interval", 1.0)),
            "format": request.form.get("output_format", "png").lower(),
            "unblur": request.form.get("unblur_option") == "on"
        }

        if params["format"] not in {"png", "jpg", "webp"}:
            return jsonify(error="Format non supporté"), 400

        video_id = str(uuid.uuid4())
        filename = secure_filename(file.filename)
        video_path = os.path.join(UPLOAD_FOLDER, f"{video_id}_{filename}")

        file.save(video_path)

        with tasks_lock:
            processing_tasks[video_id] = {
                "status": "pending",
                "progress": 0,
                "frames_count": 0,
                "total_frames": 0,
                "output_dir": None,
                "message": "En attente",
                "error_message": None
            }

        thread = threading.Thread(
            target=process_video,
            args=(video_id, video_path, params),
            daemon=True
        )
        thread.start()

        return jsonify(video_id=video_id), 202

    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route("/progress/<video_id>")
def progress(video_id):
    with tasks_lock:
        task = processing_tasks.get(video_id)

    if not task:
        return jsonify(error="ID inconnu"), 404

    return jsonify(task)


@app.route("/download/<video_id>")
def download(video_id):
    with tasks_lock:
        task = processing_tasks.get(video_id)

    if not task or task["status"] != "completed":
        return jsonify(error="Traitement non terminé"), 404

    memory = BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in os.listdir(task["output_dir"]):
            p = os.path.join(task["output_dir"], f)
            zf.write(p, f)

    memory.seek(0)
    return send_file(
        memory,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"frames_{video_id}.zip"
    )


# =========================
# ENTRYPOINT (RENDER SAFE)
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
