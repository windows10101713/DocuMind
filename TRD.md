# DocuMind TRD

> DocuMind 제품 요구사항을 구현하기 위한 기술 설계 문서

---

## 1. 시스템 구성

```text
Browser
  |
  v
Static HTML/CSS/JavaScript Web -----> FastAPI API
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
        PostgreSQL     File Storage   AI Provider
        + pgvector     (local/Blob)   (embedding/chat/VLM)
```

### 기술 스택

| 영역 | 기술 | 역할 |
|---|---|---|
| Frontend | Static HTML, CSS, JavaScript | 화면과 API 연동 |
| Backend | FastAPI, Python | 인증, 문서, 질문 API |
| Database | PostgreSQL | 계정, 문서, 기록 저장 |
| Vector Search | pgvector | 임베딩 검색 |
| Storage | 로컬 storage/Azure Blob | 원본 파일 보관 |
| AI | OpenAI/Azure OpenAI 계열 API | 임베딩, 답변, VLM |
| Test | Pytest, Playwright | API와 사용자 흐름 검증 |
| Local | Docker Compose | 개발 환경 통일 |

정적 HTML 웹은 `web/index.html`, `web/styles.css`, `web/app.js`로 구성한다. 별도 빌드 단계 없이 Python의 `http.server` 또는 정적 호스팅에 배포할 수 있다.

### 현재 로컬 구현과 교체 지점

- `DOCUMENTS`, `CONVERSATIONS` 딕셔너리: 로컬 검증용 메모리 저장소
- `split_text`: 임시 토큰 기반 청크 분할기
- `ask_question`: 임시 키워드 교집합 검색기
- `process_document`: PDF/Markdown 텍스트 추출과 처리 상태 관리

### LLM 연결

`backend/app/ai.py`는 Azure OpenAI만 사용한다. Azure 설정이 없거나 외부 호출에 실패하면 검색된 근거 발췌 답변으로 폴백한다.

필수 환경변수:

```env
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o-mini
```

LLM 프롬프트는 검색된 청크만 컨텍스트로 전달하고, 근거가 부족하면 답변하지 않도록 제한한다. API 키는 소스 코드와 프론트엔드에 포함하지 않는다.

운영 전환 시 메모리 저장소를 PostgreSQL 모델로 교체하고, `ask_question`의 키워드 검색을 임베딩 생성 및 pgvector 검색으로 교체한다. 이후 선택된 청크를 LLM에 전달해 자연어 답변을 생성한다.

### HTML 실행 구성

```powershell
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
python -m http.server 5500 --directory web --bind 127.0.0.1
```

- HTML 웹 주소: `http://127.0.0.1:5500`
- API 주소: `http://127.0.0.1:8000`
- HTML 웹은 `multipart/form-data`로 API를 호출한다.
- API는 `localhost`와 `127.0.0.1`의 3000/5500 포트를 CORS 허용한다.

## 2. 모듈 책임

| 모듈 | 책임 |
|---|---|
| `web` | 로그인, 업로드, 문서 목록, 질문 화면 |
| `api` | 인증, 문서 CRUD, 질문, 기록, 피드백 |
| `ingestion` | 파일 검증, 텍스트/미디어 추출, 청크, 임베딩 |
| `retrieval` | 사용자 필터링, 키워드/벡터 검색, 중복 제거 |
| `generation` | 컨텍스트 구성, 답변, 출처 매핑, 거절 처리 |
| `persistence` | ORM 모델, 마이그레이션, 인덱스 |
| `observability` | request ID, 로그, 처리 시간, 실패율 |

## 3. 파일 업로드 기술 설계

### 3.1 업로드 요청

```http
POST /api/documents
Authorization: Bearer <access-token>
Content-Type: multipart/form-data
```

요청 필드:

```text
file: handbook.pdf
```

성공 응답:

```json
{
  "id": "document-uuid",
  "filename": "handbook.pdf",
  "file_type": "pdf",
  "file_size": 1048576,
  "status": "uploaded",
  "created_at": "2026-10-10T12:00:00Z"
}
```

업로드 응답의 `uploaded`는 분석 완료를 의미하지 않는다. 프론트엔드는 상태 API를 호출해 `ready` 여부를 확인한다.

### 3.2 검증 순서

1. JWT에서 `user_id`를 확인한다.
2. 파일이 정확히 1개인지 확인한다.
3. 크기가 0보다 크고 제한 이하인지 확인한다.
4. 파일명 길이와 확장자를 확인한다.
5. MIME 타입과 파일 시그니처를 확인한다.
6. SHA-256으로 중복 여부를 확인한다.
7. 문서 ID를 생성하고 임시 파일로 저장한다.
8. 데이터베이스에 `uploaded` 레코드를 생성한다.
9. 원본 파일을 확정 저장소로 이동한다.
10. 문서 처리 작업을 시작한다.

검증 실패 시 원본 파일을 확정 저장하지 않는다.

### 3.3 저장 경로

사용자가 입력한 파일명을 경로에 직접 사용하지 않는다.

```text
storage/{user_id}/{document_id}/original.{validated_extension}
```

