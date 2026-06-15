/**
 * Shared contract between web, api, and worker.
 * These mirror the Prisma enums and the worker's pipeline output.
 * Keep in sync with prisma/schema.prisma and apps/worker pipeline types.
 */

// ─────────────────────────── Enums ───────────────────────────

export type JobStatus =
  | "QUEUED"
  | "RESTORING"
  | "OCR"
  | "UNDERSTANDING"
  | "RECONSTRUCTING"
  | "COMPLETED"
  | "FAILED";

export type DocumentType =
  | "UNKNOWN"
  | "CONTRACT"
  | "INVOICE"
  | "ACT"
  | "CERTIFICATE"
  | "PASSPORT"
  | "ID_CARD"
  | "FORM"
  | "COMMERCIAL_OFFER";

export type ExportFormat = "PDF" | "DOCX" | "JSON";

export type Plan = "FREE" | "PRO" | "BUSINESS" | "ENTERPRISE";

// ─────────────────────────── Geometry / OCR ───────────────────────────

/** Axis-aligned or rotated box as 4 corner points [x, y], normalized 0–1. */
export type BoundingBox = [number, number][];

export interface OcrWord {
  text: string;
  confidence: number; // 0–1
  box: BoundingBox;
}

export interface OcrResult {
  words: OcrWord[];
  /** Detected text language(s), best-effort. */
  languages: string[];
  /** Width/height of the image the boxes are normalized against. */
  imageSize: { width: number; height: number };
}

// ─────────────────────────── Document structure ───────────────────────────
// Every extracted field is grounded: it carries the OCR confidence and the
// source box, so the UI can flag low-confidence values and never silently trust
// hallucinated text.

export interface Grounded<T> {
  value: T;
  confidence: number; // 0–1
  box?: BoundingBox;
}

export interface KeyValue {
  key: string;
  value: Grounded<string>;
}

export interface TableCell {
  text: string;
  rowSpan: number;
  colSpan: number;
  confidence: number;
}

export interface DocTable {
  rows: TableCell[][];
  caption?: string;
}

export interface DocSection {
  heading?: Grounded<string>;
  level: number; // 1 = top
  paragraphs: string[];
  tables: DocTable[];
  keyValues: KeyValue[];
}

export interface SignatureMark {
  kind: "signature" | "stamp" | "seal";
  box: BoundingBox;
  label?: string;
}

export interface DocumentStructure {
  type: DocumentType;
  title?: string;
  summary?: string;
  sections: DocSection[];
  signatures: SignatureMark[];
  metadata: Record<string, string>;
}

// ─────────────────────────── API DTOs ───────────────────────────

export interface UploadResponse {
  documentId: string;
  jobId: string;
}

export interface DocumentResponse {
  id: string;
  originalName: string;
  docType: DocumentType;
  title?: string;
  summary?: string;
  status: JobStatus;
  progress: number; // 0–100
  error?: string;
  structure?: DocumentStructure;
  exports: { format: ExportFormat; url: string }[];
  createdAt: string;
}

/** Human-facing labels + ordering for the processing UI. */
export const JOB_STAGES: { status: JobStatus; label: string }[] = [
  { status: "QUEUED", label: "Queued" },
  { status: "RESTORING", label: "Restoring image" },
  { status: "OCR", label: "Reading text" },
  { status: "UNDERSTANDING", label: "Understanding document" },
  { status: "RECONSTRUCTING", label: "Rebuilding document" },
  { status: "COMPLETED", label: "Done" },
];
