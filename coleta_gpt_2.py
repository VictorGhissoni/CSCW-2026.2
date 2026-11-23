import requests
import time
import json
import os
import datetime as dt
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

sys.stdout = sys.stderr = Logger("coleta.log")

BASE = "https://arctic-shift.photon-reddit.com/api"
# Subreddits menores primeiro para liberar arquivos rapidamente para a filtragem local
SUBS = ["empreendedorismo", "Business_Ideas", "smallbusiness", "startups", "Entrepreneur", "ChatGPT"]

START_TS = int(dt.datetime(2022, 12, 1, tzinfo=dt.timezone.utc).timestamp())
END_TS = int(dt.datetime(2024, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc).timestamp())

def get_resume_state(filepath):
    """Lê o arquivo existente para retomar do último timestamp sem duplicar IDs."""
    seen = set()
    last_ts = START_TS
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    seen.add(row["id"])
                    ts = int(row["created_utc"])
                    if ts > last_ts:
                        last_ts = ts
                except json.JSONDecodeError:
                    continue
    return last_ts, seen

def request_with_retry(url, params, max_retries=100):
    """Faz a requisição medindo o tempo de resposta e aplicando backoff em erros."""
    wait = 2
    for attempt in range(1, max_retries + 1):
        t0 = time.perf_counter()
        try:
            r = requests.get(url, params=params, timeout=60)
            elapsed = time.perf_counter() - t0
            if r.status_code == 200:
                return r.json(), elapsed
            print(f"  [HTTP {r.status_code} | {elapsed:.2f}s] {r.text[:100]} -> aguardando {wait}s ({attempt}/{max_retries})")
        except requests.RequestException as e:
            elapsed = time.perf_counter() - t0
            print(f"  [Erro rede | {elapsed:.2f}s] {e} -> aguardando {wait}s ({attempt}/{max_retries})")
        time.sleep(wait)
        wait = min(wait * 2, 15)
    raise RuntimeError(f"Falha após {max_retries} tentativas na URL {url}")

def fetch_subreddit(sub, filepath):
    after, seen = get_resume_state(filepath)
    total_saved = len(seen)
    req_times = []
    sub_start = time.perf_counter()

    if total_saved > 0:
        dt_resume = dt.datetime.fromtimestamp(after, tz=dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
        print(f"  Retomando r/{sub} a partir de {dt_resume} UTC ({total_saved} posts já salvos)...")

    with open(filepath, "a", encoding="utf8") as f:
        while after < END_TS:
            params = {
                "subreddit": sub,
                "after": after,
                "before": END_TS,
                "sort": "asc",
                "limit": 100
            }
            payload, elapsed = request_with_retry(f"{BASE}/posts/search", params)
            req_times.append(elapsed)
            data = payload.get("data") or []
            rows = [x for x in data if x["id"] not in seen]

            if not rows:
                if data:
                    after += 1
                    time.sleep(1.5)
                    continue
                break

            for row in rows:
                seen.add(row["id"])
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()

            total_saved += len(rows)
            last_ts = int(rows[-1]["created_utc"])
            after = last_ts + 1 if last_ts <= after else last_ts

            dt_str = dt.datetime.fromtimestamp(after, tz=dt.timezone.utc).strftime("%Y-%m-%d")
            avg_req = sum(req_times[-20:]) / len(req_times[-20:])
            print(
                f"  r/{sub} | req #{len(req_times):04d}: {elapsed:.2f}s (média {avg_req:.2f}s) "
                f"| +{len(rows)} posts (total: {total_saved}) | data: {dt_str}"
            )

            time.sleep(1.5)

    total_time = time.perf_counter() - sub_start
    avg_all = (sum(req_times) / len(req_times)) if req_times else 0.0
    print(f"Concluído r/{sub}: {total_saved} posts em {total_time:.1f}s ({len(req_times)} requests, média {avg_all:.2f}s/req).\n")

os.makedirs("raw", exist_ok=True)
for s in SUBS:
    print(f"=== Iniciando coleta de r/{s} -> raw/{s}.jsonl ===")
    fetch_subreddit(s, f"raw/{s}.jsonl")