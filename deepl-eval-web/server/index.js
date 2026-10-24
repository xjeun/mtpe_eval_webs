import express from "express";
import dotenv from "dotenv";
import multer from "multer";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import axios from "axios";
import ExcelJS from "exceljs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ✅ deepl-eval-web/.env 를 강제 로드 (scorer 와 같은 파일을 쓴다)
const ENV_PATH = path.join(__dirname, "..", ".env");
dotenv.config({ path: ENV_PATH, override: true });
console.log("[ENV] DEEPL_API_URL =", process.env.DEEPL_API_URL);
console.log("[ENV] DEEPL_API_KEY set =", Boolean(process.env.DEEPL_API_KEY));
console.log("[ENV] env path =", ENV_PATH);

const app = express();
app.use(express.json({ limit: "20mb" }));

// ====== ENV ======
const PORT         = process.env.PORT        || 3000;
const DEEPL_API_KEY = process.env.DEEPL_API_KEY;
const DEEPL_API_URL = process.env.DEEPL_API_URL || "https://api-free.deepl.com";
const SCORER_URL    = process.env.SCORER_URL    || "http://127.0.0.1:8001";

// ====== Serve static UI ======
app.use(express.static(path.join(__dirname, "..", "public")));

// ====== uploads dir ======
const uploadsDir = path.join(__dirname, "uploads");
if (!fs.existsSync(uploadsDir)) fs.mkdirSync(uploadsDir, { recursive: true });

// ====== Multer ======
const storage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, uploadsDir),
  filename:    (_req, file,  cb) => {
    const safeName = file.originalname.replace(/[^\w.\-]+/g, "_");
    cb(null, `${Date.now()}_${safeName}`);
  },
});

