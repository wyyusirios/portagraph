// Общие помощники для сборки .docx (docx-js 9)
const fs = require("fs");
const d = require("docx");
const {
  Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType, AlignmentType,
  HeadingLevel, ImageRun, BorderStyle, PageBreak, VerticalAlign, TableLayoutType,
} = d;

const FONT = "Times New Roman";
const PORTRAIT_W = 9638;   // ширина текста A4: 21 см − 2,5 − 1,5 см (в DXA)
const LANDSCAPE_W = 14570; // ширина текста A4 альбомной ориентации (29,7 − 2,0 − 2,0 см)

let figNo = 0, tabNo = 0;

// Простая разметка: **жирный**, _курсив_, `код`
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|_[^_]+_|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith("`")) out.push(new TextRun({ text: t.slice(1, -1), font: "Courier New", size: (base.size || 24) - 2, ...base, }));
    else out.push(new TextRun({ text: t.slice(1, -1), italics: true, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}

const P = (text, o = {}) => new Paragraph({
  children: runs(text, o.run || {}),
  alignment: o.align ?? AlignmentType.JUSTIFIED,
  spacing: { after: o.after ?? 100, before: o.before ?? 0, line: o.line ?? 276 },
  indent: o.noIndent ? undefined : { firstLine: o.firstLine ?? 567 },
  keepNext: o.keepNext,
});
const Pn = (text, o = {}) => P(text, { ...o, noIndent: true });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)], pageBreakBefore: true, spacing: { after: 200 } });
const H1nb = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)], spacing: { after: 200 } });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)], spacing: { before: 240, after: 120 }, keepNext: true });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)], spacing: { before: 180, after: 80 }, keepNext: true });
const bullet = (text, level = 0) => new Paragraph({ children: runs(text), numbering: { reference: "bul", level }, spacing: { after: 60, line: 264 }, alignment: AlignmentType.JUSTIFIED });
const num = (text, ref = "num") => new Paragraph({ children: runs(text), numbering: { reference: ref, level: 0 }, spacing: { after: 60, line: 264 } });
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

function pngSize(path) {
  const b = fs.readFileSync(path);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}

// Рисунок с подписью «Рисунок N – …», ширина в пикселях (96 dpi), не выше maxH
function figure(path, caption, widthPx = 620, maxH = 820) {
  const { w, h } = pngSize(path);
  let W = widthPx, H = Math.round(widthPx * h / w);
  if (H > maxH) { H = maxH; W = Math.round(maxH * w / h); }
  figNo += 1;
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 }, keepNext: true,
      children: [new ImageRun({ type: "png", data: fs.readFileSync(path), transformation: { width: W, height: H },
        altText: { title: caption, description: caption, name: `fig${figNo}` } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
      children: [new TextRun({ text: `Рисунок ${figNo} – ${caption}`, italics: false, size: 22 })] }),
  ];
}

const border = { style: BorderStyle.SINGLE, size: 4, color: "8A94B8" };
const borders = { top: border, bottom: border, left: border, right: border };

function cell(content, width, o = {}) {
  const paras = (Array.isArray(content) ? content : [content]).map((c) =>
    typeof c === "string"
      ? new Paragraph({ children: runs(c, { size: o.size || 20, bold: o.bold }), spacing: { after: 40, line: 240 },
          alignment: o.center ? AlignmentType.CENTER : AlignmentType.LEFT })
      : c);
  return new TableCell({
    children: paras, borders, width: { size: width, type: WidthType.DXA },
    shading: o.fill ? { fill: o.fill, type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 }, verticalAlign: o.vAlign || VerticalAlign.TOP,
    columnSpan: o.span,
  });
}