표시용 이름은 `documents.filename`에 저장한다. 삭제 시 원본, 추출 데이터, 청크, 임베딩을 모두 삭제한다.

### 3.4 파일별 처리

| 형식 | 처리 방법 | 출처 |
|---|---|---|
| PDF | 페이지별 텍스트 추출 | 문서명 + 페이지 |
| Markdown | 제목/문단 경계 기반 분할 | 문서명 + 청크 |
| DOCX | 문단/표 추출 | 문서명 + 문단 |
| PPTX | 슬라이드/노트 추출 | 문서명 + 슬라이드 |
| XLSX | 시트/셀/표 추출, 수식 실행 금지 | 문서명 + 시트/범위 |
| 이미지 | VLM 설명/OCR/표 분석 | 파일명 + 이미지 ID |
| 영상 | 키프레임/VLM + ASR + 자막 | 파일명 + 시간 구간 |

### 3.5 오류 코드

| HTTP | 코드 | 의미 |
|---:|---|---|
| 400 | `FILE_REQUIRED` | 파일이 없거나 여러 개 전달됨 |
| 400 | `UNSUPPORTED_FILE_TYPE` | 허용하지 않은 형식 |
| 400 | `INVALID_FILE_SIGNATURE` | 확장자와 실제 형식 불일치 |
| 400 | `EMPTY_DOCUMENT` | 파일이 비어 있거나 텍스트가 없음 |
| 413 | `FILE_TOO_LARGE` | 크기 제한 초과 |
| 409 | `DUPLICATE_DOCUMENT` | 동일 파일이 이미 존재함 |
| 422 | `FILE_PARSE_FAILED` | 파서가 파일을 읽지 못함 |
| 422 | `SCAN_PDF_NOT_SUPPORTED` | OCR 미지원 스캔 PDF |
| 422 | `ENCRYPTED_FILE_NOT_SUPPORTED` | 암호화 파일 |

## 4. 문서 처리 파이프라인

```text
파일 업로드
  -> 확장자/MIME/시그니처 검증
  -> 원본 저장
  -> uploaded
  -> 텍스트 또는 미디어 추출
  -> processing
  -> 청크 분할
  -> 임베딩 생성
  -> document_chunks 저장
  -> ready
```

### 상태

| 상태 | 의미 |
|---|---|
| `uploaded` | 파일 저장 완료, 분석 대기 |
| `processing` | 추출/청크/임베딩 작업 중 |
| `ready` | 검색과 질문 가능 |
| `failed` | 오류 코드와 재시도 가능 |

### 상태 조회

```http
GET /api/documents/{document_id}/status
Authorization: Bearer <access-token>
```

프론트엔드는 2초 간격으로 최대 30회 폴링한다. 60초 동안 상태 변경이 없으면 폴링을 중지한다.

## 5. 멀티모달 파이프라인

### 이미지

1. 이미지 MIME과 시그니처를 검증한다.
2. 이미지 크기와 해상도를 제한한다.
3. VLM에 이미지를 전달한다.
4. 설명, OCR 텍스트, 표/객체 정보를 구조화한다.
5. 결과와 원본 이미지 ID를 함께 저장한다.
6. 결과 텍스트를 임베딩해 검색한다.

### 영상

1. 컨테이너와 코덱을 확인한다.
2. 장면 전환 또는 10초 간격으로 키프레임을 생성한다.
3. 음성을 ASR로 변환한다.
4. 기존 자막을 추출한다.
5. 키프레임을 VLM으로 요약한다.
6. 음성, 자막, 프레임 설명을 시간 구간별로 합친다.
7. 구간별 임베딩을 저장한다.
8. 답변 출처에 시작/종료 시간을 포함한다.

영상 전체를 VLM에 한 번에 전송하지 않으며, 영상 파일은 최대 200MB·5분으로 제한한다.

## 6. 검색과 답변

1. JWT에서 `user_id`를 확인한다.
2. 질문 임베딩을 생성한다.
3. 사용자 소유 문서의 청크만 검색한다.
4. 키워드와 벡터 검색 결과를 결합한다.
5. 유사도 0.70 미만을 제거한다.
6. 상위 5개 청크를 선택한다.
7. 동일 문서 결과는 최대 3개로 제한한다.
8. 청크와 출처 메타데이터를 AI 모델에 전달한다.
9. 답변과 출처 ID를 저장하고 반환한다.

### 검색 기준

- 청크 크기: 500~800 토큰
- 청크 중첩: 80~120 토큰
- 유사도 임계값: 0.70
- 기본 결과 수: 5개
- 동일 문서 최대 결과: 3개
- 일반 검색 P95 목표: 2초 이하
- AI 답변 P95 목표: 10초 이하

### 답변 규칙

- 검색된 콘텐츠에 있는 내용만 사용한다.
- 근거가 부족하면 답변을 생성하지 않는다.
- 답변에는 최소 1개의 출처를 포함한다.
- 출처 위치는 PDF 페이지, 슬라이드, 시트/범위, 이미지 ID 또는 영상 시간이다.

## 7. 데이터 모델

### User

- `id`
- `email`
- `password_hash`
- `created_at`

