import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Send, Loader2, BookOpen } from 'lucide-react';
import { getAuthToken } from '../api';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
const WELCOME = { role: 'bot', text: "Hi! I'm your AI study partner. Ask me anything about your uploaded study materials." };

export default function StudyChat({ open, onClose }) {
    const [messages, setMessages]   = useState([WELCOME]);
    const [input, setInput]         = useState('');
    const [loading, setLoading]     = useState(false);
    const bottomRef                 = useRef(null);
    const abortRef                  = useRef(null);

    useEffect(() => {
        if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, open]);

    // Cancel any in-flight stream when the component unmounts or chat closes
    useEffect(() => {
        return () => abortRef.current?.abort();
    }, []);

    const sendMessage = async (e) => {
        e?.preventDefault();
        const q = input.trim();
        if (!q || loading) return;

        setMessages(prev => [...prev, { role: 'user', text: q }]);
        setInput('');
        setLoading(true);

        // Append an empty bot bubble that we'll fill token-by-token
        setMessages(prev => [...prev, { role: 'bot', text: '', streaming: true }]);

        abortRef.current = new AbortController();

        try {
            const token = getAuthToken();
            const res = await fetch(`${BASE_URL}/content/chat-stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
                body: JSON.stringify({ question: q }),
                signal: abortRef.current.signal,
            });

            if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                // SSE lines end with \n\n; process every complete event
                const parts = buffer.split('\n\n');
                buffer = parts.pop() ?? '';   // keep incomplete trailing chunk

                for (const part of parts) {
                    for (const line of part.split('\n')) {
                        if (!line.startsWith('data: ')) continue;
                        const raw = line.slice(6).trim();
                        if (raw === '[DONE]') break;
                        try {
                            const { token: tok } = JSON.parse(raw);
                            if (tok) {
                                setMessages(prev => {
                                    const updated = [...prev];
                                    updated[updated.length - 1] = {
                                        ...updated[updated.length - 1],
                                        text: updated[updated.length - 1].text + tok,
                                    };
                                    return updated;
                                });
                            }
                        } catch { /* malformed JSON — skip */ }
                    }
                }
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                setMessages(prev => {
                    const updated = [...prev];
                    updated[updated.length - 1] = {
                        role: 'bot',
                        text: "Sorry, I couldn't reach the server. Please try again.",
                    };
                    return updated;
                });
            }
        } finally {
            setMessages(prev => {
                const updated = [...prev];
                // Mark streaming complete
                if (updated[updated.length - 1]?.streaming) {
                    updated[updated.length - 1] = {
                        ...updated[updated.length - 1],
                        streaming: false,
                    };
                }
                return updated;
            });
            setLoading(false);
        }
    };

    return (
        <>
            {/* Chat panel — anchored to left sidebar */}
            <AnimatePresence>
                {open && (
                    <motion.div
                        key="chat-panel"
                        initial={{ opacity: 0, x: -20, scale: 0.95 }}
                        animate={{ opacity: 1, x: 0, scale: 1 }}
                        exit={{ opacity: 0, x: -20, scale: 0.95 }}
                        transition={{ type: 'spring', stiffness: 320, damping: 28 }}
                        className="fixed bottom-4 left-[272px] z-[60] w-80 sm:w-96 h-[520px] bg-white rounded-2xl shadow-2xl border border-gray-200 flex flex-col overflow-hidden"
                    >
                        {/* Header */}
                        <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-primary-600 to-blue-600 text-white flex-shrink-0">
                            <div className="flex items-center space-x-2">
                                <BookOpen className="w-5 h-5" />
                                <div>
                                    <p className="text-sm font-semibold leading-none">AI Study Partner</p>
                                    <p className="text-xs text-primary-200 mt-0.5">Ask about your materials</p>
                                </div>
                            </div>
                            <button onClick={onClose}
                                className="p-1 hover:bg-white/20 rounded-lg transition">
                                <X className="w-4 h-4" />
                            </button>
                        </div>

                        {/* Messages */}
                        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
                            {messages.map((msg, idx) => (
                                <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                                    <div className={`max-w-[82%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
                                        msg.role === 'user'
                                            ? 'bg-primary-600 text-white rounded-br-sm'
                                            : 'bg-gray-100 text-gray-800 rounded-bl-sm'
                                    }`}>
                                        {msg.text || (msg.streaming && (
                                            <Loader2 className="w-4 h-4 animate-spin text-gray-500" />
                                        ))}
                                        {/* Blinking cursor while streaming */}
                                        {msg.streaming && msg.text && (
                                            <span className="inline-block w-0.5 h-3.5 bg-gray-500 animate-pulse ml-0.5 align-middle" />
                                        )}
                                        {msg.sources && msg.sources.length > 0 && (
                                            <div className="mt-2 pt-2 border-t border-gray-200">
                                                <p className="text-xs text-gray-500 font-medium mb-1">Sources:</p>
                                                {msg.sources.slice(0, 3).map((s, i) => (
                                                    <p key={i} className="text-xs text-gray-500 truncate">• {s}</p>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ))}
                            <div ref={bottomRef} />
                        </div>

                        {/* Input */}
                        <form onSubmit={sendMessage}
                            className="flex items-center space-x-2 px-3 py-3 border-t border-gray-100 flex-shrink-0">
                            <input
                                value={input}
                                onChange={e => setInput(e.target.value)}
                                placeholder="Ask anything about your studies..."
                                className="flex-1 text-sm border border-gray-200 rounded-xl px-3 py-2 focus:ring-2 focus:ring-primary-300 outline-none" />
                            <button type="submit"
                                disabled={loading || !input.trim()}
                                className="p-2 bg-primary-600 text-white rounded-xl hover:bg-primary-700 disabled:opacity-40 transition flex-shrink-0">
                                <Send className="w-4 h-4" />
                            </button>
                        </form>
                    </motion.div>
                )}
            </AnimatePresence>
        </>
    );
}
