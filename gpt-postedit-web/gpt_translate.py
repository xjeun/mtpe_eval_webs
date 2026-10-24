import os
import time
from typing import Callable, Dict, Optional, List, Tuple
import pandas as pd
from openai import OpenAI

# ============================================================
# 상수
# ============================================================
CHARACTER_CATALOG = """Characters:
- Ki-taek (male): head of a family of four unemployed adults; calm and at peace; skeptical about grandiose plans, but dreams of being able to eat and live like normal people
- Chung-sook (female): Ki-taek's wife; determined, strong image; former national medalist in hammer throw
- Ki-woo (male): Ki-taek's son; always positive by nature; visits the Park home as an English tutor, carrying a fake diploma
- Ki-jung (female): Ki-taek's daughter; the most realistic and hard-headed of her family; remains unfazed whatever the situation; works as an art tutor at the Park home
- Mr. Park (male): young CEO of a global IT firm; leaves the day-to-day running of the house to his wife; courteous to those who work in his home
- Yeon-kyo (female): Mr. Park's wife; naïve or pure-hearted; trusts people too easily; manages all household matters
- Da-hye (female): Mr. Park's high school daughter; feels neglected by her parents; fascinated by her tutor Ki-woo
- Da-song (male): Mr. Park's elementary school son; eccentric and wild; a Cub Scout who loves camping and walkie-talkies; a fanatic for all things related to Native Americans
- Moon-gwang (female): live-in housekeeper who has worked for the Park family for many years"""

OUTPUT_ONLY = "Output only the post-edited translation. Do not include any explanation or additional text."

PROMPT_TYPES = [
    "translation",
    "P0",
    "P1-domain",
    "P1-title",
    "P1-speaker",
    "P2-zero_anaphora",
    "P2-lexical_ambiguity",
]

# P2 계열 + P1-speaker는 preceding context 필요
NEEDS_CONTEXT_TYPES = {"P1-speaker", "P2-zero_anaphora", "P2-lexical_ambiguity"}

# ============================================================
# P2 언어 현상 지시문
# ============================================================
P2_INSTRUCTIONS = {
    "zero_anaphora": {
        "en": (
            "Korean frequently omits subjects and objects. Where necessary, restore appropriate pronouns "
            "(he/she/they/I) based on discourse context. Pay special attention to gender — Korean nouns do not "
            "mark gender, so use surrounding context clues to determine he/she. When the agent is unknown or "
            "unimportant, passive constructions or impersonal subjects (`it`, `there`) are acceptable and "
            "preferred over forced pronoun insertion."
        ),
        "fr": (
            "Korean frequently omits subjects and objects. In French, restore the appropriate subject pronoun "
            "(il/elle/ils/elles/on/je/tu/nous/vous) where necessary, inferred from discourse context. "
            "Pay special attention to: (1) gender agreement — infer gender from surrounding context clues, "
            "(2) vous vs. tu — use the register appropriate to the speaker relationship. "
            "When the agent is unknown or unimportant, impersonal constructions (`il`, `on`), "
            "`c'est` constructions, or passive voice are acceptable and preferred over forced pronoun insertion."
        ),
    },
    "lexical_ambiguity": (
        "When post-editing, correct any word that was mistranslated due to lexical ambiguity. "
        "Korean words are highly polysemous — select the meaning that best fits the discourse context. "
        "Korean proper nouns and names — whether written in Sino-Korean characters or pure Korean — "
        "should always be transliterated, never translated by meaning."
    ),
}

# ============================================================
# 유틸
# ============================================================
def _get_lang_code(target_lang: str) -> str:
    lang = target_lang.strip().lower()
    if "french" in lang or lang == "fr":
        return "fr"
    return "en"

def _build_preceding_block(preceding_sources: Optional[List[str]]) -> str:
    if not preceding_sources:
        return "Here are the preceding lines for context:\n(No preceding context available)"
    items = [f"{i+1}. {s}" for i, s in enumerate(preceding_sources)]
    return "Here are the preceding lines for context:\n" + "\n".join(items)

