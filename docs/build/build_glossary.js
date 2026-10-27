// Отдельный документ «Глоссарий.docx» проекта PortaGraph
const fs = require("fs");
const L = require("./lib");
const G = require("./glossary_data");
const { d, P, H2, table } = L;
const { Paragraph, TextRun, AlignmentType } = d;

const c = (t, o = {}) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: o.after ?? 60 },
  children: [new TextRun({ text: t, bold: o.bold, size: o.size ?? 24 })] });

const sorted = (arr) => [...arr].sort((a, b) => a[0].localeCompare(b[0], "ru"));
const ru = sorted(G.ru), en = sorted(G.en);

const children = [
  c("ФГБОУ ВО «Кубанский государственный аграрный университет имени И. Т. Трубилина»", { size: 22 }),
  c("Факультет прикладной информатики · дисциплина «Программная инженерия»", { size: 22, after: 400 }),
  c("ГЛОССАРИЙ ПРОЕКТА", { size: 32, bold: true, after: 80 }),
  c("«PortaGraph — интеллектуальная система анализа и визуализации программных проектов»", { size: 26, bold: true, after: 200 }),
  c("Команда: Казанкова Анастасия (тимлид), Чиженко Максим · группа ПИ24", { size: 22, after: 60 }),
  c("Редакция от 28.10.2026 (спринт 3)", { size: 22, after: 300 }),
  P("Глоссарий фиксирует единый язык команды: термины предметной области, названия вариантов использования, сущностей, модулей, ролей и состояний системы. Он устраняет неоднозначность при трактовке требований и связывает понятия предметной области с классами и модулями архитектуры. Глоссарий ведётся с первого спринта и пополняется в каждом следующем."),
  P("Термины упорядочены по алфавиту и разделены на две группы. В столбце «Синонимы / обозначение в системе» указаны синонимы, а также классы, перечисления, статусы и номера вариантов использования, соответствующие термину. Перекрёстные ссылки даны в виде «см. …»."),
  H2(`1. Термины на русском языке (${ru.length})`),
  ...table(null, ["№", "Термин", "Определение", "Синонимы / обозначение в системе"], ru.map((r, i) => [String(i + 1), ...r]), [500, 2300, 4638, 2200], { size: 19, cantSplit: true }),
  H2(`2. Англоязычные термины и аббревиатуры (${en.length})`),
  ...table(null, ["№", "Термин", "Определение", "Синонимы / обозначение в системе"], en.map((r, i) => [String(ru.length + i + 1), ...r]), [500, 2300, 4638, 2200], { size: 19, cantSplit: true }),
];

const doc = new d.Document({ creator: "Казанкова А., Чиженко М.", title: "Глоссарий проекта PortaGraph",
  styles: L.styles, numbering: L.numbering,
  sections: [{ properties: L.portrait, footers: L.footer(), children }] });
d.Packer.toBuffer(doc).then((b) => { fs.writeFileSync(process.argv[2] || "Глоссарий.docx", b); console.log("ok"); });
