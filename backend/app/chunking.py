from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from .extraction import Block, ExtractedDocument, extract_document

STRATEGIES = ("fixed", "structural")


@dataclass
class Chunk:
    chunk_id: str    # identifiant stable : <référence>:<stratégie>:<n°>
    text: str
    file: str
    reference: str
    doc_type: str
    date: str        # ISO, pour comparer les versions
    title: str       # titre du document
    page: int        # page où commence le fragment
    section: str
    strategy: str
    position: int    # rang du fragment dans le document
    amending: bool   # le document source se déclare modificatif
    modifies: str    # références modifiées, séparées par des virgules


def validate_params(strategy: str, size: int, overlap: int) -> None:
    """Lève une ValueError si les paramètres de découpage sont incohérents."""
    if strategy not in STRATEGIES:
        raise ValueError(f"Stratégie inconnue : {strategy!r} (attendu : {', '.join(STRATEGIES)})")
    if size < 50:
        raise ValueError("La taille doit être d'au moins 50 caractères")
    if not 0 <= overlap < size:
        raise ValueError("Le chevauchement doit être positif et strictement inférieur à la taille")


def split_fixed(text: str, size: int, overlap: int) -> list[tuple[int, str]]:
    """Découpe text en fenêtres de size caractères ; renvoie (position de départ, morceau)."""
    pieces = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # Couper sur le dernier espace de la seconde moitié de la fenêtre
            cut = text.rfind(" ", start + size // 2, end)
            if cut != -1:
                end = cut
        piece = text[start:end].strip()
        if piece:
            pieces.append((start, piece))
        if end >= len(text):
            break
        # Reculer de overlap caractères, puis avancer jusqu'au début d'un mot
        next_start = max(end - overlap, start + 1)
        while next_start < end and not text[next_start - 1].isspace():
            next_start += 1
        start = next_start
    return pieces


def make_chunk(doc: ExtractedDocument, strategy: str, position: int, text: str,
               page: int, section: str) -> Chunk:
    """Crée un Chunk en recopiant les métadonnées du document source."""
    meta = doc.meta
    return Chunk(
        chunk_id=f"{meta.reference}:{strategy}:{position:03d}",
        text=text,
        file=meta.file,
        reference=meta.reference,
        doc_type=meta.doc_type,
        date=meta.date,
        title=meta.title,
        page=page,
        section=section,
        strategy=strategy,
        position=position,
        amending=meta.amending,
        modifies=",".join(meta.modifies),
    )


def chunk_fixed(doc: ExtractedDocument, size: int, overlap: int) -> list[Chunk]:
    """Stratégie (a) : fenêtres de taille fixe avec chevauchement sur le texte continu du document."""
    # Texte continu ; on retient la position de début de chaque bloc
    starts = []
    parts = []
    offset = 0
    for block in doc.blocks:
        starts.append(offset)
        parts.append(block.text)
        offset += len(block.text) + 1  # + 1 pour le "\n" qui sépare les blocs
    text = "\n".join(parts)

    chunks = []
    for position, (start, piece) in enumerate(split_fixed(text, size, overlap)):
        # Le bloc qui contient le début du fragment donne sa page et sa section
        block = doc.blocks[bisect_right(starts, start) - 1]
        chunks.append(make_chunk(doc, "fixed", position, piece, block.page, block.section))
    return chunks


def group_by_section(blocks: list[Block]) -> list[tuple[str, str, list[Block]]]:
    """Regroupe les blocs sous leur titre : liste de (titre, chemin de section, blocs de contenu)."""
    groups = []
    heading, section, content = "", "", []
    for block in blocks:
        if block.kind == "heading":
            if content:
                groups.append((heading, section, content))
            heading, section, content = block.text, block.section, []
        else:
            content.append(block)
    if content:
        groups.append((heading, section, content))
    return groups


def chunk_structural(doc: ExtractedDocument, size: int, overlap: int) -> list[Chunk]:
    """Stratégie (b) : un fragment par section, précédé de son titre ; size est la taille maximale."""
    chunks = []

    def emit(header: str, body: list[str], page: int, section: str) -> None:
        text = "\n".join([header, *body])
        chunks.append(make_chunk(doc, "structural", len(chunks), text, page, section))

    for heading, section, content in group_by_section(doc.blocks):
        header = heading or doc.meta.title       # texte avant le 1er titre : titre du document
        budget = max(size - len(header) - 1, 50)  # place restante après le titre
        body = []
        page = content[0].page
        for block in content:
            # Le bloc ne tient plus : on ferme le fragment en cours
            if body and len("\n".join(body + [block.text])) > budget:
                emit(header, body, page, section)
                body, page = [], block.page
            # Bloc seul trop long : découpage à taille fixe, titre répété
            if len(block.text) > budget:
                for _, piece in split_fixed(block.text, budget, min(overlap, budget // 2)):
                    emit(header, [piece], block.page, section)
                continue
            body.append(block.text)
        if body:
            emit(header, body, page, section)
    return chunks


def chunk_document(doc: ExtractedDocument, strategy: str, size: int, overlap: int) -> list[Chunk]:
    """Point d'entrée : vérifie les paramètres puis applique la stratégie demandée."""
    validate_params(strategy, size, overlap)
    if strategy == "fixed":
        return chunk_fixed(doc, size, overlap)
    return chunk_structural(doc, size, overlap)


def chunk_corpus(docs: list[ExtractedDocument], strategy: str, size: int, overlap: int) -> list[Chunk]:
    """Découpe tous les documents et renvoie la liste complète des fragments."""
    return [chunk for doc in docs for chunk in chunk_document(doc, strategy, size, overlap)]


if __name__ == "__main__":
    doc = extract_document(Path("data/corpus/07_Note_de_service_2026-14.pdf"))
    for strategy in STRATEGIES:
        chunks = chunk_document(doc, strategy, size=500, overlap=100)
        print(f"##### {strategy} : {len(chunks)} fragments\n")
        for chunk in chunks[1:3]:
            print(f"=== {chunk.chunk_id} | page {chunk.page} | {chunk.section} | {len(chunk.text)} car.")
            print(chunk.text)
            print()
