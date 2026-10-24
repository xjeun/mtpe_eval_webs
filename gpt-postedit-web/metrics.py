from typing import Dict, Optional, Tuple, List
import pandas as pd
import sacrebleu

def compute_corpus_metrics(refs: List[str], hyps: List[str]) -> Dict[str, float]:
    bleu = sacrebleu.corpus_bleu(hyps, [refs])
    chrf = sacrebleu.corpus_chrf(hyps, [refs])
    return {"BLEU": float(bleu.score), "chrF": float(chrf.score)}

def compute_sentence_metrics(refs: List[str], hyps: List[str]) -> Tuple[List[float], List[float]]:
    sent_bleu, sent_chrf = [], []
    for r, h in zip(refs, hyps):
        sb = sacrebleu.sentence_bleu(h, [r], smooth_method="exp")
        sc = sacrebleu.sentence_chrf(h, [r])
        sent_bleu.append(float(sb.score))
        sent_chrf.append(float(sc.score))
    return sent_bleu, sent_chrf

def compute_comet_segmentwise(df: pd.DataFrame, src_col: str, ref_col: str, hyp_col: str, model_name: str):
    """Reference-based COMET: src + mt + ref"""
    from comet import download_model, load_from_checkpoint
    model_path = download_model(model_name)
    model = load_from_checkpoint(model_path)

    data = []
    for _, r in df.iterrows():
        data.append({
            "src": str(r[src_col]),
            "ref": str(r[ref_col]),
            "mt":  str(r[hyp_col]),
        })

    outputs = model.predict(data, batch_size=16, gpus=0)
    return float(outputs.system_score), list(outputs.scores)

def compute_cometkiwi_segmentwise(df: pd.DataFrame, src_col: str, hyp_col: str, model_name: str):
    """QE COMETkiwi: src + mt only (no reference)"""
    from comet import download_model, load_from_checkpoint
    model_path = download_model(model_name)
    model = load_from_checkpoint(model_path)

    data = []
    for _, r in df.iterrows():
        data.append({
            "src": str(r[src_col]),
            "mt":  str(r[hyp_col]),
        })

    outputs = model.predict(data, batch_size=16, gpus=0)
    return float(outputs.system_score), list(outputs.scores)

def compute_metrics(
    df: pd.DataFrame,
    id_col: str,
    src_col: str,
    ref_col: Optional[str],
    hyp_col: str,
    comet_model: str,
    cometkiwi_model: str = "Unbabel/wmt22-cometkiwi-da",  # ✅ 추가
) -> Dict[str, object]:
    metrics: Dict[str, object] = {"n": int(len(df))}

    if ref_col is None or ref_col not in df.columns:
        raise ValueError("reference(ref) 컬럼이 없어서 지표 계산을 할 수 없어요. ref 컬럼을 포함해줘.")

    refs = df[ref_col].astype(str).tolist()
    hyps = df[hyp_col].astype(str).tolist()

    # corpus-level BLEU / chrF
    metrics.update(compute_corpus_metrics(refs, hyps))

    # sentence-level BLEU / chrF
    sent_bleu, sent_chrf = compute_sentence_metrics(refs, hyps)
    metrics["sentence_BLEU"] = sent_bleu
    metrics["sentence_chrF"] = sent_chrf

    # ✅ COMET (reference-based)
    sys_score, seg_scores = compute_comet_segmentwise(df, src_col, ref_col, hyp_col, comet_model)
    metrics["COMET"] = sys_score
    metrics["sentence_COMET"] = seg_scores

    # ✅ COMETkiwi (QE, no reference)
    kiwi_sys, kiwi_segs = compute_cometkiwi_segmentwise(df, src_col, hyp_col, cometkiwi_model)
    metrics["COMETkiwi"] = kiwi_sys
    metrics["sentence_COMETkiwi"] = kiwi_segs

    return metrics