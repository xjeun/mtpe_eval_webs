# deepl-eval-web/scorer/app.py

from pathlib import Path
from dotenv import load_dotenv

# deepl-eval-web/.env 하나를 server 와 같이 쓴다.
# HF_TOKEN 이 환경변수로 올라가면 huggingface_hub 가 알아서 읽는다
# (COMETkiwi 는 gated 모델이라 이 토큰이 있어야 다운로드된다)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from typing import List, Optional, Dict, Any
from fastapi import FastAPI
from pydantic import BaseModel
import sacrebleu
import torch

# COMET
from comet import download_model, load_from_checkpoint

app = FastAPI(title="DeepL Eval Scorer", version="1.0.0")

# ---- Request schema ----
class ScoreRequest(BaseModel):
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None
    sources: List[str]
    references: List[str]
    hypotheses: List[str]

# ---- Load both COMET models once ----
COMET_MODEL_NAME    = "Unbabel/wmt22-comet-da"       # reference-based
COMETKIWI_MODEL_NAME = "Unbabel/wmt22-cometkiwi-da"  # QE (no reference needed)

_comet_model   = None
_cometkiwi_model = None

@app.on_event("startup")
def _startup():
    global _comet_model, _cometkiwi_model

    print("[startup] Loading COMET (wmt22-comet-da)...")
    ckpt = download_model(COMET_MODEL_NAME)
    _comet_model = load_from_checkpoint(ckpt)
    _comet_model.eval()
    print("[startup] COMET loaded.")

    print("[startup] Loading COMETkiwi (wmt22-cometkiwi-da)...")
    ckpt_kiwi = download_model(COMETKIWI_MODEL_NAME)
    _cometkiwi_model = load_from_checkpoint(ckpt_kiwi)
    _cometkiwi_model.eval()
    print("[startup] COMETkiwi loaded.")

@app.get("/health")
def health():
    return {"ok": True}

def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

@app.post("/score")
def score(req: ScoreRequest) -> Dict[str, Any]:
    if not (len(req.sources) == len(req.references) == len(req.hypotheses)):
        return {
            "error": "sources/references/hypotheses length mismatch",
            "lens": [len(req.sources), len(req.references), len(req.hypotheses)],
        }

    sources = req.sources
    refs    = req.references
    hyps    = req.hypotheses
    n       = len(hyps)

    # ---- Sentence-level BLEU / chrF ----
    sent_bleu = []
    sent_chrf = []
    for h, r in zip(hyps, refs):
        sent_bleu.append(_safe_float(sacrebleu.sentence_bleu(h, [r]).score))
        sent_chrf.append(_safe_float(sacrebleu.sentence_chrf(h, [r]).score))

    # ---- Corpus-level BLEU / chrF ----
    corpus_bleu = sacrebleu.corpus_bleu(hyps, [refs]).score
    corpus_chrf = sacrebleu.corpus_chrf(hyps, [refs]).score

    # ---- COMET (reference-based): src + mt + ref ----
    data_comet = [{"src": s, "mt": h, "ref": r} for s, h, r in zip(sources, hyps, refs)]
    with torch.no_grad():
        pred_comet = _comet_model.predict(data_comet, batch_size=8, gpus=0)

    comet_scores = pred_comet.get("scores", None)
    comet_sys    = pred_comet.get("system_score", None)

    # ---- COMETkiwi (QE): src + mt only (no reference) ----
    data_kiwi = [{"src": s, "mt": h} for s, h in zip(sources, hyps)]
    with torch.no_grad():
        pred_kiwi = _cometkiwi_model.predict(data_kiwi, batch_size=8, gpus=0)

    kiwi_scores = pred_kiwi.get("scores", None)
    kiwi_sys    = pred_kiwi.get("system_score", None)

    # ---- Per-row results ----
    results = []
    for i in range(n):
        results.append({
            "bleu":      sent_bleu[i],
            "chrf":      sent_chrf[i],
            "comet":     _safe_float(comet_scores[i]) if comet_scores is not None else None,
            "cometkiwi": _safe_float(kiwi_scores[i])  if kiwi_scores  is not None else None,
        })

    avg = {
        "bleu":      _safe_float(corpus_bleu),
        "chrf":      _safe_float(corpus_chrf),
        "comet":     _safe_float(comet_sys)  if comet_sys  is not None else None,
        "cometkiwi": _safe_float(kiwi_sys)   if kiwi_sys   is not None else None,
    }

    return {"results": results, "avg": avg}