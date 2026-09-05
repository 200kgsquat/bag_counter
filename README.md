# Bag Counter

Computer vision service for detecting, tracking, and counting bags moving on a conveyor belt.

The system accepts MP4 videos, processes them asynchronously on a GPU, tracks individual bags across frames, counts each physical bag once when it crosses a configured boundary, reports suspicious events, and produces an annotated output video.

Reference result for the supplied video:

```text
127 bags
```

---

## Quick Start

### Requirements

You need:

- Docker Desktop / Docker Engine
- Docker Compose
- NVIDIA GPU
- NVIDIA driver with Docker GPU support

You do **not** need to install Python, PyTorch, MMDetection, Redis, Celery, OpenCV or Nginx on the host.

### Windows

```powershell
git clone https://github.com/200kgsquat/bag_counter.git
cd bag_counter
.\start.bat
```

You can also double-click `start.bat` from Windows Explorer.

### Linux

```bash
git clone https://github.com/200kgsquat/bag_counter.git
cd bag_counter
./start.sh
```

The launch scripts automatically:

- check Docker
- check/start the Docker engine when possible
- verify Docker Compose
- check/download the model checkpoint
- build and recreate containers
- wait for FastAPI
- verify the Celery worker
- verify CUDA and the GPU
- verify MMDetection/OpenCV runtime
- verify the model checkpoint inside the worker
- wait for the frontend
- open the web UI when supported

Application:

```text
http://127.0.0.1:3000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

The platform-independent runtime is still Docker Compose:

```bash
docker compose up --build -d
```

---

## Architecture

```text
Browser
   │
   ▼
Nginx
   │
   ▼
FastAPI
   │
   │ enqueue job
   ▼
Redis
   │
   ▼
Celery GPU worker
   │
   ▼
RTMDet
   │
   ▼
ByteTrack
   │
   ▼
LineCrossingCounter
   │
   ▼
AnomalyMonitor
   │
   ▼
output.mp4
```

FastAPI handles HTTP requests, uploads, job state and result delivery.

The ML pipeline runs only inside the Celery worker.

### Why separate API and ML worker?

Video inference is a long-running GPU workload. Running it directly inside an HTTP request would block API workers and create timeout problems.

The API therefore creates a background job and returns immediately.

**Trade-off:** this adds Redis, Celery and distributed job state, but keeps the HTTP layer responsive and allows GPU processing to scale independently.

---

## Processing Pipeline

For each frame:

```text
decode frame
    ↓
RTMDet inference
    ↓
confidence filtering
    ↓
ByteTrack
    ↓
line-crossing logic
    ↓
anomaly monitoring
    ↓
visualization
    ↓
write output frame
```

The final result contains:

- total bag count
- processed frame count
- processing time
- anomaly events
- annotated MP4

---

## Engineering Decisions

### Fine-tuned RTMDet

The original COCO-pretrained detector was not reliable enough for the conveyor domain.

The model was therefore fine-tuned as a single-class detector:

```text
bag
```

**Why:** the largest source of error was domain shift. Tracking cannot recover objects that the detector consistently misses.

**Trade-off:** accuracy improves for this domain, but the model must be revalidated for different cameras, lighting conditions or bag distributions.

---

### Detector abstraction

The rest of the pipeline does not depend directly on MMDetection result objects.

MMDetection is wrapped behind a detector interface.

**Why:** tracking, counting and video-processing logic should operate on generic detections rather than framework-specific structures.

**Trade-off:** this adds a small abstraction layer, but makes the detector replaceable and simplifies testing.

---

### ByteTrack

A physical bag appears in many consecutive frames.

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

**Why:** counting requires persistent object identity across frames.

**Trade-off:** tracking-by-detection can still suffer from ID switches when detections disappear or objects are heavily occluded.

---

### Line crossing instead of counting unique IDs

A tracker ID only tells us that an object existed somewhere in the frame.

That does not guarantee that it actually passed the conveyor counting point.

The counter therefore increments only when a tracked bag crosses a configured boundary in the expected direction.

**Why:** the crossing event matches the physical business event we want to measure.

**Trade-off:** the line is camera-specific and must be configured for a new scene.

---

### Hysteresis

Bounding boxes and track centers naturally jitter around the counting boundary.

Without protection, the same object could appear to repeatedly switch sides.

A dead zone is therefore used around the line.

**Why:** this suppresses false crossings caused by detector/tracker noise.

**Trade-off:** if the dead zone is too large, a real crossing may be detected late or missed.

---

### Recount protection

After a valid crossing, the track ID is stored in:

```text
counted_track_ids
```

The same track cannot increment the counter twice.

**Why:** one physical bag should generate one business event.

**Trade-off:** this assumes tracker identity is sufficiently stable. Severe ID switches can still affect the final count.

---

### Celery + Redis

The API follows an asynchronous job pattern:

```text
POST /jobs
    ↓
job_id
    ↓
Celery task
    ↓
