# RAG_SLLM

회사 규정, 법령, 업무 지침이 담긴 Excel 문서를 등록하고 근거를 검색해 답변하는 Windows 데스크톱 RAG 애플리케이션입니다.

문서 원본과 추출 결과는 로컬 파일 및 SQLite에 저장하고, SQLite FTS5 키워드 검색과 ChromaDB 벡터 검색을 결합합니다. 검색된 근거는 Ollama 모델에 전달되며, 답변과 함께 실제 문서명·시트·조항·셀 범위를 확인할 수 있습니다.

## 주요 기능

### 문서 관리

- `.xlsx` 문서 등록
- 버전, 시행일, 개정일, 담당 부서 메타데이터 입력
- 파일 크기, 확장자, Excel 구조, 시트 존재 여부 검증
- SHA-256 및 통합 문서 내용 비교를 통한 중복 등록 방지
- 등록 원본을 애플리케이션 데이터 경로에 별도 보관
- 시트, 셀, 병합 범위, 수식과 캐시 값 추출
- 조항·제목·문단 구조를 고려한 검색 청크 생성
- 추출 결과와 원본 셀 참조 미리보기
- 문서 재추출, 검색 인덱싱 및 재인덱싱
- 문서를 `CURRENT` 또는 `ARCHIVED` 상태로 관리
- 문서 삭제 시 원본, 추출 데이터, FTS 인덱스, 벡터 삭제
- 문서를 삭제해도 기존 질문 이력의 출처 스냅샷은 보존

### 검색과 답변

- `keyword`: SQLite FTS5 키워드 검색
- `vector`: `sentence-transformers` 임베딩과 ChromaDB 벡터 검색
- `hybrid`: 키워드와 벡터 검색 결과를 가중 결합
- 조항 번호, 질의 표현 일치도, 검색 순위, 문서 버전 의도를 반영한 재정렬
- 기본적으로 현행 문서만 검색하고, 선택 시 보관 문서까지 포함
- Ollama `/api/generate`를 이용한 JSON 형식의 근거 기반 답변 생성
- 답변, 실행 항목, 예외 사항, 사용한 근거 ID를 검증
- 근거가 없거나 약한 경우 답변을 만들지 않고 근거 부족으로 처리
- 존재하지 않는 근거 ID, 오래된 청크, 비정상 응답을 검증
- 답변과 함께 문서명, 시트명, 조항, 제목, 셀 범위, 셀 좌표, 원문 표시

### 질문 이력

- 성공, 근거 부족, 근거 없음, 실패 상태 저장
- 질문, 답변, 검색 모드, 모델, 처리 시간, 사용 근거 수 확인
- 질문·답변·문서·시트·조항·제목 통합 검색
- 상태 및 날짜 범위 필터
- 답변 생성 당시의 검증된 출처를 스냅샷으로 저장
- 선택 이력 또는 전체 이력 삭제

### 시스템 설정

- 현재 데이터 경로와 검색·생성 설정 확인
- Ollama 서버 및 설정 모델 사용 가능 여부 확인
- `.env`를 통한 저장 경로, 모델, 검색, 문서 추출 설정 변경

## 동작 구조

```text
Excel 문서
  └─ 등록 및 원본 보관
      └─ 시트·셀 구조 추출
          └─ 조항 단위 청크 생성
              ├─ SQLite FTS5 인덱스
              └─ sentence-transformers 임베딩 → ChromaDB
                      ↓
              keyword / vector / hybrid 검색
                      ↓
                 근거 충분성 검사
                      ↓
                 Ollama 답변 생성
                      ↓
            검증된 출처와 질문 이력 저장
```

문서 처리 상태는 다음 순서로 진행됩니다.

```text
UPLOADED → PARSING → PARSED → INDEXING → COMPLETED
                                      └→ 검색 인덱스 READY
```

재추출하면 기존 검색 인덱스는 `STALE` 상태가 되므로 재인덱싱해야 다시 검색할 수 있습니다.

## 프로젝트 구조

```text
app/
  config/          환경 변수와 애플리케이션 경로 설정
  database/        SQLite 연결 및 스키마 초기화
  models/          문서, 검색, 답변, 이력 데이터 모델
  repositories/    SQLite 데이터 접근 계층
  services/        등록, 추출, 청크, 검색, 답변, 이력 서비스
  storage/         원본 파일 및 ChromaDB 벡터 저장소
  utils/           해시와 로깅 유틸리티
  viewmodels/      화면 상태와 백그라운드 작업
  views/           PySide6 데스크톱 UI
scripts/           테스트 문서 생성, 스모크 테스트, 검색·답변 평가
tests/             pytest 자동 테스트
data/              기본 데이터 저장 경로
logs/              애플리케이션 로그
run.py             실행 진입점
```

## 요구 사항

- Windows
- Python 3.11
- Ollama
- 기본 Ollama 모델: `llama3.2:3b`
- 기본 임베딩 모델: `intfloat/multilingual-e5-small`

주요 Python 패키지는 다음과 같습니다.

