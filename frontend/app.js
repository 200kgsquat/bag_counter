const input = document.getElementById("video-input");
const uploadButton = document.getElementById("upload-button");
const dropZone = document.getElementById("drop-zone");

const fileTitle = document.getElementById("file-title");
const fileDescription = document.getElementById("file-description");

const jobCard = document.getElementById("job-card");
const jobIdElement = document.getElementById("job-id");
const statusElement = document.getElementById("job-status");

const progressBar = document.getElementById("progress-bar");
const progressText = document.getElementById("progress-text");

const bagsCount = document.getElementById("bags-count");
const framesCount = document.getElementById("frames-count");
const elapsedTime = document.getElementById("elapsed-time");
const anomalyCount = document.getElementById("anomaly-count");

const anomalySection = document.getElementById("anomaly-section");
const anomalyList = document.getElementById("anomaly-list");

const downloadButton = document.getElementById("download-button");
const errorMessage = document.getElementById("error-message");
const apiStatus = document.getElementById("api-status");
const uploadError = document.getElementById("upload-error");

let selectedFile = null;
let pollingTimer = null;
let currentJobId = null;
let jobGeneration = 0;
let jobFinished = false;
let pollController = null;
let pollFailures = 0;
let uploading = false;

const REQUEST_TIMEOUT_MS = 15000;
const JOB_ID_PATTERN = /^[a-f0-9]{32}$/;
const SAVED_JOB_KEY = "bag-counter.activeJob";

function hasActiveJob() {
    return Boolean(currentJobId) && !jobFinished;
}

function syncUploadControls() {
    if (uploading) {
        input.disabled = true;
        uploadButton.disabled = true;
        uploadButton.textContent = "Uploading...";
        return;
    }

    if (hasActiveJob()) {
        input.disabled = true;
        uploadButton.disabled = true;
        uploadButton.textContent = "Processing current video...";
        return;
    }

    input.disabled = false;
    uploadButton.disabled = !selectedFile;
    uploadButton.textContent = selectedFile
        ? "Start processing"
        : "Select video";
}

async function fetchJson(url, controller = new AbortController()) {
    const timeout = setTimeout(
        () => controller.abort(),
        REQUEST_TIMEOUT_MS
    );

    try {
        const response = await fetch(url, {
            signal: controller.signal,
            cache: "no-store",
        });

        if (!response.ok) {
            const error = new Error(`Request failed (${response.status})`);
            error.status = response.status;
            throw error;
        }

        return await response.json();
    } finally {
        clearTimeout(timeout);
    }
}

async function checkApi() {
    try {
        await fetchJson("/api/health");

        apiStatus.classList.add("online");
        apiStatus.innerHTML =
            '<span class="status-dot"></span> API online';
    } catch {
        apiStatus.classList.remove("online");
        apiStatus.innerHTML =
            '<span class="status-dot"></span> API offline';
    } finally {
        setTimeout(checkApi, 5000);
    }
}

function selectFile(file) {
    if (!file || uploading || hasActiveJob()) return;

    if (!file.name.toLowerCase().endsWith(".mp4")) {
        uploadError.textContent = "Please select an MP4 video.";
        uploadError.classList.remove("hidden");
        return;
    }

    selectedFile = file;

    uploadError.classList.add("hidden");
    fileTitle.textContent = file.name;
    fileDescription.textContent =
        `${(file.size / 1024 / 1024).toFixed(1)} MB`;

    syncUploadControls();
}

input.addEventListener("change", () => {
    selectFile(input.files[0]);
});

dropZone.addEventListener("dragover", (event) => {
    event.preventDefault();

    if (!hasActiveJob() && !uploading) {
        dropZone.classList.add("dragging");
    }
});

dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragging");
});

dropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");

    if (hasActiveJob() || uploading) return;

    selectFile(event.dataTransfer.files[0]);
});

