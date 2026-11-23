# 03_realm.py
import glob
import os
import pandas as pd

# 1. Lê todos os arquivos .parquet da pasta atual e concatena em um único DataFrame
arquivos_parquet = sorted(glob.glob("*.parquet"))
print("Arquivos encontrados:", arquivos_parquet)

realm = pd.concat([pd.read_parquet(f) for f in arquivos_parquet], ignore_index=True)
print("Colunas:", realm.columns.tolist(), "| Total de linhas:", len(realm))

# 2. Mapeamento das colunas reais do Parquet para as chaves usadas no script
COLS = dict(source="source", use="category_nist", occ="category", url="url")

USE = [
    "Decision Making",
    "Recommendation",
    "Discovery",
    "Digital Assistance",
    "Content Creation",
    "Prediction"
]

OCC = [
    "Management",
    "Business and Financial",
    "Sales and Related",
    "Unknown"
]

def has(col, vals):
    return realm[COLS[col]].astype(str).apply(
        lambda s: any(v.lower() in s.lower() for v in vals)
    )

# 3. Filtra por uso de LLM e ocupação
sub = realm[has("use", USE) & has("occ", OCC)].copy()

# 4. Separa Reddit de Notícias (usando tanto a coluna 'subreddit' quanto 'source')
is_red = sub["subreddit"].notna() | sub[COLS["source"]].astype(str).str.lower().str.contains("reddit")
red, news = sub[is_red].copy(), sub[~is_red].copy()

# 5. Deduplica contra os posts já coletados em candidatos.csv
if os.path.exists("candidatos.csv"):
    cand = pd.read_csv("candidatos.csv", usecols=["id"])
    ids = set(cand["id"].astype(str))
    red["dup"] = (
        red["id"].astype(str).isin(ids)
        | red[COLS["url"]].astype(str).apply(lambda u: any(i in u for i in ids))
    )
else:
    print("Aviso: 'candidatos.csv' não encontrado; nenhum post marcado como duplicado.")
    red["dup"] = False

print(
    f"REALM total filtrado: {len(sub)} | "
    f"Reddit: {len(red)} (já coletados: {red['dup'].sum()}, novos: {(~red['dup']).sum()}) | "
    f"Notícias: {len(news)}"
)

# 6. Limpa quebras de linha nas colunas de texto para manter 1 registro = 1 linha no CSV
for df_out in (red, news):
    for col in ["title", "description", "content", "top_comments"]:
        if col in df_out.columns:
            df_out[col] = df_out[col].fillna("").astype(str).str.replace(r"[\r\n]+", " ", regex=True).str.strip()

# 7. Exporta os resultados
red[~red["dup"]].drop(columns=["dup"]).to_csv("realm_reddit_novos.csv", index=False, encoding="utf-8-sig")
news.to_csv("realm_noticias_biz.csv", index=False, encoding="utf-8-sig")
print("Arquivos 'realm_reddit_novos.csv' e 'realm_noticias_biz.csv' salvos com sucesso.")