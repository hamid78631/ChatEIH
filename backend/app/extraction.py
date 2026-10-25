import re
from collections import Counter  # NOUVEAU
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

BULLET = "(cid:127)"  # la puce « • » telle que pdfplumber la lit dans ces PDF

# Libellé de la 1re colonne du tableau de métadonnées -> nom du champ Python
META_KEYS = {
    "organisme émetteur": "issuer",
    "type de document": "doc_type",
    "référence": "reference",
    "date de publication": "date_label",
    "version": "version",
    "public visé": "audience",
    "statut": "status",
}

MONTHS = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
}

# « 5 octobre 2026 », « 1er février 2027 »
DATE_PATTERN = re.compile(r"(\d{1,2})(?:er)?\s+([a-zéû]+)\s+(\d{4})", re.IGNORECASE)
# Référence d'un document : EIH-SRE-GUIDE-2026, EIH-DE-NS-2026-14...
REF_PATTERN = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)+\b")
# Le document se déclare modificatif : « modifie », « modifient », « modificatif »
AMENDING_PATTERN = re.compile(r"\bmodifi(?:e|ent|catif)\b", re.IGNORECASE)


@dataclass
class DocumentMeta:
    file: str
    title: str = ""        # NOUVEAU : titre du document (police la plus grande)
    reference: str = ""
    doc_type: str = ""
    date: str = ""         # format ISO AAAA-MM-JJ, pour trier
    date_label: str = ""   # date telle qu'écrite dans le PDF
    version: str = ""
    status: str = ""
    issuer: str = ""
    audience: str = ""
    amending: bool = False                              # se déclare modificatif ?
    modifies: list[str] = field(default_factory=list)   # références qu'il modifie


@dataclass
class Block:  # NOUVEAU
    page: int
    kind: str          # "heading", "paragraph", "list_item", "table_row"
    text: str
    level: int = 0     # niveau de titre (1 à 3), 0 sinon
    section: str = ""  # chemin des titres : « Titre II — ... > Article 3 — ... »


@dataclass
class ExtractedDocument:  # NOUVEAU
    meta: DocumentMeta
    blocks: list[Block]


# --------------------------------------------------------------------------- utilitaires


def clean_text(text: str) -> str:
    """Remplace retours à la ligne et espaces multiples par un espace ; corrige « ECTS , soit »."""
    text = " ".join(text.split())
    return re.sub(r" ([,.])", r"\1", text)  # NOUVEAU


def is_inside(word: dict, bbox: tuple) -> bool:
    """Vrai si le centre du mot est dans le rectangle bbox = (x0, top, x1, bottom)."""
    x0, top, x1, bottom = bbox
    center_x = (word["x0"] + word["x1"]) / 2
    center_y = (word["top"] + word["bottom"]) / 2
    return x0 <= center_x <= x1 and top <= center_y <= bottom


def parse_french_date(label: str) -> str:
    """« 5 octobre 2026 » -> « 2026-10-05 » ; chaîne vide si la date est illisible."""
    match = DATE_PATTERN.search(label)
    if not match:
        return ""
    day, month_name, year = match.groups()
    month = MONTHS.get(month_name.lower())
    if month is None:
        return ""
    return f"{year}-{month:02d}-{int(day):02d}"


# --------------------------------------------------------------------------- lecture d'une page


def read_tables(page) -> list[dict]:
    """Renvoie les tableaux de la page : position, rectangle et lignes de cellules nettoyées."""
    tables = []
    for table in page.find_tables():
        rows = []
        for row in table.extract():
            cells = [clean_text(cell) if cell else "" for cell in row]
            if any(cells):
                rows.append(cells)
        tables.append({"top": table.bbox[1], "bbox": table.bbox, "rows": rows})
    return tables


def table_row_text(header: list[str], row: list[str]) -> str:
    """Réécrit une ligne de tableau : « En-tête : valeur — En-tête : valeur »."""
    parts = []
    for name, value in zip(header, row):
        if value:
            parts.append(f"{name} : {value}" if name else value)
    return " — ".join(parts)


