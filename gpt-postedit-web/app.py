import csv
import os
import time
from datetime import datetime
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from huggingface_hub import login

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
# COMETkiwi(gated 모델) 다운로드용 HuggingFace 토큰은 .env 의 HF_TOKEN 에서 읽는다
if os.getenv("HF_TOKEN", "").strip():
    login(token=os.getenv("HF_TOKEN").strip())

from gpt_translate import translate_dataframe, PROMPT_TYPES, NEEDS_CONTEXT_TYPES
from metrics import compute_metrics
from excel_export import build_excel_bytes

st.set_page_config(page_title="GPT Post-Edit + Metrics Export", layout="wide")
st.title("GPT 후편집 자동화 + BLEU/chrF/COMET/COMETkiwi + Excel Export")

# ✅ _mean 함수 탭 밖에서 한 번만 정의
def _mean(xs):
    return sum(xs) / len(xs) if xs else None

# ============================================================
# 토큰 사용량 로그 (실행마다 누적 기록)
# ============================================================
TOKEN_LOG_PATH = os.path.join(os.path.dirname(__file__), "token_usage_log.csv")
TOKEN_LOG_FIELDS = [
    "timestamp", "tab", "model", "target_lang", "prompt_type",
    "n_rows", "prompt_tokens", "completion_tokens", "total_tokens", "elapsed_sec",
]

def _log_token_usage(tab: str, model: str, target_lang: str, prompt_type: str,
                      n_rows: int, usage: dict, elapsed: float) -> None:
    is_new = not os.path.exists(TOKEN_LOG_PATH)
    with open(TOKEN_LOG_PATH, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(TOKEN_LOG_FIELDS)
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            tab, model, target_lang, prompt_type, n_rows,
            usage["prompt_tokens"], usage["completion_tokens"], usage["total_tokens"],
            round(elapsed, 1),
        ])

if os.path.exists(TOKEN_LOG_PATH):
    with st.expander("📜 토큰 사용 기록 (누적 로그)"):
        log_df = pd.read_csv(TOKEN_LOG_PATH)
        st.dataframe(log_df, use_container_width=True)
        st.caption(
            f"누적 total_tokens: {int(log_df['total_tokens'].sum()):,} "
            f"(prompt: {int(log_df['prompt_tokens'].sum()):,}, "
            f"completion: {int(log_df['completion_tokens'].sum()):,}, "
            f"실행 횟수: {len(log_df)}회)"
        )

# ---- 탭 구성 ----
tab1, tab2 = st.tabs(["🚀 후편집 실험", "📊 임계값 실험"])

