"""RAG 知识库：SQLite 存储商品/售后 FAQ，字符 bigram BM25 检索，零依赖。

检索结果注入 Tech/Default Agent 的 system 消息，让机器人回答产品参数、保修、
退换货等 FAQ 时有据可依，而非凭空编造。
"""
import math
import os
import re
import sqlite3
from datetime import datetime

from loguru import logger


def _bigrams(text):
    """字符 bigram 切分（对中文/英文/数字均有效，无需分词库）。"""
    t = re.sub(r"\s+", "", text or "").lower()
    return [t[i:i + 2] for i in range(len(t) - 1)]


class KnowledgeBase:
    def __init__(self, db_path="data/knowledge.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                keywords TEXT,
                category TEXT,
                enabled INTEGER DEFAULT 1,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
        conn.close()
        logger.debug(f"知识库数据库初始化完成: {self.db_path}")

    # ---------- CRUD ----------
    def add(self, question, answer, keywords="", category=""):
        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO entries (question, answer, keywords, category, updated_at) VALUES (?, ?, ?, ?, ?)",
                (question, answer, keywords, category, datetime.now().isoformat()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def update(self, entry_id, question=None, answer=None, keywords=None, category=None, enabled=None):
        conn = self._connect()
        cur = conn.cursor()
        try:
            fields = []
            values = []
            for key, val in (
                ("question", question), ("answer", answer), ("keywords", keywords),
                ("category", category), ("enabled", enabled),
            ):
                if val is not None:
                    fields.append(f"{key} = ?")
                    values.append(val)
            if not fields:
                return False
            fields.append("updated_at = ?")
            values.append(datetime.now().isoformat())
            values.append(entry_id)
            cur.execute(f"UPDATE entries SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def delete(self, entry_id):
        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def list(self, category=None, limit=500):
        conn = self._connect()
        cur = conn.cursor()
        try:
            if category:
                cur.execute(
                    "SELECT id, question, answer, keywords, category, enabled, updated_at FROM entries WHERE category = ? ORDER BY id DESC LIMIT ?",
                    (category, limit),
                )
            else:
                cur.execute(
                    "SELECT id, question, answer, keywords, category, enabled, updated_at FROM entries ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
            return [
                {
                    "id": r[0], "question": r[1], "answer": r[2], "keywords": r[3],
                    "category": r[4], "enabled": r[5], "updated_at": r[6],
                }
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

    # ---------- 检索 ----------
    def search(self, query, top_k=3):
        """BM25 检索知识条目，返回 top_k 条（含完整字段），分数为 0 的剔除。"""
        if not query:
            return []
        entries = [e for e in self.list() if e.get("enabled", 1)]
        if not entries:
            return []

        docs = []
        for e in entries:
            # 检索字段：问题 + 关键词 + 分类（关键词权重最高，靠重复计算放大）
            text = f"{e['question']} {e['question']} {e.get('keywords', '') or ''} {e.get('category', '') or ''}"
            docs.append((e, _bigrams(text)))

        q_terms = _bigrams(query)
        if not q_terms:
            return []

        # 计算 IDF（小语料，每次实时算即可）
        n = len(docs)
        df = {}
        for _, terms in docs:
            for term in set(terms):
                df[term] = df.get(term, 0) + 1
        avgdl = sum(len(t) for _, t in docs) / max(n, 1)

        def idf(term):
            d = df.get(term, 0)
            return math.log((n - d + 0.5) / (d + 0.5) + 1.0)

        k1, b = 1.5, 0.75
        scored = []
        for entry, terms in docs:
            dl = len(terms)
            score = 0.0
            q_set = set(q_terms)
            for term in q_set:
                if term not in df:
                    continue
                tf = terms.count(term)
                if tf == 0:
                    continue
                score += idf(term) * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / max(avgdl, 1)))
            # 关键词精确命中加分：query 直接包含某条关键词时加权
            for kw in (entry.get("keywords", "") or "").replace("，", ",").split(","):
                kw = kw.strip()
                if kw and kw in query:
                    score += 2.0
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]
