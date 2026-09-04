from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path


def find_coco_json(root: Path) -> Path:
    candidates = list(root.rglob("*.json"))

    if not candidates:
        raise FileNotFoundError(
            f"No JSON annotations found inside {root}"
        )

    # В COCO-экспорте CVAT обычно один основной json.
    for candidate in candidates:
        if candidate.name.startswith("instances"):
            return candidate

    return candidates[0]


def build_subset(
    coco: dict,
    images: list[dict],
) -> dict:
    image_ids = {image["id"] for image in images}

    annotations = [
        annotation
        for annotation in coco["annotations"]
        if annotation["image_id"] in image_ids
    ]

    return {
        "info": coco.get("info", {}),
        "licenses": coco.get("licenses", []),
        "categories": coco["categories"],
        "images": images,
        "annotations": annotations,
    }


def normalize_image_record(image: dict) -> dict:
    """
    CVAT иногда записывает file_name с префиксом директории.
    Для нашего локального датасета оставляем только имя файла.
    """
    image = image.copy()
    image["file_name"] = Path(image["file_name"]).name
    return image


def prepare_dataset(
    annotations_archive: Path,
    raw_images_dir: Path,
    output_dir: Path,
    train_ratio: float,
) -> None:
    if not annotations_archive.exists():
        raise FileNotFoundError(
            f"Archive not found: {annotations_archive}"
        )

    if not raw_images_dir.exists():
        raise FileNotFoundError(
            f"Images directory not found: {raw_images_dir}"
        )

    if not 0.0 < train_ratio < 1.0:
        raise ValueError("train_ratio must be between 0 and 1")

    temp_dir = output_dir / "_cvat_annotations"

    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    temp_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(annotations_archive) as archive:
        archive.extractall(temp_dir)

    coco_json_path = find_coco_json(temp_dir)

    print(f"COCO annotations: {coco_json_path}")

    with coco_json_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        coco = json.load(file)

    categories = coco.get("categories", [])

    if not categories:
        raise RuntimeError("COCO dataset contains no categories")

    print("\nCategories:")
    for category in categories:
        print(
            f"  id={category['id']}, "
            f"name={category['name']}"
        )

    category_names = {
        category["name"]
        for category in categories
    }

    if "bag" not in category_names:
        raise RuntimeError(
            "Expected category 'bag' was not found"
        )

    images = [
        normalize_image_record(image)
        for image in coco["images"]
    ]

    # Наши имена frame_0000..., frame_0001... имеют zero padding,
    # поэтому обычная сортировка сохраняет порядок видео.
    images.sort(
        key=lambda image: image["file_name"]
    )

    if not images:
        raise RuntimeError("COCO dataset contains no images")

    split_index = int(len(images) * train_ratio)

    train_images = images[:split_index]
    val_images = images[split_index:]

    train_dir = output_dir / "train"
    val_dir = output_dir / "val"
    annotations_dir = output_dir / "annotations"

    # Удаляем старый split, чтобы в нём не осталось мусора
    # от предыдущих запусков.
    for directory in (
        train_dir,
        val_dir,
        annotations_dir,
    ):
        if directory.exists():
            shutil.rmtree(directory)

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    local_images = {
        image_path.name: image_path
        for image_path in raw_images_dir.glob("*")
        if image_path.is_file()
    }

    def copy_images(
        image_records: list[dict],
        destination: Path,
    ) -> None:
        for image in image_records:
            filename = image["file_name"]

            source = local_images.get(filename)

            if source is None:
                raise FileNotFoundError(
                    f"CVAT references image '{filename}', "
                    "but it was not found in "
                    f"{raw_images_dir}"
                )

            shutil.copy2(
                source,
                destination / filename,
            )

    copy_images(train_images, train_dir)
    copy_images(val_images, val_dir)

    train_coco = build_subset(
        coco,
        train_images,
    )

    val_coco = build_subset(
        coco,
        val_images,
    )

    with (
        annotations_dir / "train.json"
    ).open("w", encoding="utf-8") as file:
        json.dump(
            train_coco,
            file,
            ensure_ascii=False,
            indent=2,
        )

    with (
        annotations_dir / "val.json"
    ).open("w", encoding="utf-8") as file:
        json.dump(
            val_coco,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("\nDataset prepared successfully")
    print(f"Total images:       {len(images)}")
    print(f"Train images:       {len(train_images)}")
    print(f"Validation images:  {len(val_images)}")
    print(
        f"Train annotations:  "
        f"{len(train_coco['annotations'])}"
    )
    print(
        f"Val annotations:    "
        f"{len(val_coco['annotations'])}"
    )

    print(
        f"\nTrain: {train_dir}"
    )
    print(
        f"Validation: {val_dir}"
    )
    print(
        f"Annotations: {annotations_dir}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--annotations",
        type=Path,
        default=Path("data/bags.zip"),
    )

    parser.add_argument(
        "--images",
        type=Path,
        default=Path("data/dataset/raw_images"),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/dataset"),
    )

    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.8,
    )

    args = parser.parse_args()

    prepare_dataset(
        annotations_archive=args.annotations,
        raw_images_dir=args.images,
        output_dir=args.output,
        train_ratio=args.train_ratio,
    )


if __name__ == "__main__":
    main()