GPU processing
```

The frontend polls:

```http
GET /jobs/{job_id}
```

for progress.

**Why:** full-video inference can take much longer than a normal HTTP request.

**Trade-off:** asynchronous execution adds infrastructure and job-state management, but avoids blocking the web layer.

---

### Lazy model loading and caching

The detector is loaded inside the worker only when needed and then reused for future jobs.

**Why:** loading an MMDetection checkpoint for every video would repeatedly allocate GPU memory and add initialization latency.

**Trade-off:** the first job starts slower and the worker keeps GPU memory allocated while it is alive.

---

### Docker as canonical runtime

The project depends on compatible versions of:

```text
PyTorch       2.1.2
CUDA          11.8
MMCV          2.1.0
MMDetection   3.3.0
NumPy         1.26.4
```

**Why:** OpenMMLab environments are sensitive to version mismatches, especially between CUDA, PyTorch, MMCV and NumPy.

Docker provides one reproducible runtime instead of requiring the reviewer to recreate the environment manually.

**Trade-off:** Docker images are large and the first build can take time.

---

### Host-mounted storage

Each job uses:

```text
data/jobs/<job_id>/
├── input.mp4
└── output.mp4
```

The directory is mounted into both API and worker containers.

**Why:** this is simple, persistent and sufficient for a single-machine deployment.

**Trade-off:** local filesystem storage does not scale well across multiple hosts. A production system would normally use S3-compatible object storage.

---

### OS-specific launch scripts

The repository provides:

```text
Windows -> start.bat
Linux   -> start.sh
```

Both eventually start the same Docker Compose stack.

**Why:** the bootstrap experience differs by operating system, but the actual application runtime should remain identical.

**Trade-off:** there are two small launcher scripts to maintain, while Docker Compose stays the single source of truth for deployment.

---

## Anomaly Detection

Two anomaly types are currently implemented.

### Reverse movement

```text
reverse_movement
```

A tracked bag crosses the counting line in the direction opposite to normal conveyor movement.

**Why:** this can represent real conveyor reversal or a suspicious tracking trajectory that may affect count reliability.

---

### Low confidence near counting line

```text
low_confidence_near_line
```

A detection has unusually low confidence close to the counting boundary.

**Why:** low confidence far away from the line may have no effect on the final metric, while uncertainty at the exact counting point is operationally important.

Anomalies are deduplicated per track where appropriate to avoid repeated alerts for the same object.

---

## API

### Create job

```http
POST /jobs
```

Multipart field:

```text
file=<video.mp4>
```

Example:

```json
{
  "job_id": "a42be87ddf3b4fc88eb11ac3c73fcb63",
  "status": "queued"
}
```

### Job status

```http
GET /jobs/{job_id}
```

During processing the response contains progress information.

After completion it contains:

```text
total_bags
processed_frames
total_frames
elapsed_seconds
anomalies
```

### Download result

```http
GET /jobs/{job_id}/result
```

Returns the annotated MP4.

---

## Model Checkpoint

The worker expects:

```text
checkpoints/bag_detector.pth
```

If the checkpoint is missing, the launch scripts can download:

```text
bag_detector.pth
```

from the latest GitHub Release.

The model is intentionally kept outside normal Git history to avoid storing a large binary directly in the repository.

---

## Docker Services

```text
frontend -> Nginx web UI and /api proxy
api      -> FastAPI job API
redis    -> Celery broker and result backend
worker   -> GPU video processing
```

Check status:

```bash
docker compose ps
```

Logs:

```bash
docker compose logs -f
```

Stop:

```bash
docker compose down
```

---

## Testing

Core counting and anomaly logic is tested independently from MMDetection and GPU inference.

```bash
pytest -q
```

Current result:

```text
13 passed
```

Tests cover:

- bounding-box geometry
- expected-direction crossing
- reverse-direction crossing
- hysteresis
- recount prevention
- multiple independent tracks
- reverse-movement anomaly
- low-confidence anomaly
- anomaly deduplication

### Why not unit-test exact neural-network predictions?

Detector quality is statistical, not deterministic.

Exact model quality should be evaluated on labeled data or with end-to-end regression, while deterministic counting logic is well suited for unit tests.

The supplied video is also used as an end-to-end regression check:

```text
expected count = 127
```

---

## Limitations

The current implementation intentionally targets the supplied conveyor scenario.

Main limitations:

- counting line is configured for this camera geometry
- side-of-line calculation currently treats the boundary as an infinite mathematical line
- ByteTrack can still produce ID switches under severe occlusion
- deployment assumes a single GPU worker
- videos are stored on local disk
- the detector is trained for a specific visual domain

For a larger deployment I would consider:

- per-camera ROI and counting-line configuration
- S3-compatible object storage
- PostgreSQL for durable job metadata
- separate GPU queues
- model/version tracking
- Prometheus metrics
- structured logging
- task retry policies
- integration tests
- model/data drift monitoring

---

## Project Structure

```text
.
├── app/
│   ├── api/
│   │   └── main.py
│   ├── cv/
│   │   ├── anomalies.py
│   │   ├── counter.py
│   │   ├── detector.py
│   │   ├── pipeline.py
│   │   ├── tracker.py
│   │   └── types.py
│   └── worker/
│       ├── celery_app.py
│       └── tasks.py
├── checkpoints/
├── configs/
│   └── rtmdet_bag.py
├── data/
│   └── jobs/
├── frontend/
├── scripts/
│   └── start.ps1
├── tests/
├── compose.yaml
├── Dockerfile
├── Makefile
├── start.bat
├── start.sh
└── README.md
```

---

## Summary

The main engineering problem is not simply:

```text
detect bags
```

It is:

```text
convert noisy frame-level detections
into a reliable physical event:
"this bag crossed the conveyor boundary exactly once"
```

The final processing path is:

```text
detection
    ↓
tracking
    ↓
persistent identity
    ↓
directional crossing
    ↓
recount protection
    ↓
anomaly monitoring
    ↓
asynchronous execution
    ↓
persistent annotated result
```