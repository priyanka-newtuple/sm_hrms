const TOKEN_KEY = 'ats_access_token';

const getToken = () => {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch (err) {
    return null;
  }
};

const notifyToken = () => {
  const token = getToken();
  if (!token) return;
  chrome.runtime.sendMessage({ type: 'ATS_TOKEN', token, origin: window.location.origin });
};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === 'ATS_GET_TOKEN') {
    sendResponse({ token: getToken(), origin: window.location.origin });
    return true;
  }
  return false;
});

window.addEventListener('storage', (event) => {
  if (event.key === TOKEN_KEY) {
    notifyToken();
  }
});

window.addEventListener('token-changed', notifyToken);

notifyToken();
