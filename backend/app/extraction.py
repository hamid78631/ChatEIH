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


if __name__ == "__main__":
    pdf_path = Path("data/corpus/04_Calendrier_academique_2026-2027.pdf")
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        tables = read_tables(page)
        print(f"{len(tables)} tableaux trouvés\n")
        for table in tables:
            header, *data = table["rows"]
            print("En-têtes :", header)
            for row in data[:3]:
                print("   ", table_row_text(header, row))
            print()

        print("--- Lignes hors tableaux ---")
        for line in read_lines(page, [t["bbox"] for t in tables]):
            print(f"{line['top']:6} {line['size']:5} {line['text'][:80]}")