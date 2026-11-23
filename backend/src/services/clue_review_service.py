from src.constants.enums import CLUE_REVIEW_CLAIM_STATUSES, CLUE_REVIEW_OPEN_STATUSES
from src.utils.audit import record_in_transaction
from src.utils.db import get_conn


class MissingClue(LookupError):
    pass


def list_clue_reviews(claim_id=None):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT r.id AS clue_id, r.claim_id, c.claim_no, c.status AS claim_status,
                   r.clue_type, r.severity, r.description, r.evidence, r.status AS clue_status,
                   v.status AS review_status, v.evidence_source, v.evidence_reference, v.finding,
                   v.recommendation, v.revision, v.submitted_by, v.submitted_at, v.review_note,
                   v.reviewed_at, investigator.display_name AS submitter, manager.display_name AS reviewer
            FROM risk_clues r JOIN claims c ON c.id = r.claim_id
            LEFT JOIN clue_reviews v ON v.clue_id = r.id
            LEFT JOIN users investigator ON investigator.id = v.submitted_by
            LEFT JOIN users manager ON manager.id = v.reviewed_by
            WHERE (%(claim)s::integer IS NULL OR r.claim_id = %(claim)s)
            ORDER BY CASE v.status WHEN 'pending' THEN 0 WHEN 'returned' THEN 1 ELSE 2 END,
                     CASE r.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                     r.id DESC
            """,
            {"claim": claim_id},
        ).fetchall()


def get_review_for_update(conn, clue_id):
    # Share the claim lock with adjudication and take it before any clue/review writes.
    clue = conn.execute(
        """
        SELECT r.claim_id, r.status AS clue_status, c.status AS claim_status
        FROM risk_clues r JOIN claims c ON c.id = r.claim_id
        WHERE r.id = %s FOR UPDATE OF c, r
        """,
        (clue_id,),
    ).fetchone()
    if clue is None:
        raise MissingClue("风险线索不存在")
    if clue["claim_status"] not in CLUE_REVIEW_CLAIM_STATUSES or clue["clue_status"] != "open":
        raise PermissionError("仅调查中或待核赔案件的待核查线索可以进行证据复核")
    review = conn.execute("SELECT * FROM clue_reviews WHERE clue_id = %s", (clue_id,)).fetchone()
    return clue, review


def submit_review(clue_id, payload, user_id):
    with get_conn() as conn:
        clue, review = get_review_for_update(conn, clue_id)
        if review and review["status"] != "returned":
            raise PermissionError("证据已提交，请等待风险主管处理")
        if review and review["submitted_by"] != user_id:
            raise PermissionError("请由原提交调查员补正证据")
        if payload.expected_revision != (review["revision"] if review else 0):
            raise PermissionError("复核轮次已更新，请刷新后再提交")
        fields = payload.model_dump(exclude={"expected_revision"})
        item = conn.execute(
            """
            INSERT INTO clue_reviews (clue_id, status, evidence_source, evidence_reference,
                                      finding, recommendation, submitted_by)
            VALUES (%(clue)s, 'pending', %(evidence_source)s, %(evidence_reference)s,
                    %(finding)s, %(recommendation)s, %(user)s)
            ON CONFLICT (clue_id) DO UPDATE SET status = 'pending',
                evidence_source = excluded.evidence_source, evidence_reference = excluded.evidence_reference,
                finding = excluded.finding, recommendation = excluded.recommendation,
                submitted_at = now(), revision = clue_reviews.revision + 1,
                reviewed_by = NULL, reviewed_at = NULL, review_note = NULL
            RETURNING clue_id, status, revision, recommendation
            """,
            {**fields, "clue": clue_id, "user": user_id},
        ).fetchone()
        record_in_transaction(conn, user_id, "clue_review_submitted", clue["claim_id"], {
            **item, **fields,
        })
        return item


def decide_review(clue_id, payload, user_id):
    with get_conn() as conn:
        clue, review = get_review_for_update(conn, clue_id)
        if not review or review["status"] != "pending":
            raise PermissionError("只有待主管复核的证据可以处理")
        if review["revision"] != payload.expected_revision:
            raise PermissionError("复核轮次已更新，请重新查看最新证据")
        if review["submitted_by"] == user_id:
            raise PermissionError("提交人不能复核自己的证据")
        accepted = payload.action == "accept"
        item = conn.execute(
            """
            UPDATE clue_reviews SET status = %s, reviewed_by = %s, reviewed_at = now(), review_note = %s
            WHERE clue_id = %s RETURNING clue_id, status, revision, recommendation
            """,
            ("resolved" if accepted else "returned", user_id, payload.note, clue_id),
        ).fetchone()
        if accepted:
            conn.execute("UPDATE risk_clues SET status = %s WHERE id = %s", (review["recommendation"], clue_id))
        record_in_transaction(conn, user_id, "clue_review_decided", clue["claim_id"], {
            **item, "action": payload.action, "note": payload.note,
        })
        return item


def unresolved_review_count(conn, claim_id):
    return conn.execute(
        """
        SELECT count(*) AS count FROM clue_reviews v JOIN risk_clues r ON r.id = v.clue_id
        WHERE r.claim_id = %s AND v.status = ANY(%s)
        """,
        (claim_id, list(CLUE_REVIEW_OPEN_STATUSES)),
    ).fetchone()["count"]
