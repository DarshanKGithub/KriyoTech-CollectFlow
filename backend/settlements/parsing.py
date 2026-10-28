"""Bounded CSV/XLSX input. Spreadsheet formulas/macros are never evaluated."""
import csv
import io
import json
import hashlib
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 10000
HEADERS = {
    "record_type", "external_id", "currency", "settlement_reference", "payment_reference",
    "gross", "fees", "fee_tax", "refunds", "adjustments", "net", "amount",
    "expected_date", "settled_date", "reverses_type", "reverses_id",
}


def read_rows(raw, extension):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("Upload a nonempty file up to 10 MB.")
    workbook = None
    try:
        if extension == "csv":
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
            headers = reader.fieldnames or []
            iterator = iter(reader)
        elif extension == "xlsx":
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                if len(entries) > 200 or sum(entry.file_size for entry in entries) > 50 * 1024 * 1024:
                    raise ValueError("Workbook exceeds expanded archive limits.")
                if any("vbaProject" in entry.filename for entry in entries):
                    raise ValueError("Macro-enabled workbooks are not supported.")
            from openpyxl import load_workbook
            workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=False, keep_links=False)
            sheet = workbook.active
            if sheet.max_row and sheet.max_row > MAX_ROWS + 1 or sheet.max_column and sheet.max_column > 32:
                raise ValueError("Workbook is limited to 10,000 rows and 32 columns.")
            cells = sheet.iter_rows()
            header_cells = next(cells, ())
            headers = [str(cell.value or "").strip() for cell in header_cells]
            def values():
                for row in cells:
                    if any(cell.data_type == "f" for cell in row):
                        raise ValueError("Spreadsheet formulas are not allowed; upload values only.")
                    if any(cell.value is not None for cell in row):
                        yield dict(zip(headers, [cell.value for cell in row]))
            iterator = values()
        else:
            raise ValueError("Upload a UTF-8 CSV or values-only XLSX file.")
        if not headers or len(headers) > 32 or len(set(headers)) != len(headers):
            raise ValueError("Column names must be unique and limited to 32.")
        if not {"record_type", "external_id", "currency"}.issubset(headers) or set(headers) - HEADERS:
            raise ValueError("Use the settlement template headers; record_type, external_id and currency are required.")
        rows = []
        for number, row in enumerate(iterator, 2):
            if number > MAX_ROWS + 1:
                raise ValueError("Import is limited to 10,000 rows.")
            if None in row or any(len(str(value or "")) > 500 for value in row.values()):
                raise ValueError(f"Invalid columns or oversized cell at row {number}.")
            rows.append((number, row))
        if not rows:
            raise ValueError("The report has no data rows.")
        return rows
    except (UnicodeDecodeError, csv.Error, zipfile.BadZipFile, KeyError):
        raise ValueError("File is not a supported UTF-8 CSV or XLSX workbook.") from None
    except ValueError:
        raise
    except Exception:
        raise ValueError("The workbook could not be parsed safely. Upload a values-only CSV/XLSX report.") from None
    finally:
        if workbook:
            workbook.close()


def money(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        result = Decimal(str(value).strip())
        if not result.is_finite() or abs(result) > Decimal("9999999999999999.99") or result != result.quantize(Decimal(".01")):
            raise ValueError()
        return format(result, ".2f")
    except (InvalidOperation, ValueError):
        raise ValueError("Amounts must be finite decimals with at most two places.") from None


def normalized(row, currency):
    data = {}
    for key in ("external_id", "settlement_reference", "payment_reference", "reverses_id"):
        if row.get(key) is not None and not isinstance(row[key], str):
            raise ValueError(f"{key} must be a text cell to preserve identifiers exactly.")
        data[key] = str(row.get(key) or "").strip()
        if len(data[key]) > 120:
            raise ValueError(f"{key} exceeds 120 characters.")
    data["record_type"] = str(row.get("record_type") or "").strip().upper()
    data["currency"] = str(row.get("currency") or "").strip().upper()
    if data["record_type"] not in {"SETTLEMENT", "REFUND", "REVERSAL"} or not data["external_id"]:
        raise ValueError("Use SETTLEMENT, REFUND or REVERSAL and a nonempty external_id.")
    if data["currency"] != currency:
        raise ValueError("Row currency must match the source account; FX conversion is not supported.")
    for key in ("gross", "fees", "fee_tax", "refunds", "adjustments", "net", "amount"):
        data[key] = money(row.get(key))
        if key not in {"net", "adjustments"} and data[key] is not None and Decimal(data[key]) < 0:
            raise ValueError(f"{key} cannot be negative.")
    for key in ("expected_date", "settled_date"):
        value = row.get(key)
        if isinstance(value, datetime):
            if value.time().isoformat() != "00:00:00":
                raise ValueError("Use calendar dates only; preserve detailed timestamps in the original report.")
            value = value.date()
        try:
            data[key] = date.fromisoformat(str(value)).isoformat() if value not in (None, "") else None
        except ValueError:
            raise ValueError(f"{key} must be an ISO calendar date (YYYY-MM-DD).") from None
    warnings = []
    data["reverses_type"] = str(row.get("reverses_type") or "").strip().upper()
    if data["record_type"] == "SETTLEMENT":
        if data["net"] is None or data["amount"] is not None:
            raise ValueError("Settlement rows need net and must leave amount blank.")
        components = [data[key] for key in ("gross", "fees", "fee_tax", "refunds", "adjustments")]
        if all(value is not None for value in components):
            gross, fees, tax, refunds, adjustment = map(Decimal, components)
            if gross-fees-tax-refunds+adjustment != Decimal(data["net"]):
                raise ValueError("Gross − fees − fee tax − refunds + adjustments must equal net.")
        else:
            warnings.append("Incomplete settlement components; expected net cannot be independently calculated.")
    else:
        if data["amount"] is None or Decimal(data["amount"]) <= 0:
            raise ValueError("Refund/reversal amount must be positive.")
        if any(data[key] is not None for key in ("gross", "fees", "fee_tax", "refunds", "adjustments", "net")):
            raise ValueError("Refund/reversal rows use amount only; leave settlement components blank.")
    if data["record_type"] == "REVERSAL":
        if not data["reverses_id"] or data["reverses_type"] not in {"SETTLEMENT", "REFUND"}:
            raise ValueError("Reversal needs reverses_id and reverses_type SETTLEMENT or REFUND.")
    elif data["reverses_id"] or data["reverses_type"]:
        raise ValueError("Only reversal rows may reference a reversed observation.")
    if data["record_type"] == "REFUND" and not data["payment_reference"]:
        warnings.append("Refund has no payment reference; it cannot be traced to a payment yet.")
    return data, warnings


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
