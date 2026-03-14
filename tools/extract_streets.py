#!/usr/bin/env python3
"""
extract_streets.py — Winchester TMMA Street Precinct Extractor
==============================================================
Parses the Winchester 2024 Public Book List PDF to produce a
street-to-precinct mapping for use in data.js.

Usage:
    python3 extract_streets.py <path-to-pdf> [--output-dir DIR]

Requirements:
    pip install pymupdf

Output files (written to --output-dir):
    streets_data.json    — complete mapping: street → [precincts]
    streetRanges.json    — house-number ranges for multi-precinct streets
    streets_snippet.js   — JavaScript snippet ready to paste into data.js

Algorithm:
    1. Parse the Street Index (pages 7–10) to get every
       (street_name, precinct, book_page) triple.  Streets that span
       multiple precincts appear multiple times.
    2. For multi-precinct streets, scan the corresponding street-listing
       pages and extract all house numbers (using x-coordinate to
       identify the house-number column).
    3. Build min/max ranges per precinct section.
    4. Write JSON and JS output.
"""

import sys
import json
import re
import argparse
from pathlib import Path
from collections import defaultdict

try:
    import fitz  # pymupdf
except ImportError:
    print("ERROR: pymupdf is required.  Install with: pip install pymupdf")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Constants (tuned for the 2024 Winchester Public Book List)
# ---------------------------------------------------------------------------

# x-coordinate thresholds for the two-column listing layout.
# Left column house-number column is around x=61-65.
# Right column house-number column is around x=346-354.
LEFT_HOUSE_X_MAX  = 100   # left column house numbers have x < this
RIGHT_HOUSE_X_MIN = 330   # right column house numbers have x > this
RIGHT_HOUSE_X_MAX = 400   # right column house numbers have x < this

# Street-name headers appear at x < this value
STREET_HEADER_X_MAX = 200

# The listing body starts at PDF page index 11 (book page 1).
LISTING_START_IDX = 11


def normalize(name: str) -> str:
    """Upper-case and collapse whitespace."""
    return re.sub(r"\s+", " ", name.strip()).upper().rstrip(".")


# ---------------------------------------------------------------------------
# Step 1 — Parse the Street Index (pages 7–10)
# ---------------------------------------------------------------------------

def parse_street_index(doc) -> list:
    """
    Return list of dicts: {street, precinct, book_page}
    Uses x-coordinates to robustly split the two-column index table.
    """
    entries = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        text = page.get_text()
        if "STREET INDEX" not in text:
            if page_idx > 12:   # past the index section
                break
            continue
        if "STREET LISTING" in text:
            break

        words = page.get_text("words")
        rows: dict = defaultdict(list)
        for w in words:
            y_key = round(w[1] / 5) * 5
            rows[y_key].append(w)

        page_width = page.rect.width
        col_split = page_width * 0.45   # ~270 px

        for y in sorted(rows.keys()):
            row = sorted(rows[y], key=lambda w: w[0])
            tokens = [w[4] for w in row]
            joined = " ".join(tokens)
            if any(h in joined for h in
                   ("TOWN OF WINCHESTER", "STREET NAME", "PRECINCT",
                    "STREET INDEX", "STREET LIST", "2024")):
                continue
            if joined.strip() in ("", "4", "PAGE"):
                continue

            left  = [w for w in row if w[0] < col_split]
            right = [w for w in row if w[0] >= col_split]

            for col in (left, right):
                entry = _parse_index_col(col)
                if entry:
                    entries.append(entry)

    return entries


def _parse_index_col(col_words: list) -> dict | None:
    """
    Given sorted words from one index column, extract:
        {street, precinct, book_page}
    The last two purely-numeric tokens are (precinct, page).
    Everything before is the street name.
    """
    if len(col_words) < 3:
        return None
    name_parts, digits = [], []
    for w in col_words:
        if re.fullmatch(r"\d+", w[4]):
            digits.append(w[4])
        else:
            name_parts.append(w[4])
    if len(digits) < 2:
        return None
    prec = int(digits[-2])
    pg   = int(digits[-1])
    street = normalize(" ".join(name_parts))
    if not street or prec < 1 or prec > 8:
        return None
    return {"street": street, "precinct": prec, "book_page": pg}


