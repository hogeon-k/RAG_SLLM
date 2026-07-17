# RAG_SLLM

회사 규정, 법령, 업무 지침 문서를 로컬 PC에서 등록하고 검색하기 위한 Windows 데스크톱 RAG 프로그램입니다.

현재 범위는 Goal 3까지입니다. `.xlsx` 문서 등록, 원본 저장, 엑셀 구조 추출, 조항 단위 청크 생성, SQLite FTS5 키워드 검색, `sentence-transformers` 로컬 임베딩, ChromaDB 벡터 검색, 하이브리드 검색을 제공합니다. Ollama 또는 sLLM 답변 생성은 아직 포함하지 않습니다.

## 구조

```text
app/
  config/          환경 설정과 경로 관리
  database/        SQLite 연결과 스키마
  repositories/    SQLite 저장소 접근 계층
  services/        문서 등록, 추출, 인덱싱, 검색 서비스
  storage/         원본 파일 저장소와 ChromaDB 벡터 저장소
  models/          문서, 청크, 검색 결과 모델
  viewmodels/      PySide6 화면 상태와 작업 스레드
  views/           PySide6 화면
scripts/           더미 파일 생성, 파싱 점검, 검색 평가 스크립트
tests/             자동 테스트
data/              개발 DB, 업로드 원본, 벡터 DB, 테스트 산출물
logs/              로컬 로그
run.py             프로그램 실행 진입점
```

## 요구 사항

- Python 3.11
- Windows PowerShell
- 기본 임베딩 모델: `intfloat/multilingual-e5-small`
- 벡터 저장소: 로컬 ChromaDB persistent client, 기본 경로 `data/vector_db`

## 설치

```powershell
cd C:\workspace\RAG_SLLM
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-dev.txt
```

`requirements.txt`에는 실행 의존성으로 `PySide6`, `openpyxl`, `python-dotenv`, `chromadb`, `sentence-transformers`가 포함됩니다.

## 실행

```powershell
python run.py
```

`업무 RAG 규정 검색` 창이 열립니다. 문서 관리 화면에서 `.xlsx` 문서를 등록하고, 원본 구조를 추출한 뒤 검색 인덱스를 만들 수 있습니다.

## 환경 변수

`.env.example`을 기준으로 `.env`를 만들 수 있습니다.

```text
APP_EMBEDDING_MODEL=intfloat/multilingual-e5-small
APP_EMBEDDING_DEVICE=auto
APP_EMBEDDING_BATCH_SIZE=16
APP_VECTOR_COLLECTION=rag_sllm_chunks
APP_SEARCH_TOP_K=5
APP_KEYWORD_CANDIDATE_K=20
APP_VECTOR_CANDIDATE_K=20
APP_KEYWORD_WEIGHT=0.3
APP_VECTOR_WEIGHT=0.7
APP_VECTOR_MIN_SIMILARITY=0.0
```

`APP_EMBEDDING_DEVICE=auto`는 CUDA가 가능하면 GPU를, 아니면 CPU를 사용합니다. `cuda`로 고정했는데 CUDA를 사용할 수 없으면 명확한 오류를 발생시킵니다.

## 문서 등록과 추출

지원 파일은 `.xlsx`입니다. 등록 시 파일 존재, 확장자, 크기, XLSX 구조, 시트 존재 여부를 검증하고 SHA-256으로 중복을 차단합니다. 원본은 `data/uploads/DOC-.../document.xlsx`에 복사되며 실제 회사 문서나 개발 DB는 테스트 스크립트가 수정하지 않습니다.

엑셀 추출 결과는 다음 테이블에 저장됩니다.

- `document_sheets`: 시트 이름, 순서, 숨김 상태, 크기, 병합 범위 수
- `document_cells`: 셀 좌표, 원문 텍스트, 수식, 캐시값, 병합 범위, 숨김 여부
- `document_chunks`: 조항 또는 일반 문단 청크, article, title, cell_range, cell_refs, content_hash

청크 생성은 조항 번호, 괄호 제목, 같은 행의 인접 제목 셀, 병합 셀 앵커값, 두 행 이상의 빈 행 경계, 참고/비고/주의/안내 독립 라벨 행을 규정 문서 구조 규칙으로 처리합니다.

## 검색 인덱스

Goal 3 검색 인덱스는 SQLite와 ChromaDB를 함께 사용합니다.

- `chunk_search_fts`: SQLite FTS5 키워드 검색 테이블. 한국어 부분 문자열 검색을 위해 trigram tokenizer를 사용합니다.
- `document_search_indexes`: 문서별 인덱싱 상태, 모델명, 모델 fingerprint, 청크 수, FTS 수, 벡터 수, content fingerprint를 저장합니다.
- ChromaDB collection: 기본 `rag_sllm_chunks`. 벡터에는 청크 ID와 문서 ID를 함께 저장하고, 검색 결과 본문은 항상 SQLite의 최신 청크에서 다시 읽습니다.

문서가 `PARSED` 상태일 때 인덱싱할 수 있습니다. 인덱싱 성공 후 문서 상태는 `COMPLETED`, 인덱스 상태는 `READY`가 됩니다. 같은 문서를 다시 추출하면 기존 검색 인덱스는 `STALE`로 표시되어 재인덱싱 대상이 됩니다.

## 검색 방식

- `keyword`: FTS5 `MATCH`와 BM25 점수를 사용합니다.
- `vector`: 질문을 `query:` prefix로 임베딩하고 ChromaDB에서 cosine 거리 기반 후보를 찾습니다.
- `hybrid`: 키워드 점수와 벡터 점수를 0~1로 정규화한 뒤 기본 가중치 `0.3 / 0.7`로 결합합니다.

문서 임베딩은 `passage:` prefix를 사용합니다. 빈 입력, NaN/inf, 0 norm, 서로 다른 차원 벡터는 인덱싱 오류로 차단합니다.

## 테스트용 더미 엑셀

Goal 1, 2, 2.5 검증용 XLSX와 manifest는 아래 명령으로 생성하고 점검합니다.

```powershell
python scripts/generate_goal2_test_workbooks.py
python scripts/verify_goal2_test_workbooks.py
python scripts/inspect_goal2_parsing.py
```

생성 위치는 `data/test_workbooks/`입니다. 휴가규정 기준 조항은 `제8조(연차휴가 신청)`과 `제8조의2(긴급휴가)`입니다. main과 duplicate의 SHA-256은 같고, modified는 같은 위치의 문구가 `3일 전`에서 `5일 전`으로 바뀌어 SHA-256이 달라집니다.

## 검색 평가 스크립트

가짜 임베딩으로 빠르게 검색 흐름을 검증합니다.

```powershell
python scripts/evaluate_goal3_retrieval.py
```

실제 `intfloat/multilingual-e5-small` 모델 로딩과 로컬 ChromaDB 검색까지 확인합니다. 최초 실행 시 Hugging Face 모델 다운로드가 필요할 수 있습니다.

```powershell
python scripts/run_goal3_retrieval_smoke.py
```

두 스크립트는 임시 DB와 임시 벡터 DB를 사용하며 실제 개발 DB와 등록 원본 파일을 수정하지 않습니다.

## 전체 검증

```powershell
python -m compileall app scripts run.py
python -m pytest -q
```

의존성 충돌은 다음 명령으로 확인합니다.

```powershell
python -m pip check
```

## Git 제외 대상

`.env`, 실제 회사 문서, SQLite DB, ChromaDB 벡터 DB, 업로드 원본, 로그, 더미 XLSX 산출물은 Git에 커밋하지 않습니다.
