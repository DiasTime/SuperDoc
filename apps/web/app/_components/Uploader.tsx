"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useRouter } from "next/navigation";
import type { UploadResponse } from "@docres/shared-types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ACCEPT = "image/jpeg,image/png,image/webp,image/tiff,image/bmp";

// Compress the picked image to a small JPEG thumbnail and save in sessionStorage
// so the document page can display it without access to the original File.
async function storeThumbnail(documentId: string, blobUrl: string): Promise<void> {
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new window.Image();
      el.onload = () => resolve(el);
      el.onerror = reject;
      el.src = blobUrl;
    });
    const MAX = 320;
    const scale = Math.min(1, MAX / Math.max(img.width, img.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    canvas.getContext("2d")?.drawImage(img, 0, 0, canvas.width, canvas.height);
    const thumb = canvas.toDataURL("image/jpeg", 0.75);
    sessionStorage.setItem(`preview-${documentId}`, thumb);
  } catch {
    // Compression unavailable — the document page will just skip the thumbnail.
  }
}

type Phase = "idle" | "uploading" | "error";

export default function Uploader() {
  const inputRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string>("");
  const [dragging, setDragging] = useState(false);
  const [fileName, setFileName] = useState<string>("");
  const previewUrlRef = useRef<string | null>(null);
  const router = useRouter();

  // Cleanup blob URL on unmount
  useEffect(() => {
    return () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    };
  }, []);

  const reset = useCallback(() => {
    setPhase("idle");
    setError("");
    setFileName("");
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }
  }, []);

  const start = useCallback(
    async (file: File) => {
      // Create a blob URL for the thumbnail before anything async
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = URL.createObjectURL(file);

      setFileName(file.name);
      setPhase("uploading");
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

        // Persist compressed thumbnail for the document page (survives navigation)
        await storeThumbnail(documentId, previewUrlRef.current!);

        // Enqueue processing, then navigate — document page takes over polling
        await fetch(`${API}/process/${documentId}`, { method: "POST" });
        router.push(`/document/${documentId}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "something went wrong");
        setPhase("error");
      }
    },
    [router],
  );

  const onFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0];
      if (file) void start(file);
    },
    [start],
  );

  // Paste from clipboard
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
        {/* ── IDLE ──────────────────────────────────────────── */}
        {phase === "idle" && (
          <motion.div
            key="idle"
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
                  : "border-white/15 bg-white/5 hover:border-white/25 hover:bg-white/[0.07]"
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
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z" />
                <circle cx="12" cy="13" r="4" />
              </svg>
              Take a photo
            </button>
          </motion.div>
        )}

        {/* ── UPLOADING ─────────────────────────────────────── */}
        {phase === "uploading" && (
          <motion.div
            key="uploading"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-2xl border border-white/10 bg-white/5 px-8 py-10 text-center"
          >
            <motion.div
              className="mb-5 flex justify-center"
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 1.2, ease: "linear" }}
            >
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                className="text-indigo-300"
              >
                <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.2" />
                <path d="M12 3a9 9 0 019 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </motion.div>
            <div className="text-sm font-medium text-white/70">Uploading…</div>
            {fileName && (
              <div className="mt-1 truncate text-xs text-white/35">{fileName}</div>
            )}
          </motion.div>
        )}

        {/* ── ERROR ─────────────────────────────────────────── */}
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
            <div className="mt-1 break-words text-sm text-red-200/70">
              {error}
            </div>
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
