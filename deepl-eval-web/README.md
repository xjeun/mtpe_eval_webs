# deepl-eval-web

엑셀 업로드 → **DeepL 번역** → **BLEU / chrF / COMET / COMETkiwi** 계산 → 결과 엑셀 다운로드.

```
브라우저 (public/index.html)
   │  xlsx 업로드
   ▼
server/  (Node + Express, :3000)  ── DeepL API 호출
   │  원문·참조·번역문
   ▼
scorer/  (Python + FastAPI, :8001) ── BLEU, chrF, COMET, COMETkiwi 계산
```

## 1. 설치 (처음 한 번)

이 폴더의 **`setup.bat`** 을 더블클릭합니다.

1. `scorer\.venv` 에 Python 가상환경을 만들고 패키지 설치 (torch 포함, 수 분 걸림)
2. `server` 에서 `npm install`
3. `.env.example` 을 복사해 `.env` 생성

## 2. 키 입력

`deepl-eval-web\.env` 를 메모장으로 열어 채웁니다.

```
DEEPL_API_KEY=여기에_DeepL_키
DEEPL_API_URL=https://api-free.deepl.com
HF_TOKEN=여기에_HuggingFace_토큰
```

- DeepL **Free** 키는 끝이 `:fx` 입니다. **Pro** 키면 `DEEPL_API_URL=https://api.deepl.com` 으로 바꾸세요.
- `HF_TOKEN` 은 COMETkiwi 모델 페이지에서 라이선스 동의를 한 계정의 토큰이어야 합니다.

## 3. 실행

**`start.bat`** 을 더블클릭하면 창이 2개 뜹니다.

| 창 | 내용 |
|---|---|
| `scorer-8001` | 처음엔 COMET 모델 2개(약 5GB)를 내려받습니다. **`COMETkiwi loaded.`** 가 뜰 때까지 기다리세요. |
| `server-3000` | `Server running: http://127.0.0.1:3000` |

브라우저에서 **http://127.0.0.1:3000** 을 엽니다.

## 4. 사용

1. 출발/도착 언어 선택 (기본 KO → EN)
2. xlsx 업로드 — **1행 헤더에 `source_text`, `reference` 컬럼 필수**
   (`source`/`src`/`원문`, `ref`/`참조`/`정답` 같은 이름도 인식합니다)
3. **Evaluate & Download** → `deepl_eval_KO-EN_<시각>.xlsx` 가 내려받아집니다.

연습용 파일: [`../samples/sample_input.xlsx`](../samples/sample_input.xlsx) (5문장)

### 결과 엑셀

| 시트 | 컬럼 |
|---|---|
| `results` | index, source_text, reference, deepl_translation, BLEU, chrF, COMET, COMET-kiwi |
| `summary` | 문장 수, 문장 평균, 코퍼스 BLEU/chrF, COMET system score |

이 파일을 그대로 [`gpt-postedit-web`](../gpt-postedit-web/) 에 넣을 수 있습니다.

## 자주 나는 오류

| 증상 | 원인 / 해결 |
|---|---|
| `DEEPL_API_KEY is missing` | `.env` 가 없거나 키가 비어 있음 |
| `403` / `Wrong endpoint` | Free 키인데 `api.deepl.com`, 또는 그 반대. `DEEPL_API_URL` 확인 |
| `456 Quota exceeded` | DeepL 월 사용량 초과 |
| scorer 창에 `401` / `gated repo` | COMETkiwi 라이선스 미동의 또는 `HF_TOKEN` 누락 |
| `ECONNREFUSED 127.0.0.1:8001` | scorer 가 아직 모델을 로딩 중이거나 꺼져 있음 |
| `No module named 'pkg_resources'` | setuptools 가 너무 새 버전. `scorer\.venv\Scripts\pip install "setuptools<81"` |