# ---------------------------------------------------------------------------
# Step 2 — Collect house numbers for multi-precinct streets
# ---------------------------------------------------------------------------

def collect_house_numbers(doc, index_entries: list, multi_streets: set) -> dict:
    """
    For every book page that belongs to a multi-precinct street section,
    collect all house numbers from the left and right listing columns.

    The key insight: a book page belongs to exactly one (street, precinct)
    section as indicated by the index entry.

    Returns:
        {street_name: {precinct: [house_numbers, ...]}}
    """
    # Build: book_page → (street, precinct)
    page_info: dict[int, dict] = {}
    for e in index_entries:
        if e["street"] in multi_streets:
            page_info[e["book_page"]] = {"street": e["street"], "precinct": e["precinct"]}

    results: dict = defaultdict(lambda: defaultdict(list))

    for page_idx in range(LISTING_START_IDX, len(doc)):
        book_page = page_idx - LISTING_START_IDX + 1  # book_page 1 = pdf index 11

        if book_page not in page_info:
            continue   # not a multi-precinct street page

        street   = page_info[book_page]["street"]
        precinct = page_info[book_page]["precinct"]

        page  = doc[page_idx]
        words = page.get_text("words")

        # Within the page, collect house numbers from both columns.
        # House numbers are in the "NO." column:
        #   left  column: x ≈ 61–65
        #   right column: x ≈ 346–354
        # They are numeric, 1–4 digits, and appear right after the optional '*'.
        #
        # Strategy: group words by row; for each row, look for the first
        # short numeric token in the house-number x-zone.

        rows: dict = defaultdict(list)
        for w in words:
            y_key = round(w[1] / 5) * 5
            rows[y_key].append(w)

        for y in sorted(rows.keys()):
            row = sorted(rows[y], key=lambda w: w[0])

            # Scan left column
            for w in row:
                if w[0] > LEFT_HOUSE_X_MAX:
                    break
                if re.fullmatch(r"\d{1,4}", w[4]):
                    results[street][precinct].append(int(w[4]))
                    break

            # Scan right column
            for w in row:
                if w[0] < RIGHT_HOUSE_X_MIN:
                    continue
                if w[0] > RIGHT_HOUSE_X_MAX:
                    break
                if re.fullmatch(r"\d{1,4}", w[4]):
                    results[street][precinct].append(int(w[4]))
                    break

    return results


# ---------------------------------------------------------------------------
# Step 3 — Build final data structures
# ---------------------------------------------------------------------------

def build_street_data(index_entries: list, house_data: dict) -> tuple:
    """
    Returns:
        streets  : {street_name: [precinct, ...]}       sorted
        ranges   : {street_name: [{min, max, precinct}]} only for multi
    """
    by_street: dict = defaultdict(set)
    for e in index_entries:
        by_street[e["street"]].add(e["precinct"])

    streets: dict = {}
    ranges:  dict = {}

    for street in sorted(by_street):
        precincts = sorted(by_street[street])
        streets[street] = precincts

        if len(precincts) > 1 and street in house_data:
            range_list = []
            for prec in precincts:
                nums = sorted(set(house_data[street].get(prec, [])))
                if nums:
                    range_list.append({
                        "min": min(nums),
                        "max": max(nums),
                        "precinct": prec,
                        "_sample_count": len(nums),
                        "_sample_nums": nums[:10],
                    })
            if range_list:
                ranges[street] = range_list

    return streets, ranges


# ---------------------------------------------------------------------------
# Step 4 — Emit output
# ---------------------------------------------------------------------------

