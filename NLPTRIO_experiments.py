#!/usr/bin/env python3
"""NLPTRIO - reproducible, PET-grouped Turkish euphemism experiments.

Commands:
  python NLPTRIO_experiments.py --phase audit
  python NLPTRIO_experiments.py --phase baselines
  python NLPTRIO_experiments.py --phase pilot --conditions standard,uniform,ambiguity --fold 0 --seeds 42
  python NLPTRIO_experiments.py --phase full --conditions standard,uniform --seeds 42,123,2026

The program NEVER ships fabricated scores. All output is produced from the loaded dataset.
The fixed first-look baseline numbers from the proposal are not recreated here: their exact
CSV split and hyperparameters were not supplied. This script creates a NEW 5-fold run.
"""
import argparse
import gc
import json
import random
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.model_selection import GroupShuffleSplit, StratifiedGroupKFold
from sklearn.pipeline import make_pipeline

DATASET_ID = "hasancanbiyik/turkish-potentially-euphemistic-terms"
BERTURK_ID = "dbmdz/bert-base-turkish-cased"
BOUNDARY = "[PET_BOUNDARY]"
SPAN_PATTERN = re.compile(r"\[PET_BOUNDARY\](.*?)\[PET_BOUNDARY\]", re.DOTALL)


def load_data(csv_path=None):
    if csv_path:
        df = pd.read_csv(csv_path)
    else:
        # Dataset viewer/config currently points to a non-existent turkish_pets.csv.
        # Download the real, public 2.49 MB CSV by its exact filename instead.
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as exc:
            raise RuntimeError("Install: pip install huggingface_hub (or pass --data-csv)") from exc
        csv_path = hf_hub_download(repo_id=DATASET_ID,
                filename="turkish-potentially-euphemistic-terms.csv", repo_type="dataset")
        df = pd.read_csv(csv_path)
    df.columns = [str(c).upper() for c in df.columns]
    mandatory = {"TEXT", "LABEL", "PET"}
    if not mandatory.issubset(df.columns):
        raise ValueError(f"Dataset needs {mandatory}, got {set(df.columns)}")
    df = df.reset_index(drop=True)
    df["TEXT"] = df["TEXT"].astype(str)
    df["PET"] = df["PET"].astype(str).str.strip()
    if "CATEGORY" not in df: df["CATEGORY"] = "unknown"
    df["LABEL"] = pd.to_numeric(df["LABEL"], errors="raise").astype(int)
    if not set(df["LABEL"].unique()).issubset({0, 1}):
        raise ValueError("LABEL must be binary (0/1).")
    missing = df["TEXT"].map(lambda x: len(SPAN_PATTERN.findall(x)) != 1)
    if missing.any():
        raise ValueError(f"{missing.sum()} records have !=1 correctly marked PET span; inspect input.")
    if df["PET"].eq("").any():
        raise ValueError("Empty PET group exists.")
    if df.ID.duplicated().any() if "ID" in df else False:
        raise ValueError("Duplicate source row IDs: dataset needs a careful audit.")
    df["ROW_INDEX"] = np.arange(len(df))
    df.attrs["source_csv_path"] = str(csv_path)
    return df


def original_text(text):
    return str(text).replace(BOUNDARY, "")


def masked_text(text):
    out, n = SPAN_PATTERN.subn(lambda match: f"{BOUNDARY} [MASK] {BOUNDARY}", text)
    if n != 1:
        raise ValueError(f"Invalid PET span: {text[:90]}")
    return out


