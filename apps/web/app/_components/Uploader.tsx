"use client";

import { useCallback, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  JOB_STAGES,
  type DocumentResponse,
  type JobStatus,
  type UploadResponse,
} from "@docres/shared-types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const POLL_MS = 1500;
const ACCEPT = "image/jpeg,image/png,image/webp,image/tiff,image/bmp";

// Stages shown in the live tracker (skip QUEUED/COMPLETED bookends).
const TRACKED = JOB_STAGES.filter(
  (s) => s.status !== "QUEUED" && s.status !== "COMPLETED",
);

function stageIndex(status: JobStatus): number {
  const i = TRACKED.findIndex((s) => s.status === status);
  if (status === "COMPLETED") return TRACKED.length;
  return i;
}

type Phase = "idle" | "working" | "done" | "error";

export default function Uploader() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [doc, setDoc] = useState<DocumentResponse | null>(null);
  const [error, setError] = useState<string>("");
  const [dragging, setDragging] = useState(false);

  const reset = useCallback(() => {
    setPhase("idle");
    setDoc(null);
    setError("");
  }, []);

  const poll = useCallback(async (id: string) => {
    // Poll /document/:id until the job reaches a terminal state.
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
      reset();
      setPhase("working");
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
    [poll, reset],
  );

  const onFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0];
      if (file) void start(file);
    },
    [start],
  );

  return (
    <div className="mt-12 w-full max-w-xl">
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => onFiles(e.target.files)}
      />

      <AnimatePresence mode="wait">
        {phase === "idle" && (
          <motion.button
            key="drop"
            type="button"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
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
            className={`w-full rounded-2xl border border-dashed px-8 py-14 text-center transition ${
              dragging
                ? "border-indigo-300/60 bg-indigo-500/10"
                : "border-white/15 bg-white/5 hover:bg-white/[0.07]"
            }`}
          >
            <div className="text-base font-medium text-white/90">
              Drop a document photo, or click to choose
            </div>
            <div className="mt-2 text-xs text-white/40">
              JPEG, PNG, WebP, TIFF or BMP
            </div>
          </motion.button>
        )}

        {phase === "working" && (
          <motion.div
            key="working"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-2xl border border-white/10 bg-white/5 p-6 text-left"
          >
            <div className="space-y-3">
              {TRACKED.map((stage, i) => {
                const current = doc ? stageIndex(doc.status) : 0;
                const state =
                  i < current ? "done" : i === current ? "active" : "pending";
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
                      className={`text-sm ${
                        state === "pending" ? "text-white/35" : "text-white/80"
                      }`}
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
            <div className="mt-5 h-1 w-full overflow-hidden rounded-full bg-white/10">
              <motion.div
                className="h-full bg-gradient-to-r from-indigo-300 to-fuchsia-300"
                animate={{ width: `${doc?.progress ?? 5}%` }}
                transition={{ duration: 0.4 }}
              />
            </div>
          </motion.div>
        )}

        {phase === "done" && doc && (
          <motion.div
            key="done"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-2xl border border-white/10 bg-white/5 p-6 text-left"
          >
            <div className="text-base font-medium text-white/90">
              Done — {doc.originalName}
            </div>
            <div className="mt-1 text-xs text-white/40">
              Your clean, searchable document is ready.
            </div>
            <div className="mt-5 flex flex-wrap gap-3">
              {doc.exports.length === 0 && (
                <span className="text-sm text-white/50">No exports produced.</span>
              )}
              {doc.exports.map((ex) => (
                <a
                  key={ex.format}
                  href={`${API}${ex.url}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-black transition hover:bg-white/90"
                >
                  Download {ex.format}
                </a>
              ))}
            </div>
            <button
              onClick={reset}
              className="mt-5 text-sm text-white/50 underline-offset-4 transition hover:text-white/80 hover:underline"
            >
              Process another
            </button>
          </motion.div>
        )}

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
