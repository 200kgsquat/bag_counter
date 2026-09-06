import sys
from types import ModuleType, SimpleNamespace

import pytest

from scripts.check_runtime import main


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    """Substitute the GPU runtime to test startup success/failure reporting."""
    events = []
    checkpoint = tmp_path / "model.pth"
    config = tmp_path / "model.py"
    checkpoint.touch()
    config.touch()

    cuda = SimpleNamespace(
        is_available=lambda: True,
        get_device_name=lambda device: "test GPU",
        synchronize=lambda device: events.append("synchronize"),
    )
    torch = ModuleType("torch")
    torch.cuda = cuda
    torch.device = lambda name: SimpleNamespace(type="cuda")
    monkeypatch.setitem(sys.modules, "torch", torch)
    for name in ("mmcv", "mmdet"):
        module = ModuleType(name)
        module.__version__ = "test"
        monkeypatch.setitem(sys.modules, name, module)

    def predict(frame):
        events.append("predict")
        return []

    detector = SimpleNamespace(predict=predict)

    def get_detector():
        events.append("load")
        return detector

    tasks = ModuleType("app.worker.tasks")
    tasks.DEVICE = "cuda:0"
    tasks.MODEL_CONFIG = config
    tasks.MODEL_CHECKPOINT = checkpoint
    tasks.get_detector = get_detector
    monkeypatch.setitem(sys.modules, "app.worker.tasks", tasks)
    return SimpleNamespace(
        events=events, checkpoint=checkpoint, cuda=cuda, detector=detector,
    )


def test_success_requires_model_load_inference_and_cuda_sync(runtime, capsys):
    main()
    assert runtime.events == ["load", "predict", "synchronize"]
    assert "MODEL_OK" in capsys.readouterr().out


def test_missing_checkpoint_fails_before_model_loading(runtime, capsys):
    runtime.checkpoint.unlink()
    with pytest.raises(FileNotFoundError, match="Required model file"):
        main()
    assert runtime.events == []
    assert "MODEL_OK" not in capsys.readouterr().out


def test_missing_cuda_fails_before_model_loading(runtime, capsys):
    runtime.cuda.is_available = lambda: False
    with pytest.raises(RuntimeError, match="CUDA is required"):
        main()
    assert runtime.events == []
    assert "MODEL_OK" not in capsys.readouterr().out


def test_inference_error_is_not_reported_as_success(runtime, capsys):
    def fail(frame):
        raise RuntimeError("inference failed")

    runtime.detector.predict = fail
    with pytest.raises(RuntimeError, match="inference failed"):
        main()
    assert "MODEL_OK" not in capsys.readouterr().out