def group_folds(df, split_seed=42):
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=split_seed)
    splits = []
    for fold, (other_idx, test_idx) in enumerate(splitter.split(df.TEXT, df.LABEL, groups=df.PET)):
        other = df.iloc[other_idx]
        # Validation contains entire PETs that never occur in the training partition.
        val_splitter = GroupShuffleSplit(n_splits=1, test_size=0.14, random_state=100+fold)
        train_sub, val_sub = next(val_splitter.split(other, other.LABEL, groups=other.PET))
        train_idx = other_idx[train_sub]
        val_idx = other_idx[val_sub]
        names = [set(df.iloc[idx].PET) for idx in [train_idx, val_idx, test_idx]]
        assert not (names[0]&names[1] or names[0]&names[2] or names[1]&names[2]), "PET leakage!"
        splits.append((train_idx, val_idx, test_idx))
    all_test_rows = [int(x) for _, _, ts in splits for x in ts]
    assert len(all_test_rows) == len(df) and len(set(all_test_rows)) == len(df)
    return splits


def audit_data(df, splits, out):
    pet_labels = df.groupby("PET").LABEL.nunique()
    summary = {
        "source": DATASET_ID if not out.get("csv_path") else out["csv_path"],
        "total_rows": int(len(df)), "num_pets": int(df.PET.nunique()),
        "label_1": int(df.LABEL.sum()), "label_0": int((df.LABEL == 0).sum()),
        "pets_with_both_observed_labels": int((pet_labels == 2).sum()),
        "pets_with_one_observed_label": int((pet_labels == 1).sum()),
        "duplicate_ids": int(df.ID.duplicated().sum()) if "ID" in df else None,
        "folds": [],
    }
    for f, (train, val, test) in enumerate(splits):
        row = {"fold": f}
        for name, idx in [("train", train), ("val", val), ("test", test)]:
            part = df.iloc[idx]
            row[name] = {"sentences": len(part), "pets": part.PET.nunique(),
                         "label_1": int(part.LABEL.sum()), "label_0": int((part.LABEL == 0).sum())}
        summary["folds"].append(row)
    return summary


def scores(y, pred):
    p, r, f, support = precision_recall_fscore_support(y, pred, labels=[0, 1], zero_division=0)
    return {"macro_f1": float(f1_score(y, pred, labels=[0,1], average="macro", zero_division=0)),
            "class_0_precision": float(p[0]), "class_0_recall": float(r[0]),
            "class_1_precision": float(p[1]), "class_1_recall": float(r[1]),
            "confusion_matrix_0_1": confusion_matrix(y, pred, labels=[0,1]).tolist()}