# ============================================================
# TAB 1 — 후편집 실험
# ============================================================
with tab1:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        st.error("OPENAI_API_KEY 환경변수가 비어있어요.")
    else:
        st.sidebar.header("설정")
        model       = st.sidebar.text_input("Model", value="gpt-5.2")
        temperature = st.sidebar.number_input("Temperature", 0.0, 1.0, 0.0, 0.1)
        sleep_sec   = st.sidebar.number_input("Request 간 sleep", 0.0, 5.0, 0.3, 0.1)
        target_lang = st.sidebar.selectbox("도착 언어", ["English", "French"], index=0)
        prompt_type = st.sidebar.selectbox("프롬프트 타입", PROMPT_TYPES, index=0)

        st.sidebar.divider()
        comet_model     = "Unbabel/wmt22-comet-da"
        cometkiwi_model = "Unbabel/wmt22-cometkiwi-da"
        st.sidebar.caption(f"COMET: {comet_model}")
        st.sidebar.caption(f"COMETkiwi: {cometkiwi_model}")

        needs_context = prompt_type in NEEDS_CONTEXT_TYPES

        st.subheader("1) 샘플 파일 업로드 (필수)")
        st.caption("필수 컬럼: ID, source_text, reference, deepl_translation")
        uploaded = st.file_uploader("샘플 엑셀 업로드 (.xlsx)", type=["xlsx"], key="sample")

        full_corpus_df = None
        if needs_context:
            st.subheader("2) 전체 코퍼스 파일 업로드")
            is_p2 = prompt_type.startswith("P2-")
            if is_p2:
                st.caption("⚠️ P2 계열은 전체 코퍼스 파일이 **필수**입니다.")
            else:
                st.caption("앞 4문장 원문 참조용. 없으면 preceding context 없이 실행됩니다.")
            uploaded_full = st.file_uploader(
                "전체 코퍼스 엑셀 업로드 (.xlsx)", type=["xlsx"], key="full_corpus"
            )
            if uploaded_full:
                try:
                    full_corpus_df = pd.read_excel(uploaded_full)
                    st.success(f"✅ 전체 코퍼스 로드 완료: {len(full_corpus_df)}개 문장")
                except Exception as e:
                    st.error(f"전체 코퍼스 파일 읽기 실패: {e}")
            else:
                if is_p2:
                    st.error("❌ P2 계열 실험은 전체 코퍼스 파일이 필요합니다.")

        section_num = "3)" if needs_context else "2)"
        st.subheader(f"{section_num} 컬럼 설정")
        col1, col2 = st.columns(2)
        with col1:
            id_col  = st.text_input("ID 컬럼명", value="ID")
            src_col = st.text_input("원문 컬럼명", value="source_text")
        with col2:
            ref_col = st.text_input("참조번역 컬럼명", value="reference")
            nmt_col = st.text_input("DeepL 번역 컬럼명", value="deepl_translation")

        if uploaded is not None:
            try:
                df = pd.read_excel(uploaded)
            except Exception as e:
                st.error(f"파일 읽기 실패: {e}")
                df = None

            if df is not None:
                missing = [c for c in [id_col, src_col, nmt_col] if c not in df.columns]
                if missing:
                    st.error(f"필수 컬럼이 없어요: {missing}\n현재 컬럼: {list(df.columns)}")
                else:
                    df = df.copy()
                    df[id_col]  = df[id_col].astype(str).str.strip()
                    df[src_col] = df[src_col].astype(str)
                    df[nmt_col] = df[nmt_col].astype(str)
                    if ref_col in df.columns:
                        df[ref_col] = df[ref_col].astype(str)
                    df = df[df[src_col].str.strip().ne("")].reset_index(drop=True)

                    if df[id_col].duplicated().any():
                        st.error("ID 컬럼에 중복이 있어요.")
                    else:
                        st.subheader("미리보기")
                        st.dataframe(df.head(20), use_container_width=True)
                        st.info(
                            f"🌐 도착 언어: **{target_lang}** | 📝 프롬프트: **{prompt_type}**"
                        )
                        st.divider()

                        is_p2 = prompt_type.startswith("P2-")
                        button_disabled = is_p2 and full_corpus_df is None

                        if button_disabled:
                            st.button(
                                "🚀 후편집 + 평가 + Excel 생성",
                                type="primary",
                                disabled=True
                            )
                            st.error("❌ 전체 코퍼스 파일을 업로드해야 실행할 수 있습니다.")
                        else:
                            run = st.button(
                                "🚀 후편집 + 평가 + Excel 생성",
                                type="primary"
                            )
                            if run:
                                progress = st.progress(0, text="준비 중...")
                                log = st.empty()
                                try:
                                    t0 = time.time()
                                    progress.progress(5, text="후편집 시작...")
                                    log.write(
                                        f"🔁 GPT 후편집 중... ({prompt_type} → {target_lang})"
                                    )

                                    df_out, usage = translate_dataframe(
                                        df=df,
                                        id_col=id_col,
                                        src_col=src_col,
                                        nmt_col=nmt_col,
                                        model=model,
                                        temperature=temperature,
                                        sleep_sec=sleep_sec,
                                        target_lang=target_lang,
                                        prompt_type=prompt_type,
                                        full_corpus_df=full_corpus_df,
                                        full_id_col=id_col,
                                        full_src_col=src_col,
                                        progress_callback=lambda done, total: progress.progress(
                                            int(5 + 60 * (done / max(total, 1))),
                                            text=f"후편집 진행: {done}/{total}"
                                        ),
                                    )

                                    progress.progress(70, text="평가지표 계산 중...")
                                    metrics = compute_metrics(
                                        df=df_out,
                                        id_col=id_col,
                                        src_col=src_col,
                                        ref_col=ref_col if ref_col in df_out.columns else None,
                                        hyp_col="gpt_hyp",
                                        comet_model=comet_model,
                                        cometkiwi_model=cometkiwi_model,
                                    )

                                    df_out["sent_bleu"]      = metrics["sentence_BLEU"]
                                    df_out["sent_chrf"]      = metrics["sentence_chrF"]
                                    df_out["sent_comet"]     = metrics["sentence_COMET"]
                                    df_out["sent_cometkiwi"] = metrics["sentence_COMETkiwi"]

                                    metrics["BLEU_sentence_avg"]      = _mean(metrics["sentence_BLEU"])
                                    metrics["chrF_sentence_avg"]      = _mean(metrics["sentence_chrF"])
                                    metrics["COMET_sentence_avg"]     = _mean(metrics["sentence_COMET"])
                                    metrics["COMETkiwi_sentence_avg"] = _mean(metrics["sentence_COMETkiwi"])
                                    metrics["BLEU_corpus"]            = metrics["BLEU"]
                                    metrics["chrF_corpus"]            = metrics["chrF"]
                                    metrics["COMET_system"]           = metrics["COMET"]
                                    metrics["COMETkiwi_system"]       = metrics["COMETkiwi"]
                                    for k in ["BLEU", "chrF", "COMET", "COMETkiwi"]:
                                        metrics.pop(k, None)

                                    progress.progress(90, text="Excel 생성 중...")
                                    excel_bytes = build_excel_bytes(
                                        df=df_out,
                                        metrics=metrics,
                                        meta={
                                            "model":           model,
                                            "target_lang":     target_lang,
                                            "prompt_type":     prompt_type,
                                            "temperature":     temperature,
                                            "sleep_sec":       sleep_sec,
                                            "comet_model":     comet_model,
                                            "cometkiwi_model": cometkiwi_model,
                                            "총 API 호출 수":       usage["n_calls"],
                                            "총 prompt_tokens":     usage["prompt_tokens"],
                                            "총 completion_tokens": usage["completion_tokens"],
                                            "총 total_tokens":      usage["total_tokens"],
                                        },
                                        id_col=id_col,
                                        src_col=src_col,
                                        ref_col=ref_col if ref_col in df_out.columns else None,
                                        hyp_col="gpt_hyp",
                                    )

                                    elapsed = time.time() - t0
                                    progress.progress(100, text=f"완료! (소요 {elapsed:.1f}s)")
                                    log.success("✅ 완료!")

                                    _log_token_usage(
                                        tab="tab1", model=model, target_lang=target_lang,
                                        prompt_type=prompt_type, n_rows=len(df_out),
                                        usage=usage, elapsed=elapsed,
                                    )

                                    st.subheader("토큰 사용량 (이번 실행)")
                                    st.json(usage)

                                    st.subheader("요약 지표")
                                    st.json(metrics)

                                    st.download_button(
                                        label="⬇️ 결과 Excel 다운로드",
                                        data=excel_bytes,
                                        file_name=f"gpt_{prompt_type}_{target_lang.lower()}_metrics.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    )
                                    st.subheader("결과 미리보기")
                                    st.dataframe(df_out.head(30), use_container_width=True)

                                except Exception as e:
                                    st.error(f"실행 실패: {e}")
        else:
            st.info("샘플 파일을 업로드하면 시작할 수 있어요.")

# ============================================================
# TAB 2 — 임계값 실험
# ============================================================
with tab2:
    st.subheader("COMETkiwi 임계값 기반 선택적 후편집 실험")
    st.caption(
        "DeepL COMETkiwi < 임계값인 문장만 GPT P1-title로 후편집하고, "
        "나머지는 DeepL 번역 그대로 유지하여 전체 코퍼스 기준 혼합 평균을 계산합니다."
    )

    # ---- 설정 ----
    t2_col1, t2_col2, t2_col3 = st.columns(3)
    with t2_col1:
        t2_lang = st.selectbox("도착 언어", ["English", "French"], key="t2_lang")
    with t2_col2:
        t2_threshold = st.selectbox(
            "COMETkiwi 임계값",
            [0.60, 0.65, 0.70, 0.75, 0.80, 0.85],
            index=2,
            key="t2_threshold"
        )
    with t2_col3:
        t2_model = st.text_input("Model", value="gpt-5.2", key="t2_model")

    t2_sleep = st.number_input("Request 간 sleep", 0.0, 5.0, 0.3, 0.1, key="t2_sleep")

    # ---- 파일 업로드 ----
    st.subheader("1) 실험 파일 업로드 (필수)")
    st.caption(
        "필수 컬럼: index(또는 ID), source_text, reference, "
        "deepl_translation, DeepL_CometKiwi, DeepL_COMET"
    )
    t2_uploaded = st.file_uploader(
        "실험 엑셀 업로드 (.xlsx)", type=["xlsx"], key="t2_sample"
    )
    st.caption("※ P1-title 프롬프트는 preceding context가 없어 전체 코퍼스 파일이 필요 없습니다.")

    # ---- 컬럼 설정 ----
    st.subheader("2) 컬럼 설정")
    c1, c2, c3 = st.columns(3)
    with c1:
        t2_id_col  = st.text_input("ID 컬럼명", value="index", key="t2_id")
        t2_src_col = st.text_input("원문 컬럼명", value="source_text", key="t2_src")
    with c2:
        t2_ref_col      = st.text_input("참조번역 컬럼명", value="reference", key="t2_ref")
        t2_nmt_col      = st.text_input("DeepL 번역 컬럼명", value="deepl_translation", key="t2_nmt")
    with c3:
        t2_kiwi_col     = st.text_input("DeepL COMETkiwi 컬럼명", value="DeepL_CometKiwi", key="t2_kiwi")
        t2_comet_dl_col = st.text_input("DeepL COMET 컬럼명", value="DeepL_COMET", key="t2_comet_dl")

    if t2_uploaded is not None:
        try:
            t2_df = pd.read_excel(t2_uploaded)
        except Exception as e:
            st.error(f"파일 읽기 실패: {e}")
            t2_df = None

        if t2_df is not None:
            required = [t2_id_col, t2_src_col, t2_nmt_col, t2_kiwi_col]
            t2_missing = [c for c in required if c not in t2_df.columns]
            if t2_missing:
                st.error(
                    f"필수 컬럼이 없어요: {t2_missing}\n현재 컬럼: {list(t2_df.columns)}"
                )
            else:
                t2_df = t2_df.copy()
                t2_df[t2_id_col] = t2_df[t2_id_col].astype(str).str.strip()

                # 임계값 이하 문장 선별
                selected_mask = t2_df[t2_kiwi_col] < t2_threshold
                selected_df   = t2_df[selected_mask].reset_index(drop=True)
                non_selected  = t2_df[~selected_mask]
                total_n       = len(t2_df)
                selected_n    = len(selected_df)

                st.info(
                    f"📊 전체 {total_n}개 중 DeepL COMETkiwi < {t2_threshold}: "
                    f"**{selected_n}개** ({selected_n/total_n*100:.1f}%) 후편집 대상 | "
                    f"나머지 **{total_n - selected_n}개**는 DeepL 번역 유지"
                )
                st.dataframe(
                    selected_df[[t2_id_col, t2_src_col, t2_nmt_col, t2_kiwi_col]].head(10),
                    use_container_width=True
                )
                st.divider()

                if selected_n == 0:
                    st.warning("선별된 문장이 없습니다. 임계값을 높여보세요.")
                else:
                    run_t2 = st.button(
                        f"🚀 {selected_n}개 문장 GPT P1-title 후편집 + 전체 혼합 평균 계산",
                        type="primary",
                        key="t2_run"
                    )
                    if run_t2:
                        t2_comet_model     = "Unbabel/wmt22-comet-da"
                        t2_cometkiwi_model = "Unbabel/wmt22-cometkiwi-da"

                        progress2 = st.progress(0, text="준비 중...")
                        log2 = st.empty()

                        try:
                            t0 = time.time()
                            progress2.progress(5, text="후편집 시작...")
                            log2.write(
                                f"🔁 GPT P1-title 후편집 중... "
                                f"({selected_n}개 → {t2_lang})"
                            )

                            df_out2, usage2 = translate_dataframe(
                                df=selected_df,
                                id_col=t2_id_col,
                                src_col=t2_src_col,
                                nmt_col=t2_nmt_col,
                                model=t2_model,
                                temperature=0.0,
                                sleep_sec=t2_sleep,
                                target_lang=t2_lang,
                                prompt_type="P1-title",
                                full_corpus_df=None,
                                progress_callback=lambda done, total: progress2.progress(
                                    int(5 + 60 * (done / max(total, 1))),
                                    text=f"후편집 진행: {done}/{total}"
                                ),
                            )

                            progress2.progress(70, text="평가지표 계산 중...")
                            log2.write("📏 선별 문장 COMET/COMETkiwi 계산 중...")

                            metrics2 = compute_metrics(
                                df=df_out2,
                                id_col=t2_id_col,
                                src_col=t2_src_col,
                                ref_col=t2_ref_col if t2_ref_col in df_out2.columns else None,
                                hyp_col="gpt_hyp",
                                comet_model=t2_comet_model,
                                cometkiwi_model=t2_cometkiwi_model,
                            )

                            df_out2["sent_bleu"]      = metrics2["sentence_BLEU"]
                            df_out2["sent_chrf"]      = metrics2["sentence_chrF"]
                            df_out2["sent_comet"]     = metrics2["sentence_COMET"]
                            df_out2["sent_cometkiwi"] = metrics2["sentence_COMETkiwi"]

                            # ✅ 전체 코퍼스 기준 혼합 평균 계산
                            # 선별 문장: GPT 후편집 점수
                            gpt_kiwi_scores  = metrics2["sentence_COMETkiwi"]  # 선별 n개
                            gpt_comet_scores = metrics2["sentence_COMET"]       # 선별 n개

                            # 선별 안 된 문장: DeepL 점수 그대로
                            non_sel_kiwi_scores  = non_selected[t2_kiwi_col].tolist() \
                                if t2_kiwi_col in non_selected.columns else []
                            non_sel_comet_scores = non_selected[t2_comet_dl_col].tolist() \
                                if t2_comet_dl_col in non_selected.columns else []

                            # 혼합 전체 평균
                            mixed_kiwi_mean  = _mean(gpt_kiwi_scores + non_sel_kiwi_scores)
                            mixed_comet_mean = _mean(gpt_comet_scores + non_sel_comet_scores)

                            # DeepL 전체 평균 (비교 기준)
                            deepl_full_kiwi_mean  = t2_df[t2_kiwi_col].mean()
                            deepl_full_comet_mean = t2_df[t2_comet_dl_col].mean() \
                                if t2_comet_dl_col in t2_df.columns else None

                            # 선별 문장만의 DeepL vs GPT 평균 (참고용)
                            deepl_sel_kiwi_mean  = t2_df.loc[selected_mask, t2_kiwi_col].mean()
                            deepl_sel_comet_mean = t2_df.loc[selected_mask, t2_comet_dl_col].mean() \
                                if t2_comet_dl_col in t2_df.columns else None
                            gpt_sel_kiwi_mean  = _mean(gpt_kiwi_scores)
                            gpt_sel_comet_mean = _mean(gpt_comet_scores)

                            summary2 = {
                                "── 실험 설정 ──": "",
                                "임계값":          f"< {t2_threshold}",
                                "선별 문장 수":     selected_n,
                                "선별 비율(%)":     round(selected_n / total_n * 100, 1),
                                "전체 문장 수":     total_n,
                                "── 전체 코퍼스 기준 (혼합 평균) ──": "",
                                "DeepL COMETkiwi 전체 평균":          round(deepl_full_kiwi_mean, 4),
                                "선택적 MTPE 후 COMETkiwi 혼합 평균": round(mixed_kiwi_mean, 4) if mixed_kiwi_mean else None,
                                "DeepL COMET 전체 평균":              round(deepl_full_comet_mean, 4) if deepl_full_comet_mean else None,
                                "선택적 MTPE 후 COMET 혼합 평균":     round(mixed_comet_mean, 4) if mixed_comet_mean else None,
                                "── 선별 문장만 (참고) ──": "",
                                "DeepL COMETkiwi (선별 평균)":  round(deepl_sel_kiwi_mean, 4),
                                "GPT COMETkiwi (선별 후편집)":  round(gpt_sel_kiwi_mean, 4) if gpt_sel_kiwi_mean else None,
                                "DeepL COMET (선별 평균)":      round(deepl_sel_comet_mean, 4) if deepl_sel_comet_mean else None,
                                "GPT COMET (선별 후편집)":      round(gpt_sel_comet_mean, 4) if gpt_sel_comet_mean else None,
                            }

                            progress2.progress(90, text="Excel 생성 중...")
                            excel_bytes2 = build_excel_bytes(
                                df=df_out2,
                                metrics={
                                    "n (선별)":               selected_n,
                                    "n (전체)":               total_n,
                                    "BLEU_sentence_avg":      _mean(metrics2["sentence_BLEU"]),
                                    "chrF_sentence_avg":      _mean(metrics2["sentence_chrF"]),
                                    "COMET_sentence_avg":     gpt_sel_comet_mean,
                                    "COMETkiwi_sentence_avg": gpt_sel_kiwi_mean,
                                    "COMET_혼합평균(전체)":    mixed_comet_mean,
                                    "COMETkiwi_혼합평균(전체)": mixed_kiwi_mean,
                                    "BLEU_corpus":            metrics2["BLEU"],
                                    "chrF_corpus":            metrics2["chrF"],
                                    "COMET_system":           metrics2["COMET"],
                                    "COMETkiwi_system":       metrics2["COMETkiwi"],
                                },
                                meta={
                                    "model":           t2_model,
                                    "target_lang":     t2_lang,
                                    "prompt_type":     "P1-title",
                                    "threshold":       f"DeepL_COMETkiwi < {t2_threshold}",
                                    "selected_n":      selected_n,
                                    "total_n":         total_n,
                                    "temperature":     0.0,
                                    "comet_model":     t2_comet_model,
                                    "cometkiwi_model": t2_cometkiwi_model,
                                    "총 API 호출 수":       usage2["n_calls"],
                                    "총 prompt_tokens":     usage2["prompt_tokens"],
                                    "총 completion_tokens": usage2["completion_tokens"],
                                    "총 total_tokens":      usage2["total_tokens"],
                                },
                                id_col=t2_id_col,
                                src_col=t2_src_col,
                                ref_col=t2_ref_col if t2_ref_col in df_out2.columns else None,
                                hyp_col="gpt_hyp",
                            )

                            elapsed = time.time() - t0
                            progress2.progress(100, text=f"완료! (소요 {elapsed:.1f}s)")
                            log2.success("✅ 완료!")

                            _log_token_usage(
                                tab="tab2 (임계값)", model=t2_model, target_lang=t2_lang,
                                prompt_type="P1-title", n_rows=selected_n,
                                usage=usage2, elapsed=elapsed,
                            )

                            st.subheader("토큰 사용량 (이번 실행)")
                            st.json(usage2)

                            st.subheader("실험 결과 요약")
                            st.json(summary2)

                            st.download_button(
                                label="⬇️ 결과 Excel 다운로드",
                                data=excel_bytes2,
                                file_name=f"threshold_{t2_threshold}_{t2_lang.lower()}_metrics.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )

                            st.subheader("결과 미리보기 (후편집 문장)")
                            st.dataframe(df_out2.head(20), use_container_width=True)

                        except Exception as e:
                            st.error(f"실행 실패: {e}")
    else:
        st.info("실험 파일을 업로드하면 시작할 수 있어요.")