def emit_js_snippet(streets: dict, ranges: dict) -> str:
    lines = [
        "// ── streets ──────────────────────────────────────────────────────",
        "// Generated by tools/extract_streets.py from the Winchester Public Book List PDF.",
        "// Format: { 'STREET NAME': [precinct, ...] }",
        "// Single-precinct streets have a one-element array.",
        "// Multi-precinct streets have multiple elements (rare); see streetRanges below.",
        "streets: {",
    ]
    for street, precincts in sorted(streets.items()):
        lines.append(f'  "{street}": {json.dumps(precincts)},')
    lines += [
        "},",
        "",
        "// ── streetRanges ─────────────────────────────────────────────────",
        "// Only populated for streets that span multiple precincts.",
        "// Use: if a street has multiple precincts, look up the house number here.",
        "// Format: { 'STREET': [{min, max, precinct}, ...] }",
        "streetRanges: {",
    ]
    for street, range_list in sorted(ranges.items()):
        clean = [{"min": r["min"], "max": r["max"], "precinct": r["precinct"]}
                 for r in range_list]
        lines.append(f'  "{street}": {json.dumps(clean)},')
    lines.append("},")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract Winchester street→precinct data from the Public Book List PDF."
    )
    parser.add_argument("pdf", help="Path to the Winchester Public Book List PDF")
    parser.add_argument(
        "--output-dir", default=".",
        help="Directory for output files (default: current directory)"
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}")
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Opening PDF: {pdf_path}")
    doc = fitz.open(str(pdf_path))
    print(f"  Total pages: {len(doc)}")

    # ── Step 1 ────────────────────────────────────────────────────────────
    print("Parsing street index …")
    index_entries = parse_street_index(doc)
    print(f"  Found {len(index_entries)} index entries")

    by_street: dict = defaultdict(set)
    for e in index_entries:
        by_street[e["street"]].add(e["precinct"])
    multi_streets = {s for s, ps in by_street.items() if len(ps) > 1}
    print(f"  Multi-precinct streets ({len(multi_streets)}): {sorted(multi_streets)}")

    # ── Step 2 ────────────────────────────────────────────────────────────
    print("\nCollecting house numbers for multi-precinct streets …")
    house_data = collect_house_numbers(doc, index_entries, multi_streets)
    for street in sorted(multi_streets):
        info = house_data.get(street, {})
        if info:
            for prec, nums in sorted(info.items()):
                uniq = sorted(set(nums))
                print(f"  {street} prec {prec}: "
                      f"{len(uniq)} unique addresses, range {uniq[0]}–{uniq[-1]}, "
                      f"sample: {uniq[:8]}")
        else:
            print(f"  {street}: NO numbers found (check book_page mapping)")

    doc.close()

    # ── Step 3 ────────────────────────────────────────────────────────────
    streets, ranges = build_street_data(index_entries, house_data)
    print(f"\nFinal street count   : {len(streets)}")
    print(f"Streets with ranges  : {len(ranges)}")

    # ── Step 4 ────────────────────────────────────────────────────────────
    json_path = out_dir / "streets_data.json"
    with open(json_path, "w") as f:
        json.dump(
            {"streets": streets, "streetRanges": ranges, "indexEntries": index_entries},
            f, indent=2
        )
    print(f"\nWrote: {json_path}")

    js_path = out_dir / "streets_snippet.js"
    with open(js_path, "w") as f:
        f.write(emit_js_snippet(streets, ranges))
    print(f"Wrote: {js_path}")

    # Also write a clean streetRanges.json without debug fields
    clean_ranges = {
        s: [{"min": r["min"], "max": r["max"], "precinct": r["precinct"]} for r in rl]
        for s, rl in ranges.items()
    }
    ranges_path = out_dir / "streetRanges.json"
    with open(ranges_path, "w") as f:
        json.dump(clean_ranges, f, indent=2)
    print(f"Wrote: {ranges_path}")

    print("\nDone.  Review the output files, then copy the relevant")
    print("sections from streets_snippet.js into data.js.")


if __name__ == "__main__":
    main()
