from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import hashlib
import re
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.ai import generate_grounded_answer

try:
    from pypdf import PdfReader
except ImportError:  # PDF support is optional until dependencies are installed.
    PdfReader = None

BASE_DIR = Path(__file__).resolve().parents[1]
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown"}
ALLOWED_MIME_TYPES = {
    ".pdf": {"application/pdf"},
    ".md": {"text/markdown", "text/plain", "application/octet-stream"},
    ".markdown": {"text/markdown", "text/plain", "application/octet-stream"},
}
MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_DOCUMENTS_PER_USER = 50
LOCAL_USER_ID = "local-user"
VECTOR_SCORE_THRESHOLD = 0.70

app = FastAPI(title="DocuMind API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@dataclass
class Chunk:
    id: str
    content: str
    page_number: int | None = None
    chunk_index: int = 0


@dataclass
class DocumentRecord:
    id: str
    user_id: str
    filename: str
    file_type: str
    file_size: int
    sha256: str
    storage_path: str
    status: str = "uploaded"
    error_code: str | None = None
    error_message: str | None = None
    extracted_text: str = ""
    chunks: list[Chunk] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    processed_at: str | None = None


@dataclass
class ConversationRecord:
    id: str
    user_id: str
    question: str
    answer: str
    sources: list[dict]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    feedback: dict | None = None


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class FeedbackRequest(BaseModel):
    rating: str = Field(pattern="^(up|down)$")
    comment: str | None = Field(default=None, max_length=500)


DOCUMENTS: dict[str, DocumentRecord] = {}
CONVERSATIONS: dict[str, ConversationRecord] = {}


def error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def has_valid_signature(extension: str, content: bytes) -> bool:
    if extension == ".pdf":
        return content.startswith(b"%PDF-")
    return True


def serialize_chunk(chunk: Chunk, document: DocumentRecord) -> dict:
    return {
        "id": chunk.id,
        "content": chunk.content,
        "page_number": chunk.page_number,
        "chunk_index": chunk.chunk_index,
        "filename": document.filename,
    }


def serialize_document(document: DocumentRecord) -> dict:
    return {
        "id": document.id,
        "filename": document.filename,
        "file_type": document.file_type,
        "file_size": document.file_size,
        "sha256": document.sha256,
        "status": document.status,
        "error_code": document.error_code,
        "error_message": document.error_message,
        "chunk_count": len(document.chunks),
        "created_at": document.created_at,
        "processed_at": document.processed_at,
    }


def split_text(text: str, document_id: str, page_number: int | None = None) -> list[Chunk]:
    words = re.findall(r"\S+", text)
    if not words:
        return []
    chunk_size = 180
    overlap = 30
    chunks = []
    start = 0
    index = 0
    while start < len(words):
        content = " ".join(words[start:start + chunk_size]).strip()
        if content:
            chunks.append(Chunk(
                id=f"{document_id}-{index}",
                content=content,
                page_number=page_number,
                chunk_index=index,
            ))
        start += chunk_size - overlap
        index += 1
    return chunks


def extract_text(document: DocumentRecord, content: bytes) -> list[Chunk]:
    if document.file_type in {"md", "markdown"}:
        text = content.decode("utf-8", errors="replace")
        document.extracted_text = text
        return split_text(text, document.id)

    if PdfReader is None:
        raise ValueError("PDF_PARSER_NOT_INSTALLED")

    reader = PdfReader(BytesIO(content))
    page_chunks: list[Chunk] = []
    all_text = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if not page_text:
            continue
        all_text.append(page_text)
        page_chunks.extend(split_text(page_text, document.id, page_number))
    document.extracted_text = "\n\n".join(all_text)
    return page_chunks


def process_document(document: DocumentRecord, content: bytes) -> None:
    document.status = "processing"
    try:
        chunks = extract_text(document, content)
        if len(document.extracted_text.strip()) < 50:
            raise ValueError("EMPTY_DOCUMENT")
        document.chunks = chunks
        document.status = "ready"
        document.error_code = None
        document.error_message = None
        document.processed_at = now_iso()
    except Exception as exception:
        document.status = "failed"
        document.error_code = str(exception) or "FILE_PARSE_FAILED"
        document.error_message = "문서에서 검색 가능한 텍스트를 추출하지 못했습니다."
        document.chunks = []


def get_document(document_id: str) -> DocumentRecord:
    document = DOCUMENTS.get(document_id)
    if document is None or document.user_id != LOCAL_USER_ID:
        raise error("DOCUMENT_NOT_FOUND", "문서를 찾을 수 없습니다.", 404)
    return document


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "documents": str(len(DOCUMENTS))}


