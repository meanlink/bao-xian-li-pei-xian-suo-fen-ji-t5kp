from datetime import date
from decimal import Decimal

from src.services.document_triage_service import business_date
from src.utils.audit import record_in_transaction
from src.utils.db import get_conn

# Serializes freeze transactions so a settlement record can never be swept
# into two reports at once. Adjudication itself never takes this lock, so
# closing claims keeps working while a report is being frozen.
FREEZE_LOCK_KEY = 1045004


def first_of_month(day):
    return day.replace(day=1)


def insert_settlement_record(conn, claim, settled_on, user_id):
    return conn.execute(
        """INSERT INTO settlement_records(claim_id, settled_on, loss_amount, recorded_by)
           VALUES (%s,%s,%s,%s) RETURNING *""",
        (claim["id"], settled_on, claim["loss_amount"], user_id),
    ).fetchone()


def backfill_settlement_record(claim_id, settled_on, user_id):
    with get_conn() as conn:
        claim = conn.execute("SELECT * FROM claims WHERE id=%s FOR UPDATE", (claim_id,)).fetchone()
        if not claim:
            raise LookupError("案件不存在")
        if claim["status"] != "closed":
            raise PermissionError("仅已结案的案件可以补登核赔记录")
        if settled_on > business_date(conn):
            raise ValueError("核赔日不能晚于当前工作日")
        if conn.execute("SELECT id FROM settlement_records WHERE claim_id=%s", (claim_id,)).fetchone():
            raise PermissionError("案件已存在核赔记录，不能重复补登")
        row = insert_settlement_record(conn, claim, settled_on, user_id)
        record_in_transaction(conn, user_id, "settlement_record_backfilled", claim_id, {
            "settled_on": settled_on.isoformat(), "loss_amount": str(claim["loss_amount"]),
        })
    return row


def carry_candidates(conn, month):
    # Late records: their own month is already frozen, so they can never enter
    # their own report. The first report frozen afterwards picks them up as
    # carry entries while keeping their original attribution month.
    return conn.execute(
        """SELECT s.id, s.claim_id, s.loss_amount, s.settled_on,
                  date_trunc('month', s.settled_on)::date AS attribution_month
           FROM settlement_records s
           WHERE s.settled_on < %s
             AND NOT EXISTS (SELECT 1 FROM monthly_report_entries e WHERE e.settlement_record_id = s.id)
             AND EXISTS (SELECT 1 FROM monthly_reports r
                         WHERE r.report_month = date_trunc('month', s.settled_on)::date)
           ORDER BY s.id""",
        (month,),
    ).fetchall()


def month_candidates(conn, month):
    return conn.execute(
        """SELECT s.id, s.claim_id, s.loss_amount, s.settled_on
           FROM settlement_records s
           WHERE s.settled_on >= %s AND s.settled_on < %s::date + interval '1 month'
             AND NOT EXISTS (SELECT 1 FROM monthly_report_entries e WHERE e.settlement_record_id = s.id)
           ORDER BY s.id""",
        (month, month),
    ).fetchall()


def missing_settlement_claims(conn):
    return conn.execute(
        """SELECT c.id, c.claim_no, c.customer_name, c.loss_amount, c.updated_at
           FROM claims c
           WHERE c.status = 'closed'
             AND NOT EXISTS (SELECT 1 FROM settlement_records s WHERE s.claim_id = c.id)
           ORDER BY c.updated_at DESC, c.id DESC""",
    ).fetchall()


def list_monthly_reports():
    with get_conn() as conn:
        today = business_date(conn)
        rows = conn.execute(
            """WITH months AS (
                   SELECT date_trunc('month', settled_on)::date AS month FROM settlement_records
                   UNION SELECT report_month FROM monthly_reports
                   UNION SELECT date_trunc('month', %s::date)::date
               )
               SELECT m.month, r.id AS report_id, r.closed_count, r.loss_total,
                      r.carry_count, r.carry_total, r.frozen_at, u.display_name AS frozen_by_name,
                      (SELECT count(*) FROM settlement_records s
                        WHERE s.settled_on >= m.month AND s.settled_on < m.month + interval '1 month') AS live_count,
                      (SELECT COALESCE(sum(s.loss_amount), 0) FROM settlement_records s
                        WHERE s.settled_on >= m.month AND s.settled_on < m.month + interval '1 month') AS live_total
               FROM months m
               LEFT JOIN monthly_reports r ON r.report_month = m.month
               LEFT JOIN users u ON u.id = r.frozen_by
               ORDER BY m.month DESC""",
            (today,),
        ).fetchall()
        items = []
        for row in rows:
            frozen = row["report_id"] is not None
            item = {
                "month": row["month"],
                "status": "frozen" if frozen else "open",
                "closed_count": row["closed_count"] if frozen else row["live_count"],
                "loss_total": float(row["loss_total"] if frozen else row["live_total"]),
                "frozen_by": row["frozen_by_name"],
                "frozen_at": row["frozen_at"],
            }
            if frozen:
                item["carry_count"] = row["carry_count"]
                item["carry_total"] = float(row["carry_total"])
            else:
                carry = carry_candidates(conn, row["month"])
                item["carry_count"] = len(carry)
                item["carry_total"] = float(sum((r["loss_amount"] for r in carry), Decimal("0")))
            items.append(item)
        pending_rows = missing_settlement_claims(conn)
        late = late_carry_items(conn)
    return {
        "business_month": first_of_month(today),
        "items": items,
        "missing_records": {
            "count": len(pending_rows),
            "loss_total": float(sum((r["loss_amount"] for r in pending_rows), Decimal("0"))),
            "items": [dict(r) for r in pending_rows],
        },
        "pending_carry": late,
    }


