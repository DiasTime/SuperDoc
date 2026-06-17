"use client";

import { motion } from "framer-motion";
import { JOB_STAGES } from "@docres/shared-types";
import Uploader from "./_components/Uploader";

const TRACKED = JOB_STAGES.filter(
  (s) => s.status !== "QUEUED" && s.status !== "COMPLETED",
);

const STEP_DESCRIPTIONS: Record<string, string> = {
  RESTORING: "Straightens, denoises and colour-corrects the raw photo.",
  OCR: "Extracts every word with its position and confidence score.",
  UNDERSTANDING: "Identifies document type, fields, tables, and signatures.",
  RECONSTRUCTING: "Assembles clean PDF, editable DOCX, and structured JSON.",
};

const STEP_ICONS: Record<string, React.ReactNode> = {
  RESTORING: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="opacity-70">
      <path d="M12 3a9 9 0 100 18A9 9 0 0012 3z" /><path d="M9 12h6M12 9v6" />
    </svg>
  ),
  OCR: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="opacity-70">
      <rect x="3" y="3" width="18" height="18" rx="2" /><path d="M7 8h10M7 12h6M7 16h8" />
    </svg>
  ),
  UNDERSTANDING: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="opacity-70">
      <circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M2 12h3M19 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12" />
    </svg>
  ),
  RECONSTRUCTING: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="opacity-70">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  ),
};

const OUTPUTS = [
  {
    format: "PDF",
    label: "Clean PDF",
    desc: "Searchable, colour-accurate, print-ready.",
    dot: "bg-red-400",
  },
  {
    format: "DOCX",
    label: "Editable DOCX",
    desc: "Opens in Word or Google Docs.",
    dot: "bg-blue-400",
  },
  {
    format: "JSON",
    label: "Structured JSON",
    desc: "Typed fields: type, sections, tables, signatures.",
    dot: "bg-emerald-400",
  },
];

// ─── Before/After visual (div-only mockup) ───────────────────────────────────

function BeforeAfterVisual() {
  return (
    <div className="relative mt-14 flex w-full max-w-2xl items-center justify-center gap-4 sm:gap-6">
      {/* BEFORE card */}
      <motion.div
        initial={{ opacity: 0, x: -24, rotate: -4 }}
        animate={{ opacity: 1, x: 0, rotate: -3 }}
        transition={{ duration: 0.6, delay: 0.3 }}
        className="relative w-[42%] overflow-hidden rounded-xl"
        style={{ aspectRatio: "3/4" }}
      >
        {/* Bad-photo background */}
        <div className="absolute inset-0 bg-gradient-to-br from-stone-700 via-stone-600 to-stone-800" />
        <div className="absolute inset-0 bg-gradient-to-tr from-black/60 via-transparent to-black/25" />
        {/* Skewed content (simulates a shot at an angle) */}
        <div
          className="relative p-4 pt-6"
          style={{ transform: "rotate(2deg) skew(-1deg)" }}
        >
          <div className="space-y-2 opacity-55">
            {/* "Header" lines */}
            <div className="h-3 w-2/3 rounded bg-stone-300 opacity-75" />
            <div className="h-1.5 w-full rounded bg-stone-400 opacity-50" />
            <div className="h-1.5 w-4/5 rounded bg-stone-400 opacity-45" />
            <div className="mt-3 h-1.5 w-3/4 rounded bg-stone-300 opacity-60" />
            <div className="h-1.5 w-full rounded bg-stone-400 opacity-40" />
            <div className="h-1.5 w-5/6 rounded bg-stone-400 opacity-50" />
            <div className="mt-2 h-1.5 w-2/3 rounded bg-stone-300 opacity-45" />
            <div className="h-1.5 w-full rounded bg-stone-400 opacity-38" />
            {/* "Table" rows */}
            <div className="mt-3 grid grid-cols-3 gap-1 opacity-45">
              {Array.from({ length: 9 }).map((_, i) => (
                <div key={i} className="h-1.5 rounded bg-stone-400" />
              ))}
            </div>
          </div>
        </div>
        {/* Shadow corners (bad phone photo) */}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/30 via-transparent to-black/60" />
        {/* Label */}
        <div className="absolute bottom-2.5 left-2.5 rounded bg-amber-500/80 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-black">
          Your photo
        </div>
      </motion.div>

      {/* Arrow */}
      <motion.div
        initial={{ opacity: 0, scale: 0.6 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4, delay: 0.5 }}
        className="flex flex-col items-center gap-1 text-white/25"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
        </svg>
        <span className="text-[9px] uppercase tracking-widest">AI</span>
      </motion.div>

      {/* AFTER card */}
      <motion.div
        initial={{ opacity: 0, x: 24 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.6, delay: 0.4 }}
        className="relative w-[42%] overflow-hidden rounded-xl bg-white shadow-2xl shadow-black/50"
        style={{ aspectRatio: "3/4" }}
      >
        <div className="p-3 pt-3.5">
          {/* Type badge */}
          <div className="mb-1.5 inline-block rounded bg-blue-600 px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wider text-white">
            Invoice
          </div>
          {/* Title */}
          <div className="mb-0.5 h-2.5 w-3/4 rounded bg-slate-800" />
          <div className="mb-3 h-1.5 w-1/2 rounded bg-slate-300" />
          {/* KV rows */}
          <div className="mb-3 space-y-1.5">
            {[[0.38, 0.28], [0.32, 0.35], [0.42, 0.22]].map(([kw, vw], i) => (
              <div key={i} className="flex items-center gap-2">
                <div className="h-1.5 rounded bg-slate-300" style={{ width: `${kw * 100}%` }} />
                <div className="h-1.5 rounded bg-slate-600" style={{ width: `${vw * 100}%` }} />
              </div>
            ))}
          </div>
          {/* Table */}
          <div className="overflow-hidden rounded border border-slate-200">
            {[[0.45, 0.28, 0.22], [0.45, 0.28, 0.22], [0.45, 0.28, 0.22]].map((cols, i) => (
              <div key={i} className={`flex gap-0.5 p-1 ${i === 0 ? "bg-slate-100" : ""}`}>
                {cols.map((w, j) => (
                  <div
                    key={j}
                    className={`h-1.5 rounded ${i === 0 ? "bg-slate-400" : "bg-slate-300"}`}
                    style={{ width: `${w * 100}%` }}
                  />
                ))}
              </div>
            ))}
          </div>
          {/* Stamp */}
          <div className="absolute bottom-3 right-3 flex h-9 w-9 rotate-[-15deg] items-center justify-center rounded-full border-2 border-emerald-500/50 text-[9px] font-bold text-emerald-600/60">
            OK
          </div>
        </div>
        {/* Label */}
        <div className="absolute bottom-2.5 left-2.5 rounded bg-emerald-500 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white">
          Reconstructed
        </div>
      </motion.div>
    </div>
  );
}

