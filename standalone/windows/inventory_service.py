from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date
from typing import Any

import runtime


def _now() -> str:
    return runtime.utc_now()


def _parse_date(value: Any, code: str) -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except Exception as exc:
        raise ValueError(code) from exc


def _audit(conn: sqlite3.Connection, user_id: str | None, action: str, entity_type: str, entity_id: str, details: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (id, occurred_at, user_id, action, entity_type, entity_id, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), _now(), user_id, action, entity_type, entity_id, json.dumps(details, ensure_ascii=False, sort_keys=True)),
    )


def _require_school(conn: sqlite3.Connection, school_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM schools WHERE id=? AND active=1", (school_id,)).fetchone()
    if not row:
        raise ValueError("SCHOOL_NOT_FOUND")
    return row


def _require_inventory_ingredient(conn: sqlite3.Connection, ingredient_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM ingredients WHERE id=? AND active=1 AND track_inventory=1",
        (ingredient_id,),
    ).fetchone()
    if not row:
        raise ValueError("INVALID_INVENTORY_INGREDIENT")
    return row


def list_ingredients() -> list[dict[str, Any]]:
    runtime.init_db()
    with runtime.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM ingredients WHERE active=1 ORDER BY name_en, code"
            ).fetchall()
        ]


def stock_balance(conn: sqlite3.Connection, school_id: str, ingredient_id: str) -> float:
    value = conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM stock_transactions WHERE school_id=? AND ingredient_id=?",
        (school_id, ingredient_id),
    ).fetchone()[0]
    return float(value or 0)


