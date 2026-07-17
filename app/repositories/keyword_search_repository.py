from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.database.connection import open_connection
from app.database.schema import initialize_database
from app.models.document import Document, DocumentChunk


@dataclass(frozen=True)
class KeywordCandidate:
    chunk_id: str
    document_id: str
    score: float
    rank: int
    article_exact: bool = False
    matched_terms: tuple[str, ...] = ()


@dataclass
class _CandidateScore:
    chunk_id: str
    document_id: str
    score: float = 0.0
    article_exact: bool = False
    matched_terms: set[str] | None = None

    def add(self, score: float, terms: list[str] | tuple[str, ...] = (), article_exact: bool = False) -> None:
        self.score += score
        self.article_exact = self.article_exact or article_exact
        if self.matched_terms is None:
            self.matched_terms = set()
        self.matched_terms.update(terms)


class KeywordSearchRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        initialize_database(database_path)

    def index_document(self, document: Document, chunks: list[DocumentChunk]) -> int:
        with open_connection(self._database_path) as connection:
            connection.execute("DELETE FROM chunk_search_fts WHERE document_id = ?", (document.id,))
            connection.executemany(
                """
                INSERT INTO chunk_search_fts (
                    chunk_id, document_id, original_name, sheet_name, section, article, title, content
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.id,
                        chunk.document_id,
                        document.original_name,
                        chunk.sheet_name,
                        chunk.section or "",
                        chunk.article or "",
                        chunk.title or "",
                        chunk.content,
                    )
                    for chunk in chunks
                ],
            )
        return len(chunks)

    def remove_document(self, document_id: str) -> None:
        with open_connection(self._database_path) as connection:
            connection.execute("DELETE FROM chunk_search_fts WHERE document_id = ?", (document_id,))

    def search(self, query: str, document_ids: list[str] | None = None, limit: int = 20) -> list[KeywordCandidate]:
        cleaned = _clean_query(query)
        if not cleaned:
            return []

        candidates: dict[str, _CandidateScore] = {}
        with open_connection(self._database_path) as connection:
            articles = extract_article_numbers(cleaned)
            if articles:
                self._merge_article_exact(connection, candidates, articles, document_ids)

            fts_tokens = [token for token in _query_tokens(cleaned) if len(token) >= 3]
            if cleaned:
                self._merge_fts(connection, candidates, _quote_fts(cleaned), 38.0, document_ids, ("phrase",))
            if fts_tokens:
                self._merge_fts(connection, candidates, " ".join(_quote_fts(token) for token in fts_tokens), 24.0, document_ids, tuple(fts_tokens))
                if len(candidates) < limit:
                    self._merge_fts(
                        connection,
                        candidates,
                        " OR ".join(_quote_fts(token) for token in fts_tokens),
                        12.0,
                        document_ids,
                        tuple(fts_tokens),
                    )

            tokens = _query_tokens(cleaned)
            if tokens:
                self._merge_like(connection, candidates, tokens, document_ids)

        ordered = sorted(
            candidates.values(),
            key=lambda item: (
                not item.article_exact,
                -item.score,
                item.document_id,
                item.chunk_id,
            ),
        )
        return [
            KeywordCandidate(
                candidate.chunk_id,
                candidate.document_id,
                candidate.score,
                index + 1,
                candidate.article_exact,
                tuple(sorted(candidate.matched_terms or ())),
            )
            for index, candidate in enumerate(ordered[:limit])
        ]

    def count(self, document_id: str) -> int:
        with open_connection(self._database_path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM chunk_search_fts WHERE document_id = ?", (document_id,)).fetchone()
        return int(row[0])

    def _merge_article_exact(
        self,
        connection,
        candidates: dict[str, _CandidateScore],
        articles: list[str],
        document_ids: list[str] | None,
    ) -> None:
        placeholders = ",".join("?" for _ in articles)
        sql = f"""
            SELECT id AS chunk_id, document_id, article
            FROM document_chunks
            WHERE article IN ({placeholders})
        """
        params: list[object] = list(articles)
        if document_ids:
            document_placeholders = ",".join("?" for _ in document_ids)
            sql += f" AND document_id IN ({document_placeholders})"
            params.extend(document_ids)
        for row in connection.execute(sql, tuple(params)).fetchall():
            _candidate(candidates, row["chunk_id"], row["document_id"]).add(120.0, (row["article"],), article_exact=True)

    def _merge_fts(
        self,
        connection,
        candidates: dict[str, _CandidateScore],
        fts_query: str,
        base_score: float,
        document_ids: list[str] | None,
        terms: tuple[str, ...],
    ) -> None:
        if not fts_query:
            return
        sql = """
            SELECT chunk_id, document_id, bm25(chunk_search_fts) AS bm25_score
            FROM chunk_search_fts
            WHERE chunk_search_fts MATCH ?
        """
        params: list[object] = [fts_query]
        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            sql += f" AND document_id IN ({placeholders})"
            params.extend(document_ids)
        sql += " ORDER BY bm25_score ASC LIMIT 50"
        rows = connection.execute(sql, tuple(params)).fetchall()
        for index, row in enumerate(rows):
            rank_score = max(0.0, 10.0 - index)
            bm25_score = max(0.0, min(10.0, -float(row["bm25_score"])))
            _candidate(candidates, row["chunk_id"], row["document_id"]).add(base_score + rank_score + bm25_score, terms)

    def _merge_like(
        self,
        connection,
        candidates: dict[str, _CandidateScore],
        tokens: list[str],
        document_ids: list[str] | None,
    ) -> None:
        clauses: list[str] = []
        params: list[object] = []
        for token in tokens:
            pattern = f"%{_escape_like(token)}%"
            clauses.append("(sheet_name LIKE ? ESCAPE '\\' OR article = ? OR title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')")
            params.extend((pattern, token, pattern, pattern))
        sql = f"""
            SELECT id AS chunk_id, document_id, sheet_name, article, title, content
            FROM document_chunks
            WHERE ({' OR '.join(clauses)})
        """
        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            sql += f" AND document_id IN ({placeholders})"
            params.extend(document_ids)
        rows = connection.execute(sql, tuple(params)).fetchall()
        for row in rows:
            sheet_name = str(row["sheet_name"] or "")
            article = str(row["article"] or "")
            title = str(row["title"] or "")
            content = str(row["content"] or "")
            haystack = "\n".join((sheet_name, article, title, content))
            matched = [token for token in tokens if token in haystack or token == row["article"]]
            if not matched:
                continue
            coverage = len(set(matched)) / max(1, len(set(tokens)))
            short_matches = sum(1 for token in set(matched) if len(token) <= 2)
            field_score = 0.0
            for token in set(matched):
                if token in article:
                    field_score += 8.0
                if token in title:
                    field_score += 6.0
                if token in sheet_name:
                    field_score += 4.0
            score = 8.0 + (22.0 * coverage) + (2.0 * short_matches) + field_score
            _candidate(candidates, row["chunk_id"], row["document_id"]).add(score, tuple(matched))


def extract_article_numbers(query: str) -> list[str]:
    articles: list[str] = []
    for match in re.finditer(r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?", query):
        suffix = f"의{match.group(2)}" if match.group(2) else ""
        article = f"제{match.group(1)}조{suffix}"
        if article not in articles:
            articles.append(article)
    return articles


def _candidate(candidates: dict[str, _CandidateScore], chunk_id: str, document_id: str) -> _CandidateScore:
    if chunk_id not in candidates:
        candidates[chunk_id] = _CandidateScore(chunk_id, document_id)
    return candidates[chunk_id]


def _safe_fts_query(query: str) -> str:
    tokens = [token for token in _query_tokens(query) if len(token) >= 3]
    return " ".join(_quote_fts(token) for token in tokens)


def _quote_fts(value: str) -> str:
    cleaned = value.replace('"', " ").strip()
    return f'"{cleaned}"' if cleaned else ""


def _query_tokens(query: str) -> list[str]:
    raw_tokens = re.findall(r"[0-9A-Za-z가-힣]+", query)
    tokens: list[str] = []
    for raw in raw_tokens:
        token = _normalize_token(raw)
        if token and token not in _STOPWORDS and token not in tokens:
            tokens.append(token)
    return tokens


def _normalize_token(token: str) -> str:
    token = token.strip().lower()
    if token in _STOPWORDS:
        return ""
    for suffix in ("에서는", "에게는", "으로는", "부터는", "까지는", "서는", "에는", "에서", "으로", "에게", "부터", "까지", "은", "는", "이", "가", "을", "를", "와", "과", "도", "한"):
        if len(token) > len(suffix) + 1 and token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    return token


def _clean_query(query: str) -> str:
    return " ".join(str(query).strip().split())


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


_STOPWORDS = {
    "무엇인가",
    "무엇",
    "가능한가",
    "가능",
    "하나",
    "하나요",
    "되나",
    "되나요",
    "있나",
    "있나요",
    "어떻게",
    "어디서",
    "언제",
    "며칠",
    "경우",
    "때",
}
