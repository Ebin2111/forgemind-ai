import type { ReactNode } from "react";

/**
 * Shows an AI answer: headings, numbered steps, bullets, **bold** and `code`, with [n] citations
 * turned into small buttons that jump to the matching source. Built from React elements, never raw HTML.
 */
const INLINE = /(\*\*[^*\n]+\*\*|\[\d{1,2}\]|`[^`\n]+`)/g;

function inline(text: string, onCite?: (n: number) => void): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) return <code key={i}>{part.slice(1, -1)}</code>;
    const cite = /^\[(\d{1,2})\]$/.exec(part);
    if (cite) {
      const n = Number(cite[1]);
      return onCite ? (
        <button key={i} type="button" className="cite" onClick={() => onCite(n)} aria-label={`Go to source ${n}`}>{n}</button>
      ) : (
        <sup key={i} className="cite-plain">[{n}]</sup>
      );
    }
    return part;
  });
}

type Block =
  | { kind: "h"; text: string }
  | { kind: "p"; text: string }
  | { kind: "ol" | "ul"; items: string[] };

export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  let list: { kind: "ol" | "ul"; items: string[] } | null = null;
  let para: string[] = [];
  const flushPara = () => {
    if (para.length) blocks.push({ kind: "p", text: para.join(" ") });
    para = [];
  };
  const flushList = () => {
    if (list) blocks.push(list);
    list = null;
  };
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    const heading = /^#{1,4}\s+(.+)$/.exec(line);
    const numbered = /^\d+[.)]\s+(.+)$/.exec(line);
    const bullet = /^[-*•]\s+(.+)$/.exec(line);
    if (!line) { flushPara(); flushList(); }
    else if (heading) { flushPara(); flushList(); blocks.push({ kind: "h", text: heading[1] }); }
    else if (numbered || bullet) {
      flushPara();
      const kind = numbered ? "ol" : "ul";
      if (!list || list.kind !== kind) { flushList(); list = { kind, items: [] }; }
      list.items.push((numbered ?? bullet)![1]);
    } else { flushList(); para.push(line); }
  }
  flushPara();
  flushList();
  return blocks;
}

export default function AnswerText({ text, onCite }: { text: string; onCite?: (n: number) => void }) {
  return (
    <div className="prose">
      {parseBlocks(text).map((b, i) => {
        if (b.kind === "h") return <h4 key={i}>{inline(b.text, onCite)}</h4>;
        if (b.kind === "p") return <p key={i}>{inline(b.text, onCite)}</p>;
        const Tag = b.kind;
        return <Tag key={i}>{b.items.map((item, j) => <li key={j}>{inline(item, onCite)}</li>)}</Tag>;
      })}
    </div>
  );
}