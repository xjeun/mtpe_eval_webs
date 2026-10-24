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
| `scorer-8001` | 처음엔 COMET 모델 2개(약 5GB)를 내려받습니다. 시간이 오래 걸리니 **`COMETkiwi loaded.`** 가 뜰 때까지 기다리세요. |
| `server-3000` | `Server running: http://127.0.0.1:3000` |

커멘드창에서 **ctrl을 누른 상태로, http://127.0.0.1:3000** 을 클릭하여 웹을 엽니다.

## 4. 사용

1. 출발/도착 언어 선택 (기본 KO → EN)
2. xlsx 업로드 — **1행 헤더에 `source_text`, `reference` 컬럼 필수**
   (`source`/`src`/`원문`, `ref`/`참조`/`정답` 같은 이름도 인식합니다)
   - `ID`(또는 `id`/`index`/`번호`) 컬럼이 있으면 그 값을 그대로 쓰고, 없으면 1, 2, 3… 으로 매깁니다. ID 는 문장마다 달라야 합니다.
3. **Evaluate & Download** → `deepl_eval_KO-EN_<시각>.xlsx` 가 내려받아집니다.

연습용 파일: [`../samples/sample_input.xlsx`](../samples/sample_input.xlsx) (5문장)

### 결과 엑셀

| 시트 | 컬럼 |
|---|---|
| `results` | ID, source_text, reference, deepl_translation, DeepL_BLEU, DeepL_chrF, DeepL_COMET, DeepL_CometKiwi |
| `summary` | 문장 수, 문장 평균, 코퍼스 BLEU/chrF, COMET system score |

컬럼명이 [`gpt-postedit-web`](../gpt-postedit-web/) 기본값과 똑같으므로, **이 파일을 후편집 웹 탭 1·탭 2 에 그대로 올리면 됩니다** (컬럼명 수정 불필요).

## 자주 나는 오류

| 증상 | 원인 / 해결 |
|---|---|
| `DEEPL_API_KEY is missing` | `.env` 가 없거나 키가 비어 있음 |
| `ID column has duplicate values` | 입력 파일의 ID 컬럼에 같은 값이 두 번 이상 있음. 고유하게 고치거나 ID 컬럼을 지우면 1부터 자동으로 매깁니다 |
| `403` / `Wrong endpoint` | Free 키인데 `api.deepl.com`, 또는 그 반대. `DEEPL_API_URL` 확인 |
| `456 Quota exceeded` | DeepL 월 사용량 초과 |
| scorer 창에 `401` / `gated repo` | COMETkiwi 라이선스 미동의 또는 `HF_TOKEN` 누락 |
| `ECONNREFUSED 127.0.0.1:8001` | scorer 가 아직 모델을 로딩 중이거나 꺼져 있음 |
| `No module named 'pkg_resources'` | setuptools 가 너무 새 버전. `scorer\.venv\Scripts\pip install "setuptools<81"` |