def baselines(df, splits, outdir):
    rows = []
    prediction_rows = []
    for f, (tr, _, te) in enumerate(splits):
        xtr = df.iloc[tr].TEXT.map(original_text).tolist()
        xts = df.iloc[te].TEXT.map(original_text).tolist()
        ytr, yts = df.iloc[tr].LABEL.values, df.iloc[te].LABEL.values
        models = {
            "majority": DummyClassifier(strategy="most_frequent"),
            "tfidf_logreg": make_pipeline(TfidfVectorizer(ngram_range=(1,2), max_features=100000),
                                          LogisticRegression(max_iter=2000, random_state=42)),
        }
        for name, model in models.items():
            model.fit(xtr, ytr)
            pr = model.predict(xts)
            result = {"fold": f, "model": name, "n_train": len(tr), "n_test": len(te), **scores(yts, pr)}
            rows.append(result)
            part = df.iloc[te].copy()
            part["fold"] = f; part["model"] = name; part["predicted_label"] = pr
            part["error_type"] = np.where(part.LABEL==part.predicted_label,"correct",
                np.where(part.LABEL==0,"false_positive","false_negative"))
            cols = ["ROW_INDEX", "PET", "CATEGORY", "TEXT", "LABEL", "fold", "model", "predicted_label", "error_type"]
            if "ID" in part: cols.insert(1,"ID")
            prediction_rows.append(part[cols])
            print(f"BASELINE fold={f} model={name} macro-F1={result['macro_f1']:.4f}", flush=True)
    save_json(outdir / "baseline_folds.json", rows)
    summary = {k: {"mean_fold_macro_f1": float(np.mean([r["macro_f1"] for r in rows if r["model"] == k])),
                   "std_fold_macro_f1": float(np.std([r["macro_f1"] for r in rows if r["model"] == k]))}
               for k in ["majority", "tfidf_logreg"]}
    preds = pd.concat(prediction_rows, ignore_index=True)
    preds.to_csv(outdir / "baseline_predictions.csv", index=False)
    error_summary = {}
    for model_name, frame in preds.groupby("model"):
        wrong = frame.loc[frame.error_type != "correct"].copy()
        wrong["error_category"] = wrong["error_type"] + " / " + wrong["CATEGORY"].fillna("unknown").astype(str)
        wrong.to_csv(outdir / f"baseline_errors_{model_name}.csv", index=False)
        error_summary[model_name] = {
            "total_errors": int(len(wrong)),
            "false_positives": int((wrong.error_type=="false_positive").sum()),
            "false_negatives": int((wrong.error_type=="false_negative").sum()),
            "by_category": {str(k):int(v) for k,v in wrong.error_category.value_counts().items()},
            "sample_30_row_ids": wrong.ROW_INDEX.head(30).tolist(),
        }
        # Produce one real, actually misclassified example per observed error category.
        representatives = wrong.groupby("error_category",sort=False).head(1).copy()
        representatives.to_csv(outdir / f"baseline_error_examples_{model_name}.csv",index=False)
        pooled = scores(frame.LABEL.to_numpy(), frame.predicted_label.to_numpy())
        from sklearn.metrics import f1_score
        pet_ids = frame.PET.unique()
        rng = np.random.default_rng(742)
        ci = []
        grp = {p:frame.loc[frame.PET == p] for p in pet_ids}
        for _ in range(2000):
            draw = pd.concat([grp[p] for p in rng.choice(pet_ids,size=len(pet_ids),replace=True)])
            ci.append(f1_score(draw.LABEL,draw.predicted_label,average="macro",labels=[0,1],zero_division=0))
        summary[model_name].update({
            "pooled_out_of_fold_macro_f1": pooled["macro_f1"],
            "pooled_95pct_pet_cluster_CI": [float(np.percentile(ci,2.5)),float(np.percentile(ci,97.5))],
            "pooled_confusion_matrix": pooled["confusion_matrix_0_1"],
            "n_test_examples_all_folds":int(len(frame)),
            "n_test_pets_all_folds":int(frame.PET.nunique())
        })
    save_json(outdir / "baseline_summary.json", summary)
    save_json(outdir / "baseline_error_summary.json", error_summary)
    return rows


def set_seed(seed):
    import torch
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)


def selected_mask_indices(train_df, condition, seed, mask_fraction=0.30):
    if condition == "standard": return set()
    if condition not in ("uniform", "ambiguity"):
        raise ValueError(f"Unsupported condition: {condition}")
    rng = np.random.default_rng(seed)
    n = int(round(len(train_df) * mask_fraction))
    if condition == "uniform":
        candidates = train_df.ROW_INDEX.to_numpy()
    else:
        # Only label ambiguity observed within TRAINING PET groups is used; never test labels.
        ambiguous = train_df.groupby("PET").LABEL.nunique()
        allowed = set(ambiguous[ambiguous == 2].index)
        candidates = train_df[train_df.PET.isin(allowed)].ROW_INDEX.to_numpy()
        if len(candidates) < n:
            raise ValueError(f"Only {len(candidates)} ambiguity-eligible train rows, need {n}.")
    return set(rng.choice(candidates, size=n, replace=False).tolist())


