const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const { JSDOM } = createRequire(path.resolve(__dirname, '../frontend/package.json'))('jsdom');
const html = fs.readFileSync(path.resolve(__dirname, '../frontend/index.html'), 'utf8');
const source = fs.readFileSync(path.resolve(__dirname, '../frontend/app.js'), 'utf8');
const A = 'a'.repeat(32), B = 'b'.repeat(32);
const response = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
const completed = (count = 127) => response({ status: 'completed', total_bags: count, progress: 100 });
const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };

function app(t, jobFetch, { hash = '', code = source } = {}) {
    const dom = new JSDOM(html, { url: `http://localhost:3000/${hash}`, runScripts: 'outside-only' });
    const w = dom.window;
    const timers = new Map();
    let nextId = 0;
    w.setTimeout = (fn, delay) => { timers.set(++nextId, { fn, delay }); return nextId; };
    w.clearTimeout = (id) => timers.delete(id);
    w.setInterval = () => 0;
    w.fetch = (url, options = {}) => url === '/api/health'
        ? Promise.resolve(response({ status: 'ok' })) : jobFetch(url, options);
    const uploads = [];
    w.XMLHttpRequest = class {
        constructor() { this.upload = {}; uploads.push(this); }
        open() {}
        send() {}
    };
    w.eval(code);
    t.after(() => w.close());
    return {
        w, timers, uploads,
        el: (id) => w.document.getElementById(id),
        async tick(delay) {
            await flush();
            const entry = [...timers].find(([, timer]) => timer.delay === delay);
            assert.ok(entry, `No callback scheduled for ${delay}ms`);
            timers.delete(entry[0]); entry[1].fn(); await flush();
        },
    };
}

for (const failure of ['http503', 'network', 'invalidJson']) {
    test(`status polling recovers after ${failure}`, async (t) => {
        let calls = 0;
        const ui = app(t, async () => {
            if (++calls > 1) return completed();
            if (failure === 'network') throw new TypeError('Failed to fetch');
            if (failure === 'invalidJson') return { ok: true, json: async () => { throw new SyntaxError('bad JSON'); } };
            return response({}, 503);
        });
        ui.w.showJob(A); await flush();
        assert.equal(ui.el('job-status').textContent, 'reconnecting');
        await ui.tick(2000);
        assert.equal(ui.el('job-status').textContent, 'completed');
        assert.equal(ui.el('bags-count').textContent, '127');
        assert.equal(ui.el('download-button').classList.contains('hidden'), false);
        assert.equal(ui.el('error-message').classList.contains('hidden'), true);
        assert.equal(calls, 2);
    });
}

test('stalled response body times out and polling resumes', async (t) => {
    let calls = 0;
    const ui = app(t, async (url, { signal }) => {
        if (++calls > 1) return completed();
        return { ok: true, json: () => new Promise((resolve, reject) => {
            signal.addEventListener('abort', () => reject(new Error('aborted')));
        }) };
    });
    ui.w.showJob(A); await flush();
    await ui.tick(15000);
    assert.equal(ui.el('job-status').textContent, 'reconnecting');
    await ui.tick(2000);
    assert.equal(ui.el('job-status').textContent, 'completed');
});

test('late response from an old job cannot overwrite the new one', async (t) => {
    let finishOld;
    const ui = app(t, (url) => url.endsWith(A)
        ? new Promise((resolve) => { finishOld = resolve; }) : Promise.resolve(completed(9)));
    ui.w.showJob(A);
    ui.w.showJob(B); await flush();
    finishOld(completed(1000)); await flush();
    assert.equal(ui.el('job-id').textContent, B);
    assert.equal(ui.el('bags-count').textContent, '9');
    assert.equal(ui.el('download-button').getAttribute('href'), `/api/jobs/${B}/result`);
});

test('reload restores the job from its URL without another upload', async (t) => {
    const ui = app(t, async () => completed(), { hash: `#job=${A}` });
    await flush();
    assert.equal(ui.el('job-id').textContent, A);
    assert.equal(ui.el('job-status').textContent, 'completed');
    assert.equal(ui.uploads.length, 0);
});

test('an upload failure is visible before a job exists, and duplicate clicks are blocked', async (t) => {
    const ui = app(t, async () => completed());
    ui.w.selectFile(new ui.w.File(['video'], 'clip.mp4'));
    ui.el('upload-button').click();
    ui.el('upload-button').dispatchEvent(new ui.w.Event('click'));
    ui.w.selectFile(new ui.w.File(['another'], 'other.mp4'));
    assert.equal(ui.uploads.length, 1);
    assert.equal(ui.el('file-title').textContent, 'clip.mp4');
    const xhr = ui.uploads[0]; xhr.status = 500; xhr.responseText = '{"detail":"Upload failed"}'; xhr.onload();
    await flush();
    assert.equal(ui.el('upload-error').classList.contains('hidden'), false);
    assert.equal(ui.el('upload-error').closest('#job-card'), null);
    assert.equal(ui.el('upload-button').disabled, false);
});

test('large anomaly results are displayed in batches without losing the total', async (t) => {
    const anomalies = Array.from({ length: 5000 }, (_, i) => ({ type: 'test', track_id: i, frame_index: i, message: 'event' }));
    const ui = app(t, async () => response({ status: 'completed', anomalies }));
    ui.w.showJob(A); await flush();
    assert.equal(ui.el('anomaly-count').textContent, '5000');
    assert.equal(ui.el('anomaly-list').querySelectorAll('.anomaly-item').length, 100);
    ui.el('anomaly-list').querySelector('button').click();
    assert.equal(ui.el('anomaly-list').querySelectorAll('.anomaly-item').length, 200);
});

test('a deleted job stops polling with a visible message', async (t) => {
    const ui = app(t, async () => response({}, 404));
    ui.w.showJob(A); await flush();
    assert.equal(ui.el('job-status').textContent, 'unavailable');
    assert.equal(ui.el('error-message').classList.contains('hidden'), false);
    assert.equal([...ui.timers.values()].some(({ delay }) => delay === 1000 || delay === 2000), false);
});
