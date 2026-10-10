const API_URL = 'http://127.0.0.1:8000';
const uploadForm = document.querySelector('#uploadForm');
const fileInput = document.querySelector('#fileInput');
const dropZone = document.querySelector('#dropZone');
const filePreview = document.querySelector('#filePreview');
const uploadButton = document.querySelector('#uploadButton');
const uploadStatus = document.querySelector('#uploadStatus');
const connectionBadge = document.querySelector('#connectionBadge');
const questionForm = document.querySelector('#questionForm');
const questionInput = document.querySelector('#questionInput');
const questionButton = document.querySelector('#questionButton');
const answerBox = document.querySelector('#answerBox');
const documentList = document.querySelector('#documentList');
const historyList = document.querySelector('#historyList');

function showStatus(message, isError = false) {
  uploadStatus.textContent = message;
  uploadStatus.classList.toggle('error', isError);
}

function showFile(file) {
  if (!file) {
    filePreview.textContent = '선택된 파일이 없습니다.';
    filePreview.className = 'file-preview empty';
    return;
  }
  filePreview.className = 'file-preview selected';
  filePreview.innerHTML = `<span>${escapeHtml(file.name)}</span><small>${(file.size / 1024 / 1024).toFixed(2)} MB</small>`;
}

function useFile(file) {
  if (!file) return;
  const allowedExtensions = ['.pdf', '.md', '.markdown'];
  const lowerName = file.name.toLowerCase();
  if (!allowedExtensions.some((extension) => lowerName.endsWith(extension))) {
    showStatus('PDF 또는 Markdown 파일만 업로드할 수 있습니다.', true);
    return;
  }
  if (file.size > 20 * 1024 * 1024) {
    showStatus('파일 크기는 20MB 이하여야 합니다.', true);
    return;
  }
  showStatus('');
  showFile(file);
  const transfer = new DataTransfer();
  transfer.items.add(file);
  fileInput.files = transfer.files;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#039;', '"': '&quot;' }[character]));
}

function formatBytes(bytes) {
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function formatDate(value) {
  return new Intl.DateTimeFormat('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
}

function renderDocuments(items) {
  if (!items.length) {
    documentList.innerHTML = '<p class="empty-copy">아직 등록된 문서가 없습니다.</p>';
    return;
  }
  documentList.innerHTML = items.map((document) => `
    <article class="document-item">
      <div class="document-icon">${escapeHtml(document.file_type.toUpperCase())}</div>
      <div class="document-meta"><strong>${escapeHtml(document.filename)}</strong><span>${formatBytes(document.file_size)} · ${document.chunk_count} chunks · ${formatDate(document.created_at)}</span></div>
      <span class="document-status status-${document.status}">${escapeHtml(document.status)}</span>
      <button class="icon-button delete-document" type="button" data-id="${document.id}" aria-label="문서 삭제">×</button>
    </article>`).join('');
  documentList.querySelectorAll('.delete-document').forEach((button) => button.addEventListener('click', () => deleteDocument(button.dataset.id)));
}

function renderHistory(items) {
  if (!items.length) {
    historyList.innerHTML = '<p class="empty-copy">아직 질문 기록이 없습니다.</p>';
    return;
  }
  historyList.innerHTML = items.slice(0, 8).map((conversation) => `
    <article class="history-item"><span>${formatDate(conversation.created_at)}</span><strong>${escapeHtml(conversation.question)}</strong><p>${escapeHtml(conversation.answer.slice(0, 150))}</p></article>`).join('');
}

async function loadDocuments() {
  const response = await fetch(`${API_URL}/api/documents`);
  const payload = await response.json();
  renderDocuments(payload.items);
}

async function loadHistory() {
  const response = await fetch(`${API_URL}/api/conversations`);
  const payload = await response.json();
  renderHistory(payload.items);
}

async function deleteDocument(documentId) {
  if (!window.confirm('이 문서를 삭제할까요?')) return;
  const response = await fetch(`${API_URL}/api/documents/${documentId}`, { method: 'DELETE' });
  if (!response.ok) return;
  await loadDocuments();
}

fileInput.addEventListener('change', () => useFile(fileInput.files[0]));
['dragenter', 'dragover'].forEach((eventName) => dropZone.addEventListener(eventName, (event) => { event.preventDefault(); dropZone.classList.add('is-dragging'); }));
['dragleave', 'drop'].forEach((eventName) => dropZone.addEventListener(eventName, (event) => { event.preventDefault(); dropZone.classList.remove('is-dragging'); }));
dropZone.addEventListener('drop', (event) => useFile(event.dataTransfer.files[0]));

document.querySelector('#refreshDocuments').addEventListener('click', loadDocuments);
document.querySelector('#refreshHistory').addEventListener('click', loadHistory);

uploadForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) { showStatus('업로드할 PDF 또는 Markdown 파일을 선택하세요.', true); return; }
  uploadButton.disabled = true;
  uploadButton.textContent = '업로드 중...';
  showStatus('');
  const formData = new FormData();
  formData.append('file', file);
  try {
    const response = await fetch(`${API_URL}/api/documents`, { method: 'POST', body: formData });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail?.message ?? '업로드에 실패했습니다.');
    showStatus(`처리 완료: ${payload.filename} (${payload.status}, ${payload.chunk_count} chunks)`);
    uploadForm.reset();
    showFile(null);
    await loadDocuments();
  } catch (error) {
    showStatus(error.message ?? '백엔드 서버에 연결할 수 없습니다.', true);
  } finally {
    uploadButton.disabled = false;
    uploadButton.textContent = '문서 업로드';
  }
});

questionForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();
  if (!question) { answerBox.textContent = '질문을 입력하세요.'; answerBox.className = 'answer-box empty'; return; }
  questionButton.disabled = true;
  questionButton.textContent = '근거 검색 중...';
  answerBox.textContent = '문서에서 관련 근거를 찾고 있습니다.';
  answerBox.className = 'answer-box loading';
  try {
    const response = await fetch(`${API_URL}/api/questions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail?.message ?? '질문에 답할 수 없습니다.');
    const sourceHtml = payload.sources.length ? payload.sources.map((source) => `<li><strong>${escapeHtml(source.filename)}</strong> ${source.page_number ? `· p.${source.page_number}` : `· ${escapeHtml(source.chunk_id)}`}<small>${escapeHtml(source.excerpt)}</small></li>`).join('') : '<li>근거를 찾지 못했습니다.</li>';
    answerBox.className = `answer-box ${payload.grounded ? '' : 'empty'}`;
    answerBox.innerHTML = `<p>${escapeHtml(payload.answer).replace(/\n/g, '<br>')}</p><div class="source-heading">Sources (${payload.sources.length})</div><ul class="source-list">${sourceHtml}</ul>`;
    await loadHistory();
  } catch (error) {
    answerBox.textContent = error.message ?? '질문 처리에 실패했습니다.';
    answerBox.className = 'answer-box error';
  } finally {
    questionButton.disabled = false;
    questionButton.textContent = '문서에 질문하기';
  }
});

fetch(`${API_URL}/api/health`)
  .then((response) => { if (!response.ok) throw new Error('API unavailable'); connectionBadge.textContent = 'API connected'; return Promise.all([loadDocuments(), loadHistory()]); })
  .catch(() => { connectionBadge.textContent = 'API offline'; connectionBadge.classList.add('offline'); });
