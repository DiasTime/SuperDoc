"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  JOB_STAGES,
  type DocumentResponse,
  type DocumentStructure,
  type JobStatus,
  type UploadResponse,
} from "@docres/shared-types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const POLL_MS = 1500;
const ACCEPT = "image/jpeg,image/png,image/webp,image/tiff,image/bmp";

const TRACKED = JOB_STAGES.filter(
  (s) => s.status !== "QUEUED" && s.status !== "COMPLETED",
);

function stageIndex(status: JobStatus): number {
  const i = TRACKED.findIndex((s) => s.status === status);
  if (status === "COMPLETED") return TRACKED.length;
  return i;
}

const TYPE_COLORS: Record<string, string> = {
  INVOICE: "bg-blue-500/20 text-blue-300 border-blue-400/30",
  CONTRACT: "bg-emerald-500/20 text-emerald-300 border-emerald-400/30",
  ACT: "bg-amber-500/20 text-amber-300 border-amber-400/30",
  CERTIFICATE: "bg-violet-500/20 text-violet-300 border-violet-400/30",
  PASSPORT: "bg-pink-500/20 text-pink-300 border-pink-400/30",
  ID_CARD: "bg-cyan-500/20 text-cyan-300 border-cyan-400/30",
  FORM: "bg-slate-500/20 text-slate-300 border-slate-400/30",
  COMMERCIAL_OFFER: "bg-orange-500/20 text-orange-300 border-orange-400/30",
  UNKNOWN: "bg-white/10 text-white/40 border-white/10",
};

const FORMAT_LABELS: Record<string, string> = {
  PDF: "Clean PDF",
  DOCX: "Editable DOCX",
  JSON: "Structured JSON",
};

function typeLabel(t: string) {
  return t.replace(/_/g, " ");
}

function ConfidenceDot({ conf }: { conf: number }) {
  if (conf >= 0.85) return null;
  const color = conf < 0.7 ? "bg-red-400" : "bg-yellow-400";
  return (
    <span
      className={`inline-block h-1.5 w-1.5 rounded-full ${color} ml-1 align-middle`}
      title={conf < 0.7 ? "Low confidence" : "Medium confidence"}
    />
  );
}