def run_berturk(df, tr, va, te, fold, seed, condition, outdir, epochs, batch_size, max_len, save_model, evaluate_test=False):
    # Lazy imports: audit/baselines can run locally without heavyweight DL packages.
    import torch
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    from torch.optim import AdamW
    set_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cpu": print("WARNING: no CUDA GPU; BERTurk training can be very slow.")
    tokenizer = AutoTokenizer.from_pretrained(BERTURK_ID)
    tokenizer.add_special_tokens({"additional_special_tokens": [BOUNDARY]})
    model = AutoModelForSequenceClassification.from_pretrained(BERTURK_ID, num_labels=2)
    model.resize_token_embeddings(len(tokenizer))
    model.to(device)
    train_df, val_df, test_df = [df.iloc[i].copy() for i in [tr, va, te]]
    selection = selected_mask_indices(train_df, condition, seed + 10000*fold)
    train_texts = [masked_text(t) if idx in selection else t for idx, t in
                   zip(train_df.ROW_INDEX.to_numpy(), train_df.TEXT.tolist())]
    assert len(selection) == (0 if condition == "standard" else round(len(tr)*0.30))

    class TextDataset(Dataset):
        def __init__(self, texts, labels):
            self.texts = list(texts); self.labels = list(labels)
        def __len__(self): return len(self.texts)
        def __getitem__(self, i): return (self.texts[i], int(self.labels[i]))

    def collate(batch):
        texts, labels = zip(*batch)
        tok = tokenizer(list(texts), max_length=max_len, padding=True, truncation=True,
                        return_tensors="pt")
        tok["labels"] = torch.tensor(labels, dtype=torch.long)
        return tok

    def loader(texts, labels, bs=batch_size, shuffle=False):
        return DataLoader(TextDataset(texts, labels), batch_size=bs, shuffle=shuffle, collate_fn=collate)

    def predict(texts, labels):
        model.eval(); probs = []
        with torch.no_grad():
            for batch in loader(texts, labels, bs=max(8,batch_size*2)):
                inputs = {k: v.to(device) for k,v in batch.items()}
                logits = model(**inputs).logits
                probs.extend(torch.softmax(logits, dim=-1)[:,1].detach().cpu().numpy().tolist())
        return np.array(probs), np.array(probs) >= 0.5

    train_loader = loader(train_texts, train_df.LABEL.tolist(), shuffle=True)
    optimizer = AdamW(model.parameters(), lr=2e-5, weight_decay=0.01)
    best_state = None; best_f1 = -1; history=[]
    if device.type == "cuda": torch.cuda.reset_peak_memory_stats()
    start = time.perf_counter()
    for ep in range(1, epochs+1):
        model.train(); ep_loss = 0.0; steps = 0
        for batch in train_loader:
            batch = {k:v.to(device) for k,v in batch.items()}
            optimizer.zero_grad(set_to_none=True)
            loss = model(**batch).loss
            loss.backward()
            optimizer.step()
            ep_loss += loss.item(); steps += 1
        _, val_pred = predict(val_df.TEXT.tolist(), val_df.LABEL.tolist())
        val_stats = scores(val_df.LABEL.values, val_pred.astype(int))
        history.append({"epoch":ep, "loss": ep_loss/max(steps,1),
                        "val_macro_f1": val_stats["macro_f1"]})
        print(f"{condition}: fold={fold}, seed={seed}, epoch={ep} loss={ep_loss/max(steps,1):.4f} val-F1={val_stats['macro_f1']:.4f}",flush=True)
        if val_stats["macro_f1"] > best_f1:
            best_f1 = val_stats["macro_f1"]
            best_state = {k:v.detach().cpu().clone() for k,v in model.state_dict().items()}
    elapsed = time.perf_counter()-start
    model.load_state_dict(best_state)
    # Pilot must not touch test predictions: only the disjoint validation set.
    # A full run evaluates held-out folds once, after epoch selection on validation.
    if evaluate_test:
        prob, pred = predict(test_df.TEXT.tolist(), test_df.LABEL.tolist())
        context_prob, context_pred = predict([masked_text(t) for t in test_df.TEXT], test_df.LABEL.tolist())
        test_stats = scores(test_df.LABEL.values, pred.astype(int))
        test_stats["masked_test_diagnostic_macro_f1"] = scores(test_df.LABEL.values, context_pred.astype(int))["macro_f1"]
        test_stats["mean_abs_prob_change_when_test_pet_masked"] = float(np.mean(np.abs(prob-context_prob)))
    else:
        test_stats = {}
        prob, pred, context_prob = None, None, None
    record = {"fold":fold,"seed":seed,"condition":condition,"epochs":epochs,
              "batch_size":batch_size,"max_length":max_len,"train_sentences":len(tr),
              "validation_sentences":len(va),"test_sentences":len(te),"num_masked_train_sentences":len(selection),
              "elapsed_training_seconds":elapsed,"best_val_f1":best_f1,
              "best_epoch":next(x["epoch"] for x in history if x["val_macro_f1"]==best_f1),
              "max_gpu_memory_gb": float(torch.cuda.max_memory_allocated()/(1024**3)) if device.type == "cuda" else None,
              "history":history,**test_stats}
    preds = test_df[["ROW_INDEX","PET","LABEL"]].copy() if evaluate_test else None
    if evaluate_test:
        preds["fold"] = fold; preds["seed"] = seed; preds["condition"] = condition
        preds["pred"] = pred.astype(int); preds["prob_euph"] = prob
        preds["prob_euph_test_pet_masked"] = context_prob
    if save_model:
        ckpt=outdir / f"model_{condition}_fold{fold}_seed{seed}"
        ckpt.mkdir(exist_ok=True,parents=True)
        model.save_pretrained(ckpt);tokenizer.save_pretrained(ckpt)
    del model, optimizer, best_state
    gc.collect()
    if device.type=="cuda": torch.cuda.empty_cache()
    return record, preds


