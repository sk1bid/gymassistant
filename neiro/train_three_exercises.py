# train_three_exercises.py
# -*- coding: utf-8 -*-
import argparse, json, os, re, math
import numpy as np
import pandas as pd
from dataclasses import dataclass
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error

LB_TO_KG = 0.45359237

# Канонические имена упражнений
KEEP = ["bench_press_barbell", "dips", "barbell_curl"]

# Синонимы Strong → каноническое имя
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

# Простая нормализация и маппинг
def to_canon(name: str) -> str | None:
    if not isinstance(name, str): return None
    s = name.strip().lower()
    s = s.replace("(", "").replace(")", "")
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

class MLP(nn.Module):
    def __init__(self, in_dim=2, hidden=64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 1)
        )
    def forward(self, x):  # x: [B,2]
        return self.net(x)

@dataclass
class FitResult:
    exercise: str
    n_samples: int
    mae: float
    rmse: float
    path_model: str
    path_meta: str

def load_strong_csv(path: str) -> pd.DataFrame:
    for enc in ("utf-8", "cp1252"):  # частые кодировки
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            pass
    return pd.read_csv(path)

def choose_col(df: pd.DataFrame, names: list[str]) -> str | None:
    for n in names:
        if n in df.columns: return n
    return None

def prepare_dataframe(csv_path: str) -> pd.DataFrame:
    raw = load_strong_csv(csv_path)
    col_date = choose_col(raw, ["Date","date","Workout Date","Timestamp"])
    col_ex   = choose_col(raw, ["Exercise","Exercise Name","exercise"])
    col_w    = choose_col(raw, ["Weight","Weight (lbs)","weight (lbs)","kg"])
    col_r    = choose_col(raw, ["Reps","reps","Rep Count"])
    if not all([col_date, col_ex, col_w, col_r]):
        raise ValueError(f"Не нашёл обязательные колонки. Есть: {list(raw.columns)}")

    df = pd.DataFrame({
        "date": pd.to_datetime(raw[col_date], errors="coerce"),
        "ex_raw": raw[col_ex].astype(str),
        "weight": pd.to_numeric(raw[col_w], errors="coerce"),
        "reps":   pd.to_numeric(raw[col_r], errors="coerce"),
    }).dropna()
    df = df[(df["reps"]>0) & (df["weight"]>=0)]
    df["canon"] = df["ex_raw"].map(to_canon)
    df = df[df["canon"].isin(KEEP)]

    # Переводим в кг (вход Strong — фунты)
    df["weight_kg"] = df["weight"] * LB_TO_KG

    # ВНИМАНИЕ: для dips НЕ прибавляем массу тела — работаем только с добавочным весом!
    df["adj_weight_kg"] = df["weight_kg"]

    # Цель: e1RM по сету (в кг) — относительно введённого веса (для dips это добавочный вес!)
    df["e1rm_kg"] = df.apply(lambda r: safe_e1rm(r["adj_weight_kg"], int(r["reps"])), axis=1)

    # Фильтры от опечаток
    df = df[(df["adj_weight_kg"]>=0) & (df["adj_weight_kg"]<=500)]
    df = df[(df["e1rm_kg"]>=0) & (df["e1rm_kg"]<=600)]
    df["reps"] = df["reps"].clip(1, 20)

    return df.sort_values("date").reset_index(drop=True)

