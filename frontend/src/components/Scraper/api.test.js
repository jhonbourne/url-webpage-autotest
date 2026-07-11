import { runScrapeStream } from './api';

// Build a fake fetch Response whose body streams the given string in chunks.
function streamingResponse(text, chunkSize = 16) {
  const bytes = new TextEncoder().encode(text);
  let pos = 0;
  return {
    ok: true,
    body: {
      getReader() {
        return {
          read() {
            if (pos >= bytes.length) return Promise.resolve({ done: true });
            const slice = bytes.slice(pos, pos + chunkSize);
            pos += chunkSize;
            return Promise.resolve({ done: false, value: slice });
          },
        };
      },
    },
  };
}

const SSE =
  'event: progress\ndata: {"step":"fetch_page","message":"ok"}\n\n' +
  'event: progress\ndata: {"step":"validate_result","message":"validation passed"}\n\n' +
  'event: completed\ndata: {"status":"completed","task_id":"abc"}\n\n';

test('parses SSE progress and completed events across chunk boundaries', async () => {
  global.fetch = jest.fn(() => Promise.resolve(streamingResponse(SSE, 7)));

  const progress = [];
  let completed = null;
  let error = null;

  await runScrapeStream(
    { url: 'https://x.com', prompt: 'p' },
    {
      onProgress: (e) => progress.push(e),
      onCompleted: (r) => (completed = r),
      onError: (e) => (error = e),
    }
  );

  expect(error).toBeNull();
  expect(progress.map((p) => p.step)).toEqual(['fetch_page', 'validate_result']);
  expect(completed).toEqual({ status: 'completed', task_id: 'abc' });
});

test('reports a non-ok response as an error', async () => {
  global.fetch = jest.fn(() => Promise.resolve({ ok: false, status: 500 }));

  let error = null;
  await runScrapeStream({ url: 'https://x.com' }, {
    onProgress: () => {},
    onCompleted: () => {},
    onError: (e) => (error = e),
  });

  expect(error).toEqual({ code: 'HTTP_ERROR', message: 'HTTP 500' });
});
