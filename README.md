# NLPTRIO — Turkish Euphemism Detection with BERTurk

**CSE 484 · Fall 2026 · Team 13 — Mid-project (November 2026)**

This research project investigates whether replacing potentially euphemistic terms (PETs) with a single `[MASK]` token in **30% of fine-tuning sentences** helps BERTurk generalize to **PETs not observed in training**. A small exploratory extension (*ambiguity-aware masking*) prioritizes masking PET groups observed with both literal and euphemistic labels in the training split.

The project retains the proposal's main question: **Does 30% uniform target masking improve PET-held-out macro-F1 relative to standard BERTurk fine-tuning?** A positive result requires a pre-specified practical gain of **at least 0.02 macro-F1** and a **paired 95% PET-cluster bootstrap interval excluding zero** in the final controlled comparison. The current one-fold pilot is *not* sufficient to establish that claim.

## Dataset and experimental protocol

- Source: [Turkish Potentially Euphemistic Terms](https://huggingface.co/datasets/hasancanbiyik/turkish-potentially-euphemistic-terms); dataset license reported as **CC BY 4.0**. Credit to the dataset authors; refer to the source for the original records and license.
- **2,436** sentences, **70** PET groups, **979** literal (0) / **1,457** euphemistic (1). Of the 70 groups, 56 have both observed labels.
- `StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)`; held-out test PETs never occur in that fold's train or validation partition. Validation uses group-disjoint subsets with seed rule `100 + fold`.
- Each row is in exactly one test fold (out-of-fold); the **5-fold test scores are not the proposal's earlier fixed 566-row first-look test**. Fold assignments for this experiment are frozen in `nlptrio_results/frozen_fold_partitions.csv`.

## Measured mid-project results

**Baseline, five held-out PET-group test folds (pooled out-of-fold macro-F1):**

| System | Pooled test macro-F1 | Mean fold macro-F1 ± SD | 95% PET-cluster bootstrap CI |
|---|---:|---:|---:|
| Majority class | 0.3743 | 0.3731 ± 0.0211 | [0.3544, 0.3950] |
| TF-IDF 1–2-gram + Logistic Regression | **0.4087** | 0.4094 ± 0.0400 | [0.3846, 0.4347] |

The TF-IDF baseline made **970** test errors (942 false positives, 28 false negatives). The confusion matrix in class order `[0,1]` is `[[37, 942], [28, 1429]]`. The `nlptrio_results/` folder contains all original measured predictions, a group/category error summary, and examples of wrong predictions. Error types like `false_positive / Death` combine the ground-truth confusion outcome with the dataset's semantic topic; **they are descriptive categories, not a verified causal explanation**.

**BERTurk pilot, fold 0, seed 42, 3 epochs — validation/dev macro-F1 only (246 dev sentences):**

| Fine-tuning condition | Best validation macro-F1 |
|---|---:|
| Standard (visible target) | 0.6280 |
| Uniform 30% masking | 0.6446 |
| Ambiguity-aware 30% masking (exploratory) | **0.6658** |

Each masking variant replaced the entire target span with one `[MASK]` on **513 of 1,711** training sentences. The pilot did **not** evaluate its 479-sentence held-out test fold. Do not compare these dev results directly with 5-fold baseline test values or claim statistical significance. More folds and seeds are needed for the final study.

## Reproduce the baseline (one command after installation)

Python 3.10+ recommended; use a virtual environment or Google Colab. From the repository root:

```bash
python -m pip install -r requirements.txt
python NLPTRIO_experiments.py --phase baselines --outdir nlptrio_results
```

The **second command** is the one-command reproducible baseline. It downloads the public CSV from Hugging Face on the first run (internet required); the original dataset is intentionally not vendored here. If you already have the correct public CSV, supply `--data-csv /path/to/file.csv`. The run regenerates fold assignments, metrics, confidence intervals, errors and environment files under `nlptrio_results/`. The downloaded CSV's recorded SHA-256 is in `nlptrio_results/environment.json`.

For the BERTurk training pilot, use a GPU runtime:

```bash
python NLPTRIO_experiments.py --phase pilot --fold 0 --seeds 42 --conditions standard,uniform,ambiguity --epochs 3 --batch-size 8 --outdir nlptrio_results
```

This experiment requires GPU-capable PyTorch for reasonable training time. It writes `berturk_runs.json` and does **not** write `berturk_predictions.csv`, because test prediction is deliberately disabled for pilot runs. For a full final test evaluation, use the script's `--phase full` after the agreed experimental protocol is fixed.

## Reproduce the slide figures (optional)

```bash
python NLPTRIO_build_submission.py --results nlptrio_results --output Team13_MidProject.pptx
```

Converting the PowerPoint to PDF requires LibreOffice. **Check and manually update slide prose and the repository URL before submission**; the builder can retain older narrative notes even when it updates numbers. This repo is primarily the code/evidence record, not the final submission PDF.

## Files

- `NLPTRIO_experiments.py`: data audit, fixed PET-grouped folds, baseline, error export and BERTurk training.
- `NLPTRIO_Colab.ipynb`: Google Colab execution notebook.
- `NLPTRIO_build_submission.py`: creates a draft presentation from measurements.
- `requirements.txt`: dependency ranges; exact versions and data hash from the measured run are in `nlptrio_results/environment.json`.
- `nlptrio_results/baseline_summary.json`, `baseline_folds.json`: baseline scores and confidence intervals.
- `nlptrio_results/baseline_predictions.csv`: full out-of-fold baseline predictions.
- `nlptrio_results/baseline_error_summary.json`, `baseline_errors_*.csv`, `baseline_error_examples_*.csv`: error counts and real misclassified sentences.
- `nlptrio_results/berturk_runs.json`: pilot training history, validation F1, times, and GPU memory.
- `nlptrio_results/frozen_fold_partitions.csv`: split details.

## Team roles and disclosure

- **Mustafa Başaran:** dataset audit, preprocessing, and PET-grouped partitions.
- **Gabil Rahimli:** TF-IDF/majority baselines, BERTurk fine-tuning, timing and compute logs.
- **Samet Alkan:** statistical evaluation, PET-cluster confidence intervals, error analysis and demo.

The proposal disclosed **ChatGPT** for brainstorming, coding and English editing and **Claude** for literature checks and design critique. Team members remain responsible for verifying code and reported measurements.

## Relevant work

- Biyik, Lee & Feldman (2024), [Turkish Delights: A Dataset on Turkish Euphemisms](https://aclanthology.org/2024.sigturk-1.7/).
- Biyik et al. (2026), [When Semantic Overlap Is Not Enough: Cross-Lingual Euphemism Transfer Between Turkish and English](https://aclanthology.org/2026.sigturk-1.11/).
- Poh et al. (2026), [The Multilingual Euphemism Benchmark](https://aclanthology.org/2026.lrec-1.579/).

**Note:** This repository does not redistribute the full original dataset file or any model checkpoint. The included evaluation CSVs contain sentences from the attributed public research dataset. The code is not assigned an open-source license by default; the team can decide separately how to license its own code.
