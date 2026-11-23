import json
from datetime import date, timedelta
from decimal import Decimal
from src.utils.db import get_conn
from src.utils.auth import password_hash

users = [
    ("intake@claims.local", "intake_agent", "周宁"),
    ("investigator@claims.local", "investigator", "陈默"),
    ("manager@claims.local", "risk_manager", "林岚"),
]
claims = [
    ("CLM-261101-0001", "PA-2026-0018", "赵海宁", "车损", date(2026,11,1), Decimal("86000"), "都市", "13800001111", ["身份证明","事故证明","损失清单"], ["身份证明","事故证明","损失清单"], [], "complete", "initial_review", None, False),
    ("CLM-261102-0002", "PA-2026-0027", "吴晓彤", "盗抢", date(2026,11,2), Decimal("168000"), "沿海", "13800002222", ["身份证明","事故证明","损失清单"], ["身份证明","事故证明"], ["损失清单"], "missing", "intake", None, True),
    ("CLM-261103-0003", "PA-2026-0031", "孙立诚", "水灾", date(2026,11,3), Decimal("236000"), "沿海", "13800003333", ["身份证明","事故证明","损失清单"], ["身份证明","事故证明","损失清单"], [], "complete", "initial_review", None, True),
    ("CLM-261104-0004", "PA-2026-0045", "周婉清", "医疗", date(2026,11,4), Decimal("42000"), "山区", "13800004444", ["身份证明","事故证明","损失清单"], ["身份证明","事故证明","损失清单"], [], "complete", "modeled", 0.61, False),
    ("CLM-261105-0005", "PA-2026-0052", "何志远", "火灾", date(2026,11,5), Decimal("510000"), "园区", "13800005555", ["身份证明","事故证明","损失清单"], ["身份证明","事故证明","损失清单"], [], "complete", "investigating", 0.86, True),
]

with get_conn() as conn:
    conn.execute("SELECT pg_advisory_xact_lock(1045003)")
    for username, role, display in users:
        conn.execute("INSERT INTO users(username,password_hash,role,display_name) VALUES (%s,%s,%s,%s) ON CONFLICT(username) DO NOTHING", (username, password_hash("demo123"), role, display))
    settings = [("model_threshold", "0.62"), ("last_good_threshold", "0.62"), ("max_false_positive_rate", "0.25")]
    for key, value in settings:
        conn.execute("INSERT INTO settings(key,value) VALUES (%s,%s) ON CONFLICT(key) DO NOTHING", (key, value))
    for item in claims:
        claim_no, policy_no, customer, incident, incident_date, loss, region, phone, required, received, missing, doc_status, status, score, fraud = item
        query = """INSERT INTO claims(claim_no,policy_no,customer_name,incident_type,incident_date,loss_amount,region,claimant_phone,required_documents,received_documents,missing_documents,documents_status,status,model_score,model_threshold,risk_level,verified_fraud)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0.62,%s,%s)
        ON CONFLICT(claim_no) DO NOTHING RETURNING id"""
        params = (claim_no, policy_no, customer, incident, incident_date, loss, region, phone, json.dumps(required, ensure_ascii=False), json.dumps(received, ensure_ascii=False), json.dumps(missing, ensure_ascii=False), doc_status, status, score, "high" if score and score >= 0.62 else "medium" if score else None, fraud)
        row = conn.execute(query, params).fetchone()
        if row is None:
            continue
        claim_id = row["id"]
        if claim_no == "CLM-261105-0005":
            conn.execute("INSERT INTO risk_clues(claim_id,clue_type,severity,description,evidence,status,created_by) SELECT %s,'出险时间异常','high','报案时间与气象记录存在偏差','气象站 WX-261105-07，降雨峰值晚于报案时间 3 小时','open',id FROM users WHERE username='manager@claims.local' AND NOT EXISTS (SELECT 1 FROM risk_clues WHERE claim_id=%s AND clue_type='出险时间异常')", (claim_id, claim_id))
            conn.execute("INSERT INTO investigation_tasks(claim_id,assignee,priority,status,due_date,scope) SELECT %s,'陈默','urgent','assigned',%s,'核对现场照片 EXIF、维修厂报价单与气象站记录' WHERE NOT EXISTS (SELECT 1 FROM investigation_tasks WHERE claim_id=%s)", (claim_id, date.today()+timedelta(days=2), claim_id))
        if claim_no == "CLM-261104-0004":
            conn.execute("INSERT INTO risk_clues(claim_id,clue_type,severity,description,evidence,status,created_by) SELECT %s,'历史频繁出险','medium','近 12 个月同类报案 3 次','保单 PA-2026-0045 历史赔案索引','open',id FROM users WHERE username='manager@claims.local' AND NOT EXISTS (SELECT 1 FROM risk_clues WHERE claim_id=%s AND clue_type='历史频繁出险')", (claim_id, claim_id))
print('seed_demo completed idempotently')