def create_opening_balance(data: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    school_id = str(data.get("school_id") or "").strip()
    ingredient_id = str(data.get("ingredient_id") or "").strip()
    quantity = float(data.get("quantity") or 0)
    if not school_id or not ingredient_id or quantity <= 0:
        raise ValueError("OPENING_BALANCE_FIELDS_REQUIRED")
    opening_date = _parse_date(data.get("opening_date"), "OPENING_BALANCE_DATE_INVALID")

    runtime.init_db()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        ing = _require_inventory_ingredient(conn, ingredient_id)
        existing = conn.execute(
            "SELECT COUNT(*) FROM stock_transactions WHERE school_id=? AND ingredient_id=?",
            (school_id, ingredient_id),
        ).fetchone()[0]
        if existing:
            raise ValueError("OPENING_BALANCE_ALREADY_HAS_TRANSACTIONS")
        tx_id = str(uuid.uuid4())
        reference_id = f"{school_id}:{ingredient_id}"
        now = _now()
        conn.execute(
            """
            INSERT INTO stock_transactions
              (id, school_id, ingredient_id, transaction_date, transaction_type, quantity,
               reference_type, reference_id, reference_no, remarks, entered_by_user_id,
               entered_by_username, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'OPENING', ?, 'OPENING_BALANCE', ?, 'OPENING', ?, ?, ?, ?, ?)
            """,
            (
                tx_id, school_id, ingredient_id, opening_date, quantity, reference_id,
                str(data.get("remarks") or "").strip() or None,
                user.get("id"), user.get("username") or "unknown", now, now,
            ),
        )
        _audit(conn, user.get("id"), "CREATE", "OPENING_BALANCE", tx_id, {"school_id": school_id, "ingredient_id": ingredient_id, "quantity": quantity})
        return {"ok": True, "id": tx_id, "quantity": quantity, "unit": ing["base_unit"]}


def list_balances(school_id: str) -> list[dict[str, Any]]:
    runtime.init_db()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        rows = conn.execute(
            """
            SELECT i.id AS ingredient_id, i.code, i.name_en, i.name_mr, i.base_unit AS unit,
                   i.reorder_level,
                   COALESCE(SUM(t.quantity), 0) AS balance
            FROM ingredients i
            LEFT JOIN stock_transactions t
              ON t.ingredient_id=i.id AND t.school_id=?
            WHERE i.active=1 AND i.track_inventory=1
            GROUP BY i.id, i.code, i.name_en, i.name_mr, i.base_unit, i.reorder_level
            ORDER BY i.name_en, i.code
            """,
            (school_id,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            balance = float(row["balance"] or 0)
            reorder = float(row["reorder_level"] or 0)
            result.append({
                "ingredient_id": row["ingredient_id"],
                "code": row["code"],
                "name_en": row["name_en"],
                "name_mr": row["name_mr"],
                "unit": row["unit"],
                "balance": balance,
                "reorder_level": reorder,
                "low_stock": balance <= reorder if reorder > 0 else False,
            })
        return result


def list_ledger(school_id: str, ingredient_id: str | None = None, from_date: str | None = None, to_date: str | None = None) -> list[dict[str, Any]]:
    runtime.init_db()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        where = ["t.school_id=?"]
        params: list[Any] = [school_id]
        if ingredient_id:
            where.append("t.ingredient_id=?")
            params.append(ingredient_id)
        if from_date:
            where.append("t.transaction_date>=?")
            params.append(_parse_date(from_date, "STOCK_FROM_DATE_INVALID"))
        if to_date:
            where.append("t.transaction_date<=?")
            params.append(_parse_date(to_date, "STOCK_TO_DATE_INVALID"))
        rows = conn.execute(
            f"""
            SELECT t.*, i.code AS ingredient_code, i.name_en AS ingredient_name_en,
                   i.name_mr AS ingredient_name_mr, i.base_unit AS unit
            FROM stock_transactions t
            JOIN ingredients i ON i.id=t.ingredient_id
            WHERE {' AND '.join(where)}
            ORDER BY t.transaction_date DESC, t.created_at DESC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def list_receipts(school_id: str) -> list[dict[str, Any]]:
    runtime.init_db()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        headers = conn.execute(
            "SELECT * FROM stock_receipts WHERE school_id=? ORDER BY receipt_date DESC, created_at DESC",
            (school_id,),
        ).fetchall()
        result = []
        for header in headers:
            lines = conn.execute(
                """
                SELECT l.ingredient_id, i.name_en AS ingredient_name_en, i.name_mr AS ingredient_name_mr,
                       i.base_unit AS unit, l.quantity, l.unit_cost
                FROM stock_receipt_lines l
                JOIN ingredients i ON i.id=l.ingredient_id
                WHERE l.receipt_id=? ORDER BY i.name_en, i.code
                """,
                (header["id"],),
            ).fetchall()
            item = dict(header)
            item["lines"] = [dict(line) for line in lines]
            result.append(item)
        return result


def create_receipt(data: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    school_id = str(data.get("school_id") or "").strip()
    receipt_no = str(data.get("receipt_no") or "").strip()
    receipt_date = _parse_date(data.get("receipt_date"), "RECEIPT_DATE_INVALID")
    lines = data.get("lines")
    if not school_id or not receipt_no or not isinstance(lines, list) or not lines:
        raise ValueError("RECEIPT_FIELDS_REQUIRED")
    ingredient_ids = [str(line.get("ingredient_id") or "").strip() for line in lines if isinstance(line, dict)]
    if len(ingredient_ids) != len(lines) or len(set(ingredient_ids)) != len(ingredient_ids):
        raise ValueError("RECEIPT_DUPLICATE_INGREDIENT")

    runtime.init_db()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        if conn.execute("SELECT id FROM stock_receipts WHERE school_id=? AND receipt_no=?", (school_id, receipt_no)).fetchone():
            raise ValueError("RECEIPT_NUMBER_ALREADY_EXISTS")
        validated: list[tuple[sqlite3.Row, float, float | None]] = []
        for line in lines:
            ingredient_id = str(line.get("ingredient_id") or "").strip()
            ing = _require_inventory_ingredient(conn, ingredient_id)
            quantity = float(line.get("quantity") or 0)
            if quantity <= 0:
                raise ValueError("RECEIPT_QUANTITY_INVALID")
            unit_cost = line.get("unit_cost")
            unit_cost_value = None if unit_cost in (None, "") else float(unit_cost)
            if unit_cost_value is not None and unit_cost_value < 0:
                raise ValueError("RECEIPT_UNIT_COST_INVALID")
            validated.append((ing, quantity, unit_cost_value))

        receipt_id = str(uuid.uuid4())
        now = _now()
        conn.execute(
            """
            INSERT INTO stock_receipts
              (id, school_id, receipt_date, receipt_no, source_name, remarks, entered_by_user_id,
               entered_by_username, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt_id, school_id, receipt_date, receipt_no,
                str(data.get("source_name") or "").strip() or None,
                str(data.get("remarks") or "").strip() or None,
                user.get("id"), user.get("username") or "unknown", now, now,
            ),
        )
        for ing, quantity, unit_cost in validated:
            line_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO stock_receipt_lines
                  (id, receipt_id, ingredient_id, quantity, unit_cost, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (line_id, receipt_id, ing["id"], quantity, unit_cost, now, now),
            )
            tx_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO stock_transactions
                  (id, school_id, ingredient_id, transaction_date, transaction_type, quantity,
                   reference_type, reference_id, reference_no, remarks, entered_by_user_id,
                   entered_by_username, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'RECEIPT', ?, 'STOCK_RECEIPT', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tx_id, school_id, ing["id"], receipt_date, quantity, receipt_id, receipt_no,
                    str(data.get("remarks") or data.get("source_name") or "").strip() or None,
                    user.get("id"), user.get("username") or "unknown", now, now,
                ),
            )
        _audit(conn, user.get("id"), "CREATE", "STOCK_RECEIPT", receipt_id, {"school_id": school_id, "receipt_no": receipt_no, "lines": len(validated)})
        return {"ok": True, "id": receipt_id, "receipt_no": receipt_no, "lines": len(validated)}


def create_adjustment(data: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    school_id = str(data.get("school_id") or "").strip()
    ingredient_id = str(data.get("ingredient_id") or "").strip()
    adjustment_no = str(data.get("adjustment_no") or "").strip()
    quantity = float(data.get("quantity") or 0)
    reason_code = str(data.get("reason_code") or "").strip().upper()
    if not school_id or not ingredient_id or not adjustment_no or not reason_code or quantity == 0:
        raise ValueError("ADJUSTMENT_FIELDS_REQUIRED")
    adjustment_date = _parse_date(data.get("adjustment_date"), "ADJUSTMENT_DATE_INVALID")

    runtime.init_db()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        _require_inventory_ingredient(conn, ingredient_id)
        if conn.execute("SELECT id FROM stock_adjustments WHERE school_id=? AND adjustment_no=?", (school_id, adjustment_no)).fetchone():
            raise ValueError("ADJUSTMENT_NUMBER_ALREADY_EXISTS")
        available = stock_balance(conn, school_id, ingredient_id)
        if quantity < 0 and available + quantity < -1e-9:
            raise ValueError("ADJUSTMENT_WOULD_CREATE_NEGATIVE_STOCK")

        row_id = str(uuid.uuid4())
        now = _now()
        remarks = str(data.get("remarks") or "").strip() or None
        conn.execute(
            """
            INSERT INTO stock_adjustments
              (id, school_id, adjustment_date, adjustment_no, ingredient_id, quantity, reason_code,
               remarks, entered_by_user_id, entered_by_username, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (row_id, school_id, adjustment_date, adjustment_no, ingredient_id, quantity, reason_code, remarks, user.get("id"), user.get("username") or "unknown", now, now),
        )
        tx_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO stock_transactions
              (id, school_id, ingredient_id, transaction_date, transaction_type, quantity,
               reference_type, reference_id, reference_no, remarks, entered_by_user_id,
               entered_by_username, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'ADJUSTMENT', ?, 'STOCK_ADJUSTMENT', ?, ?, ?, ?, ?, ?, ?)
            """,
            (tx_id, school_id, ingredient_id, adjustment_date, quantity, row_id, adjustment_no, f"{reason_code}: {remarks or ''}".strip(), user.get("id"), user.get("username") or "unknown", now, now),
        )
        _audit(conn, user.get("id"), "CREATE", "STOCK_ADJUSTMENT", row_id, {"school_id": school_id, "ingredient_id": ingredient_id, "quantity": quantity, "reason_code": reason_code})
        return {"ok": True, "id": row_id, "adjustment_no": adjustment_no, "quantity": quantity, "balance_after": stock_balance(conn, school_id, ingredient_id)}


def list_adjustments(school_id: str) -> list[dict[str, Any]]:
    runtime.init_db()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        rows = conn.execute(
            """
            SELECT a.*, i.name_en AS ingredient_name_en, i.name_mr AS ingredient_name_mr,
                   i.base_unit AS unit
            FROM stock_adjustments a
            JOIN ingredients i ON i.id=a.ingredient_id
            WHERE a.school_id=?
            ORDER BY a.adjustment_date DESC, a.created_at DESC
            """,
            (school_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def create_physical_verification(data: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    school_id = str(data.get("school_id") or "").strip()
    verification_no = str(data.get("verification_no") or "").strip()
    lines = data.get("lines")
    if not school_id or not verification_no or not isinstance(lines, list) or not lines:
        raise ValueError("PHYSICAL_VERIFICATION_FIELDS_REQUIRED")
    verification_date = _parse_date(data.get("verification_date"), "PHYSICAL_VERIFICATION_DATE_INVALID")
    ingredient_ids = [str(line.get("ingredient_id") or "").strip() for line in lines if isinstance(line, dict)]
    if len(ingredient_ids) != len(lines) or len(set(ingredient_ids)) != len(ingredient_ids):
        raise ValueError("PHYSICAL_VERIFICATION_DUPLICATE_INGREDIENT")

    runtime.init_db()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        if conn.execute("SELECT id FROM physical_stock_verifications WHERE school_id=? AND verification_no=?", (school_id, verification_no)).fetchone():
            raise ValueError("PHYSICAL_VERIFICATION_NUMBER_ALREADY_EXISTS")
        validated: list[tuple[sqlite3.Row, float, float, float]] = []
        for line in lines:
            ing = _require_inventory_ingredient(conn, str(line.get("ingredient_id") or "").strip())
            physical = float(line.get("physical_quantity") or 0)
            if physical < 0:
                raise ValueError("PHYSICAL_QUANTITY_INVALID")
            system = stock_balance(conn, school_id, ing["id"])
            variance = physical - system
            validated.append((ing, system, physical, variance))

        header_id = str(uuid.uuid4())
        now = _now()
        remarks = str(data.get("remarks") or "").strip() or None
        conn.execute(
            """
            INSERT INTO physical_stock_verifications
              (id, school_id, verification_date, verification_no, remarks, entered_by_user_id,
               entered_by_username, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (header_id, school_id, verification_date, verification_no, remarks, user.get("id"), user.get("username") or "unknown", now, now),
        )
        variance_count = 0
        for ing, system, physical, variance in validated:
            line_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO physical_stock_verification_lines
                  (id, verification_id, ingredient_id, system_quantity, physical_quantity,
                   variance_quantity, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (line_id, header_id, ing["id"], system, physical, variance, now, now),
            )
            if abs(variance) > 1e-9:
                variance_count += 1
                tx_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO stock_transactions
                      (id, school_id, ingredient_id, transaction_date, transaction_type, quantity,
                       reference_type, reference_id, reference_no, remarks, entered_by_user_id,
                       entered_by_username, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'PHYSICAL_ADJUSTMENT', ?, 'PHYSICAL_STOCK', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (tx_id, school_id, ing["id"], verification_date, variance, header_id, verification_no, remarks or "Physical stock verification variance", user.get("id"), user.get("username") or "unknown", now, now),
                )
        _audit(conn, user.get("id"), "CREATE", "PHYSICAL_STOCK_VERIFICATION", header_id, {"school_id": school_id, "verification_no": verification_no, "variance_lines": variance_count})
        return {"ok": True, "id": header_id, "verification_no": verification_no, "variance_lines": variance_count}


def list_physical_verifications(school_id: str) -> list[dict[str, Any]]:
    runtime.init_db()
    with runtime.connect() as conn:
        _require_school(conn, school_id)
        headers = conn.execute(
            "SELECT * FROM physical_stock_verifications WHERE school_id=? ORDER BY verification_date DESC, created_at DESC",
            (school_id,),
        ).fetchall()
        result = []
        for header in headers:
            lines = conn.execute(
                """
                SELECT l.ingredient_id, i.name_en AS ingredient_name_en, i.name_mr AS ingredient_name_mr,
                       i.base_unit AS unit, l.system_quantity, l.physical_quantity, l.variance_quantity
                FROM physical_stock_verification_lines l
                JOIN ingredients i ON i.id=l.ingredient_id
                WHERE l.verification_id=? ORDER BY i.name_en, i.code
                """,
                (header["id"],),
            ).fetchall()
            item = dict(header)
            item["lines"] = [dict(line) for line in lines]
            result.append(item)
        return result
