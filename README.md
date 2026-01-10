# Extracteur de Frames Vidéo Avancé (Flask/OpenCV/rembg)

Ce projet est une application web complète, construite avec **Python** et le framework **Flask**, conçue pour le traitement automatisé de vidéos. Elle permet aux utilisateurs d'uploader une vidéo et d'en extraire des frames selon des paramètres avancés, incluant la suppression d'arrière-plan et l'amélioration de netteté.

## Fonctionnalités

*   **Interface Web (Vanilla JS/HTML/CSS)** : Interface utilisateur simple et non bloquante.
*   **Traitement Asynchrone** : Utilisation de threads pour éviter le blocage du serveur pendant le traitement vidéo.
*   **Progression Réelle** : Suivi précis de l'avancement du traitement (0-100%).
*   **Extraction Avancée** :
    *   Extraction de frames selon un intervalle temporel défini.
    *   Redimensionnement proportionnel à une largeur cible.
    *   Option **"Unblur"** (Masque de netteté via OpenCV).
    *   **Suppression d'arrière-plan** automatique via la librairie `rembg`.
*   **Formats de Sortie** : PNG (transparence), JPG (compression), WEBP (optimisé web, transparence).
*   **Aperçu Dynamique** : Affichage des premières frames générées avant le téléchargement.
*   **Téléchargement Final** : Export de toutes les frames traitées dans une archive ZIP.

## Architecture Technique

| Composant | Technologie | Rôle |
| :--- | :--- | :--- |
| Backend | Python 3.11, Flask | Gestion des routes, de l'upload, de la progression et du traitement asynchrone. |
| Traitement Vidéo | OpenCV | Lecture vidéo, extraction de frames, redimensionnement, "unblur" (Unsharp Mask). |
| Traitement Image | rembg, PIL (Pillow) | Suppression d'arrière-plan, gestion des formats de sortie (PNG, JPG, WEBP). |
| Frontend | HTML, CSS, JavaScript (Vanilla) | Interface utilisateur, gestion du formulaire, interrogation de la progression (polling), affichage de l'aperçu. |
| Déploiement | Gunicorn, Replit | Serveur d'application pour l'hébergement web. |

## Démarrage (sur Replit)

1.  **Dépendances** : Le fichier `requirements.txt` liste toutes les dépendances Python nécessaires.
2.  **Lancement** : Le `Procfile` configure le lancement de l'application via Gunicorn : `web: venv/bin/gunicorn --bind 0.0.0.0:8080 app:app`.

L'application sera accessible via l'URL fournie par Replit.

## Routes API

| Route | Méthode | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Page principale avec le formulaire d'upload. |
| `/process` | `POST` | Lance le traitement vidéo en arrière-plan. Retourne un `video_id`. |
| `/progress/<video_id>` | `GET` | Retourne l'état d'avancement du traitement (JSON). |
| `/frames/<video_id>` | `GET` | Retourne la liste des noms de fichiers des frames générées (JSON). |
| `/outputs/<video_id>/<filename>` | `GET` | Sert une frame spécifique pour l'aperçu. |
| `/download/<video_id>` | `GET` | Génère et envoie l'archive ZIP des frames. |

## Note sur le Nettoyage

Le fichier vidéo original est automatiquement supprimé après le traitement (dans la fonction `process_video`). Les dossiers de sortie contenant les frames générées (`outputs/<video_id>`) sont conservés pour l'aperçu et le téléchargement. Pour une version de production, une tâche de nettoyage périodique devrait être ajoutée pour supprimer ces dossiers après un certain délai.
