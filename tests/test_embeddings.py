"""Test SafeChain embedding capabilities — single, batch, and error modes.

Run from cortex/ with venv active:
    python tests/test_embeddings.py
"""

import sys
import time
import traceback

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())


def main():
    print("=" * 60)
    print("SafeChain Embedding Diagnostic")
    print("=" * 60)

    # ── 1. Config & model init ──────────────────────────────
    print("\n[1] Loading SafeChain config...")
    try:
        from ee_config.config import Config
        Config.from_env()
        print("    ✓ Config loaded")
    except Exception as e:
        print(f"    ✗ Config failed: {e}")
        sys.exit(1)

    print("\n[2] Initializing embedding model (index '2')...")
    try:
        from safechain.lcel import model
        client = model("2")
        print(f"    ✓ Model initialized: {type(client).__name__}")
    except Exception as e:
        print(f"    ✗ Model init failed: {e}")
        sys.exit(1)

    # ── 2. Single embed_query ───────────────────────────────
    print("\n[3] Testing embed_query (single text)...")
    try:
        t0 = time.time()
        vec = client.embed_query("total billed business")
        dt = (time.time() - t0) * 1000
        print(f"    ✓ embed_query returned {len(vec)}-dim vector in {dt:.0f}ms")
        print(f"    ✓ First 5 values: {vec[:5]}")
    except Exception as e:
        print(f"    ✗ embed_query FAILED: {e}")
        traceback.print_exc()

    # ── 3. Single embed_query with BGE prefix ───────────────
    BGE_PREFIX = "Represent this sentence for searching relevant passages: "
    print("\n[4] Testing embed_query with BGE prefix...")
    try:
        t0 = time.time()
        vec = client.embed_query(BGE_PREFIX + "total billed business")
        dt = (time.time() - t0) * 1000
        print(f"    ✓ embed_query (prefixed) returned {len(vec)}-dim in {dt:.0f}ms")
    except Exception as e:
        print(f"    ✗ embed_query (prefixed) FAILED: {e}")
        traceback.print_exc()

    # ── 4. embed_documents (batch, 1 text) ──────────────────
    print("\n[5] Testing embed_documents (batch, 1 text)...")
    try:
        t0 = time.time()
        vecs = client.embed_documents(["total billed business"])
        dt = (time.time() - t0) * 1000
        print(f"    ✓ embed_documents(1) returned {len(vecs)} vector(s), dim={len(vecs[0])} in {dt:.0f}ms")
    except Exception as e:
        print(f"    ✗ embed_documents(1) FAILED: {e}")
        traceback.print_exc()

    # ── 5. embed_documents (batch, 3 texts) ─────────────────
    print("\n[6] Testing embed_documents (batch, 3 texts)...")
    texts = [
        "total billed business",
        "customer attrition rate",
        "merchant category spend",
    ]
    try:
        t0 = time.time()
        vecs = client.embed_documents(texts)
        dt = (time.time() - t0) * 1000
        print(f"    ✓ embed_documents(3) returned {len(vecs)} vectors, dim={len(vecs[0])} in {dt:.0f}ms")
    except Exception as e:
        print(f"    ✗ embed_documents(3) FAILED: {e}")
        traceback.print_exc()

    # ── 6. embed_documents with BGE prefix ──────────────────
    print("\n[7] Testing embed_documents with BGE prefix (batch, 3 texts)...")
    prefixed = [BGE_PREFIX + t for t in texts]
    try:
        t0 = time.time()
        vecs = client.embed_documents(prefixed)
        dt = (time.time() - t0) * 1000
        print(f"    ✓ embed_documents(3, prefixed) returned {len(vecs)} vectors in {dt:.0f}ms")
    except Exception as e:
        print(f"    ✗ embed_documents(3, prefixed) FAILED: {e}")
        traceback.print_exc()

    # ── 7. Sequential fallback comparison ───────────────────
    print("\n[8] Sequential embed_query x3 (fallback comparison)...")
    try:
        t0 = time.time()
        vecs = [client.embed_query(t) for t in texts]
        dt = (time.time() - t0) * 1000
        print(f"    ✓ 3x embed_query returned {len(vecs)} vectors in {dt:.0f}ms")
    except Exception as e:
        print(f"    ✗ Sequential embed_query FAILED: {e}")
        traceback.print_exc()

    # ── 8. Check available methods ──────────────────────────
    print("\n[9] Embedding client methods...")
    for method in ["embed_query", "embed_documents", "aembed_query", "aembed_documents"]:
        has = hasattr(client, method)
        print(f"    {'✓' if has else '✗'} {method}: {'available' if has else 'NOT available'}")

    print("\n" + "=" * 60)
    print("Done.")


if __name__ == "__main__":
    main()
