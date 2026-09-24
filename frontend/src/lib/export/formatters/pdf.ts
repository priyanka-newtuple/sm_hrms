import { jsPDF } from 'jspdf';
import autoTable from 'jspdf-autotable';
import type { ExportField, ExportRow } from '../types';
import { resolveFieldLabels } from '../fields';
import { serializeCellValue } from '../serialize';

/** Render rows as a simple landscape table PDF with a titled header. */
export function exportToPdf(rows: ExportRow[], fields: ExportField[], title: string): Blob {
  const doc = new jsPDF({ orientation: 'landscape' });
  const heading = title.trim() || 'Export';
  const labels = resolveFieldLabels(fields);

  doc.setFontSize(14);
  doc.text(heading, 14, 16);
  doc.setFontSize(9);
  doc.setTextColor(120);
  doc.text(`Exported ${new Date().toLocaleString()} · ${rows.length} rows`, 14, 22);

  if (fields.length === 0) {
    doc.setFontSize(11);
    doc.setTextColor(150);
    doc.text('No fields selected.', 14, 34);
    return doc.output('blob');
  }

  autoTable(doc, {
    startY: 28,
    head: [labels],
    body: rows.map((row) => fields.map((f) => serializeCellValue(row[f.key]))),
    styles: { fontSize: 8, cellPadding: 2, overflow: 'linebreak' },
    headStyles: { fillColor: [0, 71, 171], textColor: 255 },
  });

  return doc.output('blob');
}