@app.post("/api/documents", status_code=201)
async def upload_document(file: UploadFile = File(...), background_tasks: BackgroundTasks = None) -> dict:
    original_name = file.filename or ""
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise error("UNSUPPORTED_FILE_TYPE", "PDF 또는 Markdown 파일만 업로드할 수 있습니다.", 400)
    if len([document for document in DOCUMENTS.values() if document.user_id == LOCAL_USER_ID]) >= MAX_DOCUMENTS_PER_USER:
        raise error("DOCUMENT_LIMIT_REACHED", "사용자당 문서는 최대 50개까지 등록할 수 있습니다.", 409)

    content = await file.read()
    if not content:
        raise error("EMPTY_DOCUMENT", "빈 파일은 업로드할 수 없습니다.", 400)
    if len(content) > MAX_FILE_SIZE:
        raise error("FILE_TOO_LARGE", "파일 크기는 20MB 이하여야 합니다.", 413)
    if file.content_type not in ALLOWED_MIME_TYPES[extension]:
        raise error("INVALID_MIME_TYPE", "파일 형식과 MIME 타입이 일치하지 않습니다.", 400)
    if not has_valid_signature(extension, content):
        raise error("INVALID_FILE_SIGNATURE", "파일의 실제 형식을 확인할 수 없습니다.", 400)

    digest = hashlib.sha256(content).hexdigest()
    if any(document.sha256 == digest and document.user_id == LOCAL_USER_ID for document in DOCUMENTS.values()):
        raise error("DUPLICATE_DOCUMENT", "동일한 파일이 이미 등록되어 있습니다.", 409)

    document_id = str(uuid4())
    document_dir = STORAGE_DIR / LOCAL_USER_ID / document_id
    document_dir.mkdir(parents=True, exist_ok=False)
    stored_path = document_dir / f"original{extension}"
    stored_path.write_bytes(content)
    document = DocumentRecord(
        id=document_id,
        user_id=LOCAL_USER_ID,
        filename=original_name,
        file_type=extension.removeprefix("."),
        file_size=len(content),
        sha256=digest,
        storage_path=str(stored_path),
    )
    DOCUMENTS[document_id] = document
    process_document(document, content)
    return serialize_document(document)


@app.get("/api/documents")
def list_documents() -> dict:
    documents = [serialize_document(document) for document in DOCUMENTS.values() if document.user_id == LOCAL_USER_ID]
    documents.sort(key=lambda document: document["created_at"], reverse=True)
    return {"items": documents, "total": len(documents)}


@app.get("/api/documents/{document_id}")
def document_detail(document_id: str) -> dict:
    document = get_document(document_id)
    return {**serialize_document(document), "sources": [serialize_chunk(chunk, document) for chunk in document.chunks]}


@app.get("/api/documents/{document_id}/status")
def document_status(document_id: str) -> dict:
    return serialize_document(get_document(document_id))


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str) -> dict[str, str]:
    document = get_document(document_id)
    DOCUMENTS.pop(document.id, None)
    document_path = Path(document.storage_path)
    if document_path.exists():
        document_path.unlink()
    if document_path.parent.exists():
        document_path.parent.rmdir()
    return {"id": document_id, "status": "deleted"}


@app.post("/api/documents/{document_id}/retry")
def retry_document(document_id: str) -> dict:
    document = get_document(document_id)
    content = Path(document.storage_path).read_bytes()
    process_document(document, content)
    return serialize_document(document)


@app.post("/api/questions")
def ask_question(request: QuestionRequest) -> dict:
    terms = {term.lower() for term in re.findall(r"[\w가-힣]{2,}", request.question.lower())}
    candidates = []
    for document in DOCUMENTS.values():
        if document.user_id != LOCAL_USER_ID or document.status != "ready":
            continue
        for chunk in document.chunks:
            chunk_terms = set(re.findall(r"[\w가-힣]{2,}", chunk.content.lower()))
            matched = len(terms & chunk_terms)
            if matched:
                score = min(0.99, 0.70 + (matched / max(len(terms), 1)) * 0.29)
                candidates.append((score, chunk, document))

    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    selected = candidates[:5]
    if not selected:
        answer = "업로드된 문서에서 답변의 근거를 찾지 못했습니다."
        sources = []
    else:
        excerpts = []
        sources = []
        for score, chunk, document in selected:
            excerpts.append(f"[{document.filename}] {chunk.content[:260]}")
            sources.append({
                "document_id": document.id,
                "filename": document.filename,
                "page_number": chunk.page_number,
                "chunk_id": chunk.id,
                "score": round(score, 3),
                "excerpt": chunk.content[:260],
            })
        answer = "문서에서 다음 근거를 찾았습니다.\n\n" + "\n\n".join(excerpts)
        try:
            ai_answer = generate_grounded_answer(request.question, sources)
            if ai_answer:
                answer = ai_answer
        except Exception:
            # The grounded excerpt fallback keeps local development usable when AI is unavailable.
            pass

    conversation = ConversationRecord(
        id=str(uuid4()),
        user_id=LOCAL_USER_ID,
        question=request.question,
        answer=answer,
        sources=sources,
    )
    CONVERSATIONS[conversation.id] = conversation
    return {"id": conversation.id, "question": request.question, "answer": answer, "sources": sources, "grounded": bool(sources)}


@app.get("/api/conversations")
def list_conversations() -> dict:
    items = [asdict(conversation) for conversation in CONVERSATIONS.values() if conversation.user_id == LOCAL_USER_ID]
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return {"items": items[:50], "total": len(items)}


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, str]:
    conversation = CONVERSATIONS.get(conversation_id)
    if conversation is None or conversation.user_id != LOCAL_USER_ID:
        raise error("CONVERSATION_NOT_FOUND", "질문 기록을 찾을 수 없습니다.", 404)
    CONVERSATIONS.pop(conversation_id)
    return {"id": conversation_id, "status": "deleted"}


@app.post("/api/conversations/{conversation_id}/feedback")
def add_feedback(conversation_id: str, request: FeedbackRequest) -> dict:
    conversation = CONVERSATIONS.get(conversation_id)
    if conversation is None or conversation.user_id != LOCAL_USER_ID:
        raise error("CONVERSATION_NOT_FOUND", "질문 기록을 찾을 수 없습니다.", 404)
    conversation.feedback = request.model_dump()
    return {"id": conversation_id, "feedback": conversation.feedback}
