# Bag Counter — CV baseline

First milestone for the conveyor bag-counting assignment.

This version intentionally does **detection only**:

`video -> MMDetection -> annotated video + detection statistics`

Tracking and counting are added only after validating detector behavior on the
provided `input.mp4`.

## Layout

```text
app/cv/types.py            framework-independent CV data types
app/cv/detector.py         MMDetection adapter
app/cv/video_processor.py  video I/O and visualization
scripts/run_baseline.py    CLI entry point
```

## Environment

Recommended starting point: Python 3.10.

Install PyTorch appropriate for your CUDA environment first.

Then install the OpenMMLab stack:

```bash
pip install -U openmim
mim install "mmengine>=0.7.1,<1.0.0"
mim install "mmcv>=2.0.0rc4,<2.2.0"
pip install "mmdet==3.3.0"

pip install -r requirements.txt
```

Download an RTMDet-tiny COCO config/checkpoint using MIM or from the
official MMDetection model zoo.

Put the supplied video at:

```text
data/input.mp4
```

Run:

```bash
python scripts/run_baseline.py \
  --input data/input.mp4 \
  --output outputs/baseline.mp4 \
  --config checkpoints/rtmdet_tiny_8xb32-300e_coco.py \
  --checkpoint checkpoints/rtmdet_tiny_8xb32-300e_coco.pth \
  --device cuda:0 \
  --score-threshold 0.25
```

For CPU smoke testing, use `--device cpu`.

Outputs:

```text
outputs/baseline.mp4
outputs/baseline.json
```

The JSON is deliberately useful for domain-shift diagnosis: it shows which
COCO classes the detector assigns to objects in the conveyor video.

## Why no counter yet?

A detection is not a unique physical bag. One bag can be detected in dozens
of consecutive frames. Counting starts only after tracking assigns persistent
track IDs.