- `PySide6`
- `openpyxl`
- `python-dotenv`
- `chromadb`
- `sentence-transformers`

## 설치

PowerShell에서 프로젝트 가상 환경을 만들고 의존성을 설치합니다.

```powershell
cd C:\workspace\RAG_SLLM
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

테스트와 개발 도구까지 설치하려면 대신 다음 파일을 사용합니다.

```powershell
python -m pip install -r requirements-dev.txt
```

환경 파일을 생성합니다.

```powershell
Copy-Item .env.example .env
```

Ollama를 실행하고 `.env`의 `OLLAMA_MODEL`에 지정된 모델을 준비합니다. 기본 설정을 사용할 경우 모델명은 `llama3.2:3b`입니다.

```powershell
ollama pull llama3.2:3b
```

`intfloat/multilingual-e5-small` 모델이 로컬에 없으면 최초 임베딩 또는 인덱싱 시 모델 파일 다운로드가 필요할 수 있습니다.

## 실행

```powershell
.\.venv\Scripts\Activate.ps1
python run.py
```

애플리케이션에는 다음 네 화면이 있습니다.

1. `질의응답`: 검색 모드와 보관 문서 포함 여부를 선택하고 답변 및 근거 확인
2. `문서 관리`: 문서 등록, 추출, 미리보기, 인덱싱, 상태 전환, 삭제
3. `질문 이력`: 저장된 답변과 출처 스냅샷 조회, 필터, 삭제
4. `시스템 설정`: 적용된 설정과 Ollama 상태 확인

처음 사용할 때는 `문서 등록 → 내용 추출 → 검색 인덱싱 → 질의응답` 순서로 진행합니다.

## 환경 변수

설정은 프로젝트 루트의 `.env`에서 읽습니다. 빈 `APP_DATA_DIR`는 개발 환경에서 프로젝트의 `data` 디렉터리를 사용합니다. `APP_ENV=production`이고 `APP_DATA_DIR`가 비어 있으면 `%LOCALAPPDATA%\RAG_SLLM`을 사용합니다.

### 애플리케이션과 저장소

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `APP_ENV` | `development` | 실행 환경 |
| `APP_DATA_DIR` | 빈 값 | 데이터 저장 경로 |
| `APP_LOG_LEVEL` | `INFO` | 로그 레벨 |

기본 데이터 구성은 다음과 같습니다.

```text
data/
  database/app.sqlite3   문서, 추출 결과, 인덱스 상태, 질문 이력
  uploads/               등록한 Excel 원본
  vector_db/             ChromaDB 벡터 데이터
logs/                    실행 로그
```

### Ollama와 답변 생성

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama API 주소 |
| `OLLAMA_MODEL` | `llama3.2:3b` | 답변 생성 모델 |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | API 제한 시간(초) |
| `OLLAMA_NUM_CTX` | `4096` | 컨텍스트 크기 |
| `OLLAMA_NUM_PREDICT` | `512` | 최대 생성 토큰 설정 |
| `OLLAMA_TEMPERATURE` | `0.0` | 생성 temperature |
| `OLLAMA_TOP_P` | `0.8` | 생성 top-p |
| `OLLAMA_TOP_K` | `20` | 생성 top-k |
| `OLLAMA_REPEAT_PENALTY` | `1.1` | 반복 패널티 |
| `RETRIEVAL_TOP_K` | `5` | 답변 생성에 전달할 검색 결과 수 |

### 문서 추출

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `APP_MAX_XLSX_MB` | `50` | 등록 가능한 `.xlsx` 최대 크기(MB) |
| `APP_CHUNK_MAX_CHARS` | `1500` | 청크 최대 문자 수 |
| `APP_CHUNK_MIN_CHARS` | `80` | 청크 최소 문자 수 |
| `APP_MAX_EXTRACTED_CELLS` | `200000` | 문서당 최대 추출 셀 수 |
| `APP_INCLUDE_HIDDEN_SHEETS` | `false` | 숨김 시트 추출 여부 |

### 임베딩과 검색

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `APP_EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | 임베딩 모델 |
| `APP_EMBEDDING_DEVICE` | `auto` | `auto`, `cpu`, `cuda` 장치 선택 |
| `APP_EMBEDDING_BATCH_SIZE` | `16` | 임베딩 배치 크기 |
| `APP_VECTOR_COLLECTION` | `rag_sllm_chunks` | ChromaDB 컬렉션 이름 |
| `APP_SEARCH_TOP_K` | `5` | 일반 검색의 기본 결과 수 |
| `APP_KEYWORD_CANDIDATE_K` | `20` | 키워드 검색 후보 수 |
| `APP_VECTOR_CANDIDATE_K` | `20` | 벡터 검색 후보 수 |
| `APP_KEYWORD_WEIGHT` | `0.3` | 하이브리드 키워드 가중치 |
| `APP_VECTOR_WEIGHT` | `0.7` | 하이브리드 벡터 가중치 |
| `APP_VECTOR_MIN_SIMILARITY` | `0.0` | 벡터 후보 최소 유사도 |