// ─── How it works ─────────────────────────────────────────────────────────────

function HowItWorks() {
  return (
    <section className="mx-auto mt-28 w-full max-w-4xl px-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5 }}
        className="mb-10 text-center"
      >
        <h2 className="text-xl font-semibold text-white/80">How it works</h2>
        <p className="mt-2 text-sm text-white/40">Four stages, seconds to minutes depending on the model.</p>
      </motion.div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {TRACKED.map((stage, i) => (
          <motion.div
            key={stage.status}
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.4, delay: i * 0.08 }}
            className="rounded-xl border border-white/8 bg-white/[0.03] p-5"
          >
            <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-lg bg-white/8 text-white/70">
              {STEP_ICONS[stage.status] ?? (
                <span className="text-xs font-bold text-white/50">{i + 1}</span>
              )}
            </div>
            <div className="mb-1 text-sm font-medium text-white/80">{stage.label}</div>
            <div className="text-[11px] leading-relaxed text-white/40">
              {STEP_DESCRIPTIONS[stage.status]}
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

// ─── Output badges ────────────────────────────────────────────────────────────

function OutputBadges() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5 }}
      className="mx-auto mt-16 flex max-w-2xl flex-wrap items-stretch justify-center gap-3 px-6"
    >
      {OUTPUTS.map((o) => (
        <div
          key={o.format}
          className="flex items-center gap-3 rounded-xl border border-white/8 bg-white/[0.03] px-5 py-3.5"
        >
          <span className={`h-2 w-2 rounded-full ${o.dot}`} />
          <div>
            <div className="text-sm font-medium text-white/80">{o.label}</div>
            <div className="text-[11px] text-white/40">{o.desc}</div>
          </div>
        </div>
      ))}
    </motion.div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Home() {
  return (
    <main className="relative min-h-screen overflow-hidden">
      {/* Ambient glows */}
      <div className="pointer-events-none absolute left-1/2 top-[-10rem] h-[36rem] w-[36rem] -translate-x-1/2 rounded-full bg-indigo-500/18 blur-[130px]" />
      <div className="pointer-events-none absolute bottom-[10rem] left-1/2 h-[28rem] w-[28rem] -translate-x-1/2 rounded-full bg-fuchsia-600/10 blur-[140px]" />

      {/* ── Hero ─────────────────────────────────────────── */}
      <section className="mx-auto flex max-w-5xl flex-col items-center px-6 pt-28 text-center">
        <motion.span
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs font-medium tracking-wide text-white/70"
        >
          Not OCR — document reconstruction
        </motion.span>

        <motion.h1
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.06 }}
          className="mt-6 text-balance text-5xl font-semibold leading-tight tracking-tight sm:text-6xl"
        >
          Bad photo in.
          <br />
          <span className="bg-gradient-to-r from-indigo-300 to-fuchsia-300 bg-clip-text text-transparent">
            Source-quality document out.
          </span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.12 }}
          className="mt-5 max-w-lg text-pretty text-lg text-white/55"
        >
          Upload a skewed scan, a phone photo, or an old PDF. Get back a clean
          PDF, editable DOCX, and structured JSON — with every field typed and
          grounded.
        </motion.p>

        {/* Before / After comparison */}
        <BeforeAfterVisual />

        {/* Upload CTA */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.55 }}
          className="flex w-full flex-col items-center"
        >
          <Uploader />
        </motion.div>
      </section>

      {/* ── How it works ─────────────────────────────────── */}
      <HowItWorks />

      {/* ── What you get ─────────────────────────────────── */}
      <OutputBadges />

      {/* ── Footer ───────────────────────────────────────── */}
      <footer className="mt-28 border-t border-white/5 py-8 text-center text-xs text-white/25">
        Document Resurrection AI — M2 complete: document intelligence · DOCX · rich PDF.{" "}
        <span className="text-white/15">See PLAN.md for the roadmap.</span>
      </footer>
    </main>
  );
}
