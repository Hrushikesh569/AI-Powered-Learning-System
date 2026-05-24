import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Send, Loader2, BookOpen, Sparkles } from 'lucide-react';
import { agentAPI, getAuthToken } from '../api';

const WELCOME = { role: 'bot', text: "Hi! I'm the quick PDF Q&A panel. For a full study workspace, open Study Tutor." };

export default function StudyChat({ open, onClose }) {
    const [messages, setMessages] = useState([WELCOME]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const bottomRef = useRef(null);

    const quickPrompts = [
        'Summarize the main idea of this file.',
        'Explain the topic like I am a beginner.',
        'Give me three likely exam questions.',
    ];

    useEffect(() => {
        if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, open]);

    const sendMessage = async (e) => {
        e?.preventDefault();
        const q = input.trim();
        if (!q || loading) return;

        setMessages(prev => [...prev, { role: 'user', text: q }]);
        setInput('');
        setLoading(true);

        try {
            const token = getAuthToken();
            const res = await agentAPI.chatWithBot({ question: q }, token);
            const answer = res?.answer || 'I could not build a response right now.';
            const suggestions = Array.isArray(res?.suggested_questions) ? res.suggested_questions : [];
            const sources = Array.isArray(res?.sources) ? res.sources : [];

            setMessages(prev => [...prev, {
                role: 'bot',
                text: answer,
                sources,
                suggestions,
            }]);
        } catch (err) {
            setMessages(prev => [...prev, {
                role: 'bot',
                text: "Sorry, I couldn't reach the server. Please try again.",
            }]);
        } finally {
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
                                    <p className="text-sm font-semibold leading-none">Quick PDF Q&A</p>
                                    <p className="text-xs text-primary-200 mt-0.5">Fast answers for uploaded files</p>
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
                                    <div className={`max-w-[82%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
                                        msg.role === 'user'
                                            ? 'bg-primary-600 text-white rounded-br-sm'
                                            : 'bg-gray-100 text-gray-800 rounded-bl-sm'
                                    }`}>
                                        {msg.text || (loading && msg.role === 'bot' && (
                                            <Loader2 className="w-4 h-4 animate-spin text-gray-500" />
                                        ))}
                                        {msg.sources && msg.sources.length > 0 && (
                                            <div className="mt-2 pt-2 border-t border-gray-200">
                                                <p className="text-xs text-gray-500 font-medium mb-1">Sources:</p>
                                                {msg.sources.slice(0, 3).map((s, i) => (
                                                    <p key={i} className="text-xs text-gray-500 truncate">• {s}</p>
                                                ))}
                                            </div>
                                        )}
                                        {msg.suggestions && msg.suggestions.length > 0 && (
                                            <div className="mt-2 pt-2 border-t border-gray-200 space-y-1">
                                                <p className="text-xs text-gray-500 font-medium flex items-center gap-1"><Sparkles className="w-3 h-3" /> Suggested questions</p>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {msg.suggestions.slice(0, 3).map((question, index) => (
                                                        <button
                                                            key={index}
                                                            type="button"
                                                            onClick={() => setInput(question)}
                                                            className="text-[11px] px-2 py-1 rounded-full bg-white border border-gray-200 text-gray-700 hover:border-primary-300 hover:text-primary-700 transition"
                                                        >
                                                            {question}
                                                        </button>
                                                    ))}
                                                </div>
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
                        <div className="px-3 pb-3 flex flex-wrap gap-2 border-t border-gray-100 pt-3">
                            {quickPrompts.map((prompt) => (
                                <button
                                    key={prompt}
                                    type="button"
                                    onClick={() => setInput(prompt)}
                                    className="text-[11px] px-2.5 py-1 rounded-full bg-primary-50 text-primary-700 border border-primary-100 hover:bg-primary-100 transition"
                                >
                                    {prompt}
                                </button>
                            ))}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </>
    );
}