`APP_EMBEDDING_DEVICE=auto`는 CUDA를 사용할 수 있으면 GPU를, 그렇지 않으면 CPU를 선택합니다. `cuda`로 고정했는데 CUDA를 사용할 수 없으면 인덱싱 중 오류가 발생합니다.

## 문서 등록과 검색 범위

지원 형식은 `.xlsx`입니다. 등록 시 입력한 원본은 `data/uploads/DOC-.../document.xlsx` 형식의 내부 경로에 복사됩니다.

기본 검색 대상은 다음 조건을 모두 만족하는 문서입니다.

- 문서 처리 상태가 `COMPLETED`
- 검색 인덱스 상태가 `READY`
- 업무 상태가 `CURRENT`

질의응답 화면에서 `Include archived`를 선택하면 `ARCHIVED` 문서도 검색 범위에 포함됩니다. 문서를 현행 상태로 승격하면 같은 문서 계열의 기존 현행 문서를 보관 상태로 전환할 수 있습니다.

## 검색 방식

### Keyword

SQLite FTS5의 trigram tokenizer와 BM25 점수를 사용합니다. 한글 부분 문자열 검색과 조항 번호 검색을 지원하며 검색 점수는 결합 전에 정규화됩니다.

### Vector

문서 청크는 `passage:` 접두사, 질의는 `query:` 접두사를 사용해 임베딩합니다. ChromaDB의 cosine 거리에서 유사도를 계산합니다.

### Hybrid

정규화된 키워드 점수와 벡터 점수를 기본 가중치 `0.3 / 0.7`로 결합합니다. 조항의 정확한 일치, 두 검색 방식의 순위, 질의 토큰 포함 정도, 시트·조항·제목 일치, 현행·이전 규정 의도도 최종 순위에 반영합니다.

## 답변과 근거 검증

검색 결과가 있더라도 바로 답변을 생성하지 않습니다. 먼저 조항 일치, 키워드와 벡터의 교차 지지, 표현 일치도, 출처 힌트, 현행·이전 규정 의도, 근거 간 충돌을 검사합니다.

근거가 충분하면 Ollama에 질문과 검색 근거를 전달합니다. 응답은 정해진 JSON 스키마로 제한되며 다음 항목을 검증합니다.

- 답변 본문
- 실행 항목
- 예외 사항
- 근거 부족 여부와 사유
- 실제로 제공된 근거 ID만 사용했는지 여부
- 답변에 사용된 청크와 문서가 현재 저장소에 존재하는지 여부

검증을 통과하지 못한 모델 응답은 한 번 재생성을 시도합니다. 이후에도 적합하지 않으면 코드에 정의된 근거 기반 대체 응답 또는 안전한 답변 거부로 처리합니다.

## 질문 이력과 문서 삭제

질문 처리 결과는 SQLite의 `question_histories`에 저장되고, 사용한 원문은 `question_history_sources`에 별도 스냅샷으로 저장됩니다.

문서를 삭제하면 현재 문서 데이터와 검색 인덱스는 제거되지만, 과거 답변을 확인할 수 있도록 질문 이력과 당시 출처 스냅샷은 유지됩니다. 질문 이력은 이력 화면에서 별도로 삭제할 수 있습니다.

## 검증과 테스트

전체 Python 구문과 자동 테스트를 확인합니다.

```powershell
python -m compileall app scripts run.py
python -m pytest -q
python -m pip check
```

테스트용 Excel 문서를 생성하고 구조를 확인할 수 있습니다.

```powershell
python scripts/generate_goal2_test_workbooks.py
python scripts/verify_goal2_test_workbooks.py
python scripts/inspect_goal2_parsing.py
```

실제 임베딩 모델을 사용하는 검색 스모크 테스트는 다음 순서로 실행합니다.

```powershell
python scripts/generate_goal2_test_workbooks.py
python scripts/run_goal3_retrieval_smoke.py
```

Ollama 연결 및 JSON 답변 생성 확인:

```powershell
python scripts/run_goal4_ollama_smoke.py
```

Ollama 답변과 질문 이력 저장 확인:

```powershell
python scripts/run_goal5_history_smoke.py
```

검색·답변 평가 스크립트의 옵션은 다음 명령으로 확인할 수 있습니다.

```powershell
python scripts/run_goal6_evaluation.py --help
```

평가 모드는 `retrieval-only`, `fake-answer`, `live-ollama`를 지원합니다. 평가 보고서는 기본적으로 `data/test_workbooks/goal6_reports`에 생성되며, README에는 실행하지 않은 평가 결과나 성능 수치를 기재하지 않습니다.

## Git에서 제외되는 로컬 데이터

다음 항목은 `.gitignore`에 의해 버전 관리에서 제외됩니다.

- `.env`
- SQLite 데이터베이스
- 등록한 Excel 원본
- ChromaDB 벡터 데이터
- 로그
- 생성한 테스트 문서와 평가 산출물
