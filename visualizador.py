import pandas as pd
import json
import os

# Lê para_codificar.csv se existir, senão usa candidatos.csv
CSV_PATH = "para_codificar.csv" if os.path.exists("para_codificar.csv") else "candidatos.csv"
df = pd.read_csv(CSV_PATH).fillna("")

records = []
for idx, row in df.iterrows():
    comments = []
    if "thread" in row and str(row["thread"]).strip().startswith("["):
        try:
            comments = json.loads(row["thread"])
        except Exception:
            comments = []

    records.append({
        "idx": int(idx) + 1,
        "id": str(row.get("id", "")),
        "subreddit": str(row.get("subreddit", "")),
        "date": str(row.get("created_date", "")),
        "score": int(row.get("score", 0)) if str(row.get("score", "")).isdigit() else 0,
        "num_comments": int(row.get("num_comments", 0)) if str(row.get("num_comments", "")).isdigit() else 0,
        "title": str(row.get("title", "")),
        "selftext": str(row.get("selftext", "")),
        "url": str(row.get("url", "")),
        "comments": comments
    })

data_json = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")

html_template = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Visualizador de Posts - {CSV_PATH}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f0f2f5; color: #1c1e21; margin: 0; padding: 20px;
  }}
  .container {{ max-width: 860px; margin: 0 auto; }}
  .topbar {{
    display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between;
    align-items: center; background: #fff; padding: 14px 18px;
    border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin-bottom: 16px;
  }}
  .controls {{ display: flex; gap: 8px; align-items: center; }}
  button, select, input[type=number] {{
    padding: 8px 12px; border: 1px solid #ccd0d5; border-radius: 6px;
    background: #fff; font-size: 14px; cursor: pointer;
  }}
  button:hover {{ background: #f5f6f7; }}
  button.primary {{ background: #0066cc; color: #fff; border-color: #0066cc; }}
  button.primary:hover {{ background: #0052a3; }}
  .card {{
    background: #fff; padding: 26px; border-radius: 10px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08); min-height: 360px;
  }}
  .meta {{
    display: flex; flex-wrap: wrap; gap: 12px; font-size: 13px;
    color: #65676b; margin-bottom: 12px; align-items: center;
  }}
  .badge {{
    background: #e7f3ff; color: #1877f2; padding: 3px 8px;
    border-radius: 99px; font-weight: 600;
  }}
  h2 {{ margin: 0 0 16px 0; font-size: 21px; line-height: 1.35; }}
  .body-text {{
    font-size: 15.5px; line-height: 1.65; white-space: pre-wrap;
    color: #242526; border-top: 1px solid #ebedf0; padding-top: 16px;
  }}
  .tag-bar {{
    display: flex; gap: 8px; margin-top: 22px; padding-top: 16px;
    border-top: 1px solid #ebedf0; align-items: center; flex-wrap: wrap;
  }}
  .tag-btn.active-valid {{ background: #d4edda; border-color: #28a745; color: #155724; font-weight: 600; }}
  .tag-btn.active-noise {{ background: #f8d7da; border-color: #dc3545; color: #721c24; font-weight: 600; }}
  .tag-btn.active-later {{ background: #fff3cd; border-color: #ffc107; color: #856404; font-weight: 600; }}
  .comments {{ margin-top: 24px; border-top: 2px solid #ebedf0; padding-top: 14px; }}
  .comment {{
    background: #f7f8fa; padding: 10px 14px; border-radius: 8px;
    margin-bottom: 8px; font-size: 14px; line-height: 1.5; white-space: pre-wrap;
  }}
  .hint {{ font-size: 12px; color: #65676b; text-align: center; margin-top: 12px; }}
</style>
</head>
<body>
<div class="container">
  <div class="topbar">
    <div class="controls">
      <button onclick="prev()">← Anterior</button>
      <span id="counter" style="font-weight:600; min-width:95px; text-align:center;">1 / 1</span>
      <button class="primary" onclick="next()">Próximo →</button>
      <input type="number" id="jumpInput" min="1" placeholder="Ir para #" style="width:90px;" onchange="jumpTo(this.value)">
    </div>
    <div class="controls">
      <select id="subFilter" onchange="applyFilter()">
        <option value="ALL">Todos subreddits</option>
      </select>
      <button onclick="exportTags()">Exportar Triagem (CSV)</button>
    </div>
  </div>

  <div class="card" id="card"></div>
  <div class="hint">Atalhos: <b>←</b> Anterior | <b>→</b> Próximo | <b>1</b> Válido | <b>2</b> Ruído | <b>3</b> Revisar</div>
</div>

<script>
const ALL_POSTS = {data_json};
let filtered = [...ALL_POSTS];
let current = 0;
let tags = JSON.parse(localStorage.getItem("reddit_triage_tags") || "{{}}");

// Preenche filtro de subreddits
const subs = [...new Set(ALL_POSTS.map(p => p.subreddit))].sort();
const sel = document.getElementById("subFilter");
subs.forEach(s => {{
  const opt = document.createElement("option");
  opt.value = s;
  opt.textContent = "r/" + s;
  sel.appendChild(opt);
}});

function applyFilter() {{
  const val = sel.value;
  filtered = val === "ALL" ? [...ALL_POSTS] : ALL_POSTS.filter(p => p.subreddit === val);
  current = 0;
  render();
}}

function setTag(status) {{
  const p = filtered[current];
  if (!p) return;
  if (tags[p.id] === status) delete tags[p.id];
  else tags[p.id] = status;
  localStorage.setItem("reddit_triage_tags", JSON.stringify(tags));
  render();
}}

function render() {{
  const card = document.getElementById("card");
  const counter = document.getElementById("counter");
  if (!filtered.length) {{
    counter.textContent = "0 / 0";
    card.innerHTML = "<p>Nenhum post neste filtro.</p>";
    return;
  }}
  const p = filtered[current];
  counter.textContent = `${{current + 1}} / ${{filtered.length}}`;
  const st = tags[p.id] || "";

  let commentsHtml = "";
  if (p.comments && p.comments.length) {{
    commentsHtml = `<div class="comments"><h4>Comentários (${{p.comments.length}})</h4>` +
      p.comments.map(c => `<div class="comment" style="margin-left:${{Math.min(c.depth || 0, 5) * 18}}px"><b>Score: ${{c.score}}</b><br>${{escapeHtml(c.body)}}</div>`).join("") +
      `</div>`;
  }}

  card.innerHTML = `
    <div class="meta">
      <span class="badge">r/${{escapeHtml(p.subreddit)}}</span>
      <span>ID: <b>${{escapeHtml(p.id)}}</b></span>
      <span>Data: ${{escapeHtml(p.date)}}</span>
      <span>Score: ${{p.score}}</span>
      <span>Comentários: ${{p.num_comments}}</span>
      ${{p.url ? `<a href="${{escapeHtml(p.url)}}" target="_blank">Abrir no Reddit ↗</a>` : ""}}
    </div>
    <h2>${{escapeHtml(p.title)}}</h2>
    <div class="body-text">${{escapeHtml(p.selftext)}}</div>
    <div class="tag-bar">
      <span style="font-size:13px;color:#65676b;">Classificação rápida:</span>
      <button class="tag-btn ${{st === 'valido' ? 'active-valid' : ''}}" onclick="setTag('valido')">[1] Válido</button>
      <button class="tag-btn ${{st === 'ruido' ? 'active-noise' : ''}}" onclick="setTag('ruido')">[2] Ruído / Spam</button>
      <button class="tag-btn ${{st === 'revisar' ? 'active-later' : ''}}" onclick="setTag('revisar')">[3] Revisar depois</button>
    </div>
    ${{commentsHtml}}
  `;
}}

function escapeHtml(str) {{
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}}

function prev() {{ if (current > 0) {{ current--; render(); window.scrollTo(0,0); }} }}
function next() {{ if (current < filtered.length - 1) {{ current++; render(); window.scrollTo(0,0); }} }}
function jumpTo(n) {{
  const idx = parseInt(n, 10) - 1;
  if (idx >= 0 && idx < filtered.length) {{ current = idx; render(); }}
}}

function exportTags() {{
  let csv = "id,subreddit,status,title\\n";
  ALL_POSTS.forEach(p => {{
    if (tags[p.id]) {{
      csv += `"${{p.id}}","${{p.subreddit}}","${{tags[p.id]}}","${{p.title.replace(/"/g, '""')}}"\\n`;
    }}
  }});
  const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8;" }});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "triagem_posts.csv";
  a.click();
}}

document.addEventListener("keydown", e => {{
  if (e.target.tagName === "INPUT") return;
  if (e.key === "ArrowLeft") prev();
  else if (e.key === "ArrowRight") next();
  else if (e.key === "1") setTag("valido");
  else if (e.key === "2") setTag("ruido");
  else if (e.key === "3") setTag("revisar");
}});

render();
</script>
</body>
</html>
"""

with open("visualizador.html", "w", encoding="utf-8") as f:
    f.write(html_template)

print(f"Visualizador gerado com {len(records)} posts a partir de '{CSV_PATH}'. Abra 'visualizador.html' no navegador.")