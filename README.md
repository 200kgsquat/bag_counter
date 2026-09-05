# Bag Counter

Computer vision service for detecting, tracking, and counting bags moving on a conveyor belt.

The system processes uploaded MP4 videos asynchronously, tracks individual bags across frames, counts each physical bag once when it crosses a configured counting line, detects suspicious events, and produces an annotated output video.

The project is built with:

- MMDetection / RTMDet for object detection
- ByteTrack for multi-object tracking
- FastAPI for the HTTP API
- Celery + Redis for asynchronous video processing
- OpenCV for video I/O and visualization
- Docker Compose for reproducible deployment
- Nginx + a lightweight frontend for interaction

---

## Architecture

```text
                    ┌──────────────────┐
                    │     Browser      │
                    │  localhost:3000  │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │      Nginx       │
                    │ static frontend  │
                    │   /api proxy     │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │     FastAPI      │
                    │ upload / status  │
                    │     result       │
                    └────────┬─────────┘
                             │
                       enqueue task
                             │
                             ▼
                    ┌──────────────────┐
                    │      Redis       │
                    │ broker + backend │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Celery Worker   │
                    │       GPU        │
                    └────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
     ┌────────────────┐            ┌────────────────┐
     │   MMDetection  │            │     OpenCV     │
     │ RTMDet detector│            │ video I/O      │
     └───────┬────────┘            └────────────────┘
             │
             ▼
     ┌────────────────┐
     │    ByteTrack   │
     │ persistent IDs │
     └───────┬────────┘
             │
             ▼
     ┌────────────────┐
     │ Line Crossing  │
     │    Counter     │
     └───────┬────────┘
             │
             ▼
     ┌────────────────┐
     │    Anomaly     │
     │    Monitor     │
     └───────┬────────┘
             │
             ▼
        output.mp4
```

The HTTP server does not perform ML inference directly.

FastAPI only stores the uploaded video and enqueues a Celery task. The GPU-heavy detection and tracking pipeline runs inside a separate worker process.

This keeps HTTP requests responsive while long-running videos are processed in the background.

---

## Counting approach

A detection is not equivalent to a physical object.

The same bag can be detected in dozens of consecutive frames, so simply counting detections would massively overestimate the number of bags.

The processing pipeline is therefore:

```text
frame
  ↓
object detection
  ↓
ByteTrack
  ↓
stable track ID
  ↓
line-crossing detection
  ↓
count once per track ID
```

Each tracked bag receives a persistent `track_id`.

A bag is counted only when its center moves from one stable side of the counting line to the other in the expected conveyor direction.

The counter also maintains:

```text
counted_track_ids
```

so a track cannot be counted twice.

### Hysteresis

Bounding boxes naturally jitter between frames.

Without protection, an object located close to the counting line could repeatedly switch sides and produce false crossing events.

A dead zone around the line is therefore used:

```text
       side A
          |
----------|----------
    hysteresis zone
----------|----------
          |
       side B
```

Objects inside the hysteresis region are ignored until they move confidently onto one side of the line.

This reduces false counts caused by detector and tracker noise.

---

## Detector

The detector is based on RTMDet from MMDetection.

The original COCO-pretrained detector was not sufficiently reliable for the conveyor domain, so the model was fine-tuned as a single-class detector:

```text
class: bag
```

Training configuration:

```text
configs/rtmdet_bag.py
```

The production worker expects the resulting model at:

```text
checkpoints/bag_detector.pth
```

The detector instance is created lazily inside the Celery worker and cached between jobs.

This is intentional: loading an MMDetection checkpoint onto the GPU for every video would add unnecessary initialization latency and GPU memory churn.

---

## Model checkpoint

The trained checkpoint is intentionally not committed to the Git repository.

Before running inference, place the trained model here:

```text
checkpoints/bag_detector.pth
```

Expected structure:

```text
checkpoints/
├── bag_detector.pth
└── .gitkeep
```

The Docker worker mounts the directory read-only:

```text
./checkpoints:/app/checkpoints:ro
```

If the checkpoint is missing, the worker will fail when the first video-processing task attempts to initialize the detector.

---

## Anomaly detection

The pipeline reports events that may indicate unreliable counting or unusual conveyor behavior.

Currently implemented anomalies:

### Reverse movement

A tracked bag crosses the counting line in the direction opposite to the expected conveyor movement.

```text
type = reverse_movement
```

Possible causes include:

- conveyor reversal
- object moving backward
- unusual tracking trajectory

### Low confidence near count line

A tracked object has unusually low detector confidence while close to the counting line.

```text
type = low_confidence_near_line
```

This is useful because detections close to the counting boundary have a higher impact on the final count.

Anomaly events include:

```json
{
  "type": "reverse_movement",
  "frame_index": 1234,
  "track_id": 42,
  "message": "Bag crossed count line in reverse direction"
}
```

