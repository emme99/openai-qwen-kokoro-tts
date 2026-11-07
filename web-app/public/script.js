const generateBtn = document.getElementById('generateBtn');
const textInput = document.getElementById('textInput');
const voiceSelect = document.getElementById('voiceSelect');
const languageSelect = document.getElementById('languageSelect');
const audioPlayer = document.getElementById('audioPlayer');
const statusDiv = document.getElementById('status');
const serviceTime = document.getElementById('serviceTime');
const totalTime = document.getElementById('totalTime');
const cpuMedianTime = document.getElementById('cpuMedianTime');
const mpsMedianTime = document.getElementById('mpsMedianTime');
const timingHistoryBody = document.getElementById('timingHistory');
const timings = [];

function formatTime(milliseconds) {
    return `${Math.round(milliseconds)} ms`;
}

function median(values) {
    const sorted = [...values].sort((a, b) => a - b);
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2
        ? sorted[middle]
        : (sorted[middle - 1] + sorted[middle]) / 2;
}

function renderTimings() {
    const latest = timings[0];
    const cpuTimes = timings.filter((timing) => timing.device === 'cpu').map((timing) => timing.totalMs);
    const mpsTimes = timings.filter((timing) => timing.device === 'mps').map((timing) => timing.totalMs);
    serviceTime.textContent = latest.serviceMs === null ? '--' : formatTime(latest.serviceMs);
    totalTime.textContent = formatTime(latest.totalMs);
    cpuMedianTime.textContent = cpuTimes.length ? formatTime(median(cpuTimes)) : '--';
    mpsMedianTime.textContent = mpsTimes.length ? formatTime(median(mpsTimes)) : '--';

    timingHistoryBody.replaceChildren(...timings.map((timing) => {
        const row = document.createElement('tr');
        const timeCell = document.createElement('td');
        const deviceCell = document.createElement('td');
        const serviceCell = document.createElement('td');
        const totalCell = document.createElement('td');

        timeCell.textContent = timing.time;
        deviceCell.textContent = timing.device.toUpperCase();
        serviceCell.textContent = timing.serviceMs === null ? '--' : formatTime(timing.serviceMs);
        totalCell.textContent = formatTime(timing.totalMs);
        row.append(timeCell, deviceCell, serviceCell, totalCell);
        return row;
    }));
}

generateBtn.addEventListener('click', async () => {
    const text = textInput.value;
    const voice = voiceSelect.value;
    const language = languageSelect.value;

    if (!text) {
        alert("Inserisci del testo!");
        return;
    }

    generateBtn.disabled = true;
    statusDiv.textContent = "Generazione in corso...";
    const startedAt = performance.now();

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: text,
                voice: voice,
                language: language,
                response_format: 'mp3'
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(errorText || 'Errore nella generazione');
        }

        const blob = await response.blob();
        const requestTimeMs = performance.now() - startedAt;
        const responseTime = Number(response.headers.get('X-TTS-Process-Time-Ms'));
        const device = response.headers.get('X-TTS-Device') || 'unknown';
        const previousUrl = audioPlayer.src;
        const url = URL.createObjectURL(blob);
        audioPlayer.src = url;
        if (previousUrl.startsWith('blob:')) {
            URL.revokeObjectURL(previousUrl);
        }
        audioPlayer.play();
        timings.unshift({
            time: new Date().toLocaleTimeString('it-IT'),
            device,
            serviceMs: Number.isFinite(responseTime) && responseTime > 0 ? responseTime : null,
            totalMs: requestTimeMs
        });
        timings.splice(10);
        renderTimings();
        statusDiv.textContent = `Completato in ${formatTime(requestTimeMs)}`;
    } catch (error) {
        console.error(error);
        statusDiv.textContent = "Errore: " + error.message;
    } finally {
        generateBtn.disabled = false;
    }
});
