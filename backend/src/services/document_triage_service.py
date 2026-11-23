from src.utils.audit import record_in_transaction
from src.utils.db import get_conn

INTAKE_STATES = ("intake", "initial_review")
TRIAGE_ROLES = ("intake_agent", "risk_manager")
BUCKETS = ("overdue", "due_today", "unscheduled", "scheduled")


def missing_documents(claim, received=None):
    if received is None:
        received = claim["received_documents"]
    return sorted(set(claim["required_documents"]) - set(received))


def business_date(conn):
    return conn.execute("SELECT (now() AT TIME ZONE 'Asia/Shanghai')::date AS today").fetchone()["today"]


def list_document_triage():
    with get_conn() as conn:
        today = business_date(conn)
        claims = conn.execute(
            """SELECT c.id, c.claim_no, c.customer_name, c.claimant_phone, c.loss_amount,
                      c.required_documents, c.received_documents,
                      to_jsonb(f) AS followup, actor.display_name AS recorded_by_name
               FROM claims c
               LEFT JOIN document_followups f ON f.claim_id=c.id AND f.completed_at IS NULL
               LEFT JOIN users actor ON actor.id=f.recorded_by
               WHERE c.status = ANY(%s)""",
            (list(INTAKE_STATES),),
        ).fetchall()

    today_iso = today.isoformat()
    counts = dict.fromkeys(BUCKETS, 0)
    items = []
    for claim in claims:
        missing = missing_documents(claim)
        if not missing:
            continue
        followup = claim["followup"]
        due = followup["due_on"] if followup else None
        if due is None:
            bucket = "unscheduled"
        elif due < today_iso:
            bucket = "overdue"
        elif due == today_iso:
            bucket = "due_today"
        else:
            bucket = "scheduled"
        counts[bucket] += 1
        items.append({
            "claim_id": claim["id"],
            "claim_no": claim["claim_no"],
            "customer_name": claim["customer_name"],
            "claimant_phone": claim["claimant_phone"],
            "loss_amount": claim["loss_amount"],
            "missing_documents": missing,
            "bucket": bucket,
            "followup": followup,
            "recorded_by_name": claim["recorded_by_name"],
        })
    items.sort(key=lambda item: (
        BUCKETS.index(item["bucket"]),
        item["followup"]["due_on"] if item["followup"] else "",
        -item["loss_amount"],
        item["claim_id"],
    ))
    return {"business_date": today, "counts": counts, "items": items}


def latest_followup(conn, claim_id):
    return conn.execute(
        """SELECT f.*, recorder.display_name AS recorded_by_name,
                  verifier.display_name AS completed_by_name
           FROM document_followups f
           JOIN users recorder ON recorder.id=f.recorded_by
           LEFT JOIN users verifier ON verifier.id=f.completed_by
           WHERE f.claim_id=%s ORDER BY f.id DESC LIMIT 1""",
        (claim_id,),
    ).fetchone()


def log_followup(claim_id, payload, user_id):
    with get_conn() as conn:
        # Verification takes the same claim lock before changing the document checklist.
        claim = conn.execute("SELECT * FROM claims WHERE id=%s FOR UPDATE", (claim_id,)).fetchone()
        if not claim:
            raise LookupError("案件不存在")
        missing = missing_documents(claim)
        if claim["status"] not in INTAKE_STATES or not missing:
            raise PermissionError("仅受理或初审阶段且仍有缺项的案件可以登记补件联系")
        if set(payload.expected_missing_documents) != set(missing):
            raise PermissionError("缺项清单已更新，请刷新队列后重试")
        if payload.contacted_on > business_date(conn):
            raise ValueError("联系日期不能晚于当前工作日")

        current = conn.execute(
            "SELECT id, revision, contacted_on FROM document_followups WHERE claim_id=%s AND completed_at IS NULL",
            (claim_id,),
        ).fetchone()
        version = (current["id"], current["revision"]) if current else (None, 0)
        if (payload.followup_id, payload.expected_revision) != version:
            raise PermissionError("补件记录已更新，请刷新队列后重试")
        if current and payload.contacted_on < current["contacted_on"]:
            raise ValueError("再次联系日期不能早于上次联系日期")

        values = (payload.channel, payload.contacted_on, payload.due_on, payload.contact_note, missing, user_id)
        if current:
            row = conn.execute(
                """UPDATE document_followups SET revision=revision+1, channel=%s, contacted_on=%s,
                          due_on=%s, contact_note=%s, requested_documents=%s, recorded_by=%s, recorded_at=now()
                   WHERE id=%s RETURNING *""",
                (*values, current["id"]),
            ).fetchone()
        else:
            row = conn.execute(
                """INSERT INTO document_followups
                       (channel, contacted_on, due_on, contact_note, requested_documents, recorded_by, claim_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (*values, claim_id),
            ).fetchone()
        record_in_transaction(conn, user_id, "document_followup_recorded", claim_id, {
            "followup_id": row["id"], "revision": row["revision"], "channel": row["channel"],
            "contacted_on": row["contacted_on"].isoformat(), "due_on": row["due_on"].isoformat(),
            "requested_documents": missing, "contact_note": row["contact_note"],
        })
    return row


def complete_followup(conn, claim_id, user_id):
    followup = conn.execute(
        """UPDATE document_followups SET completed_at=now(), completed_by=%s
           WHERE claim_id=%s AND completed_at IS NULL RETURNING id, revision""",
        (user_id, claim_id),
    ).fetchone()
    if followup:
        record_in_transaction(conn, user_id, "document_followup_completed", claim_id, {
            "followup_id": followup["id"], "revision": followup["revision"],
        })
