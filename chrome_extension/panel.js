const baseUrlInput = document.getElementById('baseUrl');
const applicationSelect = document.getElementById('applicationSelect');
const refreshBtn = document.getElementById('refreshBtn');
const openAtsBtn = document.getElementById('openAtsBtn');
const includeMic = document.getElementById('includeMic');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const statusEl = document.getElementById('status');
const tabMeter = document.getElementById('tabMeter');
const micMeter = document.getElementById('micMeter');

let ws;
let audioContext;
let processor;
let tabStream;
let micStream;
let tabSource;
let micSource;
let gainNode;
let isRunning = false;
let authToken = null;
let currentSession = null;
let apiPrefix = '/api';

const setStatus = (text) => {
  statusEl.textContent = text;
};

const updateMeters = (tabLevel, micLevel) => {
  tabMeter.style.width = `${Math.min(tabLevel * 100, 100)}%`;
  micMeter.style.width = `${Math.min(micLevel * 100, 100)}%`;
};

const normalizeStreamUrl = (value) => {
  if (!value) return value;
  if (value.startsWith('http://')) return value.replace('http://', 'ws://');
  if (value.startsWith('https://')) return value.replace('https://', 'wss://');
  return value;
};

const normalizeBaseUrl = (value) => {
  if (!value) return '';
  return value.endsWith('/') ? value.slice(0, -1) : value;
};

const buildApiUrl = (baseUrl, path) => {
  const normalized = normalizeBaseUrl(baseUrl);
  if (!normalized) return '';
  if (normalized.endsWith('/api')) {
    return `${normalized}${path}`;
  }
  return `${normalized}${apiPrefix}${path}`;
};

const downsampleBuffer = (buffer, sampleRate, outSampleRate) => {
  if (outSampleRate === sampleRate) return buffer;
  const ratio = sampleRate / outSampleRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);
  let offset = 0;
  for (let i = 0; i < result.length; i++) {
    const nextOffset = Math.round((i + 1) * ratio);
    let sum = 0;
    let count = 0;
    for (let j = offset; j < nextOffset && j < buffer.length; j++) {
      sum += buffer[j];
      count += 1;
    }
    result[i] = count ? sum / count : 0;
    offset = nextOffset;
  }
  return result;
};

