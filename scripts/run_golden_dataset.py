import json
import sys
import urllib.request


def main(path: str, url: str = "http://127.0.0.1:4501/support", timeout_s: int = 60) -> int:
    headers_base = {
        "x-channel-id": "golden",
        "Content-Type": "application/json",
    }
    with open(path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            payload = json.loads(line)
            headers = dict(headers_base)
            headers["x-request-id"] = f"golden-{idx}"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                    body = resp.read().decode("utf-8")
                    print(f"golden-{idx} status={resp.status} bytes={len(body)}")
            except Exception as exc:
                print(f"golden-{idx} failed: {exc}")
    return 0


if __name__ == "__main__":
    dataset_path = sys.argv[1] if len(sys.argv) > 1 else "data/golden_dataset.jsonl"
    sys.exit(main(dataset_path))
