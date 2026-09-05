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

let selectedFile = null;
let pollingTimer = null;


async function checkApi() {
    try {
        const response = await fetch("/api/health");

        if (!response.ok) {
            throw new Error("API unavailable");
        }

        apiStatus.classList.add("online");
        apiStatus.innerHTML =
            '<span class="status-dot"></span> API online';
    } catch {
        apiStatus.classList.remove("online");
        apiStatus.innerHTML =
            '<span class="status-dot"></span> API offline';
    }
}


function selectFile(file) {
    if (!file) {
        return;
    }

    if (!file.name.toLowerCase().endsWith(".mp4")) {
        alert("Please select an MP4 video.");
        return;
    }

    selectedFile = file;

    fileTitle.textContent = file.name;

    fileDescription.textContent =
        `${(file.size / 1024 / 1024).toFixed(1)} MB`;

    uploadButton.disabled = false;
}


input.addEventListener("change", () => {
    selectFile(input.files[0]);
});


dropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
});


dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragging");
});


dropZone.addEventListener("drop", (event) => {
    event.preventDefault();

    dropZone.classList.remove("dragging");

    selectFile(event.dataTransfer.files[0]);
});


uploadButton.addEventListener("click", async () => {
    if (!selectedFile) {
        return;
    }

    uploadButton.disabled = true;
    uploadButton.textContent = "Uploading...";

    hideError();

    const formData = new FormData();

    formData.append("file", selectedFile);

    try {
        const response = await fetch("/api/jobs", {
            method: "POST",
            body: formData,
        });

        if (!response.ok) {
            let message = "Upload failed";

            try {
                const data = await response.json();
                message = data.detail || message;
            } catch {
                // response was not JSON
            }

            throw new Error(message);
        }

        const data = await response.json();

        showJob(data.job_id);
    } catch (error) {
        showError(error.message);
    } finally {
        uploadButton.disabled = false;
        uploadButton.textContent = "Start processing";
    }
});


function showJob(jobId) {
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

    pollJob(jobId);
}


function updateProgress(value) {
    const progress = Math.max(
        0,
        Math.min(100, Number(value || 0))
    );

    progressBar.style.width = `${progress}%`;
    progressText.textContent = `${progress.toFixed(1)}%`;
}


function updateStatus(status) {
    statusElement.textContent = status;
    statusElement.className = `badge ${status}`;
}


async function pollJob(jobId) {
    clearTimeout(pollingTimer);

    try {
        const response = await fetch(
            `/api/jobs/${jobId}`
        );

        if (!response.ok) {
            throw new Error("Cannot load job status");
        }

        const job = await response.json();

        renderJob(jobId, job);

        if (
            job.status !== "completed" &&
            job.status !== "failed"
        ) {
            pollingTimer = setTimeout(
                () => pollJob(jobId),
                1000
            );
        }
    } catch (error) {
        showError(error.message);
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
        elapsedTime.textContent =
            `${job.elapsed_seconds}s`;
    }

    const anomalies = job.anomalies || [];

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


function renderAnomalies(anomalies) {
    anomalyList.innerHTML = "";

    if (anomalies.length === 0) {
        anomalySection.classList.add("hidden");
        return;
    }

    anomalySection.classList.remove("hidden");

    for (const anomaly of anomalies) {
        const item = document.createElement("div");

        item.className = "anomaly-item";

        item.textContent =
            `${anomaly.type} · ` +
            `track #${anomaly.track_id} · ` +
            `frame ${anomaly.frame_index} · ` +
            `${anomaly.message}`;

        anomalyList.appendChild(item);
    }
}


function showError(message) {
    errorMessage.textContent = message;
    errorMessage.classList.remove("hidden");
}


function hideError() {
    errorMessage.textContent = "";
    errorMessage.classList.add("hidden");
}


checkApi();

setInterval(checkApi, 5000);