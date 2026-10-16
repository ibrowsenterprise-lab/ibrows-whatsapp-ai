"""One-time, fingerprint-guarded repair of wrongly labelled MSJ catalogue images.

The two uploaded four-shirt design sheets were assigned to one another at
import.  We verified these precise JPEG MD5 fingerprints against the actual
user-provided source mockup sheets and the live MSJ production database.
This only swaps image bytes among the eight existing products if *all* eight
are in the exact known mistaken state; no prices, codes, status, orders, sizes,
or descriptions are changed. Never apply it to newly modified artwork.
"""
EXPECTED_WRONG = {
    "MSJ-CIRCLE": "332235adfb8160c0fa92b890f871de66",      # Varsity shirt
    "MSJ-HANDWRITTEN": "85f5530fafaf69fa0a94132622b68ef5", # Stencil shirt
    "MSJ-LABEL": "1c5ebb5320f224d1d90d7e216da7f316",      # Motion shirt
    "MSJ-RETRO-FLOW": "4cc4169b2c3dcf95a121d7524ea903f8", # Vertical shirt
    "MSJ-VARSITY": "fb72ee5f25003ab4f30d5326782dfff3",   # Circle shirt
    "MSJ-STENCIL": "7fb2740ff9438907a690ddc09f4dbf38",    # Handwritten shirt
    "MSJ-MOTION": "4119e5d2839f952a81ca30c5be8efef2",     # Label shirt
    "MSJ-VERTICAL": "ac913f2f1b33feb13b5bbf3b47329221",   # Retro Flow shirt
}
SOURCE_FOR_TARGET = {
    "MSJ-CIRCLE": "MSJ-VARSITY",
    "MSJ-HANDWRITTEN": "MSJ-STENCIL",
    "MSJ-LABEL": "MSJ-MOTION",
    "MSJ-RETRO-FLOW": "MSJ-VERTICAL",
    "MSJ-VARSITY": "MSJ-CIRCLE",
    "MSJ-STENCIL": "MSJ-HANDWRITTEN",
    "MSJ-MOTION": "MSJ-LABEL",
    "MSJ-VERTICAL": "MSJ-RETRO-FLOW",
}
EXPECTED_CORRECT = {
    target: EXPECTED_WRONG[source] for target, source in SOURCE_FOR_TARGET.items()
}


def repair_ms_j_misassigned_sheet_images(cur):
    """Return 'repaired', 'already_correct', 'unrelated_catalogue', or 'changed_skip'.

    Caller holds the existing PostgreSQL transaction advisory lock and commits.
    On unexpected data, do nothing; on a partial UPDATE, raise to roll back.
    """
    codes = sorted(EXPECTED_WRONG)
    cur.execute(
        "SELECT code, md5(image_bytes) FROM msj_merch_designs "
        "WHERE code = ANY(%s) ORDER BY code FOR UPDATE",
        (codes,),
    )
    current = dict(cur.fetchall())
    if not current:
        return "unrelated_catalogue"
    if current == EXPECTED_CORRECT:
        return "already_correct"
    if current != EXPECTED_WRONG:
        return "changed_skip"

    case_sql = "CASE dest.code " + " ".join(
        "WHEN '" + target + "' THEN '" + source + "'"
        for target, source in SOURCE_FOR_TARGET.items()
    ) + " END"
    # Materialize all source assets *before* replacing any target bytea.
    # The guarding fingerprint comparison above means unrelated customer art
    # is never substituted into these codes.
    cur.execute(
        "WITH originals AS MATERIALIZED ("
        " SELECT code, image_bytes, image_mime FROM msj_merch_designs"
        " WHERE code = ANY(%s)"
        ") UPDATE msj_merch_designs AS dest"
        " SET image_bytes=originals.image_bytes, image_mime=originals.image_mime"
        " FROM originals"
        " WHERE dest.code=ANY(%s) AND originals.code=" + case_sql
        + " RETURNING dest.code",
        (codes, codes),
    )
    updated = {row[0] for row in cur.fetchall()}
    if updated != set(codes):
        raise RuntimeError("MSJ artwork mapping was incomplete; rolling back this transaction.")
    cur.execute(
        "SELECT code, md5(image_bytes) FROM msj_merch_designs "
        "WHERE code = ANY(%s) ORDER BY code",
        (codes,),
    )
    after = dict(cur.fetchall())
    if after != EXPECTED_CORRECT:
        raise RuntimeError("MSJ artwork verification failed; rolling back this transaction.")
    return "repaired"
