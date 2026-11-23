import json
import re
import glob
import hashlib
import os
import datetime as dt
import pandas as pd
import sys

class Logger:
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, "a", encoding="utf-8")
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()
    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = sys.stderr = Logger("filtro.log")

def log_regras_filtragem(df_bruto, df_aprovados, llm_re, biz_re):
    llm_termos = [t.strip() for t in llm_re.pattern.split("|")]
    biz_termos = [t.strip() for t in biz_re.pattern.split("|")]

    print("=" * 70)
    print("[LOG DE FILTRAGEM - CRITÉRIOS E KEYWORDS APLICADOS]")
    print(f"1. Escopo textual      : Concatenação de 'title' + 'selftext' (normalizados sem quebras de linha)")
    print(f"2. Limpeza estrutural  : Exclusão de selftext vazio, '[removed]', '[deleted]', author == 'AutoModerator' e len(texto) < 300 chars")
    print(f"3. Lógica booleana     : (Corresponde a >= 1 termo LLM) AND (Corresponde a >= 1 termo BIZ)")
    print(f"4. Regex LLM (case-ins., exceto 'AI' estrito):")
    print(f"   Padrão : {llm_re.pattern}")
    print(f"   Termos : {', '.join(llm_termos)}")
    print(f"5. Regex BIZ (case-insensitive):")
    print(f"   Padrão : {biz_re.pattern}")
    print(f"   Termos : {', '.join(biz_termos)}")
    print(f"6. Funil desta rodada  : {len(df_bruto)} brutos -> {len(df_aprovados)} aprovados")

    if not df_aprovados.empty:
        # Mostra quais termos específicos mais apareceram nos posts aprovados
        llm_hits = df_aprovados["text"].str.findall(llm_re).explode().str.lower().str.strip().value_counts().head(8).to_dict()
        biz_hits = df_aprovados["text"].str.findall(biz_re).explode().str.lower().str.strip().value_counts().head(8).to_dict()
        print(f"   Top matches LLM     : {llm_hits}")
        print(f"   Top matches BIZ     : {biz_hits}")
    print("=" * 70)

STATE_FILE = "filtro_state.json"
OUT_CSV = "candidatos.csv"

KEEP_COLS = [
    "id", "subreddit", "created_utc", "created_date", "author_hash",
    "title", "selftext", "score", "num_comments", "permalink", "url"
]

LLM = re.compile(r"chat\s?gpt|\bgpt|openai|claude|gemini|copilot|\bllm|(?-i:\bAI\b)", re.I)
BIZ = re.compile(
    r"business plan|startup|start-up|pricing|entrepreneur|my business|side hustle"
    r"|go-to-market|market research|competitor|empreend|negócio",
    re.I
)

if os.path.exists(STATE_FILE):
    with open(STATE_FILE, "r", encoding="utf8") as f:
        state = json.load(f)
else:
    state = {"offsets": {}, "seen_ids": []}

seen_ids = set(state.get("seen_ids", []))
offsets = state.get("offsets", {})

new_rows = []
arquivos = sorted(glob.glob("raw/*.jsonl") + glob.glob("raw/*.jsonl.part"))

for filepath in arquivos:
    key = os.path.basename(filepath).replace(".part", "")
    last_offset = offsets.get(key, 0)
    file_size = os.path.getsize(filepath)

    if file_size <= last_offset:
        continue

    novos_brutos = 0
    with open(filepath, "rb") as f:
        f.seek(last_offset)
        while True:
            pos_antes = f.tell()
            line_bytes = f.readline()
            if not line_bytes:
                break
            if not line_bytes.endswith(b"\n"):
                f.seek(pos_antes)
                break
            try:
                row = json.loads(line_bytes.decode("utf8"))
                novos_brutos += 1
                pid = row.get("id")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    new_rows.append(row)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

        offsets[key] = f.tell()

    print(f"{key}: lidos +{novos_brutos} novos posts brutos (offset: {offsets[key]:,} bytes)")

if not new_rows:
    print("Nenhum post novo desde a última execução.")
    exit()

df = pd.DataFrame(new_rows)
df["title"] = df["title"].fillna("").str.replace(r"[\r\n]+", " ", regex=True).str.strip()
df["selftext"] = df["selftext"].fillna("").str.replace(r"[\r\n]+", " ", regex=True).str.strip()
df["text"] = df["title"] + " " + df["selftext"]

bad = (
    df["selftext"].isin(["[removed]", "[deleted]", ""])
    | (df["text"].str.len() < 300)
    | (df["author"] == "AutoModerator")
)

df_filt = df[~bad & df["text"].str.contains(LLM) & df["text"].str.contains(BIZ)].copy()

log_regras_filtragem(df, df_filt, LLM, BIZ)

if not df_filt.empty:
    df_filt["author_hash"] = df_filt["author"].map(
        lambda a: hashlib.sha256(("troque-este-sal" + str(a)).encode()).hexdigest()[:10]
    )
    df_filt["created_date"] = pd.to_numeric(df_filt["created_utc"], errors="coerce").map(
        lambda ts: dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if pd.notna(ts) else ""
    )

    for col in KEEP_COLS:
        if col not in df_filt.columns:
            df_filt[col] = ""

    df_out = df_filt[KEEP_COLS]
    write_header = not os.path.exists(OUT_CSV)
    df_out.to_csv(OUT_CSV, mode="a", header=write_header, index=False, encoding="utf-8-sig")

state["offsets"] = offsets
state["seen_ids"] = list(seen_ids)
tmp_state = STATE_FILE + ".tmp"
with open(tmp_state, "w", encoding="utf8") as f:
    json.dump(state, f)
os.replace(tmp_state, STATE_FILE)

print(f"\nNovos candidatos adicionados nesta rodada: {len(df_filt)}")
if os.path.exists(OUT_CSV):
    total_df = pd.read_csv(OUT_CSV, usecols=["subreddit"])
    print(f"Total acumulado em {OUT_CSV}: {len(total_df)}")
    print(total_df["subreddit"].value_counts())