const floatTo16BitPCM = (input) => {
  const output = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    let s = Math.max(-1, Math.min(1, input[i]));
    output[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return output;
};

const connectWebSocket = (url) => {
  ws = new WebSocket(url);
  ws.binaryType = 'arraybuffer';
  ws.onopen = () => setStatus('Connected. Streaming audio...');
  ws.onclose = () => setStatus('Disconnected');
  ws.onerror = () => setStatus('Connection error');
};

const getActiveTab = async () => {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
};

const requestTabCapture = async () => {
  return new Promise((resolve, reject) => {
    let resolved = false;
    const timeout = setTimeout(() => {
      if (resolved) return;
      resolved = true;
      reject(new Error('No capture prompt appeared. Click the extension icon again and retry.'));
    }, 5000);

    chrome.tabCapture.capture(
      { audio: true, video: false },
      (stream) => {
        if (resolved) return;
        resolved = true;
        clearTimeout(timeout);
        if (chrome.runtime.lastError) {
          const message = chrome.runtime.lastError.message || 'Tab capture denied.';
          if (message.includes('invoked for the current page')) {
            reject(
              new Error(
                'Access not granted for this tab. Click the extension icon while the meeting tab is active, then click Start again.'
              )
            );
            return;
          }
          if (message.includes('Chrome pages cannot be captured')) {
            reject(new Error('Chrome internal pages cannot be captured. Switch to the Meet/Teams tab.'));
            return;
          }
          reject(new Error(message));
          return;
        }
        if (!stream) {
          reject(new Error('Tab capture denied.'));
          return;
        }
        resolve(stream);
      }
    );
  });
};

const fetchTokenFromTab = async (tabId) => {
  try {
    const response = await chrome.tabs.sendMessage(tabId, { type: 'ATS_GET_TOKEN' });
    if (response?.token) {
      authToken = response.token;
      await chrome.storage.local.set({ atsAuthToken: authToken });
      if (response.origin) {
        const normalizedOrigin = normalizeBaseUrl(response.origin);
        baseUrlInput.value = normalizedOrigin;
        await chrome.storage.local.set({ atsBaseUrl: normalizedOrigin });
      }
      return authToken;
    }
  } catch (err) {
    return null;
  }
  return null;
};

const fetchApplications = async () => {
  const baseUrl = normalizeBaseUrl(baseUrlInput.value.trim());
  if (!baseUrl || !authToken) {
    setStatus('Open ATS and log in to authenticate the extension.');
    return;
  }
  setStatus('Loading candidates...');
  applicationSelect.innerHTML = '';
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = 'Select a candidate';
  applicationSelect.appendChild(placeholder);

  try {
    let response = await fetch(
      buildApiUrl(baseUrl, `/entities?entity_type=ATS.Application&limit=100`),
      {
        headers: { Authorization: `Bearer ${authToken}` },
      }
    );
    if (response.status === 404 && apiPrefix === '/api') {
      apiPrefix = '';
      chrome.storage.local.set({ atsApiPrefix: apiPrefix });
      response = await fetch(
        buildApiUrl(baseUrl, `/entities?entity_type=ATS.Application&limit=100`),
        {
          headers: { Authorization: `Bearer ${authToken}` },
        }
      );
    }
    if (!response.ok) {
      setStatus('Unable to load candidates. Check authentication.');
      return;
    }
    const data = await response.json();
    const items = Array.isArray(data) ? data : data.items || [];
    items.forEach((item) => {
      const option = document.createElement('option');
      option.value = item.entity_id;
      const candidateName = item.data?.candidate_name || 'Unknown candidate';
      const jobTitle = item.data?.job_title || 'Unknown role';
      option.textContent = `${candidateName} — ${jobTitle}`;
      applicationSelect.appendChild(option);
    });
    setStatus(items.length ? 'Ready.' : 'No applications found.');
  } catch (err) {
    setStatus('Failed to load candidates.');
  }
};

const fetchWithTimeout = (url, options, timeoutMs = 10000) => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...options, signal: controller.signal }).finally(() => clearTimeout(timeout));
};

const createSession = async (baseUrl, applicationId) => {
  let response = await fetchWithTimeout(buildApiUrl(baseUrl, `/transcription/sessions`), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({
      entity_type: 'ATS.Application',
      entity_id: applicationId,
      capture_mode: 'local',
    }),
  });
  if (response.status === 404 && apiPrefix === '/api') {
    apiPrefix = '';
    chrome.storage.local.set({ atsApiPrefix: apiPrefix });
    response = await fetchWithTimeout(buildApiUrl(baseUrl, `/transcription/sessions`), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({
        entity_type: 'ATS.Application',
        entity_id: applicationId,
        capture_mode: 'local',
      }),
    });
  }
  if (!response.ok) {
    throw new Error('Failed to create transcription session');
  }
  return response.json();
};