def get_preceding_sources(
    full_df: pd.DataFrame,
    id_col: str,
    src_col: str,
    target_id: str,
    n: int = 4,
) -> List[str]:
    """원본 전체 코퍼스에서 target_id 앞 n개 원문 반환"""
    full_ids = full_df[id_col].astype(str).tolist()
    try:
        idx = full_ids.index(str(target_id))
    except ValueError:
        return []
    start = max(0, idx - n)
    return full_df.iloc[start:idx][src_col].tolist()

# ============================================================
# 프롬프트 빌더
# ============================================================
def _build_user_message(
    source: str,
    nmt: str,
    target_lang: str,
    prompt_type: str,
    preceding_sources: Optional[List[str]] = None,
) -> str:
    lang_code = _get_lang_code(target_lang)
    lines = []

    base_instruction = (
        f"Referring to the source sentence, post-edit the {target_lang} machine translation above.\n"
        + OUTPUT_ONLY
    )

    context_instruction = (
        f"The machine translation may contain errors. "
        f"Referring to the source sentence and preceding context, "
        f"post-edit the {target_lang} machine translation above.\n"
        + OUTPUT_ONLY
    )

    speaker_instruction = (
        f"Using the character information and preceding context to identify the speaker "
        f"and understand the situation, post-edit the {target_lang} machine translation "
        f"above referring to the source sentence.\n"
        + OUTPUT_ONLY
    )

    # ── translation ─────────────────────────────────────────
    if prompt_type == "translation":
        lines += [
            "Translate the following Korean sentence into English. Do not add any conversational fillers or explanations. Provide only the translated text.",
            source,
        ]

    # ── P0 ──────────────────────────────────────────────────
    elif prompt_type == "P0":
        lines += [
            f"Source (Korean): {source}",
            f"Machine translation: {nmt}",
            base_instruction,
        ]

    # ── P1-domain ───────────────────────────────────────────
    elif prompt_type == "P1-domain":
        lines += [
            "The following is a machine translation of a sentence from a film subtitle.",
            f"Source (Korean): {source}",
            f"Machine translation: {nmt}",
            base_instruction,
        ]

    # ── P1-title ────────────────────────────────────────────
    elif prompt_type == "P1-title":
        lines += [
            "The following is a machine translation of a sentence from the subtitles of the film 'Parasite' (2019).",
            f"Source (Korean): {source}",
            f"Machine translation: {nmt}",
            base_instruction,
        ]

    # ── P1-speaker ──────────────────────────────────────────
    elif prompt_type == "P1-speaker":
        preceding_block = _build_preceding_block(preceding_sources)
        lines += [
            "The following is a machine translation of a sentence from the subtitles of the film 'Parasite' (2019).",
            CHARACTER_CATALOG,
            preceding_block,
            f"Source (Korean): {source}",
            f"Machine translation: {nmt}",
            speaker_instruction,
        ]

    # ── P2-zero_anaphora ────────────────────────────────────
    elif prompt_type == "P2-zero_anaphora":
        p2_instr = P2_INSTRUCTIONS["zero_anaphora"][lang_code]
        preceding_block = _build_preceding_block(preceding_sources)
        lines += [
            "The following is a machine translation of a sentence from the subtitles of the film 'Parasite' (2019).",
            p2_instr,
            preceding_block,
            f"Source (Korean): {source}",
            f"Machine translation: {nmt}",
            context_instruction,
        ]

    # ── P2-lexical_ambiguity ─────────────────────────────────
    elif prompt_type == "P2-lexical_ambiguity":
        p2_instr = P2_INSTRUCTIONS["lexical_ambiguity"]  # 단순 문자열, 언어 분기 없음
        preceding_block = _build_preceding_block(preceding_sources)
        lines += [
            "The following is a machine translation of a sentence from the subtitles of the film 'Parasite' (2019).",
            p2_instr,
            preceding_block,
            f"Source (Korean): {source}",
            f"Machine translation: {nmt}",
            context_instruction,
        ]

    else:
        raise ValueError(f"Unknown prompt_type: {prompt_type}")

    return "\n".join(lines)

