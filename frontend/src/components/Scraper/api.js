// Thin API client for the scraper backend.

const BASE = '/api/v1';

// POST /scrape/stream and invoke callbacks for each SSE event.
// onProgress(entry), onCompleted(response), onError({code, message}).
export async function runScrapeStream(payload, { onProgress, onCompleted, onError }) {
  const response = await fetch(`${BASE}/scrape/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    onError({ code: 'HTTP_ERROR', message: `HTTP ${response.status}` });
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const dispatch = (block) => {
    const lines = block.split('\n');
    let event = 'message';
    let data = '';
    for (const line of lines) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data += line.slice(5).trim();
    }
    if (!data) return;
    let parsed;
    try {
      parsed = JSON.parse(data);
    } catch {
      return;
    }
    if (event === 'progress') onProgress(parsed);
    else if (event === 'completed') onCompleted(parsed);
    else if (event === 'error') onError(parsed);
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      dispatch(buffer.slice(0, idx));
      buffer = buffer.slice(idx + 2);
    }
  }
  if (buffer.trim()) dispatch(buffer);
}

export async function fetchTasks(limit = 20, offset = 0) {
  const res = await fetch(`${BASE}/tasks?limit=${limit}&offset=${offset}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchTaskDetail(taskId) {
  const res = await fetch(`${BASE}/tasks/${taskId}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function exportUrl(taskId, format) {
  return `${BASE}/tasks/${taskId}/export?format=${format}`;
}
