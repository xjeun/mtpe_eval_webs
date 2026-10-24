# 번역 평가 자동화 웹 (DeepL + GPT 후편집)

기계번역(DeepL) → 자동평가(BLEU / chrF / COMET / COMETkiwi) → GPT 후편집 → 다시 평가까지
엑셀 파일 하나로 돌릴 수 있는 웹 도구 두 개입니다.

| 폴더 | 하는 일 | 기술 |
|---|---|---|
| [`deepl-eval-web/`](deepl-eval-web/) | 엑셀 업로드 → DeepL 번역 → 지표 계산 → 결과 엑셀 다운로드 | Node(Express) + Python(FastAPI) |
| [`gpt-postedit-web/`](gpt-postedit-web/) | DeepL 결과를 GPT로 후편집 → 지표 계산 → 엑셀. COMETkiwi 임계값 기반 선택적 후편집 실험 | Python(Streamlit) |

```
 samples/sample_input.xlsx           (source_text, reference)
          │
          ▼
 ① deepl-eval-web   ──►  deepl_eval_KO-EN_....xlsx  (+ deepl_translation, BLEU, chrF, COMET, COMET-kiwi)
          │
          ▼
 ② gpt-postedit-web ──►  gpt_P0_english_metrics.xlsx (+ gpt_hyp, sent_bleu, sent_comet, ...)
```

> 모든 실행은 **각자 PC에서, 각자 API 키로** 합니다. API 사용료는 키 주인 계정에 청구됩니다.

---

## 0. 준비물

| 항목 | 용도 | 받는 곳 |
|---|---|---|
| Windows 10/11 | `.bat` 스크립트로 설치·실행 | — |
| **Python 3.11** | 두 웹 모두 | https://www.python.org/downloads/release/python-3119/ (설치 시 "Add to PATH" 체크) |
| **Node.js LTS** | `deepl-eval-web` 서버 | https://nodejs.org |
| 디스크 여유 **10GB 이상** | torch + COMET 모델 2개 (약 5GB) | — |
| RAM 8GB 이상 (16GB 권장) | COMET 를 CPU 로 계산 | — |

GPU 는 없어도 됩니다. 모두 CPU 로 돌아갑니다(대신 문장 수가 많으면 느립니다).

설치 확인:
```bat
py -3.11 --version
node --version
```

## 1. API 키 발급

| 키 | 필요한 곳 | 발급 |
|---|---|---|
| `DEEPL_API_KEY` | deepl-eval-web | https://www.deepl.com/pro-api → **DeepL API Free** 가입 → 계정 > API Keys (월 50만 자 무료) |
| `OPENAI_API_KEY` | gpt-postedit-web | https://platform.openai.com/api-keys (결제 수단 등록 필요, 유료) |
| `HF_TOKEN` | 둘 다 (COMETkiwi) | ① https://huggingface.co/Unbabel/wmt22-cometkiwi-da 에서 **라이선스 동의** ② https://huggingface.co/settings/tokens 에서 **Read** 토큰 발급 |

COMETkiwi 는 gated 모델이라 **라이선스 동의를 안 하면 토큰이 있어도 다운로드가 실패**합니다.

## 2. 받기

GitHub 페이지에서 **Code → Download ZIP** 후 압축 풀기, 또는

```bat
git clone https://github.com/<계정>/mtpe_eval_webs.git
```

> 폴더 경로에 한글·공백이 없는 곳(예: `C:\work\mtpe_eval_webs`)에 두면 문제가 적습니다.

## 3. 설치·실행

각 폴더의 README 를 따라가세요.

- [deepl-eval-web/README.md](deepl-eval-web/README.md)
- [gpt-postedit-web/README.md](gpt-postedit-web/README.md)

요약하면 둘 다 **`setup.bat` → `.env` 에 키 입력 → `start.bat`** 순서입니다. (두 웹 모두 파일 이름이 같습니다)

## 4. 지표 읽는 법

| 지표 | 범위 | 방향 | 참조번역 필요 |
|---|---|---|---|
| BLEU | 0~100 | 높을수록 좋음 | 필요 |
| chrF | 0~100 | 높을수록 좋음 | 필요 |
| COMET (`Unbabel/wmt22-comet-da`) | 대략 0~1 | 높을수록 좋음 | 필요 |
| COMETkiwi (`Unbabel/wmt22-cometkiwi-da`) | 대략 0~1 | 높을수록 좋음 | **불필요** (품질 추정, QE) |

## 🔒 보안 — 꼭 지켜주세요

- API 키는 **`.env` 파일에만** 넣으세요. 코드(`.py`, `.js`)에 직접 쓰지 마세요.
- `.env` 는 `.gitignore` 에 들어 있어 GitHub 에 올라가지 않습니다. **지우거나 바꾸지 마세요.**
- 이 저장소를 fork 해서 고친 뒤 올릴 때, `git status` 에 `.env` 가 보이면 멈추세요.
- 키가 노출됐다면(채팅·캡처·커밋 등) 바로 해당 사이트에서 **폐기(revoke) 후 재발급**하세요.