def paired_bootstrap(predictions, cond_a, cond_b, iters=2000, seed=7):
    by = {(c,s):p for (c,s),p in predictions.groupby(["condition","seed"])}
    seeds = sorted(set(s for c,s in by if c==cond_a)&set(s for c,s in by if c==cond_b))
    if not seeds: return None
    pet_ids = sorted(predictions.PET.unique())
    rng = np.random.default_rng(seed)
    aligned={}
    for s in seeds:
        a=by[cond_a,s].set_index("ROW_INDEX").sort_index()
        b=by[cond_b,s].set_index("ROW_INDEX").sort_index()
        if not a.index.equals(b.index) or not np.array_equal(a.LABEL,b.LABEL) or not a.PET.equals(b.PET):
            raise ValueError("Bootstrap condition predictions not paired!")
        aligned[s]=(a,b)
    draws=[]
    for _ in range(iters):
        sampled = rng.choice(pet_ids, size=len(pet_ids), replace=True)
        diffs=[]
        for s,(a,b) in aligned.items():
            indexes=np.concatenate([np.flatnonzero(a.PET.values==pet) for pet in sampled])
            y=a.LABEL.values[indexes]
            fa=f1_score(y,a.pred.values[indexes],average="macro",labels=[0,1],zero_division=0)
            fb=f1_score(y,b.pred.values[indexes],average="macro",labels=[0,1],zero_division=0)
            diffs.append(fb-fa)
        draws.append(np.mean(diffs))
    observed = float(np.mean([scores(a.LABEL.values,b.pred.values)["macro_f1"]-
                              scores(a.LABEL.values,a.pred.values)["macro_f1"] for a,b in aligned.values()]))
    ci=np.percentile(draws,[2.5,97.5])
    return {"comparison":f"{cond_b} minus {cond_a}","seeds":seeds,
            "n_pets":len(pet_ids),"bootstrap_iterations":iters,
            "observed_mean_seed_difference":observed,"ci95_lower":float(ci[0]),"ci95_upper":float(ci[1]),
            "interval_excludes_zero":bool(ci[0]>0 or ci[1]<0),
            "practical_gain_ge_0_02":bool(observed>=0.02)}


