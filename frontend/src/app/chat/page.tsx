"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import AnswerText from "@/components/AnswerText";
import Icon from "@/components/Icon";
import Orb from "@/components/Orb";
import SourceCard from "@/components/SourceCard";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/format";
import { useFetch } from "@/lib/useFetch";
import type { Equipment, Passage, Source } from "@/types";
import styles from "./chat.module.css";

const MIN_QUESTION = 2;
const MAX_QUESTION = 1000; // the backend rejects longer questions
const STORAGE_KEY = "forgemind.chat.v1";
const KEEP_MESSAGES = 40;
const SEND_ICON = "M5 12h14M13 6l6 6-6 6";
const SPARK_ICON = "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z";

interface Msg {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: Source[];
  meta?: { retrieval: string; generatedBy: string; latencyMs: number };
  error?: boolean;
}

const newId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;

function loadSaved(): Msg[] {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function save(messages: Msg[]) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-KEEP_MESSAGES)));
  } catch {
    /* private mode or storage full: the chat still works, it just is not remembered */
  }
}

/** Short heading-like lines from the indexed manuals (e.g. "Oil separator replacement") become suggested questions. */
function suggestionsFrom(passages: Passage[], equipment: Equipment[]): string[] {
  const seen = new Set<string>();
  const fromDocs: string[] = [];
  for (const p of passages) {
    const line = p.text.split("\n")[0].trim().replace(/[:.]$/, "");
    const key = line.toLowerCase();
    if (line.length < 8 || line.length > 70 || !/^[A-Za-z]/.test(line) || seen.has(key)) continue;
    if ((line.match(/[A-Za-z]/g)?.length ?? 0) < line.length * 0.6) continue;
    seen.add(key);
    fromDocs.push(`What does the documentation say about "${line}"?`);
    if (fromDocs.length === 3) break;
  }
  const fromEquipment = equipment.slice(0, 2).map((e) => `What are the common faults and checks for the ${e.name} (${e.tag})?`);
  return [...fromDocs, ...fromEquipment];
}

const generatedLabel = (g: string) =>
  g === "extractive" ? "Document excerpts" : g === "none" ? "No matching documents" : g;

