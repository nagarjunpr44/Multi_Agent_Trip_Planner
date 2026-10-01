import { Fragment } from "react";
import { safeUrl } from "@/lib/format";

// Tiny markdown subset for planner replies: paragraphs, bullet/numbered lists, headings,
// **bold** and bare links. Renders React elements only, so model output can't inject markup.

function inline(text: string) {
  return text.split(/(\*\*[^*]+\*\*|https?:\/\/[^\s)]+)/g).map((part, i) => {
    if (i % 2 === 0) return <Fragment key={i}>{part}</Fragment>;
    if (part.startsWith("**")) return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>;
    const href = safeUrl(part);
    return href ? <a key={i} href={href} target="_blank" rel="noopener" className="text-lagoon underline underline-offset-2 hover:text-coral">{part}</a> : part;
  });
}

export function Markdown({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const Tag = list.ordered ? "ol" : "ul";
    blocks.push(
      <Tag key={blocks.length} className={list.ordered ? "my-2 list-decimal space-y-1 pl-5 marker:text-coral" : "my-2 list-disc space-y-1 pl-5 marker:text-coral"}>
        {list.items.map((it, i) => <li key={i}>{inline(it)}</li>)}
      </Tag>,
    );
    list = null;
  };
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const m = line.match(/^\s*(?:[-*•]|(\d+)[.)])\s+(.*)/);
    if (m) {
      const ordered = Boolean(m[1]);
      if (list && list.ordered !== ordered) flush();
      list ??= { ordered, items: [] };
      list.items.push(m[2]);
      continue;
    }
    flush();
    if (!line.trim()) continue;
    const h = line.match(/^#{1,4}\s+(.*)/);
    blocks.push(h
      ? <h4 key={blocks.length} className="mt-3 font-display text-xl">{inline(h[1])}</h4>
      : <p key={blocks.length} className="my-1.5">{inline(line)}</p>);
  }
  flush();
  return <>{blocks}</>;
}
