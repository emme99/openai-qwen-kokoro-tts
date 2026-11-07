const express = require('express');
const axios = require('axios');
const cors = require('cors');
const path = require('path');

const app = express();
const PORT = Number(process.env.PORT || 3000);
const TTS_API_URL = 'http://localhost:5050/v1/audio/speech';

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Proxy endpoint
app.post('/api/generate', async (req, res) => {
    try {
        const { text, voice, language, response_format } = req.body;

        const response = await axios.post(TTS_API_URL, {
            model: "qwen3-tts",
            input: text,
            voice: voice || 'default',
            language: language || 'it',
            response_format: response_format || 'mp3'
        }, {
            responseType: 'arraybuffer',
            headers: { 'Content-Type': 'application/json' }
        });

        const contentType = response.headers['content-type'];
        res.set('Content-Type', contentType);
        const processTime = response.headers['x-process-time-ms'];
        if (processTime) {
            res.set('X-TTS-Process-Time-Ms', processTime);
        }
        const device = response.headers['x-device'];
        if (device) {
            res.set('X-TTS-Device', device);
        }
        res.send(response.data);
    } catch (error) {
        console.error('Error proxying to TTS service:', error.message);
        res.status(error.response?.status || 500).send(error.response?.data || 'Error communicating with TTS service');
    }
});

app.listen(PORT, () => {
    console.log(`Web tester running at http://localhost:${PORT}`);
});
