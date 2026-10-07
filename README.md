# Gaurdian-AI

Student-track implementation of the GuardianAI-RAG proposal's AI/ML core.
Module 1 (this baseline): detecting whether an image is AI-generated.

## Status

**Baseline only.** This model is trained solely on the CIFAKE dataset. CIFAKE's
"REAL" images are CIFAR-10 photos upscaled from 32x32, which have a different
sharpness/compression fingerprint than an ordinary phone or internet photo. A
model trained only on CIFAKE can learn to detect "is this a 32x32-upscaled
image" rather than "is this AI-generated" — it will score well on CIFAKE's own
test set and perform badly on real-world images. That's expected at this
stage. The fix (adding a higher-resolution, multi-generator dataset like
GenImage, plus JPEG/resize augmentation) is the next milestone, not yet in
this version — don't quote this baseline's accuracy as a real-world number.

## Setup

1. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/Scripts/activate
   ```
2. Install dependencies (read the note at the top of `requirements.txt` first
   if you have an NVIDIA GPU):
   ```
   pip install -r requirements.txt
   ```
3. Download the CIFAKE dataset from Kaggle:
   https://www.kaggle.com/datasets/birdy654/cifake-real-and-ai-generated-synthetic-images
   Extract it so you end up with this structure:
   ```
   data/cifake/train/REAL/
   data/cifake/train/FAKE/
   data/cifake/test/REAL/
   data/cifake/test/FAKE/
   ```

## Run

Fast test run on a small subset first (a few minutes, confirms the pipeline works):
```
python src/train.py --subset-size 2000 --epochs 2
```

Full training run (slow on CPU — see the warning the script prints):
```
python src/train.py --epochs 5
```

The trained weights are saved to `models/baseline_resnet18.pt` (gitignored —
weights live locally/on your own backup, not in the repo).

## Roadmap

- [x] Baseline: ResNet18 transfer learning on CIFAKE
- [ ] Add GenImage (or similar) to fix the generalization gap above
- [ ] Add JPEG/resize augmentation for robustness
- [ ] Frame-level deepfake video classifier (FaceForensics++) — later phase
