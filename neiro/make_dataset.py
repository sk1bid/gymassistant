# make_dataset.py
# -*- coding: utf-8 -*-
import argparse, re
import numpy as np
import pandas as pd

LB_TO_KG = 0.45359237
KEEP = ["bench_press_barbell", "dips", "barbell_curl"]
ALIASES = {
    "bench_press_barbell": [
        "bench press", "bench press barbell", "bench press (barbell)",
        "flat bench press", "flat barbell bench press", "barbell bench press"
    ],
    "dips": [
        "dips", "dip", "weighted dips", "tricep dips", "parallel bar dip"
    ],
    "barbell_curl": [
        "barbell curl", "barbell curls", "curl barbell", "standing barbell curl",
        "ez bar curl", "ez-bar curl", "ez barbell curl"
    ],
}

def to_canon(name: str) -> str | None:
    if not isinstance(name, str): return None
    s = name.strip().lower().replace("(", "").replace(")", "")
    s = re.sub(r"\s+", " ", s)
    for canon, variants in ALIASES.items():
        for v in variants:
            if s == v or s.startswith(v):
                return canon
    return None

def safe_e1rm(weight_kg: float, reps: int) -> float:
    denom = 1.0278 - 0.0278 * float(reps)
    if denom <= 0.1: denom = 0.1
    return float(weight_kg) / denom

def choose(df, names):
    for n in names:
        if n in df.columns: return n
    return None

def load_csv_any(path: str) -> pd.DataFrame:
    for enc in ("utf-8", "cp1252"):
        try: return pd.read_csv(path, encoding=enc)
        except Exception: pass
    return pd.read_csv(path)

def build_dataset(csv_path: str) -> pd.DataFrame:
    raw = load_csv_any(csv_path)
    c_date = choose(raw, ["Date","date","Workout Date","Timestamp"])
    c_ex   = choose(raw, ["Exercise","Exercise Name","exercise"])
    c_w    = choose(raw, ["Weight","Weight (lbs)","weight (lbs)","kg"])
    c_r    = choose(raw, ["Reps","reps","Rep Count"])
    if not all([c_date,c_ex,c_w,c_r]):
        raise ValueError(f"Нет обязательных колонок. Найдены: {list(raw.columns)}")

    df = pd.DataFrame({
        "date": pd.to_datetime(raw[c_date], errors="coerce"),
        "ex_raw": raw[c_ex].astype(str),
        "weight": pd.to_numeric(raw[c_w], errors="coerce"),
        "reps":   pd.to_numeric(raw[c_r], errors="coerce"),
    }).dropna()
    df = df[(df["reps"]>0) & (df["weight"]>=0)]
    df["exercise"] = df["ex_raw"].map(to_canon)
    df = df[df["exercise"].isin(KEEP)]

    # → кг (исходник Strong — фунты)
    df["weight_kg"] = df["weight"] * LB_TO_KG

    # ВАЖНО: для dips НЕ добавляем массу тела — работаем только с весом на поясе
    df["adj_weight_kg"] = df["weight_kg"]

    # e1RM по сету (в кг)
    df["reps"] = df["reps"].clip(1, 20)
    df["e1rm_kg"] = df.apply(lambda r: safe_e1rm(r["adj_weight_kg"], int(r["reps"])), axis=1)

    # фильтры от опечаток
    df = df[(df["adj_weight_kg"]>=0) & (df["adj_weight_kg"]<=500)]
    df = df[(df["e1rm_kg"]>=0) & (df["e1rm_kg"]<=600)]

    return df.sort_values("date").reset_index(drop=True)

def save_splits(df: pd.DataFrame, outdir: str, base: str):
    n = len(df)
    n_val = max(int(0.15*n), 10)
    n_test = max(int(0.15*n), 10)
    n_train = max(n - n_val - n_test, 1)
    tr = df.iloc[:n_train]
    va = df.iloc[n_train:n_train+n_val]
    te = df.iloc[n_train+n_val:]
    tr.to_csv(f"{outdir}/{base}_train.csv", index=False)
    va.to_csv(f"{outdir}/{base}_val.csv", index=False)
    te.to_csv(f"{outdir}/{base}_test.csv", index=False)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="Путь к экспорту Strong (CSV)")
    ap.add_argument("--outdir", default="data_kg", help="Куда сохранить датасеты")
    args = ap.parse_args()

    import os
    os.makedirs(args.outdir, exist_ok=True)

    df = build_dataset(args.csv)
    cols = ["date","exercise","weight_kg","reps","adj_weight_kg","e1rm_kg"]
    df[cols].to_csv(f"{args.outdir}/clean_all.csv", index=False)

    for ex in KEEP:
        dfe = df[df["exercise"]==ex][cols].reset_index(drop=True)
        if dfe.empty: continue
        base = ex + "_all"
        dfe.to_csv(f"{args.outdir}/{base}.csv", index=False)
        save_splits(dfe, args.outdir, ex)

    # краткая сводка
    summ = (df.groupby("exercise")
              .agg(samples=("e1rm_kg","count"),
                   min_date=("date","min"),
                   max_date=("date","max"),
                   avg_reps=("reps","mean"),
                   p50_e1rm=("e1rm_kg","median"))
              .reset_index())
    summ.to_csv(f"{args.outdir}/summary.csv", index=False)
    print(f"✓ Готово. Папка: {args.outdir}")
    with pd.option_context("display.max_rows", None, "display.width", 160):
        print(summ.to_string(index=False))

if __name__ == "__main__":
    main()
