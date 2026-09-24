# ATS Transcription Capture Extension

This Chrome extension captures the active tab audio (Google Meet/Teams in the browser) and optionally the microphone, then streams PCM audio to ATS over WebSocket. It opens as a right-side panel in Chrome.

## Install (Developer Mode)

1. Open `chrome://extensions`.
2. Enable **Developer mode** (top right).
3. Click **Load unpacked** and select the `chrome_extension` folder in this repo.

## Use

1. Open ATS and make sure you are logged in.
2. Click the extension icon to open the side panel.
3. The extension will read your ATS session and load candidate applications. Use **Open ATS** if needed.
4. Select the candidate and click **Start transcription**.
5. Choose the Meet/Teams tab and ensure **Share audio** is enabled.
6. Click **Stop** when finished.

Notes:
- The extension streams 16kHz mono PCM frames over WebSocket.
- Make sure the tab you want to capture is active when you start.
