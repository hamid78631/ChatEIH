import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

def read_pages(path: Path) -> list[tuple[int, str]]:
    """Lit un PDF et renvoie la liste (numéro de page, texte de la page)."""
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append((page.page_number, text))
    return pages


BULLET = "(cid:127)"  # la puce « • » telle que pdfplumber la lit dans ces PDF

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
    reference: str = ""
    doc_type: str = ""
    date: str = ""         # format ISO AAAA-MM-JJ, pour trier
    date_label: str = ""   # date telle qu'écrite dans le PDF
    version: str = ""
    status: str = ""
    issuer: str = ""
    audience: str = ""
    amending: bool = False                              
    modifies: list[str] = field(default_factory=list)   


def clean_text(text: str) -> str:
    """Remplace les retours à la ligne et les espaces multiples par un seul espace."""
    return " ".join(text.split())


def is_inside(word: dict, bbox: tuple) -> bool:
    """Vrai si le centre du mot est dans le rectangle bbox = (x0, top, x1, bottom)."""
    x0, top, x1, bottom = bbox
    center_x = (word["x0"] + word["x1"]) / 2
    center_y = (word["top"] + word["bottom"]) / 2
    return x0 <= center_x <= x1 and top <= center_y <= bottom


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
            "text": " ".join(w["text"] for w in content),
        })
    return lines

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


def read_metadata(path: Path) -> DocumentMeta:
    """Lit le tableau de métadonnées de la page 1 d'un PDF."""
    meta = DocumentMeta(file=path.name)
    with pdfplumber.open(path) as pdf:
        for table in read_tables(pdf.pages[0]):
            if parse_meta_table(table["rows"], meta):
                break
    finalize_meta(meta)
    return meta


if __name__ == "__main__":
    for pdf_path in sorted(Path("data/corpus").glob("*.pdf")):
        meta = read_metadata(pdf_path)
        modif = f"modifie {meta.modifies}" if meta.amending else ""
        print(f"{meta.file[:30]:30} {meta.reference:20} {meta.date}  v{meta.version[:3]:4} {modif}")