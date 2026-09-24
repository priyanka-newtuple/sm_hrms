# Transcription Bot Service (Scaffold)

This is a minimal scaffold for a headless meeting bot service. The backend calls this service to join meetings and stream audio to the transcription websocket.

## Expected Endpoints

- `POST /bot/start`
  - Payload: `{ session_id, meeting_url, stream_url, token, meeting_platform }`
  - Action: Join the meeting and start streaming PCM audio to `stream_url` with `token`.

- `POST /bot/stop`
  - Payload: `{ session_id }`
  - Action: Leave the meeting and stop streaming.

## Implementation Notes

- Use Playwright/Chromium to automate Google Meet/Teams in headless mode.
- Capture system audio via a virtual audio device (e.g., PulseAudio + virtual sink).
- Stream raw PCM16 @ 16kHz to the backend websocket.

This scaffold does not implement meeting automation. It provides the contract and a place to implement the bot logic.
