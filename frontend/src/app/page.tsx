"use client";

import { ChangeEvent, FormEvent, useState } from "react";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const acceptedTypes = ".pdf,.md,.markdown";

export default function Home() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadError, setUploadError] = useState("");

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0] ?? null;
    setSelectedFile(nextFile);
    setUploadMessage("");
    setUploadError("");
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) {
      setUploadError("업로드할 PDF 또는 Markdown 파일을 선택하세요.");
      return;
    }

    setIsUploading(true);
    setUploadMessage("");
    setUploadError("");

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const response = await fetch(`${apiUrl}/api/documents`, {
        method: "POST",
        body: formData,
      });
      const payload = await response.json();

      if (!response.ok) {
        const message = payload.detail?.message ?? "파일 업로드에 실패했습니다.";
        throw new Error(message);
      }

      setUploadMessage(`업로드 접수 완료: ${payload.filename} (${payload.status})`);
      setSelectedFile(null);
      event.currentTarget.reset();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "업로드에 실패했습니다.");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f4f1ea] text-[#17211b]">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 py-6 lg:px-10 lg:py-8">
        <header className="flex items-center justify-between border-b border-[#c9c8bc] pb-5">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#173d32] text-sm font-bold text-[#f4f1ea]">
              DM
            </span>
            <div>
              <p className="text-lg font-semibold tracking-tight">DocuMind</p>
              <p className="text-xs text-[#667168]">Evidence-first knowledge workspace</p>
            </div>
          </div>
          <span className="rounded-full border border-[#b6c2b3] bg-[#e7eee4] px-3 py-1 text-xs font-medium text-[#31543e]">
            Local workspace
          </span>
        </header>

        <section className="grid flex-1 gap-10 py-12 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:gap-20">
          <div className="max-w-2xl">
            <p className="mb-5 text-sm font-semibold uppercase tracking-[0.2em] text-[#b05f3c]">
              Your documents, properly grounded
            </p>
            <h1 className="max-w-xl text-5xl font-semibold leading-[1.03] tracking-[-0.04em] sm:text-6xl">
              Ask your documents.
              <span className="block text-[#b05f3c]">See the evidence.</span>
            </h1>
            <p className="mt-7 max-w-lg text-lg leading-8 text-[#536058]">
              PDF와 Markdown을 업로드하면 검색 가능한 지식으로 정리하고, 답변마다 근거 위치를 연결합니다.
            </p>
            <div className="mt-9 grid max-w-lg grid-cols-3 gap-3 border-t border-[#c9c8bc] pt-5 text-sm">
              <div>
                <p className="font-semibold">20MB</p>
                <p className="mt-1 text-[#778078]">per file</p>
              </div>
              <div>
                <p className="font-semibold">PDF / MD</p>
                <p className="mt-1 text-[#778078]">MVP formats</p>
              </div>
              <div>
                <p className="font-semibold">0.70+</p>
                <p className="mt-1 text-[#778078]">retrieval threshold</p>
              </div>
            </div>
          </div>

          <section className="rounded-2xl border border-[#c9c8bc] bg-[#fbfaf5] p-6 shadow-[0_18px_50px_rgba(51,58,43,0.08)] sm:p-8">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#b05f3c]">Step 01</p>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight">Add a source document</h2>
              </div>
              <span className="rounded-full bg-[#edf0e8] px-3 py-1 text-xs text-[#536058]">Ready</span>
            </div>

            <form className="mt-8" onSubmit={handleUpload}>
              <label className="group flex min-h-52 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-[#aeb8aa] bg-[#f4f5ed] px-6 text-center transition-colors hover:border-[#b05f3c] hover:bg-[#f0f2e9]">
                <span className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-[#173d32] text-xl text-[#f4f1ea]">+</span>
                <span className="font-medium">파일을 선택하거나 여기에 놓으세요</span>
                <span className="mt-2 text-sm text-[#778078]">PDF, Markdown · 최대 20MB</span>
                <input className="sr-only" type="file" accept={acceptedTypes} onChange={handleFileChange} />
              </label>

              <div className="mt-4 min-h-12 rounded-lg border border-[#e0ded3] bg-white px-4 py-3 text-sm">
                {selectedFile ? (
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate font-medium">{selectedFile.name}</span>
                    <span className="shrink-0 text-[#778078]">{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</span>
                  </div>
                ) : (
                  <span className="text-[#9a9f98]">선택된 파일이 없습니다.</span>
                )}
              </div>

              <button
                className="mt-4 flex h-12 w-full items-center justify-center rounded-lg bg-[#b05f3c] px-5 font-semibold text-white transition-colors hover:bg-[#934b2f] disabled:cursor-not-allowed disabled:bg-[#c9b0a3]"
                type="submit"
                disabled={isUploading}
              >
                {isUploading ? "업로드 중..." : "문서 업로드"}
              </button>

              {uploadMessage && <p className="mt-4 text-sm text-[#31543e]">{uploadMessage}</p>}
              {uploadError && <p className="mt-4 text-sm text-[#a53f2d]">{uploadError}</p>}
            </form>

            <div className="mt-8 border-t border-[#e0ded3] pt-5 text-sm text-[#667168]">
              <div className="flex items-center justify-between py-1">
                <span>Next</span>
                <span>Processing & indexing</span>
              </div>
              <div className="flex items-center justify-between py-1">
                <span>Then</span>
                <span>Ask with sources</span>
              </div>
            </div>
          </section>
        </section>
      </div>
    </main>
  );
}
