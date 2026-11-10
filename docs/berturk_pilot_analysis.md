# BERTurk Pilot Analysis

We evaluated three fine-tuning approaches using PET-grouped fold 0, seed 42, and three training epochs.

| Method | Validation Macro-F1 |
|---|---:|
| Standard BERTurk | 0.6280 |
| Uniform 30% Masking | 0.6446 |
| Ambiguity-Aware 30% Masking | 0.6658 |

Ambiguity-aware masking achieved the highest validation Macro-F1, improving by 0.0378 compared with standard fine-tuning. Uniform masking improved by 0.0166.

These results suggest that prioritizing ambiguous PETs during masking may improve contextual generalization. However, this is a preliminary experiment using only one fold and one random seed. Therefore, no statistically significant improvement can be claimed yet.

The final experiments will compare the methods across five PET-grouped folds and multiple random seeds.