def read_lines(page, table_bboxes=()) -> list[dict]:
    """Regroupe les mots d'une page en lignes, avec position, taille, gras et puce."""
    words = page.extract_words(extra_attrs=["size", "fontname"])
    words = [w for w in words if not any(is_inside(w, bbox) for bbox in table_bboxes)]
    words.sort(key=lambda w: (round(w["top"]), w["x0"]))

    # 1. Regrouper les mots qui sont à la même hauteur
    groups = []
    for word in words:
        if groups and abs(word["top"] - groups[-1][0]["top"]) <= 2.5:
            groups[-1].append(word)
        else:
            groups.append([word])

    # 2. Transformer chaque groupe en une ligne décrite par un dictionnaire
    lines = []
    for group in groups:
        group.sort(key=lambda w: w["x0"])
        is_bullet = any(w["text"] == BULLET for w in group)
        content = [w for w in group if w["text"] != BULLET]
        if not content:
            continue
        bold_count = sum("Bold" in w["fontname"] for w in content)
        lines.append({
            "top": round(group[0]["top"], 1),
            "size": round(content[0]["size"], 1),
            "bold": bold_count > len(content) / 2,
            "bullet": is_bullet,
            "text": clean_text(" ".join(w["text"] for w in content)),  # NOUVEAU : clean_text
        })
    return lines


# --------------------------------------------------------------------------- métadonnées


def parse_meta_table(rows: list[list[str]], meta: DocumentMeta) -> bool:
    """Remplit meta si le tableau est le tableau de métadonnées ; renvoie True dans ce cas."""
    found = False
    for row in rows:
        if len(row) < 2:
            continue
        field_name = META_KEYS.get(row[0].lower())
        if field_name:
            setattr(meta, field_name, row[1])
            found = True
    return found


def finalize_meta(meta: DocumentMeta) -> None:
    """Calcule les champs dérivés : date ISO, caractère modificatif, références modifiées."""
    meta.date = parse_french_date(meta.date_label)
    meta.amending = bool(AMENDING_PATTERN.search(f"{meta.doc_type} {meta.status}"))
    if meta.amending:
        meta.modifies = [ref for ref in REF_PATTERN.findall(meta.status) if ref != meta.reference]


# --------------------------------------------------------------------------- assemblage  (NOUVEAU)


def normalize_repeated(text: str) -> str:
    """Clé de comparaison des en-têtes / pieds de page : les numéros sont neutralisés."""
    return re.sub(r"\d+", "#", text)


def remove_repeated_lines(pages: list[list[dict]], page_height: float) -> None:
    """Supprime les lignes situées en haut / bas de page qui se répètent sur au moins 2 pages."""
    margin = page_height * 0.12

    def in_margin(event: dict) -> bool:
        return event["type"] == "line" and (event["top"] < margin or event["top"] > page_height - margin)

    counts = Counter()
    for events in pages:
        counts.update({normalize_repeated(e["text"]) for e in events if in_margin(e)})
    repeated = {text for text, n in counts.items() if n >= 2}

    for events in pages:
        events[:] = [e for e in events if not (in_margin(e) and normalize_repeated(e["text"]) in repeated)]


def heading_levels(lines: list[dict]) -> tuple[float, dict[float, int]]:
    """Renvoie la taille du titre du document et la correspondance taille -> niveau de titre."""
    weight = Counter()
    for line in lines:
        weight[line["size"]] += len(line["text"])
    body_size = weight.most_common(1)[0][0]
    title_size = max(line["size"] for line in lines)
    sizes = {l["size"] for l in lines if l["bold"] and body_size < l["size"] < title_size}
    levels = {size: i + 1 for i, size in enumerate(sorted(sizes, reverse=True)[:3])}
    return title_size, levels


def current_section(headings: list[str]) -> str:
    return " > ".join(h for h in headings if h)


