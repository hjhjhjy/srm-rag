"""Resume-capable, stall-resistant downloader for BGE model weights.

Usage:
    python -m scripts.download_bge [--url URL] [--out PATH] [--expected N]

Driven by Python `requests` (uses its own CA bundle, which avoids the Windows
schannel cert-revocation failures that block `curl`).

Important gotcha handled here: `hf-mirror.com` answers a `Range` request with a
redirect to a CDN, and that redirect can drop the `Range` header so the CDN
returns `200` (full file) instead of `206` (remainder). Naively opening the
output in `"wb"` on a `200` would then *truncate a perfectly good partial* and
restart from zero. To resume correctly we capture the final (post-redirect) URL
and re-issue the `Range` request directly against it, which the CDN honors with
`206`. A retry loop makes the whole thing survive the sandbox's frequent stalls.
"""
import os
import sys
import time
import argparse
import requests

DEFAULT_URL = (
    "https://hf-mirror.com/BAAI/bge-small-zh-v1.5/resolve/main/model.safetensors"
)
DEFAULT_OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "app", "data", "models", "bge-small-zh-v1.5", "model.safetensors",
)

CHUNK = 1 << 16  # 64KB
TIMEOUT = 30
MAX_RETRIES = 200
RETRY_SLEEP = 4


def download(url, out_path, expected=None, max_retries=MAX_RETRIES):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if expected is None:
        try:
            h = requests.head(url, timeout=TIMEOUT, allow_redirects=True)
            cl = h.headers.get("Content-Length")
            if cl:
                expected = int(cl)
        except Exception as e:
            print(f"[head] could not read size ({e}); will detect on the fly")

    retries = 0
    final_url = url  # updated to the post-redirect CDN url after the first hop
    while True:
        existing = os.path.getsize(out_path) if os.path.exists(out_path) else 0
        if expected and existing >= expected:
            print(f"[complete] {existing} bytes == expected {expected}")
            return True
        if expected:
            print(f"[resume] have {existing}/{expected} ({existing*100//expected}%)")
        headers = {"Range": f"bytes={existing}-"}
        try:
            with requests.get(final_url, headers=headers, stream=True,
                              timeout=TIMEOUT, allow_redirects=False) as r:
                # Redirect: grab the CDN location and retry with Range on it.
                if r.status_code in (301, 302, 303, 307, 308):
                    loc = r.headers.get("Location")
                    if loc:
                        final_url = loc
                        print(f"[redirect] -> {final_url[:80]}...")
                        continue
                if r.status_code == 200 and existing > 0:
                    # Server ignored Range and sent the full file. Don't clobber
                    # our good partial with a 0-based stream; retry against the
                    # final url (captured below) which usually honors Range.
                    final_url = r.url
                    r.close()
                    print("[note] server ignored Range (200); retrying on final url")
                    continue
                if r.status_code not in (200, 206):
                    r.raise_for_status()
                mode = "ab" if (existing > 0 and r.status_code == 206) else "wb"
                written = 0
                with open(out_path, mode) as f:
                    for chunk in r.iter_content(CHUNK):
                        if not chunk:
                            continue
                        f.write(chunk)
                        f.flush()
                        written += len(chunk)
                if written == 0:
                    raise IOError("0 bytes received this pass")
                retries = 0
        except Exception as e:
            retries += 1
            cur = os.path.getsize(out_path) if os.path.exists(out_path) else 0
            print(f"[retry {retries}/{max_retries}] {type(e).__name__}: {e} "
                  f"@ {cur} bytes; sleeping {RETRY_SLEEP}s then resuming")
            if retries > max_retries:
                print("[abort] exceeded max retries")
                return False
            time.sleep(RETRY_SLEEP)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--expected", type=int, default=None)
    args = ap.parse_args()
    ok = download(args.url, args.out, args.expected)
    sys.exit(0 if ok else 1)
