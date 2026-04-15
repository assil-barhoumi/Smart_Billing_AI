import os
import sys
import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.db import get_connection

router = APIRouter(prefix="/chat", tags=["chat"])

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "meta-llama/llama-4-scout-17b-16e-instruct"

DB_SCHEMA = """
Tables:
- invoices (id, file_path, source, sender, subject, received_at, status, extracted_json,
            confidence_score, supplier_name, invoice_number, invoice_date, due_date,
            total_ht, vat_amount, total_ttc, currency, payment_status, validated_at,
            odoo_invoice_id, error_message)
- suppliers (id, name, street, country, email, odoo_partner_id, first_seen, last_seen, invoice_count)

Status values:
- invoices.status: 'pending', 'extracted', 'validated', 'rejected'
- invoices.payment_status: 'unpaid', 'paid', 'partial'
"""

SQL_PROMPT = """You are a PostgreSQL expert. Convert the user question to a valid SQL query.

Schema:
{schema}

Rules:
- Return ONLY the SQL query, no explanation, no markdown
- Only SELECT queries are allowed
- Use ILIKE for name comparisons
- Use NOW() for current date/time
- Always filter out NULL amounts: add WHERE total_ttc IS NOT NULL when querying amounts
- When asked for a specific invoice (most expensive, latest...), return supplier_name, invoice_number, total_ttc, currency — not just the aggregate value
- Return null if the question cannot be answered with the available schema

Question: {question}"""

ANSWER_PROMPT = """You are a helpful business assistant. Answer the user's question based on the query results.

Question: {question}
SQL Result: {result}

Rules:
- Answer in the same language as the question (French, English, or Arabic)
- Be concise — one or two sentences maximum
- No reasoning, no explanation — just the answer
- Format numbers with currency when available
- If result is empty, say no data was found"""


def _is_safe_sql(sql: str) -> bool:
    """Only allow SELECT queries."""
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        return False
    forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "CREATE"]
    return not any(word in sql_upper for word in forbidden)


def _call_groq(prompt: str) -> str:
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=512,
    )
    return response.choices[0].message.content.strip()


def _run_sql(sql: str) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            if cur.description is None:
                return []
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


class ChatRequest(BaseModel):
    question: str


@router.post("/")
def chat(body: ChatRequest):
    """Answer a natural language question about invoices and suppliers."""
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    sql_prompt = SQL_PROMPT.format(schema=DB_SCHEMA, question=question)
    sql = _call_groq(sql_prompt)
    sql = re.sub(r"```sql|```", "", sql).strip()

    if not _is_safe_sql(sql):
        raise HTTPException(status_code=400, detail="Sorry, I can only answer questions about your data.")

    try:
        rows = _run_sql(sql)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

    answer_prompt = ANSWER_PROMPT.format(
        question=question,
        result=json.dumps(rows, ensure_ascii=False, default=str)
    )
    answer = _call_groq(answer_prompt)

    return {
        "question": question,
        "answer":   answer,
        "sql":      sql,
        "rows":     rows,
    }