// Таблица с подписью «Таблица N – …» над ней. rows — массивы строк/массивов строк.
function table(caption, headers, rows, widths, o = {}) {
  const total = widths.reduce((a, b) => a + b, 0);
  tabNo += 1;
  const out = [];
  if (caption) out.push(new Paragraph({ children: [new TextRun({ text: `Таблица ${tabNo} – ${caption}`, size: 22 })],
    spacing: { before: 160, after: 80 }, keepNext: true }));
  const trs = [new TableRow({ tableHeader: true, cantSplit: true,
    children: headers.map((h, i) => cell(h, widths[i], { bold: true, fill: "DCE3F7", size: o.size || 20 })) })];
  rows.forEach((r, ri) => {
    if (r.section) {
      trs.push(new TableRow({ cantSplit: true, children: [cell(r.section, total, { bold: true, fill: "F1F3F8", span: widths.length, size: o.size || 20 })] }));
      return;
    }
    trs.push(new TableRow({ cantSplit: o.cantSplit ?? true,
      children: r.map((c, i) => cell(c, widths[i], { size: o.size || 20, fill: o.fills ? o.fills(ri, i, c) : undefined,
        bold: o.boldFirst && i === 0 })) }));
  });
  out.push(new Table({ width: { size: total, type: WidthType.DXA }, columnWidths: widths, rows: trs, layout: TableLayoutType.FIXED }));
  out.push(new Paragraph({ children: [], spacing: { after: 120 } }));
  return out;
}

// Таблица «поле — значение» (расширенное описание варианта использования)
function kvTable(caption, pairs, widths = [2600, 7038]) {
  tabNo += 1;
  const total = widths[0] + widths[1];
  const rows = pairs.map(([k, v]) => {
    const vals = Array.isArray(v) ? v : [v];
    const paras = vals.map((t) => new Paragraph({ children: runs(t, { size: 20 }), spacing: { after: 40, line: 240 } }));
    return new TableRow({ cantSplit: false, children: [cell(k, widths[0], { bold: true, fill: "EEF2FB" }), new TableCell({
      children: paras, borders, width: { size: widths[1], type: WidthType.DXA }, margins: { top: 50, bottom: 50, left: 90, right: 90 } })] });
  });
  return [
    new Paragraph({ children: [new TextRun({ text: `Таблица ${tabNo} – ${caption}`, size: 22 })], spacing: { before: 160, after: 80 }, keepNext: true }),
    new Table({ width: { size: total, type: WidthType.DXA }, columnWidths: widths, rows, layout: TableLayoutType.FIXED }),
    new Paragraph({ children: [], spacing: { after: 160 } }),
  ];
}

function codeBlock(lines) {
  return lines.map((l, i) => new Paragraph({
    children: [new TextRun({ text: l.length ? l : " ", font: "Courier New", size: 17 })],
    spacing: { after: 0, line: 228 }, shading: { fill: "F4F6FB", type: ShadingType.CLEAR, color: "auto" },
    indent: { left: 200 }, keepLines: true,
  }));
}

const numbering = {
  config: [
    { reference: "bul", levels: [
      { level: 0, format: d.LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 709, hanging: 284 } } } },
      { level: 1, format: d.LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 1134, hanging: 284 } } } } ] },
    { reference: "num", levels: [
      { level: 0, format: d.LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 709, hanging: 360 } } } } ] },
  ],
};

const styles = {
  default: { document: { run: { font: FONT, size: 24 } } },
  paragraphStyles: [
    { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: 30, bold: true, font: FONT, color: "1B2559" }, paragraph: { spacing: { before: 120, after: 200 }, outlineLevel: 0 } },
    { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: 26, bold: true, font: FONT, color: "1B2559" }, paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
    { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: 24, bold: true, italics: true, font: FONT, color: "2F4AC0" }, paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 2 } },
  ],
};

function footer() {
  return { default: new d.Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
    children: [new TextRun({ children: [d.PageNumber.CURRENT], size: 20 })] })] }) };
}
const portrait = { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1418, right: 850 } } };
const landscape = { page: { size: { width: 11906, height: 16838, orientation: d.PageOrientation.LANDSCAPE },
  margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } };

module.exports = { d, P, Pn, H1, H1nb, H2, H3, bullet, num, pageBreak, figure, table, kvTable, codeBlock, runs, cell,
  numbering, styles, footer, portrait, landscape, PORTRAIT_W, LANDSCAPE_W, FONT };
