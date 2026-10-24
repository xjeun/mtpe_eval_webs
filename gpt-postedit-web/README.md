# gpt-postedit-web

DeepL 번역을 **GPT 로 후편집(APE)** 하고 **BLEU / chrF / COMET / COMETkiwi** 로 평가해 엑셀로 내보내는 Streamlit 앱입니다.

| 탭 | 내용 |
|---|---|
| 🚀 후편집 실험 | 전체 문장을 선택한 프롬프트로 후편집 → 지표 계산 → 엑셀 |
| 📊 임계값 실험 | DeepL COMETkiwi 가 **임계값 미만인 문장만** GPT 로 후편집하고 나머지는 DeepL 그대로 둔 **선택적 후편집** 결과를 계산 |

## 1. 설치 (처음 한 번)

이 폴더의 **`setup.bat`** 을 더블클릭합니다. `.venv` 생성 → 패키지 설치(torch 포함, 수 분) → `.env` 생성까지 합니다.

## 2. 키 입력

`gpt-postedit-web\.env` 를 메모장으로 열어 채웁니다.

```
OPENAI_API_KEY=여기에_OpenAI_키
HF_TOKEN=여기에_HuggingFace_토큰
```

## 3. 실행

**`run.bat`** 을 더블클릭하면 브라우저에서 http://localhost:8501 이 열립니다.

처음 지표를 계산할 때 COMET 모델 2개(약 5GB)를 내려받으므로 오래 걸립니다.

## 4. 사용 — 탭 1 (후편집 실험)

왼쪽 사이드바에서 설정합니다.

| 설정 | 설명 |
|---|---|
| Model | OpenAI 모델 이름 (기본 `gpt-5.2`) |
| Temperature | 기본 0 (재현성) |
| Request 간 sleep | API 호출 사이 대기(초). 429 오류가 나면 늘리세요 |
| 도착 언어 | English / French |
| 프롬프트 타입 | 아래 표 |

### 입력 파일

`deepl-eval-web` 결과 엑셀을 그대로 쓰면 됩니다. 이때 **ID 컬럼명을 `ID` → `index` 로 바꿔 입력**하세요.

| 컬럼 | 기본 이름 | deepl-eval-web 결과에서의 이름 |
|---|---|---|
| ID | `ID` | `index` |
| 원문 | `source_text` | `source_text` |
| 참조번역 | `reference` | `reference` |
| DeepL 번역 | `deepl_translation` | `deepl_translation` |

### 프롬프트 타입

프롬프트 원문은 [`gpt_translate.py`](gpt_translate.py) 의 `_build_user_message()` 에 있습니다.
P1/P2 계열은 영화 **〈기생충〉(2019) 자막** 실험용으로 작성돼 있으니, 다른 데이터에 쓸 때는 이 함수의 문구를 바꾸세요.

| 타입 | 내용 | 전체 코퍼스 파일 |
|---|---|---|
| `translation` | 후편집 없이 GPT 로 직접 번역 (비교용) | — |
| `P0` | 원문 + 기계번역만 주고 후편집 | — |
| `P1-domain` | + "영화 자막 문장" 이라는 도메인 정보 | — |
| `P1-title` | + 작품명(〈기생충〉) | — |
| `P1-speaker` | + 등장인물 목록 + 앞 4문장 | 선택 |
| `P2-zero_anaphora` | + 영(零)대명사 복원 지시 + 앞 4문장 | **필수** |
| `P2-lexical_ambiguity` | + 어휘 중의성 지시 + 앞 4문장 | **필수** |

"전체 코퍼스 파일" 은 앞 문장 문맥을 찾기 위한 원본 전체 엑셀입니다(같은 ID·원문 컬럼 이름).

### 결과 엑셀

- **Summary** — 실행 설정, 토큰 사용량, 코퍼스/문장 평균 지표
- **Results** — ID, 원문, 참조, `gpt_hyp`(후편집문), sent_bleu, sent_chrf, sent_comet, sent_cometkiwi, 토큰 수

실행할 때마다 토큰 사용량이 `token_usage_log.csv` 에 누적됩니다(GitHub 에는 올라가지 않음).

## 5. 사용 — 탭 2 (임계값 실험)

1. 도착 언어, **COMETkiwi 임계값**(0.60~0.85), 모델 선택
2. `deepl-eval-web` 결과 엑셀 업로드
3. 컬럼명을 결과 파일에 맞게 입력

| 입력란 | 기본값 | deepl-eval-web 결과에서의 이름 |
|---|---|---|
| ID | `index` | `index` |
| DeepL COMETkiwi | `DeepL_CometKiwi` | **`COMET-kiwi`** |
| DeepL COMET | `DeepL_COMET` | **`COMET`** |

임계값 미만 문장만 `P1-title` 프롬프트로 후편집되므로, 전체를 후편집할 때보다 API 비용이 적게 듭니다.

## 비용 감각

GPT 비용은 문장 수 × 프롬프트 길이에 비례합니다. 처음에는 [`../samples/sample_input.xlsx`](../samples/sample_input.xlsx) 처럼
**5~10문장으로 먼저 돌려보고** 결과 화면의 토큰 사용량을 확인한 뒤 전체를 돌리세요.

## 자주 나는 오류

| 증상 | 원인 / 해결 |
|---|---|
| `OPENAI_API_KEY 환경변수가 비어있어요` | `.env` 가 없거나 키가 비어 있음. 수정 후 `run.bat` 재시작 |
| `필수 컬럼이 없어요` | 컬럼명 입력란을 엑셀 헤더와 똑같이 (대소문자 포함) |
| `401` / `gated repo` | COMETkiwi 라이선스 미동의 또는 `HF_TOKEN` 누락 |
| `429 Rate limit` | Request 간 sleep 을 늘리거나 잠시 후 재시도 |
| `model ... does not exist` | 본인 계정에서 쓸 수 없는 모델명. 사이드바 Model 을 바꾸세요 |
| `No module named 'pkg_resources'` | `.venv\Scripts\pip install "setuptools<81"` |