const startCapture = async () => {
  if (isRunning) return;
  if (!authToken) {
    setStatus('Open ATS and log in, then try again.');
    return;
  }
  const applicationId = applicationSelect.value;
  if (!applicationId) {
    setStatus('Select a candidate first.');
    return;
  }

  const baseUrl = normalizeBaseUrl(baseUrlInput.value.trim());
  if (!baseUrl) {
    setStatus('Enter the ATS base URL.');
    return;
  }

  setStatus('Requesting tab capture permission...');
  try {
    const stream = await requestTabCapture();
    tabStream = stream;

    try {
      setStatus('Creating transcription session...');
      const sessionResponse = await createSession(baseUrl, applicationId);
      currentSession = sessionResponse.session;
      const token = sessionResponse.participant_token;
      const wsUrl = normalizeStreamUrl(
        `${normalizeBaseUrl(baseUrl)}${apiPrefix}/transcription/sessions/${currentSession.id}/stream?token=${encodeURIComponent(
          token
        )}`
      );
      connectWebSocket(wsUrl);
    } catch (err) {
      if (err?.name === 'AbortError') {
        setStatus('Session creation timed out. Check backend/CORS.');
      } else {
        setStatus('Failed to create transcription session.');
      }
      tabStream.getTracks().forEach((t) => t.stop());
      tabStream = null;
      return;
    }

    if (includeMic.checked) {
      try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      } catch (err) {
        micStream = null;
        setStatus('Mic permission denied. Streaming tab audio only.');
      }
    }

      audioContext = new AudioContext();
      processor = audioContext.createScriptProcessor(4096, 1, 1);
      gainNode = audioContext.createGain();

      tabSource = audioContext.createMediaStreamSource(tabStream);
      tabSource.connect(gainNode);

      if (micStream) {
        micSource = audioContext.createMediaStreamSource(micStream);
        micSource.connect(gainNode);
      }

      gainNode.connect(processor);
      processor.connect(audioContext.destination);

      processor.onaudioprocess = (event) => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        const inputData = event.inputBuffer.getChannelData(0);
        const downsampled = downsampleBuffer(inputData, audioContext.sampleRate, 16000);
        const pcm = floatTo16BitPCM(downsampled);
        ws.send(pcm.buffer);

        const peak = Math.max(...inputData.map((v) => Math.abs(v)));
        updateMeters(peak, micStream ? peak : 0);
      };

    isRunning = true;
    startBtn.disabled = true;
    stopBtn.disabled = false;
    setStatus('Capturing tab audio...');
  } catch (err) {
    setStatus(err?.message || 'Tab capture denied. Make sure the meeting tab is active.');
  }
};

const stopCapture = () => {
  if (!isRunning) return;
  isRunning = false;
  startBtn.disabled = false;
  stopBtn.disabled = true;

  if (processor) {
    processor.disconnect();
    processor.onaudioprocess = null;
  }
  if (gainNode) gainNode.disconnect();
  if (tabSource) tabSource.disconnect();
  if (micSource) micSource.disconnect();
  if (tabStream) tabStream.getTracks().forEach((t) => t.stop());
  if (micStream) micStream.getTracks().forEach((t) => t.stop());
  if (audioContext) audioContext.close();
  if (ws) ws.close();

  updateMeters(0, 0);
  setStatus('Stopped');
};

const init = async () => {
  const stored = await chrome.storage.local.get(['atsAuthToken', 'atsBaseUrl']);
  if (stored?.atsBaseUrl) {
    baseUrlInput.value = stored.atsBaseUrl;
  }
  if (stored?.atsAuthToken) {
    authToken = stored.atsAuthToken;
  }
  apiPrefix = stored?.atsApiPrefix || '/api';

  const activeTab = await getActiveTab();
  if (activeTab?.id) {
    await fetchTokenFromTab(activeTab.id);
  }

  if (!authToken) {
    setStatus('Open ATS and log in to authenticate the extension.');
  } else {
    await fetchApplications();
  }
};

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === 'ATS_TOKEN' && message.token) {
    authToken = message.token;
    chrome.storage.local.set({ atsAuthToken: authToken });
    if (message.origin) {
      const normalizedOrigin = normalizeBaseUrl(message.origin);
      baseUrlInput.value = normalizedOrigin;
      chrome.storage.local.set({ atsBaseUrl: normalizedOrigin });
    }
    fetchApplications();
  }
});

baseUrlInput.addEventListener('change', async () => {
  const value = normalizeBaseUrl(baseUrlInput.value.trim());
  baseUrlInput.value = value;
  await chrome.storage.local.set({ atsBaseUrl: value });
});

refreshBtn.addEventListener('click', fetchApplications);
openAtsBtn.addEventListener('click', () => {
  const baseUrl = normalizeBaseUrl(baseUrlInput.value.trim()) || 'http://localhost:5173';
  chrome.tabs.create({ url: baseUrl });
});
startBtn.addEventListener('click', startCapture);
stopBtn.addEventListener('click', stopCapture);

init();