def fit_one(ex_name: str, df: pd.DataFrame, outdir: str, device: torch.device) -> FitResult | None:
    ex_df = df[df["canon"]==ex_name].copy()
    if len(ex_df) < 50:
        return None

    X = ex_df[["adj_weight_kg","reps"]].values.astype("float32")
    y = ex_df["e1rm_kg"].values.astype("float32").reshape(-1,1)

    # масштабируем входы
    x_scaler = StandardScaler().fit(X)
    Xs = x_scaler.transform(X).astype("float32")

    # хронологическое разбиение
    n = len(Xs)
    n_test = max(int(0.15*n), 10)
    n_val  = max(int(0.15*n), 10)
    n_train = n - n_val - n_test
    if n_train < 30: return None

    def split(a): return a[:n_train], a[n_train:n_train+n_val], a[n_train+n_val:]
    Xtr, Xva, Xte = split(Xs); ytr, yva, yte = split(y)

    dl_tr = DataLoader(TensorDataset(torch.from_numpy(Xtr), torch.from_numpy(ytr)), batch_size=64, shuffle=True)
    dl_va = DataLoader(TensorDataset(torch.from_numpy(Xva), torch.from_numpy(yva)), batch_size=128)
    dl_te = DataLoader(TensorDataset(torch.from_numpy(Xte), torch.from_numpy(yte)), batch_size=128)

    model = MLP(in_dim=2, hidden=64).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    loss_fn = nn.MSELoss()

    best = math.inf; best_state=None; patience=10; noimp=0
    for ep in range(1, 200+1):
        model.train()
        for xb,yb in dl_tr:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad(set_to_none=True)
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward(); opt.step()

        # val
        model.eval()
        with torch.no_grad():
            v_losses=[]
            for xb,yb in dl_va:
                xb, yb = xb.to(device), yb.to(device)
                v_losses.append(loss_fn(model(xb), yb).item())
            v = float(np.mean(v_losses))
        if v < best - 1e-6:
            best = v; noimp=0
            best_state = {k:v_.detach().cpu() for k,v_ in model.state_dict().items()}
        else:
            noimp += 1
            if noimp>=patience: break

    model.load_state_dict(best_state)

    # test metrics
    model.eval()
    with torch.no_grad():
        pred = []
        for xb,yb in dl_te:
            p = model(xb.to(device)).cpu().numpy().ravel()
            pred.append(p)
        pred = np.concatenate(pred)
    rmse = float(np.sqrt(mean_squared_error(yte.ravel(), pred)))
    mae = float(mean_absolute_error(yte.ravel(), pred))

    os.makedirs(outdir, exist_ok=True)
    safe = ex_name
    model_path = os.path.join(outdir, f"{safe}.pt")
    meta_path  = os.path.join(outdir, f"{safe}.meta.json")
    torch.save({"state_dict": best_state}, model_path)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "exercise": ex_name,
            "input_scaler": {"mean": x_scaler.mean_.tolist(), "scale": x_scaler.scale_.tolist()},
            "metrics": {"mae_e1rm_kg": mae, "rmse_e1rm_kg": rmse},
            "units": "kg",
            "notes": "NO bodyweight added. Model input: [weight_kg_on_belt_or_bar, reps]"
        }, f, ensure_ascii=False, indent=2)

    print(f"✓ {ex_name}: n={len(ex_df)} | MAE={mae:.2f} кг | RMSE={rmse:.2f} кг")
    return FitResult(ex_name, len(ex_df), mae, rmse, model_path, meta_path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="Путь к экспорту Strong (CSV)")
    ap.add_argument("--outdir", default="models_kg", help="Куда сохранить модели")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available()
                          else "mps" if getattr(torch.backends,'mps',None) and torch.backends.mps.is_available()
                          else "cpu")
    print("Device:", device)

    df = prepare_dataframe(args.csv)
    results=[]
    for ex in KEEP:
        r = fit_one(ex, df, args.outdir, device)
        if r: results.append(r)

    if not results:
        print("Недостаточно данных для трёх выбранных упражнений.")
    else:
        # сводка
        rows = [{
            "exercise": r.exercise, "samples": r.n_samples,
            "MAE_kg": round(r.mae,2), "RMSE_kg": round(r.rmse,2),
            "model": os.path.basename(r.path_model)
        } for r in results]
        summ = pd.DataFrame(rows).sort_values("MAE_kg")
        print("\n=== Summary ===")
        print(summ.to_string(index=False))
        summ.to_csv(os.path.join(args.outdir, "summary.csv"), index=False)

if __name__ == "__main__":
    main()