function uploadVideo(file) {
    return new Promise((resolve, reject) => {
        const request = new XMLHttpRequest();

        request.open("POST", "/api/jobs");
        request.timeout = 15 * 60 * 1000;

        request.upload.onprogress = (event) => {
            if (!event.lengthComputable) return;

            const percent = Math.round(
                event.loaded / event.total * 100
            );

            uploadButton.textContent =
                percent < 100
                    ? `Uploading ${percent}%...`
                    : "Waiting for job confirmation...";
        };

        request.onload = () => {
            let data;

            try {
                data = JSON.parse(request.responseText);
            } catch {
                reject(
                    new Error(
                        `Invalid upload response (${request.status})`
                    )
                );
                return;
            }

            if (request.status < 200 || request.status >= 300) {
                reject(
                    new Error(
                        typeof data?.detail === "string"
                            ? data.detail
                            : `Upload failed (${request.status})`
                    )
                );
                return;
            }

            if (!JOB_ID_PATTERN.test(data?.job_id || "")) {
                reject(
                    new Error("The server did not return a valid job ID.")
                );
                return;
            }

            resolve(data);
        };

        const uncertainUpload =
            "Upload confirmation was lost. The server may have accepted the video.";

        request.onerror = () => reject(new Error(uncertainUpload));
        request.ontimeout = () => reject(new Error(uncertainUpload));
        request.onabort = () =>
            reject(new Error("Upload was interrupted."));

        const formData = new FormData();
        formData.append("file", file);

        request.send(formData);
    });
}

uploadButton.addEventListener("click", async () => {
    if (!selectedFile || uploading || hasActiveJob()) return;

    const file = selectedFile;

    uploading = true;
    uploadError.classList.add("hidden");
    syncUploadControls();

    try {
        const data = await uploadVideo(file);

        selectedFile = null;
        input.value = "";

        showJob(data.job_id);
    } catch (error) {
        uploadError.textContent = error.message;
        uploadError.classList.remove("hidden");
    } finally {
        uploading = false;
        syncUploadControls();
    }
});

function showJob(jobId) {
    clearTimeout(pollingTimer);

    if (pollController) {
        pollController.abort();
    }

    currentJobId = jobId;
    jobGeneration += 1;
    jobFinished = false;
    pollFailures = 0;

    try {
        sessionStorage.setItem(SAVED_JOB_KEY, jobId);
    } catch {}

    history.replaceState(
        null,
        "",
        `#job=${encodeURIComponent(jobId)}`
    );

    hideError();

    jobCard.classList.remove("hidden");
    jobIdElement.textContent = jobId;

    bagsCount.textContent = "—";
    framesCount.textContent = "0 / 0";
    elapsedTime.textContent = "—";
    anomalyCount.textContent = "0";

    anomalyList.innerHTML = "";
    anomalySection.classList.add("hidden");
    downloadButton.classList.add("hidden");

    updateStatus("queued");
    updateProgress(0);

    syncUploadControls();
    pollJob(jobId, jobGeneration);
}

function updateProgress(value) {
    const number = Number(value);

    const progress = Number.isFinite(number)
        ? Math.max(0, Math.min(100, number))
        : 0;

    progressBar.style.width = `${progress}%`;
    progressText.textContent = `${progress.toFixed(1)}%`;
}

function updateStatus(status) {
    statusElement.textContent = status;
    statusElement.className = `badge ${status}`;
}