def build_blocks(pages: list[list[dict]], meta: DocumentMeta) -> list[Block]:
    """Transforme les lignes et tableaux de chaque page en blocs classés, rattachés à leur section."""
    lines = [e for events in pages for e in events if e["type"] == "line"]
    title_size, levels = heading_levels(lines)

    blocks: list[Block] = []
    headings = ["", "", ""]  # titres courants de niveau 1, 2 et 3
    title_parts = []

    for events in pages:
        previous = None  # dernière ligne lue ; pas de fusion d'une page à l'autre
        for event in events:
            # Tableau : une ligne de tableau = un bloc
            if event["type"] == "table":
                if event["rows"]:
                    header, *data = event["rows"]
                    for row in data:
                        text = table_row_text(header, row)
                        if text:
                            blocks.append(Block(event["page"], "table_row", text,
                                                section=current_section(headings)))
                previous = None
                continue

            size, text = event["size"], event["text"]
            # La ligne prolonge la précédente si l'écart vertical est celui d'un interligne
            close = previous is not None and event["top"] - previous["top"] <= size * 1.65

            # Titre du document
            if size == title_size:
                title_parts.append(text)
                previous = None
                continue

            # Titre de section
            if size in levels:
                level = levels[size]
                if close and previous["kind"] == "heading" and blocks[-1].level == level:
                    blocks[-1].text += " " + text          # titre écrit sur deux lignes
                    headings[level - 1] = blocks[-1].text
                else:
                    headings[level - 1] = text
                    for deeper in range(level, 3):         # on quitte les sous-sections
                        headings[deeper] = ""
                    blocks.append(Block(event["page"], "heading", text, level=level))
                blocks[-1].section = current_section(headings)
                previous = {"top": event["top"], "kind": "heading"}
                continue

            # Paragraphe ou élément de liste
            if close and not event["bullet"] and previous["kind"] in ("paragraph", "list_item"):
                blocks[-1].text += " " + text              # suite du même paragraphe
            else:
                kind = "list_item" if event["bullet"] else "paragraph"
                blocks.append(Block(event["page"], kind, f"• {text}" if event["bullet"] else text,
                                    section=current_section(headings)))
            previous = {"top": event["top"], "kind": blocks[-1].kind}

    meta.title = " ".join(title_parts)
    return blocks


def extract_document(path: Path) -> ExtractedDocument:
    """Extrait un PDF : métadonnées + blocs structurés dans l'ordre de lecture."""
    meta = DocumentMeta(file=path.name)
    pages = []  # pour chaque page : lignes et tableaux triés de haut en bas

    with pdfplumber.open(path) as pdf:
        page_height = pdf.pages[0].height
        for page in pdf.pages:
            tables = read_tables(page)
            events = [{**line, "type": "line", "page": page.page_number}
                      for line in read_lines(page, [t["bbox"] for t in tables])]
            for table in tables:
                if page.page_number == 1 and parse_meta_table(table["rows"], meta):
                    continue  # le tableau de métadonnées n'est pas du contenu
                events.append({**table, "type": "table", "page": page.page_number})
            events.sort(key=lambda e: e["top"])
            pages.append(events)

    remove_repeated_lines(pages, page_height)
    blocks = build_blocks(pages, meta)
    finalize_meta(meta)
    return ExtractedDocument(meta=meta, blocks=blocks)


def extract_corpus(corpus_dir: Path) -> list[ExtractedDocument]:
    """Extrait tous les PDF d'un dossier, dans l'ordre alphabétique (01 -> 07)."""
    return [extract_document(path) for path in sorted(corpus_dir.glob("*.pdf"))]


if __name__ == "__main__":
    doc = extract_document(Path("data/corpus/01_Reglement_des_etudes_2026-2027.pdf"))
    print("Titre :", doc.meta.title, "|", doc.meta.reference, doc.meta.date)
    print(f"{len(doc.blocks)} blocs\n")
    for block in doc.blocks[:25]:
        print(f"p{block.page} {block.kind:10} | {block.section[-45:]:45} | {block.text[:60]}")