function ChatView() {
  const params = useSearchParams();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [ready, setReady] = useState(false);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [flash, setFlash] = useState<{ id: string; n: number } | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const run = useRef(0);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const health = useFetch(() => api.health(), []);
  const ideas = useFetch(async () => {
    const [p, e] = await Promise.all([api.passages({ limit: 60 }), api.equipment()]);
    return suggestionsFrom(p.items, e);
  }, []);

  useEffect(() => {
    document.title = "Chat | ForgeMind AI";
    setMessages(loadSaved());
    setReady(true);
    const q = params.get("q");
    if (q) setDraft(q.slice(0, MAX_QUESTION));
    inputRef.current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (ready && !pending) save(messages);
  }, [messages, pending, ready]);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "end" });
  }, [messages, pending]);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [draft]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2200);
    return () => clearTimeout(t);
  }, [toast]);

  const ask = useCallback(async (question: string, history: Msg[]) => {
    const id = ++run.current;
    setMessages(history);
    setPending(true);
    try {
      const r = await api.ask(question);
      if (id !== run.current) return;
      setMessages([...history, {
        id: newId(), role: "assistant", text: r.answer, sources: r.sources,
        meta: { retrieval: r.retrieval_mode, generatedBy: r.generated_by, latencyMs: r.latency_ms },
      }]);
    } catch (err) {
      if (id !== run.current) return;
      setMessages([...history, { id: newId(), role: "assistant", text: errorMessage(err), error: true }]);
    } finally {
      if (id === run.current) setPending(false);
    }
  }, []);

  function send(text = draft) {
    const q = text.trim();
    if (pending || q.length < MIN_QUESTION) return;
    setDraft("");
    ask(q, [...messages, { id: newId(), role: "user", text: q }]);
  }

  function retry(index: number) {
    const question = messages[index - 1]?.text;
    if (question && !pending) ask(question, messages.slice(0, index));
  }

  function newChat() {
    run.current++;
    setMessages([]);
    setPending(false);
    setDraft("");
    save([]);
    inputRef.current?.focus();
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setToast("Answer copied");
    } catch {
      setToast("Could not copy. Select the text instead.");
    }
  }

  function jumpToSource(messageId: string, n: number) {
    document.getElementById(`m-${messageId}-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    setFlash({ id: messageId, n });
    setTimeout(() => setFlash(null), 1500);
  }

  const h = health.data;
  const empty = ready && messages.length === 0 && !pending;
  const lastAssistant = messages.length - 1;

  return (
    <>
      <section className={styles.chat} aria-label="Chat with ForgeMind AI">
        <header className={styles.head}>
          <Orb size={46} thinking={pending} />
          <div>
            <h1>ForgeMind Copilot</h1>
            <p className={styles.status}>
              {h ? (
                <>
                  <span><i className={`dot ${h.gemini_configured ? "ok" : "neutral"}`} />{h.gemini_configured ? "AI answers on" : "AI model off: showing document excerpts"}</span>
                  <span><i className="dot ok" />{h.semantic_search ? "Semantic search" : "Keyword search"}</span>
                  <span>{h.indexed_chunks.toLocaleString()} searchable passages</span>
                </>
              ) : (
                <span>{pending ? "Searching your documents…" : "Ask about equipment, procedures and maintenance"}</span>
              )}
            </p>
          </div>
          {messages.length > 0 && (
            <div className={styles.headActions}>
              <button type="button" className="ghost small" onClick={newChat}>New chat</button>
            </div>
          )}
        </header>

        <div className={styles.stream} aria-live="polite" aria-busy={pending}>
          {empty && (
            <div className={styles.welcome}>
              <span className={styles.glow}><Orb size={84} /></span>
              <h2>How can I help on the shop floor?</h2>
              <p>Answers come from your uploaded manuals and SOPs, with the page they were found on.</p>
              {h && h.indexed_chunks === 0 ? (
                <p>No documents are indexed yet. <Link href="/documents">Add a manual</Link> to get cited answers.</p>
              ) : (
                ideas.data && ideas.data.length > 0 && (
                  <div className={styles.suggestions}>
                    <span className={styles.suggestionLabel}>Try asking</span>
                    {ideas.data.map((s) => (
                      <button key={s} type="button" className={styles.suggestion} onClick={() => send(s)}>
                        <Icon d={SPARK_ICON} size={16} />{s}
                      </button>
                    ))}
                  </div>
                )
              )}
            </div>
          )}

          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={m.id} className={`${styles.row} ${styles.user}`}>
                <div className={styles.bubble}>{m.text}</div>
              </div>
            ) : (
              <div key={m.id} className={`${styles.row} ${styles.assistant}${m.error ? ` ${styles.failed}` : ""}`}>
                <span className={styles.avatar}><Orb size={34} /></span>
                <div className={styles.bubble}>
                  {m.error ? <p className="error">{m.text}</p> : <AnswerText text={m.text} onCite={(n) => jumpToSource(m.id, n)} />}

                  {!m.error && m.meta?.generatedBy === "extractive" && (
                    <p className={styles.notice}>
                      <Icon d="M12 9v4M12 17h.01M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" size={16} />
                      The AI model is not available, so these are the most relevant excerpts from your documents.
                    </p>
                  )}

                  {m.sources && m.sources.length > 0 && (
                    <>
                      <p className={styles.sourcesTitle}>Sources</p>
                      <div className="source-list">
                        {m.sources.map((s, n) => (
                          <SourceCard key={n} n={n + 1} source={s} idPrefix={`m-${m.id}`}
                                      maxScore={Math.max(...m.sources!.map((x) => x.score))}
                                      active={flash?.id === m.id && flash.n === n + 1} />
                        ))}
                      </div>
                    </>
                  )}

                  <div className={styles.meta}>
                    {m.meta && m.meta.generatedBy !== "assistant" && (
                      <>
                        <span className="badge">{generatedLabel(m.meta.generatedBy)}</span>
                        <span>{m.meta.retrieval} search</span>
                        <span>{(m.meta.latencyMs / 1000).toFixed(1)} s</span>
                      </>
                    )}
                    <span className={styles.actions}>
                      {!m.error && <button type="button" className="ghost small" onClick={() => copy(m.text)}>Copy</button>}
                      {i === lastAssistant && i > 0 && (
                        <button type="button" className="ghost small" onClick={() => retry(i)} disabled={pending}>
                          {m.error ? "Try again" : "Regenerate"}
                        </button>
                      )}
                    </span>
                  </div>
                </div>
              </div>
            ),
          )}

          {pending && (
            <div className={`${styles.row} ${styles.assistant}`} role="status">
              <span className={styles.avatar}><Orb size={34} thinking /></span>
              <div className={styles.bubble}>
                <span className={styles.typing}>
                  <span className={styles.dots} aria-hidden="true"><i /><i /><i /></span>
                  Searching your documents…
                </span>
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form className={styles.composer} onSubmit={(e) => { e.preventDefault(); send(); }}>
          <div className={styles.box}>
            <textarea
              ref={inputRef}
              rows={1}
              value={draft}
              maxLength={MAX_QUESTION}
              placeholder="Ask about a fault, a procedure, a part or a maintenance interval…"
              aria-label="Your question"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button type="submit" className={styles.send} disabled={pending || draft.trim().length < MIN_QUESTION} aria-label="Send question">
              <Icon d={SEND_ICON} size={20} />
            </button>
          </div>
          <div className={styles.foot}>
            <span>Enter to send · Shift+Enter for a new line · Each question is answered on its own</span>
            {draft.length > MAX_QUESTION * 0.8 && <span>{draft.length}/{MAX_QUESTION}</span>}
          </div>
        </form>
      </section>
      {toast && <div className="toast" role="status">{toast}</div>}
    </>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <ChatView />
    </Suspense>
  );
}