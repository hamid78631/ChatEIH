"""Phase 1 : extrait le corpus, le découpe et écrit les fragments dans un fichier JSON.

Usage (depuis la racine du dépôt) :
    python -m backend.app.build_chunks
    python -m backend.app.build_chunks --strategy fixed --size 500 --overlap 100
"""

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .chunking import STRATEGIES, chunk_corpus
from .config import ROOT_DIR, get_settings
from .extraction import extract_corpus


def main() -> Path:
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Extraction + découpage du corpus EIH")
    parser.add_argument("--strategy", choices=STRATEGIES, default=settings.chunk_strategy)
    parser.add_argument("--size", type=int, default=settings.chunk_size)
    parser.add_argument("--overlap", type=int, default=settings.chunk_overlap)
    parser.add_argument("--out", type=Path, default=None,
                        help="fichier de sortie (défaut : data/chunks_<stratégie>.json)")
    args = parser.parse_args()

    docs = extract_corpus(settings.corpus_path)
    chunks = chunk_corpus(docs, args.strategy, args.size, args.overlap)

    out = args.out or ROOT_DIR / "data" / f"chunks_{args.strategy}.json"
    payload = {
        "config": {"strategy": args.strategy, "size": args.size, "overlap": args.overlap},
        "documents": [asdict(doc.meta) for doc in docs],
        "chunks": [asdict(chunk) for chunk in chunks],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Résumé
    per_file = Counter(chunk.file for chunk in chunks)
    lengths = [len(chunk.text) for chunk in chunks]
    print(f"Stratégie {args.strategy} (taille {args.size}, chevauchement {args.overlap})")
    for doc in docs:
        flag = f"  modifie {', '.join(doc.meta.modifies)}" if doc.meta.amending else ""
        print(f"  {doc.meta.file:42} {doc.meta.reference:20} {doc.meta.date}  "
              f"{per_file[doc.meta.file]:3} fragments{flag}")
    print(f"Total : {len(chunks)} fragments, longueur moyenne {sum(lengths) // len(lengths)} car., "
          f"max {max(lengths)} car.")
    print(f"Écrit dans {out}")
    return out


if __name__ == "__main__":
    main()