# ============================================================
# 단일 문장 후편집
# ============================================================
def _postedit_single(
    client: OpenAI,
    model: str,
    source: str,
    nmt: str,
    target_lang: str,
    prompt_type: str,
    temperature: float,
    preceding_sources: Optional[List[str]] = None,
    max_retries: int = 3,
) -> Tuple[str, Dict[str, int]]:
    user_msg = _build_user_message(
        source=source,
        nmt=nmt,
        target_lang=target_lang,
        prompt_type=prompt_type,
        preceding_sources=preceding_sources,
    )

    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": user_msg}],
                temperature=temperature,
            )
            result = (resp.choices[0].message.content or "").strip()
            result = result.splitlines()[0].strip() if result else ""
            usage = resp.usage
            token_usage = {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                "total_tokens": getattr(usage, "total_tokens", 0) or 0,
            } if usage else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            return result, token_usage
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(0.8 * (2 ** attempt))

    raise RuntimeError("Unexpected: retries exhausted")

# ============================================================
# 메인 함수
# ============================================================
def translate_dataframe(
    df: pd.DataFrame,
    id_col: str,
    src_col: str,
    nmt_col: str,
    model: str,
    temperature: float,
    sleep_sec: float,
    target_lang: str = "English",
    prompt_type: str = "P0",
    full_corpus_df: Optional[pd.DataFrame] = None,
    full_id_col: str = "ID",
    full_src_col: str = "source_text",
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise RuntimeError("OPENAI_API_KEY is missing.")

    if prompt_type not in PROMPT_TYPES:
        raise ValueError(f"prompt_type must be one of {PROMPT_TYPES}")

    needs_context = prompt_type in NEEDS_CONTEXT_TYPES

    # P2 계열은 full_corpus 필수
    if prompt_type.startswith("P2-") and full_corpus_df is None:
        raise RuntimeError(
            f"{prompt_type}는 preceding context가 필요합니다. "
            "전체 코퍼스 파일을 업로드해주세요."
        )

    client = OpenAI()
    total = len(df)
    results = []
    token_rows = []
    usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    for i, row in df.iterrows():
        source = str(row[src_col])
        nmt    = str(row[nmt_col])

        preceding_sources = None
        if needs_context and full_corpus_df is not None:
            preceding_sources = get_preceding_sources(
                full_df=full_corpus_df,
                id_col=full_id_col,
                src_col=full_src_col,
                target_id=str(row[id_col]),
                n=4,
            )

        result, usage = _postedit_single(
            client=client,
            model=model,
            source=source,
            nmt=nmt,
            target_lang=target_lang,
            prompt_type=prompt_type,
            temperature=temperature,
            preceding_sources=preceding_sources,
        )
        results.append((str(row[id_col]), result))
        token_rows.append((str(row[id_col]), usage["prompt_tokens"], usage["completion_tokens"], usage["total_tokens"]))
        usage_totals["prompt_tokens"]     += usage["prompt_tokens"]
        usage_totals["completion_tokens"] += usage["completion_tokens"]
        usage_totals["total_tokens"]      += usage["total_tokens"]

        if progress_callback:
            progress_callback(len(results), total)

        time.sleep(sleep_sec)

    out_df = df.copy()
    mp = {rid: hyp for rid, hyp in results}
    out_df["gpt_hyp"] = out_df[id_col].astype(str).map(mp)

    token_mp = {rid: (p, c, t) for rid, p, c, t in token_rows}
    out_df["prompt_tokens"]     = out_df[id_col].astype(str).map(lambda x: token_mp.get(x, (None, None, None))[0])
    out_df["completion_tokens"] = out_df[id_col].astype(str).map(lambda x: token_mp.get(x, (None, None, None))[1])
    out_df["total_tokens"]      = out_df[id_col].astype(str).map(lambda x: token_mp.get(x, (None, None, None))[2])

    if out_df["gpt_hyp"].isna().any():
        missing = out_df.loc[out_df["gpt_hyp"].isna(), id_col].tolist()[:20]
        raise ValueError(f"후편집 누락 발생: {missing}")

    usage_totals["n_calls"] = total
    return out_df, usage_totals