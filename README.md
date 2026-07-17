# RAG_SLLM

회사 규정, 법령, 업무 지침 문서를 로컬 PC에서 검색하고 질의응답하기 위한 Windows 데스크톱 RAG 프로그램입니다.

현재 범위는 Goal 0 개발 기반 구성입니다. Ollama, 임베딩, ChromaDB, 실제 문서 처리와 RAG 답변 생성은 아직 구현하지 않았습니다.

## 구조

```text
app/
  config/          환경 설정과 경로 관리
  database/        SQLite 연결 기반
  repositories/    데이터 저장소 접근 계층
  services/        유스케이스 흐름 계층
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

실행하면 `업무 RAG 규정 검색` 메인 창이 열리고 왼쪽 메뉴에서 4개 화면을 전환할 수 있습니다.

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

## 다음 단계

Goal 1에서는 엑셀/문서 등록, 기본 문서 메타데이터 저장, 파일 검증, 초기 문서 처리 흐름을 구현하는 것을 권장합니다.