### Document

- `id`
- `user_id`
- `filename`
- `storage_path`
- `file_type`
- `file_size`
- `sha256`
- `status`
- `error_code`
- `error_message`
- `created_at`
- `processed_at`

### DocumentChunk

- `id`
- `document_id`
- `content`
- `page_number`
- `section_name`
- `start_time`
- `end_time`
- `chunk_index`
- `embedding`

### Conversation

- `id`
- `user_id`
- `question`
- `answer`
- `retrieved_chunks`
- `created_at`

### Feedback

- `id`
- `conversation_id`
- `rating`
- `comment`
- `created_at`

## 8. API 설계

| Method | Endpoint | 설명 |
|---|---|---|
| `POST` | `/api/auth/signup` | 회원가입 |
| `POST` | `/api/auth/login` | 로그인 |
| `POST` | `/api/documents` | 문서 업로드 |
| `GET` | `/api/documents` | 문서 목록 |
| `GET` | `/api/documents/{id}` | 문서 상세 |
| `GET` | `/api/documents/{id}/status` | 처리 상태 |
| `DELETE` | `/api/documents/{id}` | 문서 삭제 |
| `POST` | `/api/documents/{id}/retry` | 처리 재시도 |
| `POST` | `/api/questions` | 질문/답변 생성 |
| `GET` | `/api/conversations` | 질문 기록 조회 |
| `DELETE` | `/api/conversations/{id}` | 질문 기록 삭제 |
| `POST` | `/api/conversations/{id}/feedback` | 답변 평가 |
| `GET` | `/api/health` | 서버 상태 |

공통 규칙:

- 보호 API는 `Authorization: Bearer <token>`을 요구한다.
- 성공 응답은 JSON이다.
- 오류 형식은 `{ "code": "ERROR_CODE", "message": "..." }`다.
- 목록 기본값은 `page=1`, `size=20`이다.
- 질문 최대 길이는 1,000자다.
- 소유하지 않은 리소스는 `404`로 응답한다.

## 9. 보안과 운영

### 보안

- 비밀번호는 Argon2 또는 bcrypt로 해시한다.
- 파일명은 저장 경로에 직접 사용하지 않는다.
- MIME, 확장자, 시그니처를 모두 검증한다.
- 모든 문서/청크 조회에 `user_id` 조건을 포함한다.
- JWT 키와 AI API 키는 환경변수로 주입한다.
- HTML은 프론트엔드에서 이스케이프한다.
- 파일을 실행하거나 ISO를 마운트하지 않는다.

### 장애 처리

- 외부 AI 호출 타임아웃: 30초
- AI 호출 자동 재시도: 최대 1회
- 문서 처리 실패 시 원본은 보존하고 재시도 가능
- 사용자에게 스택 트레이스와 키를 노출하지 않음

### 관측성

- 모든 요청에 `request_id`를 부여한다.
- 처리 실패율, 질문 응답 시간, AI 실패율을 기록한다.
- 운영 환경에서는 Application Insights 또는 동등한 도구로 로그를 전송한다.

## 10. 환경변수

```env
DATABASE_URL=
JWT_SECRET_KEY=
AI_API_KEY=
AI_EMBEDDING_MODEL=
AI_CHAT_MODEL=
AI_VLM_MODEL=
AI_ASR_MODEL=
STORAGE_ROOT=./storage
MAX_UPLOAD_SIZE_MB=20
VECTOR_SCORE_THRESHOLD=0.70
```

## 11. 테스트 기준

### 기능

- PDF가 `uploaded -> ready`로 전환되는가?
- Markdown의 제목과 문단이 검색되는가?
- DOCX/PPTX/XLSX와 이미지가 로드맵대로 처리되는가?
- 확장자만 바꾼 파일이 거부되는가?
- 20MB 초과, 0바이트, 중복 파일이 거부되는가?
- 실행 파일, ISO, RAW가 차단되는가?
- 다른 사용자의 문서와 상태를 조회할 수 없는가?
- 답변 출처 위치가 실제 문서와 일치하는가?
- 영상 출처 시간이 실제 구간과 일치하는가?
- 근거 없는 질문에 추측으로 답하지 않는가?

### 성능

| 항목 | 목표 |
|---|---:|
| 문서 목록 응답 | 500ms 이하 |
| 일반 검색 P95 | 2초 이하 |
| AI 답변 P95 | 10초 이하 |
| 10MB PDF 처리 | 60초 이하 |
| 이미지 1장 처리 | 15초 이하 |
| 동시 질문 처리 | 5건 이상 |

## 12. 개발 순서

1. Next.js/FastAPI 프로젝트와 Docker Compose 구성
2. PostgreSQL/pgvector 연결
3. 인증과 사용자 격리 구현
4. PDF/Markdown 업로드 및 처리
5. 키워드/벡터 검색 구현
6. AI 답변과 출처 연결
7. 질문 기록과 피드백 구현
8. API/Playwright 테스트 작성
9. 이미지 VLM 파이프라인 추가
10. 영상 키프레임/ASR 파이프라인 추가
11. 배포와 성능 측정