The same anomaly type is reported at most once per track.

---

## Asynchronous processing

Video processing can take significantly longer than a normal HTTP request.

For that reason the API follows a job-based asynchronous pattern.

### 1. Upload video

```http
POST /jobs
```

The API:

1. validates the file
2. creates a unique job ID
3. stores the source video
4. enqueues a Celery task
5. immediately returns `202 Accepted`

Example response:

```json
{
  "job_id": "a42be87ddf3b4fc88eb11ac3c73fcb63",
  "status": "queued"
}
```

### 2. Poll job status

```http
GET /jobs/{job_id}
```

Queued:

```json
{
  "job_id": "...",
  "status": "queued",
  "progress": 0.0
}
```

Processing:

```json
{
  "job_id": "...",
  "status": "processing",
  "progress": 54.2,
  "processed_frames": 2710,
  "total_frames": 5000
}
```

Completed:

```json
{
  "job_id": "...",
  "status": "completed",
  "progress": 100.0,
  "total_bags": 127,
  "processed_frames": 5000,
  "total_frames": 5000,
  "elapsed_seconds": 123.4,
  "anomalies": []
}
```

### 3. Download result

```http
GET /jobs/{job_id}/result
```

Returns the annotated MP4 file after processing completes.

---

## Persistent storage

Each processing job has its own directory:

```text
data/jobs/<job_id>/
├── input.mp4
└── output.mp4
```

The host directory is mounted into both the API and worker containers:

```text
./data:/app/data
```

As a result:

- uploaded videos survive container restarts
- output videos survive container restarts
- API and worker operate on the same files
- generated videos can be inspected directly from the host

---

## Docker services

The application consists of four services.

### `frontend`

Nginx container serving the web UI.

```text
http://127.0.0.1:3000
```

Requests under `/api/` are proxied to FastAPI.

### `api`

FastAPI service.

```text
http://127.0.0.1:8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

Health endpoint:

```text
http://127.0.0.1:8000/health
```

### `redis`

Used as:

- Celery message broker
- Celery result backend

### `worker`

Celery worker responsible for GPU inference and video processing.

The worker executes:

```text
MMDetection
    ↓
ByteTrack
    ↓
LineCrossingCounter
    ↓
AnomalyMonitor
    ↓
annotated MP4
```

---

## Requirements

Recommended environment:

- Docker Desktop / Docker Engine
- Docker Compose
- NVIDIA GPU
- NVIDIA drivers with Docker GPU support

The Docker image uses:

```text
PyTorch 2.1.2
CUDA 11.8
MMCV 2.1.0
MMDetection 3.3.0
NumPy 1.26.4
```

NumPy is intentionally pinned below 2.x because this OpenMMLab / PyTorch stack expects the NumPy 1.x ABI.

---

## Running the application

### 1. Clone repository

```bash
git clone https://github.com/200kgsquat/bag_counter.git
cd bag_counter
```

### 2. Add model checkpoint

Place the trained model at:

```text
checkpoints/bag_detector.pth
```

Verify:

```bash
ls checkpoints
```

Expected:

```text
bag_detector.pth
```

On PowerShell:

```powershell
Test-Path checkpoints\bag_detector.pth
```

Expected:

```text
True
```

### 3. Verify GPU access from Docker

For NVIDIA GPUs:

```bash
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

### 4. Start application

Using Make:

```bash
make app
```

or directly:

```bash
docker compose up --build -d
```

### 5. Check services

```bash
docker compose ps
```

Expected services:

```text
api
frontend
redis
worker
```

### 6. Check API

```bash
curl http://127.0.0.1:8000/health
```

Expected:

```json
{"status":"ok"}
```

### 7. Open frontend

```text
http://127.0.0.1:3000
```

Upload an MP4 video and wait for processing to complete.

---

## Makefile commands

Start/build application:

```bash
make app
```

Build containers:

```bash
make build
```

Start existing containers:

```bash
make up
```

Stop containers:

```bash
make down
```

Show service status:

```bash
make status
```

Follow all logs:

```bash
make logs
```

Worker logs:

```bash
make worker-logs
```

API logs:

```bash
make api-logs
```

Frontend logs:

```bash
make frontend-logs
```

---

## API examples

### Upload video

```bash
curl -X POST \
  -F "file=@input.mp4" \
  http://127.0.0.1:8000/jobs
```

### Get status

```bash
curl \
  http://127.0.0.1:8000/jobs/<job_id>
```

### Download result

```bash
curl \
  -o output.mp4 \
  http://127.0.0.1:8000/jobs/<job_id>/result
```

---

## Project structure