function StructurePreview({ s }: { s: DocumentStructure }) {
  const sections = s.sections ?? [];
  const metadata = s.metadata ?? {};
  const sigs = s.signatures ?? [];
  const metaEntries = Object.entries(metadata).slice(0, 6);
  const tableCount = sections.reduce((acc, sec) => acc + (sec.tables?.length ?? 0), 0);
  const kvCount = sections.reduce((acc, sec) => acc + (sec.keyValues?.length ?? 0), 0);

  return (
    <div className="mt-4 space-y-3">
      {metaEntries.length > 0 && (
        <div className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-2.5">
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-white/30">
            Key facts
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
            {metaEntries.map(([k, v]) => (
              <span key={k} className="contents">
                <dt className="truncate font-medium text-white/50">{k}</dt>
                <dd className="truncate text-white/80">{v}</dd>
              </span>
            ))}
          </dl>
        </div>
      )}

      {sections.length > 0 && (
        <div className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-2.5">
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-white/30">
            {sections.length} section{sections.length !== 1 ? "s" : ""}
            {tableCount > 0 && ` · ${tableCount} table${tableCount !== 1 ? "s" : ""}`}
            {kvCount > 0 && ` · ${kvCount} field${kvCount !== 1 ? "s" : ""}`}
          </div>
          <ul className="space-y-0.5">
            {sections.slice(0, 5).map((sec, i) => {
              const headingText = sec.heading?.value ?? "";
              const conf = sec.heading?.confidence ?? 1;
              return (
                <li key={i} className="flex items-center gap-1 text-xs text-white/60">
                  <span className="text-white/25">§</span>
                  <span className="truncate">
                    {headingText || <em className="text-white/30">untitled</em>}
                  </span>
                  <ConfidenceDot conf={conf} />
                </li>
              );
            })}
            {sections.length > 5 && (
              <li className="text-xs text-white/30">+{sections.length - 5} more…</li>
            )}
          </ul>
        </div>
      )}

      {sigs.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {sigs.map((sig, i) => (
            <span
              key={i}
              className="rounded border border-dashed border-white/20 px-2 py-0.5 text-[10px] text-white/40"
            >
              {sig.kind?.toUpperCase() ?? "SIGNATURE"}
              {sig.label ? ` — ${sig.label}` : ""}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-3 text-[10px] text-white/30">
        <span className="flex items-center gap-1">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-yellow-400" />
          medium confidence
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-red-400" />
          low confidence
        </span>
      </div>
    </div>
  );
}

type Phase = "idle" | "working" | "done" | "error";

export default function Uploader() {
  const inputRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [doc, setDoc] = useState<DocumentResponse | null>(null);
  const [error, setError] = useState<string>("");
  const [dragging, setDragging] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>("");

  const reset = useCallback(() => {
    setPhase("idle");
    setDoc(null);
    setError("");
    setFileName("");
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
  }, [previewUrl]);

  // Revoke object URL on unmount
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const poll = useCallback(async (id: string) => {
    while (true) {
      const res = await fetch(`${API}/document/${id}`);
      if (!res.ok) throw new Error(`status check failed (${res.status})`);
      const data: DocumentResponse = await res.json();
      setDoc(data);
      if (data.status === "COMPLETED") {
        setPhase("done");
        return;
      }
      if (data.status === "FAILED") {
        throw new Error(data.error || "processing failed");
      }
      await new Promise((r) => setTimeout(r, POLL_MS));
    }
  }, []);

  const start = useCallback(
    async (file: File) => {
      // Create preview before resetting so URL is fresh
      const url = URL.createObjectURL(file);
      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
      setFileName(file.name);
      setPhase("working");
      setDoc(null);
      setError("");
      try {
        const form = new FormData();
        form.append("file", file);
        const up = await fetch(`${API}/upload`, { method: "POST", body: form });
        if (!up.ok) {
          const detail = await up.json().catch(() => null);
          throw new Error(detail?.detail || `upload failed (${up.status})`);
        }
        const { documentId }: UploadResponse = await up.json();
        const proc = await fetch(`${API}/process/${documentId}`, { method: "POST" });
        if (!proc.ok) throw new Error(`could not start processing (${proc.status})`);
        await poll(documentId);
      } catch (e) {
        setError(e instanceof Error ? e.message : "something went wrong");
        setPhase("error");
      }
    },
    [poll],
  );

  const onFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0];
      if (file) void start(file);
    },
    [start],
  );

  // Paste-from-clipboard support
  useEffect(() => {
    const handlePaste = (e: ClipboardEvent) => {
      if (phase !== "idle") return;
      const items = Array.from(e.clipboardData?.items ?? []);
      const imageItem = items.find(
        (item) => item.kind === "file" && item.type.startsWith("image/"),
      );
      if (imageItem) {
        const file = imageItem.getAsFile();
        if (file) void start(file);
      }
    };
    document.addEventListener("paste", handlePaste);
    return () => document.removeEventListener("paste", handlePaste);
  }, [phase, start]);

  return (
    <div className="mt-10 w-full max-w-xl">
      {/* Hidden file inputs */}
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => onFiles(e.target.files)}
      />
      <input
        ref={cameraRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={(e) => onFiles(e.target.files)}
      />

      <AnimatePresence mode="wait">
        {/* ── IDLE ─────────────────────────────────────────────── */}
        {phase === "idle" && (
          <motion.div
            key="drop"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
          >
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                onFiles(e.dataTransfer.files);
              }}
              className={`w-full rounded-2xl border border-dashed px-8 py-20 text-center transition-all duration-200 ${
                dragging
                  ? "scale-[1.01] border-indigo-300/70 bg-indigo-500/10"
                  : "border-white/15 bg-white/5 hover:bg-white/[0.07] hover:border-white/25"
              }`}
            >
              {/* Upload icon */}
              <div className="mb-4 flex justify-center">
                <svg
                  width="36"
                  height="36"
                  viewBox="0 0 36 36"
                  fill="none"
                  className="opacity-40"
                >
                  <rect x="4" y="20" width="28" height="12" rx="3" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M18 4v16M12 10l6-6 6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <div className="text-base font-medium text-white/90">
                Drop a document photo here
              </div>
              <div className="mt-2 text-xs text-white/40">
                or click to browse · paste from clipboard
              </div>
              <div className="mt-3 text-[11px] text-white/25">
                JPEG · PNG · WebP · TIFF · BMP
              </div>
            </button>

            {/* Camera button (mobile) */}
            <button
              type="button"
              onClick={() => cameraRef.current?.click()}
              className="mt-3 flex w-full items-center justify-center gap-2 text-xs text-white/35 transition hover:text-white/60"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z" />
                <circle cx="12" cy="13" r="4" />
              </svg>
              Take a photo
            </button>
          </motion.div>
        )}

        {/* ── WORKING ──────────────────────────────────────────── */}
        {phase === "working" && (
          <motion.div
            key="working"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-2xl border border-white/10 bg-white/5 p-6 text-left"
          >
            {/* Preview + file name header */}
            <div className="mb-5 flex items-center gap-3">
              {previewUrl && (
                <img
                  src={previewUrl}
                  alt="preview"
                  className="h-14 w-11 flex-shrink-0 rounded-md object-cover border border-white/10"
                />
              )}
              <div className="min-w-0">
                <div className="truncate text-xs font-medium text-white/70">{fileName}</div>
                <div className="text-[11px] text-white/35">Processing…</div>
              </div>
            </div>

            {/* Stage tracker */}
            <div className="space-y-3">
              {TRACKED.map((stage, i) => {
                const current = doc ? stageIndex(doc.status) : 0;
                const state = i < current ? "done" : i === current ? "active" : "pending";
                return (
                  <div key={stage.status} className="flex items-center gap-3">
                    <span
                      className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] ${
                        state === "done"
                          ? "bg-indigo-400 text-black"
                          : state === "active"
                            ? "bg-white/90 text-black"
                            : "bg-white/10 text-white/40"
                      }`}
                    >
                      {state === "done" ? "✓" : i + 1}
                    </span>
                    <span
                      className={`text-sm ${state === "pending" ? "text-white/35" : "text-white/80"}`}
                    >
                      {stage.label}
                    </span>
                    {state === "active" && (
                      <motion.span
                        className="ml-auto text-xs text-white/40"
                        animate={{ opacity: [0.3, 1, 0.3] }}
                        transition={{ repeat: Infinity, duration: 1.4 }}
                      >
                        working…
                      </motion.span>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Progress bar */}
            <div className="mt-5 h-1 w-full overflow-hidden rounded-full bg-white/10">
              <motion.div
                className="h-full bg-gradient-to-r from-indigo-300 to-fuchsia-300"
                animate={{ width: `${doc?.progress ?? 5}%` }}
                transition={{ duration: 0.4 }}
              />
            </div>
          </motion.div>
        )}

        {/* ── DONE ─────────────────────────────────────────────── */}
        {phase === "done" && doc && (
          <motion.div
            key="done"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-2xl border border-white/10 bg-white/5 p-6 text-left"
          >
            {/* Header: preview + type badge + title */}
            <div className="flex items-start gap-3">
              {previewUrl && (
                <img
                  src={previewUrl}
                  alt="preview"
                  className="h-16 w-12 flex-shrink-0 rounded-md object-cover border border-white/10"
                />
              )}
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  {doc.docType && doc.docType !== "UNKNOWN" && (
                    <span
                      className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${TYPE_COLORS[doc.docType] ?? TYPE_COLORS.UNKNOWN}`}
                    >
                      {typeLabel(doc.docType)}
                    </span>
                  )}
                </div>
                <div className="mt-1 truncate text-sm font-medium text-white/80">
                  {doc.title ?? doc.originalName}
                </div>
                {doc.summary && (
                  <p className="mt-1 text-xs leading-relaxed text-white/45 line-clamp-2">
                    {doc.summary}
                  </p>
                )}
              </div>
            </div>

            {/* Structured preview */}
            {doc.structure && <StructurePreview s={doc.structure} />}

            {/* Download buttons */}
            <div className="mt-5 flex flex-wrap gap-2">
              {doc.exports.length === 0 && (
                <span className="text-sm text-white/50">No exports produced.</span>
              )}
              {doc.exports.map((ex) => (
                <a
                  key={ex.format}
                  href={`${API}${ex.url}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-black transition hover:bg-white/90"
                >
                  {FORMAT_LABELS[ex.format] ?? `Download ${ex.format}`}
                </a>
              ))}
            </div>

            <button
              onClick={reset}
              className="mt-5 text-sm text-white/35 underline-offset-4 transition hover:text-white/65 hover:underline"
            >
              Process another
            </button>
          </motion.div>
        )}

        {/* ── ERROR ────────────────────────────────────────────── */}
        {phase === "error" && (
          <motion.div
            key="error"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-2xl border border-red-400/30 bg-red-500/10 p-6 text-left"
          >
            <div className="text-base font-medium text-red-200">
              Couldn&apos;t process that
            </div>
            <div className="mt-1 break-words text-sm text-red-200/70">{error}</div>
            <button
              onClick={reset}
              className="mt-5 rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-white/80 transition hover:bg-white/5"
            >
              Try again
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