def save_json(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=lambda x:x.item() if hasattr(x,"item") else str(x)),encoding="utf-8")


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--phase", choices=["audit","baselines","pilot","full"],default="audit")
    parser.add_argument("--data-csv",help="Local dataset CSV for offline execution, same TEXT/PET/LABEL fields.")
    parser.add_argument("--outdir",default="nlptrio_results")
    parser.add_argument("--conditions",default="standard,uniform",help="standard,uniform,ambiguity")
    parser.add_argument("--seeds",default="42,123,2026")
    parser.add_argument("--fold",type=int,default=0,help="Only for pilot; 0..4")
    parser.add_argument("--epochs",type=int,default=3)
    parser.add_argument("--batch-size",type=int,default=8)
    parser.add_argument("--max-length",type=int,default=256)
    parser.add_argument("--save-model",action="store_true",help="Save full checkpoints (requires extra disk space).")
    args=parser.parse_args()
    outdir=Path(args.outdir);outdir.mkdir(parents=True,exist_ok=True)
    df=load_data(args.data_csv)
    splits=group_folds(df)
    audit=audit_data(df,splits,{"csv_path":args.data_csv})
    save_json(outdir / "audit.json",audit)
    import sklearn,sys,hashlib
    versions = {"python":sys.version.split()[0], "numpy":np.__version__,
                "pandas":pd.__version__,"scikit_learn":sklearn.__version__,
                "model_id":BERTURK_ID,"dataset_id":DATASET_ID,"split_seed":42,
                "validation_seed_rule":"100 + fold", "mask_fraction":.30,
                "training_seeds":[42,123,2026]}
    src = df.attrs.get("source_csv_path") or args.data_csv
    if src and Path(src).exists():
        versions["dataset_sha256"] = hashlib.sha256(Path(src).read_bytes()).hexdigest()
    try:
        import importlib.metadata
        for package in ["torch","transformers","huggingface-hub"]:
            try: versions[package+"_version"] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError: versions[package+"_version"] = None
    except Exception: pass
    save_json(outdir / "environment.json",versions)
    pd.DataFrame([{"fold":f,"partition":part,"row_index":int(i),"PET":df.iloc[i].PET,
                "source_id":str(df.iloc[i].ID) if "ID" in df else str(i)}
                for f,(tr,va,te) in enumerate(splits)
                for part,idx in [("train",tr),("dev",va),("test",te)] for i in idx]).to_csv(
                    outdir/"frozen_fold_partitions.csv",index=False)
    print(json.dumps({k:audit[k] for k in ["total_rows","num_pets","label_0","label_1","pets_with_both_observed_labels"]},ensure_ascii=False,indent=2))
    if args.phase=="audit":return
    if args.phase=="baselines":baselines(df,splits,outdir);return
    conditions=[x.strip() for x in args.conditions.split(",")]
    seeds=[int(x.strip()) for x in args.seeds.split(",")]
    if args.phase=="pilot":folds=[args.fold]
    else:folds=list(range(5))
    records=[];pred_list=[]
    for fold in folds:
        tr,va,te=splits[fold]
        for seed in seeds:
            for cond in conditions:
                rec, pr=run_berturk(df,tr,va,te,fold,seed,cond,outdir,args.epochs,
                                    args.batch_size,args.max_length,args.save_model,
                                    evaluate_test=(args.phase=="full"))
                records.append(rec)
                save_json(outdir/"berturk_runs.json",records)
                if pr is not None:
                    pred_list.append(pr)
                    pd.concat(pred_list,ignore_index=True).to_csv(outdir/"berturk_predictions.csv",index=False)
    if args.phase=="full":
        predictions=pd.concat(pred_list,ignore_index=True)
        totals=[]
        for (condition,seed),part in predictions.groupby(["condition","seed"]):
            if part.ROW_INDEX.nunique()!=len(df):raise ValueError("Incomplete OOF coverage")
            totals.append({"condition":condition,"seed":int(seed),
                           **scores(part.LABEL.values,part.pred.values)})
        save_json(outdir/"full_oof_scores.json",totals)
        if "standard" in conditions:
            comparisons=[paired_bootstrap(predictions,"standard",c) for c in conditions if c!="standard"]
            save_json(outdir/"pet_cluster_bootstrap.json",comparisons)
        print(json.dumps(totals,indent=2,ensure_ascii=False))
    else:
        print("PILOT COMPLETE: use berturk_runs.json and berturk_predictions.csv for actual numbers.")

if __name__=="__main__":main()
