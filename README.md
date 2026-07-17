# RAG_SLLM

회사 규정, 법령, 업무 지침 문서를 로컬 PC에서 검색하고 질의응답하기 위한 Windows 데스크톱 RAG 프로그램입니다.

현재 범위는 Goal 1 문서 등록 기반까지입니다. Ollama, 임베딩, ChromaDB, 실제 문서 내용 추출과 RAG 답변 생성은 아직 구현하지 않았습니다.

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

## 다음 단계

Goal 2에서는 엑셀 내용 추출, 시트/행 범위 분석, 문서 청크 분할, 추출 결과 저장 흐름을 구현하는 것을 권장합니다.