```text
.
├── app/
│   ├── api/
│   │   └── main.py
│   │
│   ├── cv/
│   │   ├── anomalies.py
│   │   ├── counter.py
│   │   ├── detector.py
│   │   ├── pipeline.py
│   │   ├── tracker.py
│   │   └── types.py
│   │
│   └── worker/
│       ├── celery_app.py
│       └── tasks.py
│
├── checkpoints/
│   └── bag_detector.pth
│
├── configs/
│   └── rtmdet_bag.py
│
├── data/
│   └── jobs/
│
├── frontend/
│   ├── app.js
│   ├── Dockerfile
│   ├── index.html
│   ├── nginx.conf
│   └── styles.css
│
├── scripts/
├── tests/
├── compose.yaml
├── Dockerfile
├── Makefile
└── README.md
```

---

## Processing pipeline

For every video frame:

```text
1. Read frame
2. Run RTMDet inference
3. Filter detections by confidence
4. Update ByteTrack
5. Update line-crossing counter
6. Detect anomalies
7. Draw tracks and counting line
8. Draw total count / FPS
9. Write output frame
10. Update Celery task progress
```

The final result contains:

```text
total bag count
processed frame count
processing time
anomaly list
annotated output video
```

---

## Reference result

For the provided conveyor video and the fine-tuned checkpoint used during development, the final pipeline produces:

```text
127 bags
```

This value was used as an end-to-end regression check while refactoring the detector, tracker, counting logic, anomaly monitor, and asynchronous processing pipeline.

---

## Design decisions

### Why tracking instead of counting detections?

A physical bag appears in many frames.

Tracking converts frame-level detections into persistent object identities.

Without tracking:

```text
1 bag × 40 frames ≈ 40 detections
```

With tracking:

```text
40 detections
      ↓
track #17
      ↓
1 physical bag
```

### Why line crossing?

Counting every unique tracker ID is also unsafe.

A bag may appear only briefly at the edge of the scene, or a tracker may create an ID before the object actually passes through the conveyor's counting region.

A crossing event provides a clear business event:

```text
bag crossed the required conveyor boundary
```

### Why ByteTrack?

ByteTrack works well for online multi-object tracking and can associate detections across frames without requiring a separate appearance embedding model.

This keeps the pipeline relatively lightweight while still providing persistent identities for counting.

### Why Celery?

Inference over a full video is a long-running operation.

Executing it directly inside an HTTP request would:

- block API workers
- create request timeout problems
- reduce service concurrency
- couple web-serving latency to GPU workload

Celery separates request handling from compute-heavy inference.

### Why cache the detector?

Model initialization is expensive.

The worker therefore loads the detector once and reuses it for subsequent tasks.

---

## Limitations

### Counting line is currently video-specific

The counting line is defined relative to frame dimensions and was tuned for the supplied conveyor camera.

A more general system could provide:

- per-camera configuration
- user-defined counting regions
- automatic conveyor geometry calibration

### Infinite-line crossing calculation

The current side-of-line calculation mathematically treats the counting boundary as an infinite line.

For the supplied camera this is sufficient because relevant conveyor trajectories pass through the intended counting region.

A more general implementation should additionally verify that the crossing occurs within the finite line segment or inside a configured region of interest.

### Tracker identity switches

Like all tracking-by-detection systems, ByteTrack can occasionally produce ID switches when objects are heavily occluded or detections disappear for an extended period.

Possible future improvements include:

- tracker parameter tuning
- appearance-based ReID
- motion constraints based on conveyor geometry

### Single GPU worker

The current deployment is designed around one GPU worker.

For higher throughput, the architecture could be extended to:

```text
API
 ↓
queue
 ↓
GPU worker 1
GPU worker 2
GPU worker 3
```

with routing or one Celery queue per GPU.

### Local filesystem storage

Videos are stored on a shared Docker-mounted filesystem.

For multi-host deployments this should be replaced with shared object storage such as S3-compatible storage.

---

## Production improvements

For a larger production system I would consider:

- S3-compatible object storage instead of local files
- PostgreSQL for persistent job metadata
- separate queues for CPU and GPU workloads
- structured logging
- Prometheus metrics
- GPU utilization monitoring
- task retries and failure policies
- upload size validation
- authentication and rate limiting
- configurable camera/counting-line profiles
- finite ROI-based crossing
- automated integration tests
- model versioning
- model/data drift monitoring

---

## Testing

Run:

```bash
pytest
```

The most important logic to cover with unit tests is independent of MMDetection and GPU inference:

- bounding-box geometry
- expected-direction line crossing
- reverse-direction crossing
- hysteresis around the count line
- prevention of repeated counting
- anomaly deduplication

This allows core counting behavior to be tested quickly without loading the neural network.

---

## Summary

The main engineering goal of this project is not merely detecting bags.

It is converting noisy frame-level detections into a reliable physical event:

```text
"This bag crossed the conveyor counting boundary exactly once."
```

The complete path is:

```text
detection
→ tracking
→ persistent identity
→ directional crossing
→ recount protection
→ anomaly monitoring
→ asynchronous processing
→ persistent annotated result
```