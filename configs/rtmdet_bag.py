_base_ = "mmdet::rtmdet/rtmdet_tiny_8xb32-300e_coco.py"


# =========================
# Dataset
# =========================

data_root = "data/dataset/"

metainfo = {
    "classes": ("bag",),
    "palette": [(220, 20, 60)],
}


# =========================
# Model
# =========================

model = dict(
    bbox_head=dict(
        num_classes=1,
    ),
)


# =========================
# Training pipeline
# =========================

train_pipeline = [
    dict(
        type="LoadImageFromFile",
    ),
    dict(
        type="LoadAnnotations",
        with_bbox=True,
    ),
    dict(
        type="Resize",
        scale=(640, 640),
        keep_ratio=True,
    ),
    dict(
        type="YOLOXHSVRandomAug",
    ),
    dict(
        type="RandomFlip",
        prob=0.5,
    ),
    dict(
        type="Pad",
        size=(640, 640),
        pad_val=dict(
            img=(114, 114, 114),
        ),
    ),
    dict(
        type="PackDetInputs",
    ),
]


# =========================
# Dataloaders
# =========================

train_dataloader = dict(
    batch_size=4,
    num_workers=0,
    persistent_workers=False,
    dataset=dict(
        data_root=data_root,
        metainfo=metainfo,
        ann_file="annotations/train.json",
        data_prefix=dict(
            img="train/",
        ),
        pipeline=train_pipeline,
    ),
)

val_dataloader = dict(
    batch_size=4,
    num_workers=0,
    persistent_workers=False,
    dataset=dict(
        data_root=data_root,
        metainfo=metainfo,
        ann_file="annotations/val.json",
        data_prefix=dict(
            img="val/",
        ),
    ),
)

test_dataloader = val_dataloader


# =========================
# Evaluation
# =========================

val_evaluator = dict(
    ann_file=data_root + "annotations/val.json",
)

test_evaluator = val_evaluator


# =========================
# Optimization
# =========================

optim_wrapper = dict(
    optimizer=dict(
        type="AdamW",
        lr=1e-4,
        weight_decay=0.05,
    ),
)


# =========================
# Training schedule
# =========================

max_epochs = 50

train_cfg = dict(
    type="EpochBasedTrainLoop",
    max_epochs=max_epochs,
    val_interval=5,
)

param_scheduler = [
    dict(
        type="CosineAnnealingLR",
        begin=0,
        end=max_epochs,
        T_max=max_epochs,
        eta_min=1e-6,
        by_epoch=True,
    ),
]


# =========================
# Checkpoints
# =========================

default_hooks = dict(
    checkpoint=dict(
        type="CheckpointHook",
        interval=5,
        max_keep_ckpts=3,
        save_best="coco/bbox_mAP",
        rule="greater",
    ),
)


# =========================
# Pretrained checkpoint
# =========================

load_from = (
    "checkpoints/"
    "rtmdet_tiny_8xb32-300e_coco_20220902_112414-78e30dcc.pth"
)


# =========================
# Output
# =========================

work_dir = "work_dirs/rtmdet_bag"