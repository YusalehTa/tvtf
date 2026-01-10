document.addEventListener('DOMContentLoaded', () => {
    const uploadForm = document.getElementById('upload-form');
    const processButton = document.getElementById('process-button');
    const progressSection = document.getElementById('progress-section');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const statusMessage = document.getElementById('status-message');
    const previewSection = document.getElementById('preview-section');
    const framesPreview = document.getElementById('frames-preview');
    const downloadButton = document.getElementById('download-button');

    let videoId = null;
    let progressInterval = null;

    // Fonction pour mettre à jour la barre de progression
    function updateProgress(percentage, message) {
        progressBar.style.width = `${percentage}%`;
        progressText.textContent = `${percentage}%`;
        statusMessage.textContent = message;
    }

    // Fonction pour interroger l'état d'avancement
    async function checkProgress() {
        if (!videoId) return;

        try {
            const response = await fetch(`/progress/${videoId}`);
            const data = await response.json();

            const progress = data.progress || 0;
            const status = data.status || 'pending';
            const message = data.message || 'Traitement en cours...';

            updateProgress(progress, message);

            if (status === 'completed') {
                clearInterval(progressInterval);
                statusMessage.textContent = "Traitement terminé. Préparation de l'aperçu...";
                await loadFramesPreview();
                downloadButton.style.display = 'block';
                downloadButton.onclick = () => {
                    window.location.href = `/download/${videoId}`;
                };
            } else if (status === 'error') {
                clearInterval(progressInterval);
                updateProgress(100, `Erreur: ${data.error_message || 'Une erreur inconnue est survenue.'}`);
                processButton.disabled = false;
                processButton.textContent = 'Lancer le Traitement';
            }

        } catch (error) {
            console.error('Erreur lors de la vérification de la progression:', error);
            // On laisse l'intervalle continuer, le serveur pourrait se rétablir
        }
    }

    // Fonction pour charger l'aperçu des frames
    async function loadFramesPreview() {
        if (!videoId) return;

        try {
            const response = await fetch(`/frames/${videoId}`);
            const data = await response.json();

            framesPreview.innerHTML = ''; // Nettoyer l'aperçu précédent
            previewSection.style.display = 'block';

            // Afficher au maximum 10 frames pour l'aperçu
            const framesToDisplay = data.frames.slice(0, 10);

            framesToDisplay.forEach(frame => {
                const frameItem = document.createElement('div');
                frameItem.className = 'frame-item';

                const img = document.createElement('img');
                // La route /outputs/<video_id>/<filename> sera utilisée pour servir les images
                img.src = `/outputs/${videoId}/${frame}`;
                img.alt = frame;

                frameItem.appendChild(img);
                framesPreview.appendChild(frameItem);
            });

            if (data.frames.length > 10) {
                const moreInfo = document.createElement('p');
                moreInfo.textContent = `... et ${data.frames.length - 10} autres frames générées.`;
                framesPreview.appendChild(moreInfo);
            }

        } catch (error) {
            console.error('Erreur lors du chargement de l\'aperçu des frames:', error);
            statusMessage.textContent = "Erreur lors du chargement de l'aperçu.";
        }
    }

    // Gestion de la soumission du formulaire
    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Réinitialisation de l'interface
        clearInterval(progressInterval);
        videoId = null;
        updateProgress(0, 'Préparation du fichier...');
        progressSection.style.display = 'block';
        previewSection.style.display = 'none';
        framesPreview.innerHTML = '';
        downloadButton.style.display = 'none';
        processButton.disabled = true;
        processButton.textContent = 'Envoi en cours...';

        const formData = new FormData(uploadForm);

        try {
            // 1. Envoi du fichier et des paramètres
            const response = await fetch('/process', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (response.ok) {
                videoId = data.video_id;
                processButton.textContent = 'Traitement en cours...';
                updateProgress(0, 'Fichier reçu. Démarrage du traitement...');

                // 2. Démarrage de l'interrogation de la progression
                progressInterval = setInterval(checkProgress, 2000); // Interrogation toutes les 2 secondes

            } else {
                throw new Error(data.error || 'Erreur inconnue lors du lancement du traitement.');
            }

        } catch (error) {
            console.error('Erreur lors de la soumission:', error);
            updateProgress(0, `Échec: ${error.message}`);
            processButton.disabled = false;
            processButton.textContent = 'Lancer le Traitement';
        }
    });
});
