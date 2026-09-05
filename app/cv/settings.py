"""Shared defaults for the tracking-by-detection pipeline."""


# ByteTrack uses detections between 0.10 and the activation threshold
# during its second association stage. The detector must preserve them.
DEFAULT_DETECTION_SCORE_THRESHOLD = 0.10
DEFAULT_TRACK_ACTIVATION_THRESHOLD = 0.25