def late_carry_items(conn):
    rows = conn.execute(
        """SELECT s.id, s.claim_id, s.loss_amount, s.settled_on,
                  date_trunc('month', s.settled_on)::date AS attribution_month,
                  c.claim_no, c.customer_name
           FROM settlement_records s JOIN claims c ON c.id = s.claim_id
           WHERE NOT EXISTS (SELECT 1 FROM monthly_report_entries e WHERE e.settlement_record_id = s.id)
             AND EXISTS (SELECT 1 FROM monthly_reports r
                         WHERE r.report_month = date_trunc('month', s.settled_on)::date)
           ORDER BY s.settled_on, s.id""",
    ).fetchall()
    return {
        "count": len(rows),
        "loss_total": float(sum((r["loss_amount"] for r in rows), Decimal("0"))),
        "items": [dict(r, loss_amount=float(r["loss_amount"])) for r in rows],
    }


def get_monthly_report(month):
    with get_conn() as conn:
        report = conn.execute(
            """SELECT r.*, u.display_name AS frozen_by_name
               FROM monthly_reports r LEFT JOIN users u ON u.id = r.frozen_by
               WHERE r.report_month = %s""",
            (month,),
        ).fetchone()
        if report:
            entries = conn.execute(
                """SELECT e.id, e.entry_kind, e.attribution_month, e.loss_amount, e.claim_id,
                          c.claim_no, c.customer_name, s.settled_on
                   FROM monthly_report_entries e
                   JOIN claims c ON c.id = e.claim_id
                   JOIN settlement_records s ON s.id = e.settlement_record_id
                   WHERE e.report_id = %s
                   ORDER BY CASE e.entry_kind WHEN 'current' THEN 0 ELSE 1 END, e.id""",
                (report["id"],),
            ).fetchall()
            return {
                "month": report["report_month"],
                "status": "frozen",
                "closed_count": report["closed_count"],
                "loss_total": float(report["loss_total"]),
                "carry_count": report["carry_count"],
                "carry_total": float(report["carry_total"]),
                "frozen_by": report["frozen_by_name"],
                "frozen_at": report["frozen_at"],
                "entries": [dict(e, loss_amount=float(e["loss_amount"])) for e in entries],
            }
        current = conn.execute(
            """SELECT s.id, s.claim_id, s.loss_amount, s.settled_on, c.claim_no, c.customer_name
               FROM settlement_records s JOIN claims c ON c.id = s.claim_id
               WHERE s.settled_on >= %s AND s.settled_on < %s::date + interval '1 month'
               ORDER BY s.settled_on, s.id""",
            (month, month),
        ).fetchall()
        carry = conn.execute(
            """SELECT s.id, s.claim_id, s.loss_amount, s.settled_on, c.claim_no, c.customer_name,
                      date_trunc('month', s.settled_on)::date AS attribution_month
               FROM settlement_records s JOIN claims c ON c.id = s.claim_id
               WHERE s.settled_on < %s
                 AND NOT EXISTS (SELECT 1 FROM monthly_report_entries e WHERE e.settlement_record_id = s.id)
                 AND EXISTS (SELECT 1 FROM monthly_reports r
                             WHERE r.report_month = date_trunc('month', s.settled_on)::date)
               ORDER BY s.settled_on, s.id""",
            (month,),
        ).fetchall()
    entries = [
        dict(e, entry_kind="current", attribution_month=month, loss_amount=float(e["loss_amount"]))
        for e in current
    ] + [
        dict(e, entry_kind="carry", loss_amount=float(e["loss_amount"]))
        for e in carry
    ]
    return {
        "month": month,
        "status": "open",
        "closed_count": len(current),
        "loss_total": float(sum((e["loss_amount"] for e in current), Decimal("0"))),
        "carry_count": len(carry),
        "carry_total": float(sum((e["loss_amount"] for e in carry), Decimal("0"))),
        "frozen_by": None,
        "frozen_at": None,
        "entries": entries,
    }


def freeze_monthly_report(month, user_id):
    with get_conn() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (FREEZE_LOCK_KEY,))
        if month > first_of_month(business_date(conn)):
            raise ValueError("不能冻结未来月份")
        if conn.execute("SELECT id FROM monthly_reports WHERE report_month=%s", (month,)).fetchone():
            raise PermissionError("该月月报已冻结，不能重复冻结")
        current = month_candidates(conn, month)
        carry = carry_candidates(conn, month)
        loss_total = sum((r["loss_amount"] for r in current), Decimal("0"))
        carry_total = sum((r["loss_amount"] for r in carry), Decimal("0"))
        report = conn.execute(
            """INSERT INTO monthly_reports(report_month, closed_count, loss_total, carry_count, carry_total, frozen_by)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
            (month, len(current), loss_total, len(carry), carry_total, user_id),
        ).fetchone()
        for record in current:
            conn.execute(
                """INSERT INTO monthly_report_entries(report_id, settlement_record_id, claim_id, entry_kind, attribution_month, loss_amount)
                   VALUES (%s,%s,%s,'current',%s,%s)""",
                (report["id"], record["id"], record["claim_id"], month, record["loss_amount"]),
            )
        for record in carry:
            conn.execute(
                """INSERT INTO monthly_report_entries(report_id, settlement_record_id, claim_id, entry_kind, attribution_month, loss_amount)
                   VALUES (%s,%s,%s,'carry',%s,%s)""",
                (report["id"], record["id"], record["claim_id"], record["attribution_month"], record["loss_amount"]),
            )
        record_in_transaction(conn, user_id, "monthly_report_frozen", None, {
            "month": month.isoformat(),
            "closed_count": len(current), "loss_total": str(loss_total),
            "carry_count": len(carry), "carry_total": str(carry_total),
        })
    return get_monthly_report(month)
