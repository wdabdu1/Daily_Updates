import io

import pandas as pd
from fastapi.responses import StreamingResponse


def xlsx_response(rows: list[dict], filename: str) -> StreamingResponse:
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def xlsx_template_response(
    columns: list[str],
    example_rows: list[list],
    notes: list[str],
    filename: str,
) -> StreamingResponse:
    """A blank-ish import template: one 'Template' sheet with headers and a
    couple of example rows (so column meaning/format is obvious), plus a
    'Notes' sheet documenting rules (allowed values, upsert behavior)."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        example_df = pd.DataFrame(example_rows, columns=columns)
        example_df.to_excel(writer, index=False, sheet_name="Template")
        notes_df = pd.DataFrame({"Notes": notes})
        notes_df.to_excel(writer, index=False, sheet_name="Notes")

        # Auto-width columns roughly to content, purely cosmetic.
        ws = writer.sheets["Template"]
        for i, col in enumerate(columns, start=1):
            width = max(12, len(col) + 2)
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width
        ws_notes = writer.sheets["Notes"]
        ws_notes.column_dimensions["A"].width = 100

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def read_uploaded_xlsx(file_bytes: bytes) -> pd.DataFrame:
    """Reads the 'Template' sheet if present (our own templates use that
    name), otherwise falls back to the first sheet, so a user's edited
    copy of the template -- or a simple single-sheet file they built
    themselves -- both work."""
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    sheet = "Template" if "Template" in xls.sheet_names else xls.sheet_names[0]
    df = xls.parse(sheet)
    # Drop fully-blank rows (common when someone leaves trailing empty rows).
    return df.dropna(how="all")
