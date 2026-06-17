"use client";

import { use, useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import {
  JOB_STAGES,
  type DocumentResponse,
  type JobStatus,
} from "@docres/shared-types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const POLL_MS = 1500;

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

// ─── Navbar ──────────────────────────────────────────────────────────────────

function Navbar() {
  return (
    <header className="flex items-center justify-between border-b border-white/8 px-5 py-3.5">
      <Link
        href="/"
        className="flex items-center gap-2 text-sm text-white/50 transition hover:text-white/80"
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
          <line x1="19" y1="12" x2="5" y2="12" />
          <polyline points="12 19 5 12 12 5" />
        </svg>
        SuperDoc
      </Link>
      <Link
        href="/"
        className="rounded-lg border border-white/12 px-3 py-1.5 text-sm text-white/60 transition hover:bg-white/5 hover:text-white/80"
      >
        Process another
      </Link>
    </header>
  );
}

// ─── Processing view ──────────────────────────────────────────────────────────

function ProcessingView({
  doc,
  thumbnail,
}: {
  doc: DocumentResponse | null;
  thumbnail: string | null;
}) {
  return (
    <div className="flex flex-1 items-center justify-center px-6 py-20">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-sm"
      >
        {thumbnail && (
          <div className="mb-8 flex justify-center">
            <img
              src={thumbnail}
              alt="preview"
              className="h-28 w-22 rounded-xl object-cover border border-white/10 shadow-2xl shadow-black/40"
            />
          </div>
        )}

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

        <div className="mt-6 h-1 w-full overflow-hidden rounded-full bg-white/10">
          <motion.div
            className="h-full bg-gradient-to-r from-indigo-300 to-fuchsia-300"
            animate={{ width: `${doc?.progress ?? 5}%` }}
            transition={{ duration: 0.4 }}
          />
        </div>

        {!doc && (
          <p className="mt-4 text-center text-xs text-white/25">
            AI inference may take a minute or two.
          </p>
        )}
      </motion.div>
    </div>
  );
}

// ─── Result view ──────────────────────────────────────────────────────────────

function ResultView({
  doc,
  thumbnail,
}: {
  doc: DocumentResponse;
  thumbnail: string | null;
}) {
  const pdfExport = doc.exports.find((e) => e.format === "PDF");
  const docType =
    doc.docType && doc.docType !== "UNKNOWN" ? doc.docType : null;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-1 flex-col lg:flex-row"
    >
      {/* ── LEFT: PDF iframe preview ──────────────────────── */}
      <div className="relative flex-shrink-0 bg-white/[0.015] lg:w-[46%] lg:border-r lg:border-white/8">
        {pdfExport ? (
          <iframe
            src={`${API}${pdfExport.url}`}
            title="Document preview"
            className="h-[55vh] w-full lg:h-full"
          />
        ) : thumbnail ? (
          <div className="flex h-[50vh] items-center justify-center p-8 lg:h-full">
            <img
              src={thumbnail}
              alt="Original document"
              className="max-h-full max-w-full rounded-lg object-contain shadow-2xl shadow-black/40"
            />
          </div>
        ) : (
          <div className="flex h-[50vh] items-center justify-center lg:h-full">
            <span className="text-sm text-white/20">No preview available</span>
          </div>
        )}
      </div>

      {/* ── RIGHT: Structured result ───────────────────────── */}
      <div className="flex-1 overflow-y-auto px-6 py-8 lg:px-8">
        {/* Type badge + title */}
        <div>
          {docType && (
            <span
              className={`inline-block rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${TYPE_COLORS[docType] ?? TYPE_COLORS.UNKNOWN}`}
            >
              {docType.replace(/_/g, " ")}
            </span>
          )}
          <h1 className="mt-2.5 text-2xl font-semibold leading-snug text-white/90">
            {doc.title ?? doc.originalName}
          </h1>
          {doc.summary && (
            <p className="mt-2 text-sm leading-relaxed text-white/50">
              {doc.summary}
            </p>
          )}
        </div>

        {/* Key facts (metadata) */}
        {doc.structure?.metadata &&
          Object.keys(doc.structure.metadata).length > 0 && (
            <div className="mt-7">
              <SectionLabel>Key facts</SectionLabel>
              <div className="overflow-hidden rounded-xl border border-white/8">
                {Object.entries(doc.structure.metadata)
                  .slice(0, 10)
                  .map(([k, v], i, arr) => (
                    <div
                      key={k}
                      className={`flex px-4 py-2.5 ${i < arr.length - 1 ? "border-b border-white/5" : ""}`}
                    >
                      <span className="w-2/5 text-xs text-white/40">{k}</span>
                      <span className="flex-1 text-xs text-white/80">{v}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}

        {/* Sections */}
        {doc.structure?.sections && doc.structure.sections.length > 0 && (
          <div className="mt-7">
            <SectionLabel>
              {doc.structure.sections.length} section
              {doc.structure.sections.length !== 1 ? "s" : ""}
            </SectionLabel>
            <div className="space-y-2">
              {doc.structure.sections.map((sec, i) => {
                const heading = sec.heading?.value ?? null;
                const conf = sec.heading?.confidence ?? 1;
                const tableCount = sec.tables?.length ?? 0;
                const kvCount = sec.keyValues?.length ?? 0;
                const pCount = sec.paragraphs?.length ?? 0;
                return (
                  <div
                    key={i}
                    className="rounded-xl border border-white/8 bg-white/[0.025] px-4 py-3"
                  >
                    <div className="flex items-center gap-2">
                      {heading ? (
                        <span className="text-sm font-medium text-white/80">
                          {heading}
                        </span>
                      ) : (
                        <em className="text-sm text-white/30">untitled</em>
                      )}
                      {conf < 0.7 && (
                        <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
                      )}
                      {conf >= 0.7 && conf < 0.85 && (
                        <span className="h-1.5 w-1.5 rounded-full bg-yellow-400" />
                      )}
                    </div>
                    {pCount > 0 && (
                      <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-white/40">
                        {sec.paragraphs[0]}
                      </p>
                    )}
                    {(kvCount > 0 || tableCount > 0) && (
                      <div className="mt-1.5 flex gap-3 text-[10px] text-white/25">
                        {kvCount > 0 && (
                          <span>
                            {kvCount} field{kvCount !== 1 ? "s" : ""}
                          </span>
                        )}
                        {tableCount > 0 && (
                          <span>
                            {tableCount} table{tableCount !== 1 ? "s" : ""}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Signatures */}
        {doc.structure?.signatures && doc.structure.signatures.length > 0 && (
          <div className="mt-7">
            <SectionLabel>Signatures &amp; stamps</SectionLabel>
            <div className="flex flex-wrap gap-2">
              {doc.structure.signatures.map((sig, i) => (
                <span
                  key={i}
                  className="rounded border border-dashed border-white/20 px-2 py-0.5 text-[10px] text-white/40"
                >
                  {sig.kind.toUpperCase()}
                  {sig.label ? ` — ${sig.label}` : ""}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Downloads */}
        <div className="mt-8">
          <SectionLabel>Downloads</SectionLabel>
          <div className="flex flex-wrap gap-2">
            {doc.exports.map((ex) => (
              <a
                key={ex.format}
                href={`${API}${ex.url}`}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-black transition hover:bg-white/90"
              >
                {FORMAT_LABELS[ex.format] ?? `Download ${ex.format}`}
              </a>
            ))}
            {doc.exports.length === 0 && (
              <span className="text-sm text-white/35">No exports produced.</span>
            )}
          </div>
        </div>

        {/* Processed at */}
        <p className="mt-8 text-[11px] text-white/20">
          {doc.originalName} · processed{" "}
          {new Date(doc.createdAt).toLocaleString()}
        </p>
      </div>
    </motion.div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2.5 text-[10px] font-semibold uppercase tracking-widest text-white/30">
      {children}
    </div>
  );
}

// ─── Error view ───────────────────────────────────────────────────────────────

function ErrorView({ doc }: { doc: DocumentResponse }) {
  return (
    <div className="flex flex-1 items-center justify-center px-6 py-20">
      <div className="text-center">
        <div className="mb-2 text-base font-medium text-red-200">
          Processing failed
        </div>
        <div className="mb-6 max-w-sm text-sm text-red-200/60">{doc.error}</div>
        <Link
          href="/"
          className="text-sm text-white/45 underline-offset-4 transition hover:text-white/75 hover:underline"
        >
          ← Try another document
        </Link>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DocumentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [doc, setDoc] = useState<DocumentResponse | null>(null);
  const [thumbnail, setThumbnail] = useState<string | null>(null);

  // Load thumbnail stored by the uploader
  useEffect(() => {
    try {
      const stored = sessionStorage.getItem(`preview-${id}`);
      if (stored) setThumbnail(stored);
    } catch {
      // sessionStorage unavailable (e.g. private browsing restrictions)
    }
  }, [id]);

  // Poll until terminal state
  useEffect(() => {
    let cancelled = false;
    async function poll() {
      while (!cancelled) {
        try {
          const res = await fetch(`${API}/document/${id}`);
          if (!res.ok) break;
          const data: DocumentResponse = await res.json();
          if (!cancelled) setDoc(data);
          if (data.status === "COMPLETED" || data.status === "FAILED") break;
          await new Promise<void>((r) => setTimeout(r, POLL_MS));
        } catch {
          break;
        }
      }
    }
    void poll();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const isTerminal =
    doc?.status === "COMPLETED" || doc?.status === "FAILED";

  return (
    <div className="relative flex min-h-screen flex-col">
      {/* Ambient glow */}
      <div className="pointer-events-none absolute left-1/2 top-[-8rem] h-[30rem] w-[30rem] -translate-x-1/2 rounded-full bg-indigo-500/12 blur-[120px]" />

      <Navbar />

      <AnimatePresence mode="wait">
        {!isTerminal && (
          <motion.div
            key="processing"
            className="flex flex-1"
            exit={{ opacity: 0 }}
          >
            <ProcessingView doc={doc} thumbnail={thumbnail} />
          </motion.div>
        )}

        {doc?.status === "FAILED" && (
          <motion.div
            key="error"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-1"
          >
            <ErrorView doc={doc} />
          </motion.div>
        )}

        {doc?.status === "COMPLETED" && (
          <motion.div
            key="result"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-1"
          >
            <ResultView doc={doc} thumbnail={thumbnail} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
