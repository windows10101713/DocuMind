# DocuMind

> 업로드한 문서를 검색하고, 근거와 함께 답변받는 AI 지식관리 서비스

---

## 빠른 요약

| 항목 | 내용 |
|---|---|
| 해결 문제 | 흩어진 문서에서 정보를 찾기 어렵고 AI 답변의 근거를 확인하기 어려움 |
| MVP 파일 | `.pdf`, `.md`, `.markdown` |
| 핵심 기능 | 로그인, 파일 업로드, 문서 처리, 키워드/벡터 검색, AI 질문, 출처 표시 |
| 처리 흐름 | 업로드 -> 검증 -> 텍스트 추출 -> 청크/임베딩 -> 검색 -> 답변 |
| 기술 스택 | HTML/CSS/JavaScript, FastAPI, PostgreSQL, pgvector, OpenAI 계열 API |
| 파일 제한 | 일반 파일 20MB, 사용자당 50개 문서 |
| 확장 계획 | 이미지 VLM 2차, 영상 VLM+ASR 3차 |

```text
로그인 -> 파일 업로드 -> 처리 완료 -> 질문 -> 답변과 출처 확인
```

---

## 문서

| 문서 | 담당 내용 |
|---|---|
| [PRD.md](PRD.md) | 제품 목표, 사용자, 기능 요구사항, 파일 지원 정책, 성공 지표 |
| [TRD.md](TRD.md) | 시스템 구조, 업로드 파이프라인, 데이터 모델, API, 보안, 테스트 |

---

## 제품 동작

### 1. 파일 업로드

브라우저가 `POST /api/documents`로 파일 하나를 `multipart/form-data`로 전송한다.

MVP에서는 PDF와 Markdown만 허용한다.

- 최대 크기: 20MB
- 사용자별 최대 문서: 50개
- MIME 타입과 파일 시그니처 검증
- 동일 SHA-256 파일 중복 차단
- 원본 파일명은 저장 경로에 사용하지 않음

### 2. 문서 처리

```text
uploaded -> processing -> ready
										\-> failed
```

- PDF: 페이지 번호를 보존해 텍스트 추출
- Markdown: 제목과 문단 구조를 보존
- 처리 완료 문서만 검색과 질문에 사용
- 실패 시 오류 코드와 재시도 기능 제공

### 3. 질문과 답변

1. 사용자의 문서만 검색한다.
2. 키워드 검색과 벡터 검색 결과를 결합한다.
3. 유사도 0.70 이상인 상위 5개 청크를 선택한다.
4. 선택된 청크만 AI 모델에 전달한다.
5. 답변에 문서명과 페이지/청크 위치를 표시한다.
6. 근거가 부족하면 답변하지 않는다.

답변 출처는 파일 형식에 따라 다음처럼 표시한다.

- PDF: 문서명 + 페이지 번호
- Markdown: 문서명 + 청크 위치
- 이미지: 파일명 + 이미지 ID
- 영상: 파일명 + 시간 구간

---

## 파일 지원 로드맵

| 단계 | 지원 형식 | 처리 방식 |
|---|---|---|
| MVP | PDF, Markdown | 텍스트 추출과 벡터 검색 |
| 2차 | TXT, DOCX, PPTX, XLSX, PNG, JPG, ZIP | 전용 파서 또는 VLM 기반 처리 |
| 3차 | MP4, MOV, WEBM | 키프레임 + ASR + 자막 + VLM |
| 차단 | EXE, DLL, SYS, APK, DEB, ISO, RAW | 실행/마운트하지 않으며 별도 분석 영역으로 분리 |

실행 파일, 시스템 파일, 디스크 이미지는 일반 문서 검색에 바로 넣지 않는다. 파일을 실행하거나 ISO를 마운트하지 않고, 필요한 경우 별도의 격리된 정적 분석 서비스로 분리한다.

---

## 기술 구성

```text
Browser
	|
	+--> Static HTML/CSS/JavaScript Web
	|          |
	+----------+----> FastAPI API
												 |
						 +-------------+-------------+
						 |             |             |
						 v             v             v
				PostgreSQL     File Storage   AI Provider
				+ pgvector     (local/Blob)   (embedding/chat/VLM)
```

