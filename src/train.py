"""
GuardianAI-RAG — Module 1 baseline: AI-generated image detector.

Transfer learning: take a ResNet18 already trained on ImageNet (so it
already knows general visual features — edges, textures, shapes) and
replace its final layer so it predicts REAL vs FAKE instead of ImageNet's
1000 classes, then fine-tune it on CIFAKE.

KNOWN LIMITATION — read this before trusting any number this script prints:
CIFAKE's "REAL" images are CIFAR-10 photos upscaled from 32x32. That gives
them a different sharpness/compression signature than a normal phone photo.
A model trained only on this dataset can quietly learn "is this a
32x32-upscaled image" instead of "is this AI-generated" - it will look great
on CIFAKE's own test set and fail on real-world images. This script is a
correctness-first baseline to prove the pipeline runs end to end. Fixing the
generalization gap (adding a higher-res, multi-generator dataset + JPEG/
resize augmentation) is the next step, intentionally not in this version.

NEW in this version: checkpoints after every epoch, and can resume from one.
Long CPU runs get interrupted (laptop sleeps, you need the machine, you
switch hardware) - this version survives that instead of losing everything.

Usage:
    python src/train.py --subset-size 2000 --epochs 2        # fast test run
    python src/train.py --epochs 5                            # full run
    python src/train.py --epochs 5 --resume models/checkpoint_latest.pt
"""

import argparse
import os

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms, models
from torchvision.models import ResNet18_Weights


def get_dataloaders(data_dir, batch_size, subset_size=None):
    normalize = transforms.Normalize(
        mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
    )

    train_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        normalize,
    ])
    test_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        normalize,
    ])

    train_dir = os.path.join(data_dir, "train")
    test_dir = os.path.join(data_dir, "test")
    for d in (train_dir, test_dir):
        if not os.path.isdir(d):
            raise FileNotFoundError(
                f"Expected folder not found: {d}\n"
                f"Did you extract CIFAKE into data/cifake/ with train/ and "
                f"test/ subfolders, each containing REAL/ and FAKE/?"
            )

    train_dataset = datasets.ImageFolder(train_dir, transform=train_transform)
    test_dataset = datasets.ImageFolder(test_dir, transform=test_transform)
    print(f"Class mapping: {train_dataset.class_to_idx}")

    if subset_size:
        train_dataset = Subset(
            train_dataset, range(min(subset_size, len(train_dataset)))
        )
        test_dataset = Subset(
            test_dataset, range(min(max(subset_size // 5, 1), len(test_dataset)))
        )

    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True, num_workers=2
    )
    test_loader = DataLoader(
        test_dataset, batch_size=batch_size, shuffle=False, num_workers=2
    )
    return train_loader, test_loader


def build_model(device):
    model = models.resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
    model.fc = nn.Linear(model.fc.in_features, 2)
    return model.to(device)


def run_epoch(model, loader, criterion, optimizer, device, train):
    model.train() if train else model.eval()
    running_loss, correct, total = 0.0, 0, 0

    context = torch.enable_grad() if train else torch.no_grad()
    with context:
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)

            if train:
                optimizer.zero_grad()

            outputs = model(images)
            loss = criterion(outputs, labels)

            if train:
                loss.backward()
                optimizer.step()

            running_loss += loss.item() * images.size(0)
            _, predicted = outputs.max(1)
            correct += predicted.eq(labels).sum().item()
            total += labels.size(0)

    return running_loss / total, correct / total


def save_checkpoint(path, model, optimizer, epoch, train_acc, test_acc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    torch.save({
        "epoch": epoch,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "train_acc": train_acc,
        "test_acc": test_acc,
    }, path)
    print(f"Checkpoint saved -> {path} (after epoch {epoch})")


def main():
    parser = argparse.ArgumentParser(
        description="Train a baseline AI-generated-image detector on CIFAKE"
    )
    parser.add_argument(
        "--data-dir", type=str, default="data/cifake",
        help="Path to the extracted CIFAKE folder (must contain train/ and test/)",
    )
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument(
        "--subset-size", type=int, default=None,
        help="Use a small subset for a fast correctness check, e.g. 2000. "
             "Leave unset to train on the full dataset.",
    )
    parser.add_argument(
        "--checkpoint", type=str, default="models/checkpoint_latest.pt",
        help="Where the resumable checkpoint is saved after every epoch.",
    )
    parser.add_argument(
        "--resume", type=str, default=None,
        help="Path to a checkpoint to resume from, e.g. models/checkpoint_latest.pt",
    )
    parser.add_argument("--output", type=str, default="models/baseline_resnet18.pt")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    if device.type == "cpu":
        print(
            "WARNING: no GPU detected. Training the FULL dataset on CPU can "
            "take hours. Use --subset-size 2000 first to confirm everything "
            "works, and seriously consider Google Colab's free GPU instead."
        )

    train_loader, test_loader = get_dataloaders(
        args.data_dir, args.batch_size, args.subset_size
    )
    model = build_model(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    start_epoch = 1
    if args.resume:
        if not os.path.isfile(args.resume):
            raise FileNotFoundError(f"No checkpoint found at {args.resume}")
        ckpt = torch.load(args.resume, map_location=device)
        model.load_state_dict(ckpt["model_state_dict"])
        optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        start_epoch = ckpt["epoch"] + 1
        print(f"Resumed from {args.resume} - continuing at epoch {start_epoch}")

    last_train_acc, last_test_acc = None, None
    try:
        for epoch in range(start_epoch, args.epochs + 1):
            train_loss, train_acc = run_epoch(
                model, train_loader, criterion, optimizer, device, train=True
            )
            test_loss, test_acc = run_epoch(
                model, test_loader, criterion, optimizer, device, train=False
            )
            print(
                f"Epoch {epoch}/{args.epochs} | "
                f"train_loss={train_loss:.4f} train_acc={train_acc:.4f} | "
                f"test_loss={test_loss:.4f} test_acc={test_acc:.4f}"
            )
            last_train_acc, last_test_acc = train_acc, test_acc
            save_checkpoint(args.checkpoint, model, optimizer, epoch, train_acc, test_acc)

    except KeyboardInterrupt:
        print(
            "\nInterrupted. Your last completed epoch is already saved in "
            f"{args.checkpoint} (checkpoints save after every epoch, not just "
            "at the end). Resume anytime with:\n"
            f"  python src/train.py --resume {args.checkpoint} --epochs {args.epochs}"
        )
        return

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    torch.save(model.state_dict(), args.output)
    print(f"Training complete. Final weights saved to {args.output}")


if __name__ == "__main__":
    main()
