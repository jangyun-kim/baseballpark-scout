const WS_URL = "ws://127.0.0.1:8777";
let sock = null;

function connect() {
  try {
    sock = new WebSocket(WS_URL);
    sock.onopen = () => console.log("bridge connected");
    sock.onclose = () => { sock = null; setTimeout(connect, 2000); };
    sock.onerror = () => { try { sock.close(); } catch (e) {} };
  } catch (e) {
    setTimeout(connect, 2000);
  }
}
connect();

async function report() {
  if (!sock || sock.readyState !== WebSocket.OPEN) return;
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab || tab.id === undefined) return;
    const zoom = await chrome.tabs.getZoom(tab.id);
    sock.send(JSON.stringify({ zoom: Math.round(zoom * 100), url: tab.url || "" }));
  } catch (e) {
    console.error("zoom report failed", e);
  }
}

setInterval(report, 400);
chrome.tabs.onZoomChange.addListener(report);
chrome.tabs.onActivated.addListener(report);