async function pollJob(jobId, generation) {
    if (generation !== jobGeneration || jobFinished) return;

    clearTimeout(pollingTimer);

    const controller = new AbortController();
    pollController = controller;

    let nextDelay = 1000;

    try {
        const job = await fetchJson(
            `/api/jobs/${encodeURIComponent(jobId)}`,
            controller
        );

        if (generation !== jobGeneration) return;

        if (!job || typeof job.status !== "string") {
            throw new Error("Invalid job status response");
        }

        pollFailures = 0;
        hideError();

        renderJob(jobId, job);

        jobFinished =
            job.status === "completed" ||
            job.status === "failed";
    } catch (error) {
        if (generation !== jobGeneration) return;

        if (error.status === 404) {
            jobFinished = true;

            updateStatus("unavailable");
            showError("This job is no longer available on the server.");

            try {
                sessionStorage.removeItem(SAVED_JOB_KEY);
            } catch {}
        } else {
            pollFailures += 1;

            nextDelay = Math.min(
                1000 * 2 ** Math.min(pollFailures, 4),
                10000
            );

            updateStatus("reconnecting");

            showError(
                `Cannot refresh job status. Retrying in ${nextDelay / 1000}s.`
            );
        }
    } finally {
        if (generation === jobGeneration) {
            pollController = null;

            syncUploadControls();

            if (!jobFinished) {
                pollingTimer = setTimeout(
                    () => pollJob(jobId, generation),
                    nextDelay
                );
            }
        }
    }
}

function renderJob(jobId, job) {
    updateStatus(job.status);
    updateProgress(job.progress || 0);

    const processed = job.processed_frames || 0;
    const total = job.total_frames || 0;

    framesCount.textContent = `${processed} / ${total}`;

    if (job.total_bags !== undefined) {
        bagsCount.textContent = job.total_bags;
    }

    if (job.elapsed_seconds !== undefined) {
        elapsedTime.textContent = `${job.elapsed_seconds}s`;
    }

    const anomalies = Array.isArray(job.anomalies)
        ? job.anomalies
        : [];

    anomalyCount.textContent = anomalies.length;

    renderAnomalies(anomalies);

    if (job.status === "completed") {
        updateProgress(100);

        downloadButton.href =
            `/api/jobs/${jobId}/result`;

        downloadButton.classList.remove("hidden");
    }

    if (job.status === "failed") {
        showError(
            job.error || "Processing failed"
        );
    }
}

function renderAnomalies(anomalies, visibleCount = 100) {
    anomalyList.innerHTML = "";

    if (anomalies.length === 0) {
        anomalySection.classList.add("hidden");
        return;
    }

    anomalySection.classList.remove("hidden");

    const fragment = document.createDocumentFragment();

    for (const anomaly of anomalies.slice(0, visibleCount)) {
        const item = document.createElement("div");

        item.className = "anomaly-item";

        item.textContent =
            `${anomaly.type} · ` +
            `track #${anomaly.track_id} · ` +
            `frame ${anomaly.frame_index} · ` +
            `${anomaly.message}`;

        fragment.appendChild(item);
    }

    if (anomalies.length > visibleCount) {
        const more = document.createElement("button");

        more.type = "button";
        more.className = "primary-button";
        more.textContent = "Show next 100 anomalies";

        more.addEventListener("click", () => {
            renderAnomalies(
                anomalies,
                visibleCount + 100
            );
        });

        fragment.appendChild(more);
    }

    anomalyList.appendChild(fragment);
}

function showError(message) {
    errorMessage.textContent = message;
    errorMessage.classList.remove("hidden");
}

function hideError() {
    errorMessage.textContent = "";
    errorMessage.classList.add("hidden");
}

function resumePolling() {
    if (
        currentJobId &&
        !jobFinished &&
        !pollController
    ) {
        clearTimeout(pollingTimer);
        pollJob(currentJobId, jobGeneration);
    }
}

window.addEventListener("online", resumePolling);
window.addEventListener("focus", resumePolling);

document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
        resumePolling();
    }
});

syncUploadControls();
checkApi();

let savedJob =
    new URLSearchParams(
        location.hash.slice(1)
    ).get("job");

if (!savedJob) {
    try {
        savedJob =
            sessionStorage.getItem(SAVED_JOB_KEY);
    } catch {}
}

if (JOB_ID_PATTERN.test(savedJob || "")) {
    showJob(savedJob);
}