const upload = multer({
  storage,
  limits:     { fileSize: 200 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => {
    const ext = path.extname(file.originalname).toLowerCase();
    if (ext !== ".xlsx") return cb(new Error("Only .xlsx files are supported."));
    cb(null, true);
  },
});

// ====== Helpers ======
function mapToDeepLLang(lang) {
  return String(lang || "").trim().toUpperCase();
}

function chunkArray(arr, size) {
  const out = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

function normalizeHeaderKey(s) {
  return String(s || "").trim().toLowerCase().replace(/\s+/g, "_");
}

function findColumn(headersMap, candidates) {
  for (const cand of candidates) {
    if (headersMap[cand]) return headersMap[cand];
  }
  return null;
}

function coerceNumber(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string") {
    const n = parseFloat(v);
    return Number.isFinite(n) ? n : null;
  }
  if (typeof v === "object") {
    if ("score" in v) return coerceNumber(v.score);
    if ("value" in v) return coerceNumber(v.value);
    if ("mean"  in v) return coerceNumber(v.mean);
    if ("avg"   in v) return coerceNumber(v.avg);
  }
  return null;
}

// ✅ cometkiwi 필드 추가
function normalizeScoreObj(obj) {
  if (!obj || typeof obj !== "object") return { bleu: null, chrf: null, comet: null, cometkiwi: null };

  return {
    bleu:      coerceNumber(obj.bleu      ?? obj.BLEU),
    chrf:      coerceNumber(obj.chrf      ?? obj.chrF  ?? obj.CHRF),
    comet:     coerceNumber(obj.comet     ?? obj.COMET),
    cometkiwi: coerceNumber(obj.cometkiwi ?? obj.COMETkiwi ?? obj.COMETKIWI),
  };
}

async function readXlsxRows(filePath) {
  const wb = new ExcelJS.Workbook();
  await wb.xlsx.readFile(filePath);

  const ws = wb.worksheets[0];
  if (!ws) throw new Error("No worksheet found in the uploaded file.");

  const headerRow = ws.getRow(1);
  const headers   = {};
  headerRow.eachCell((cell, colNumber) => {
    const key = normalizeHeaderKey(cell.value);
    if (key) headers[key] = colNumber;
  });

  const sourceCol = findColumn(headers, ["source_text", "source", "src", "원문"]);
  const refCol    = findColumn(headers, ["reference", "ref", "참조", "정답", "reference_text"]);

  if (!sourceCol || !refCol) {
    throw new Error(
      `Missing required columns.\nRow1 headers must include source_text and reference.\nDetected: ${Object.keys(headers).join(", ")}`
    );
  }

  const rows = [];
  for (let r = 2; r <= ws.rowCount; r++) {
    const row          = ws.getRow(r);
    const source_text  = String(row.getCell(sourceCol).value ?? "").trim();
    const reference    = String(row.getCell(refCol).value    ?? "").trim();
    if (!source_text && !reference) continue;
    rows.push({ row_index: r, source_text, reference });
  }

  if (rows.length === 0) throw new Error("No data rows found.");
  return rows;
}

async function deeplTranslateBatch(texts, sourceLang, targetLang) {
  if (!DEEPL_API_KEY) throw new Error("DEEPL_API_KEY is missing in deepl-eval-web/.env");

  const url  = `${DEEPL_API_URL.replace(/\/$/, "")}/v2/translate`;
  const resp = await axios.post(url, {
    text:        texts,
    source_lang: mapToDeepLLang(sourceLang),
    target_lang: mapToDeepLLang(targetLang),
  }, {
    headers: {
      Authorization:  `DeepL-Auth-Key ${DEEPL_API_KEY}`,
      "Content-Type": "application/json",
    },
    timeout: 120000,
  });

  const translations = resp.data?.translations;
  if (!Array.isArray(translations)) throw new Error("Unexpected DeepL response.");
  return translations.map((x) => String(x.text ?? ""));
}

async function scorerBatch(pairs, sourceLang, targetLang) {
  const url  = `${SCORER_URL.replace(/\/$/, "")}/score`;
  const resp = await axios.post(url, {
    source_lang: mapToDeepLLang(sourceLang),
    target_lang: mapToDeepLLang(targetLang),
    sources:     pairs.map((p) => p.source_text),
    references:  pairs.map((p) => p.reference),
    hypotheses:  pairs.map((p) => p.hypothesis),
  }, {
    headers: { "Content-Type": "application/json" },
    timeout: 300000,
  });

  const data = resp.data;

  if (data && Array.isArray(data.results)) {
    const results = data.results.map(normalizeScoreObj);
    const avg     = data.avg && typeof data.avg === "object" ? normalizeScoreObj(data.avg) : null;

    if (results.length !== pairs.length) {
      throw new Error(`Scorer length mismatch: results(${results.length}) != pairs(${pairs.length}).`);
    }
    return { results, avg };
  }

  throw new Error(
    `Scorer returned unexpected shape. keys: ${
      data && typeof data === "object" ? Object.keys(data).join(", ") : "n/a"
    } | sample: ${JSON.stringify(data).slice(0, 600)}`
  );
}

function mean(arr) {
  const nums = arr.filter((x) => typeof x === "number" && Number.isFinite(x));
  if (nums.length === 0) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

// ✅ COMET-kiwi 컬럼 및 summary 행 추가
async function buildOutputWorkbook(allRows, summary) {
  const wb = new ExcelJS.Workbook();

  // ---- results sheet ----
  const ws = wb.addWorksheet("results");
  ws.columns = [
    { header: "index",            key: "index",            width: 8  },
    { header: "source_text",      key: "source_text",      width: 60 },
    { header: "reference",        key: "reference",        width: 60 },
    { header: "deepl_translation",key: "deepl_translation",width: 60 },
    { header: "BLEU",             key: "BLEU",             width: 10 },
    { header: "chrF",             key: "chrF",             width: 10 },
    { header: "COMET",            key: "COMET",            width: 10 },
    { header: "COMET-kiwi",       key: "COMETkiwi",        width: 12 }, // ✅ 추가
  ];

  allRows.forEach((r, idx) => {
    ws.addRow({
      index:             idx + 1,
      source_text:       r.source_text,
      reference:         r.reference,
      deepl_translation: r.deepl_translation,
      BLEU:              r.bleu,
      chrF:              r.chrf,
      COMET:             r.comet,
      COMETkiwi:         r.cometkiwi,  // ✅ 추가
    });
  });
  ws.getRow(1).font = { bold: true };

  // ---- summary sheet ----
  const sum = wb.addWorksheet("summary");
  sum.columns = [
    { header: "metric", key: "metric", width: 30 },
    { header: "value",  key: "value",  width: 20 },
    { header: "note",   key: "note",   width: 60 },
  ];
  sum.getRow(1).font = { bold: true };

  sum.addRow({ metric: "n_sentences",                value: summary.n,                note: "" });
  sum.addRow({ metric: "BLEU_mean(sentence)",        value: summary.bleu_mean,        note: "mean of sentence-level BLEU" });
  sum.addRow({ metric: "chrF_mean(sentence)",        value: summary.chrf_mean,        note: "mean of sentence-level chrF" });
  sum.addRow({ metric: "COMET_mean(sentence)",       value: summary.comet_mean,       note: "mean of sentence-level COMET (ref-based)" });
  sum.addRow({ metric: "COMETkiwi_mean(sentence)",   value: summary.cometkiwi_mean,   note: "mean of sentence-level COMET-kiwi (QE, no ref)" }); // ✅
  sum.addRow({ metric: "BLEU_corpus(scorer.avg)",    value: summary.avg_bleu,         note: "corpus BLEU (if provided)" });
  sum.addRow({ metric: "chrF_corpus(scorer.avg)",    value: summary.avg_chrf,         note: "corpus chrF (if provided)" });
  sum.addRow({ metric: "COMET_system(scorer.avg)",   value: summary.avg_comet,        note: "system_score COMET (if provided)" });
  sum.addRow({ metric: "COMETkiwi_system(scorer.avg)",value: summary.avg_cometkiwi,  note: "system_score COMETkiwi (if provided)" }); // ✅

  return wb;
}

// ====== API: evaluate & return xlsx ======
app.post("/api/evaluate", upload.single("file"), async (req, res) => {
  const uploadedPath = req.file?.path;

  try {
    const sourceLang = req.body?.sourceLang || "KO";
    const targetLang = req.body?.targetLang || "EN";

    if (!req.file)       throw new Error("No file uploaded.");
    if (!DEEPL_API_KEY)  throw new Error("DEEPL_API_KEY is missing in deepl-eval-web/.env");

    // 1) read input
    const rows = await readXlsxRows(uploadedPath);

    // 2) DeepL translate (batch)
    const TRANSLATE_BATCH = 40;
    const translatedRows  = [];

    for (const chunk of chunkArray(rows, TRANSLATE_BATCH)) {
      const translated = await deeplTranslateBatch(chunk.map((x) => x.source_text), sourceLang, targetLang);
      chunk.forEach((item, i) => {
        translatedRows.push({ ...item, deepl_translation: translated[i] ?? "" });
      });
    }

    // 3) scorer (batch)
    const SCORE_BATCH = 25;
    const scoredRows  = [];
    let   lastAvg     = null;

    for (const chunk of chunkArray(translatedRows, SCORE_BATCH)) {
      const pairs = chunk.map((x) => ({
        source_text: x.source_text,
        reference:   x.reference,
        hypothesis:  x.deepl_translation,
      }));

      const { results, avg } = await scorerBatch(pairs, sourceLang, targetLang);
      if (avg) lastAvg = avg;

      chunk.forEach((x, i) => {
        const s = results[i] || { bleu: null, chrf: null, comet: null, cometkiwi: null };
        scoredRows.push({ ...x, bleu: s.bleu, chrf: s.chrf, comet: s.comet, cometkiwi: s.cometkiwi });
      });
    }

    // 4) summary 계산 (✅ cometkiwi 포함)
    const summary = {
      n:               scoredRows.length,
      bleu_mean:       mean(scoredRows.map((r) => r.bleu)),
      chrf_mean:       mean(scoredRows.map((r) => r.chrf)),
      comet_mean:      mean(scoredRows.map((r) => r.comet)),
      cometkiwi_mean:  mean(scoredRows.map((r) => r.cometkiwi)),  // ✅
      avg_bleu:        lastAvg?.bleu        ?? null,
      avg_chrf:        lastAvg?.chrf        ?? null,
      avg_comet:       lastAvg?.comet       ?? null,
      avg_cometkiwi:   lastAvg?.cometkiwi   ?? null,              // ✅
    };

    // 5) build output xlsx
    const wb     = await buildOutputWorkbook(scoredRows, summary);
    const buffer = await wb.xlsx.writeBuffer();

    const stamp   = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    const outName = `deepl_eval_${mapToDeepLLang(sourceLang)}-${mapToDeepLLang(targetLang)}_${stamp}.xlsx`;

    res.setHeader("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    res.setHeader("Content-Disposition", `attachment; filename="${outName}"`);
    return res.status(200).send(Buffer.from(buffer));

  } catch (err) {
    const axiosMsg = err?.response?.data ? ` | detail: ${JSON.stringify(err.response.data)}` : "";
    return res.status(400).json({ error: (err?.message || String(err)) + axiosMsg });
  } finally {
    if (uploadedPath && fs.existsSync(uploadedPath)) {
      try { fs.unlinkSync(uploadedPath); } catch {}
    }
  }
});

// ✅ MulterError 핸들러
app.use((err, _req, res, _next) => {
  if (err instanceof multer.MulterError) {
    if (err.code === "LIMIT_FILE_SIZE")
      return res.status(413).json({ error: "File too large." });
    return res.status(400).json({ error: `MulterError: ${err.code}` });
  }
  if (err) return res.status(400).json({ error: err.message || String(err) });
});

// ====== Health ======
app.get("/api/health", (_req, res) => {
  res.json({ ok: true, scorer: SCORER_URL, deepl: DEEPL_API_URL });
});

app.listen(PORT, () => {
  console.log(`Server running: http://127.0.0.1:${PORT}`);
  console.log(`Scorer expected at: ${SCORER_URL}`);
});