"use client";

import { motion } from "framer-motion";
import { JOB_STAGES } from "@docres/shared-types";
import Uploader from "./_components/Uploader";

export default function Home() {
  return (
    <main className="relative min-h-screen overflow-hidden">
      {/* ambient glow */}
      <div className="pointer-events-none absolute left-1/2 top-[-10rem] h-[32rem] w-[32rem] -translate-x-1/2 rounded-full bg-indigo-500/20 blur-[120px]" />

      <section className="mx-auto flex max-w-5xl flex-col items-center px-6 pt-32 text-center">
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
          transition={{ duration: 0.6, delay: 0.05 }}
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
          className="mt-6 max-w-xl text-pretty text-lg text-white/60"
        >
          Upload a skewed scan, a screenshot, or an old PDF. Get back a clean PDF,
          editable DOCX, and structured JSON that looks like the original file.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.18 }}
          className="flex w-full flex-col items-center"
        >
          <Uploader />
        </motion.div>

        {/* pipeline preview */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.3 }}
          className="mt-20 flex flex-wrap items-center justify-center gap-2 text-xs text-white/50"
        >
          {JOB_STAGES.filter((s) => s.status !== "QUEUED" && s.status !== "COMPLETED").map(
            (stage, i, arr) => (
              <span key={stage.status} className="flex items-center gap-2">
                <span className="rounded-md border border-white/10 bg-white/5 px-3 py-1.5">
                  {stage.label}
                </span>
                {i < arr.length - 1 && <span className="text-white/25">→</span>}
              </span>
            ),
          )}
        </motion.div>
      </section>

      <footer className="mt-32 border-t border-white/5 py-8 text-center text-xs text-white/30">
        Document Resurrection AI — M1.2: OCR + searchable PDF. See PLAN.md for the roadmap.
      </footer>
    </main>
  );
}