| 영역 | 기술 |
|---|---|
| Frontend | Static HTML, CSS, JavaScript |
| Backend | FastAPI, Python |
| Database | PostgreSQL + pgvector |
| Storage | 로컬 `storage/`, 운영 Azure Blob Storage |
| AI | OpenAI 또는 Azure OpenAI 계열 API |
| Test | Pytest, Playwright |
| Local | Docker Compose |

### 현재 구현 상태

- 업로드, 문서 목록/삭제, Markdown/PDF 텍스트 추출, 청크 생성이 동작한다.
- 질문 API는 현재 키워드 기반 검색과 근거 발췌 답변으로 동작한다.
- 로컬 개발에서는 문서와 질문 기록을 메모리에 저장하므로 서버 재시작 시 초기화된다.
- PostgreSQL/pgvector, 실제 임베딩 모델, LLM 답변 생성은 다음 구현 단계에서 연결한다.

### AI 연결

실제 AI 답변을 사용하려면 `backend/.env.example`을 `backend/.env`로 복사하고 Azure OpenAI 또는 OpenAI 값을 입력한다. 키가 없으면 로컬 키워드 검색과 근거 발췌 답변으로 자동 폴백한다.

```powershell
Copy-Item backend/.env.example backend/.env
```

Azure OpenAI 사용 시 `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_CHAT_DEPLOYMENT`를 설정한다. Azure OpenAI 설정이 없으면 로컬 개발에서는 근거 발췌 답변으로 폴백한다.

---

## HTML 웹 실행

백엔드와 정적 HTML 서버를 각각 실행한다.

```powershell
# 터미널 1: API
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

# 터미널 2: HTML 웹
python -m http.server 5500 --directory web --bind 127.0.0.1
```

브라우저에서 `http://127.0.0.1:5500`을 연다.

HTML 화면은 다음 기능을 제공한다.

- PDF/Markdown 파일 선택 및 드래그 앤 드롭
- 20MB 파일 크기 사전 검증
- 업로드 중 상태 표시
- FastAPI 업로드 성공/실패 메시지 표시
- API 연결 상태 표시
- 제품 원칙과 다음 처리 단계 안내

프론트엔드 파일은 [web/index.html](web/index.html), [web/styles.css](web/styles.css), [web/app.js](web/app.js)로 구성한다.

---

## API 핵심 목록

| Method | Endpoint | 설명 |
|---|---|---|
| `POST` | `/api/auth/signup` | 회원가입 |
| `POST` | `/api/auth/login` | 로그인 |
| `POST` | `/api/documents` | 파일 업로드 |
| `GET` | `/api/documents` | 문서 목록 |
| `GET` | `/api/documents/{id}/status` | 처리 상태 |
| `DELETE` | `/api/documents/{id}` | 문서 삭제 |
| `POST` | `/api/documents/{id}/retry` | 처리 재시도 |
| `POST` | `/api/questions` | 질문/답변 생성 |
| `GET` | `/api/conversations` | 질문 기록 |
| `POST` | `/api/conversations/{id}/feedback` | 답변 평가 |
| `GET` | `/api/health` | 서버 상태 |

모든 보호 API는 `Authorization: Bearer <token>`을 사용한다.

---

## 개발 순서

1. Next.js/FastAPI 프로젝트 구성
2. Docker Compose와 PostgreSQL/pgvector 연결
3. 회원가입, 로그인, 사용자 데이터 격리
4. PDF/Markdown 업로드와 파일 검증
5. 텍스트 추출과 청크 분할
6. 임베딩 저장과 키워드/벡터 검색
7. AI 답변과 출처 연결
8. 질문 기록과 답변 평가
9. Pytest/Playwright 테스트
10. 이미지 VLM 확장
11. 영상 키프레임/ASR 확장

---

## MVP 완료 기준

- PDF와 Markdown을 업로드할 수 있다.
- 잘못된 확장자, MIME, 파일 시그니처, 크기를 차단한다.
- 문서가 `ready` 상태로 처리된다.
- 처리 완료 문서에 질문할 수 있다.
- 답변에 실제 출처가 표시된다.
- 근거 없는 질문에 추측으로 답하지 않는다.
- 다른 사용자의 문서와 질문 기록에 접근할 수 없다.
- 핵심 사용자 흐름 테스트가 통과한다.

자세한 제품 기준은 [PRD.md](PRD.md), 구현 기준은 [TRD.md](TRD.md)를 참고한다.
