# RAG_SLLM

회사 규정, 법령, 업무 지침 문서를 로컬 PC에서 검색하고 질의응답하기 위한 Windows 데스크톱 RAG 프로그램입니다.

현재 범위는 Goal 2 엑셀 원문 구조 추출과 조항 단위 청크 생성까지입니다. Ollama, 임베딩, ChromaDB, 벡터 검색, RAG 답변 생성은 아직 구현하지 않았습니다.

## 구조

```text
app/
  config/          환경 설정과 경로 관리
  database/        SQLite 연결 기반
  repositories/    데이터 저장소 접근 계층
  services/        유스케이스 흐름 계층
  models/          문서 도메인 모델
  storage/         원본 파일 저장 계층
  viewmodels/      화면 상태와 요청 전달 계층
  views/           PySide6 화면
data/              개발 환경 데이터 경로
logs/              로컬 로그
tests/             자동 테스트
run.py             프로그램 실행 진입점
```

## 요구 사항

- Python 3.11
- Windows PowerShell

## 가상환경 활성화

```powershell
cd C:\workspace\RAG_SLLM
.\.venv\Scripts\Activate.ps1
```

## 패키지 설치

```powershell
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-dev.txt
```

## 실행

```powershell
python run.py
```

실행하면 `업무 RAG 규정 검색` 메인 창이 열립니다. `문서 관리` 화면에서 `.xlsx` 파일을 선택하고 선택 메타데이터를 입력해 등록할 수 있습니다.

## 테스트

```powershell
python -m compileall app run.py
python -m pytest -q
```

GUI 테스트는 `pytest-qt`를 사용하며 실제 프로젝트 DB 대신 `tmp_path` 임시 경로를 사용합니다.

## 테스트용 더미 엑셀 생성

Goal 1과 Goal 2를 수동 검증하기 위한 가상 규정 XLSX를 생성할 수 있습니다. 모든 내용은 기능 검증용 더미 데이터이며 실제 회사 정보나 개인정보를 포함하지 않습니다.

```powershell
python scripts/generate_goal2_test_workbooks.py
python scripts/verify_goal2_test_workbooks.py
python scripts/inspect_goal2_parsing.py
```

출력 위치:

```text
data/test_workbooks/
```

생성 파일:

- `goal2_regulations_fixture.xlsx`: 정상 등록 및 추출 검증용 주 문서
- `goal2_regulations_fixture_duplicate.xlsx`: 주 문서의 바이트 단위 복사본으로 SHA-256 중복 검증용
- `goal2_regulations_fixture_modified.xlsx`: 같은 구조에서 일부 내용과 버전만 변경한 별도 등록 검증용
- `goal2_corrupted.xlsx`: 확장자만 `.xlsx`인 손상 파일 검증용
- `goal2_fixture_manifest.json`: 생성 파일, 해시, 시트 구조, 주요 검증 포인트 설명

`inspect_goal2_parsing.py`는 기존 `ExcelParserService`와 `ChunkService`로 파일을 직접 읽어 요약을 출력하며 개발 DB에는 저장하지 않습니다. 생성된 XLSX와 manifest는 재현 가능한 산출물이므로 Git 추적 대상에서 제외됩니다.

휴가규정 더미 데이터는 `제8조(연차휴가 신청)`과 `제8조의2(긴급휴가)`를 기준 조항으로 사용합니다. main 파일의 `제8조` 청크에는 `3일 전` 문구가 있고, modified 파일의 동일 위치에는 `5일 전` 문구가 있습니다.

## Git 제외 대상

`.env`, 회사 문서 파일, SQLite DB, 벡터 DB, 업로드 파일, 로그 파일은 Git에 커밋하지 않습니다. 빈 디렉터리 유지를 위해 `.gitkeep` 파일만 추적합니다.

## 현재 구현 범위

- Python 3.11 `.venv` 구성
- PySide6 메인 창과 `QStackedWidget` 화면 전환
- 설정 로딩과 개발용 데이터 경로 생성
- 콘솔 및 파일 로깅 기반
- SQLite 연결, `row_factory`, `foreign_keys` 설정
- View, ViewModel, Service, Repository 최소 분리
- 자동 테스트 기반
- `.xlsx` 문서 등록
- 파일 존재, 확장자, 크기, 빈 파일, XLSX 구조, 시트 존재 여부 검증
- SHA-256 기반 중복 등록 차단
- 원본 파일을 `data/uploads/DOC-.../document.xlsx`에 안전하게 복사
- SQLite `documents` 테이블에 문서 메타데이터 저장
- 문서 관리 화면 목록 표시와 백그라운드 Worker 등록 처리
- 저장된 `.xlsx` 원본에서 시트, 셀, 병합 범위, 수식 정보를 추출
- 조항 단위 또는 행 단위 청크 생성
- 청크마다 실제 셀 범위와 개별 셀 참조 저장
- 추출 결과 미리보기 화면 제공

