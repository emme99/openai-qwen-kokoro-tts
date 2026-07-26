const generateBtn = document.getElementById('generateBtn');
const textInput = document.getElementById('textInput');
const voiceSelect = document.getElementById('voiceSelect');
const audioPlayer = document.getElementById('audioPlayer');
const statusDiv = document.getElementById('status');

generateBtn.addEventListener('click', async () => {
    const text = textInput.value;
    const voice = voiceSelect.value;

    if (!text) {
        alert("Inserisci del testo!");
        return;
    }

    generateBtn.disabled = true;
    statusDiv.textContent = "Generazione in corso...";

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: text,
                voice: voice,
                response_format: 'mp3'
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(errorText || 'Errore nella generazione');
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        audioPlayer.src = url;
        audioPlayer.play();
        statusDiv.textContent = "Completato!";
    } catch (error) {
        console.error(error);
        statusDiv.textContent = "Errore: " + error.message;
    } finally {
        generateBtn.disabled = false;
    }
});