## 문서 등록

지원 파일은 `.xlsx`만 가능합니다. 기본 최대 파일 크기는 50MB이며 `.env`의 `APP_MAX_XLSX_MB`로 변경할 수 있습니다.

등록 메타데이터:

- 원본 파일명
- 저장 경로
- SHA-256 해시
- 파일 크기
- 버전
- 시행일
- 개정일
- 담당 부서
- 최신 여부
- 처리 상태
- 등록 일시

동일한 내용의 파일은 파일명이 달라도 SHA-256 해시로 중복 차단됩니다.

## 원문 추출

문서 관리 화면에서 등록된 문서를 선택한 뒤 `내용 추출`을 실행하면 저장된 원본 파일을 읽어 다음 데이터를 SQLite에 저장합니다.

- `document_sheets`: 시트 이름, 순서, 표시 상태, 행/열 크기, 비어 있지 않은 셀 수, 병합 범위 수
- `document_cells`: 셀 좌표, 행/열 번호, 값 타입, 정규화된 텍스트, 수식, 캐시 값, 병합 범위, 숨김 여부
- `document_chunks`: 조항 또는 업무 단위 청크, 원문, 조항/제목, 셀 범위, 개별 셀 참조

기본 설정에서는 visible 시트만 셀/청크 추출 대상으로 사용합니다. hidden 또는 veryHidden 시트는 `document_sheets`에 기록되지만 기본 청크 생성에서는 제외됩니다. `.env`에서 `APP_INCLUDE_HIDDEN_SHEETS=true`로 바꾸면 숨김 시트도 추출 대상에 포함할 수 있습니다.

## 병합 셀

병합 셀은 첫 번째 앵커 셀만 원문 셀로 저장합니다. 예를 들어 `B2:F2`가 병합되어 있고 값이 `B2`에 있으면 `B2`만 `ParsedCell`로 저장하며 `merged_range`에 `B2:F2`를 기록합니다. 청크의 `cell_range`는 전체 근거 범위를 나타내고, `cell_refs`는 실제 참조 셀 또는 병합 범위를 개별적으로 보존합니다.

## 수식

openpyxl은 수식을 직접 계산하지 않습니다. 수식 셀은 원본 수식 문자열을 보존하고, 파일에 저장된 캐시 계산값이 있으면 추출 텍스트로 우선 사용합니다. 캐시 값이 없으면 수식 문자열을 안전하게 보존합니다.

## 청크 생성

청크는 결정론적인 규칙으로 생성됩니다.

- 같은 행의 셀 텍스트는 열 순서대로 결합합니다.
- `제1장`, `제1절`, `제1조`, `제1조의2`, `제1조(목적)` 같은 한국어 규정 구조를 인식합니다.
- 새 조항이 시작되면 새 청크 경계로 사용합니다.
- 조항 구조가 없는 표 형태 문서는 행 묶음과 최대 글자 수 기준으로 청크를 나눕니다.
- 서로 다른 시트의 내용은 하나의 청크로 합치지 않습니다.
- `APP_CHUNK_MAX_CHARS`, `APP_CHUNK_MIN_CHARS`, `APP_MAX_EXTRACTED_CELLS`로 추출 동작을 조정할 수 있습니다.

문서 처리 상태:

- `UPLOADED`: 등록 완료
- `PARSING`: 원문 추출 중
- `PARSED`: 추출 및 청크 저장 완료
- `FAILED`: 추출 실패

`추출 결과 보기`에서는 저장된 실제 청크 원문, 조항, 제목, 셀 범위, 개별 셀 참조를 읽기 전용으로 확인할 수 있습니다.

## 다음 단계

Goal 3에서는 청크 검색 인덱스, SQLite FTS5 또는 벡터 DB 연동, 임베딩 생성 준비 흐름을 구현하는 것을 권장합니다.
