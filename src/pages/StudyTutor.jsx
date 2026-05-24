import { useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { ChevronDown, BookOpen, FileText, Loader2, Sparkles, Send, ChevronRight } from 'lucide-react';
import DashboardLayout from '../layouts/DashboardLayout';
import { agentAPI, getAuthToken } from '../api';

const QUICK_PROMPTS = [
    'Summarize this PDF in simple words.',
    'Teach me the main concept step by step.',
    'What should I revise first from this file?',
];

const _cleanText = (value) => String(value || '').replace(/\s+/g, ' ').trim();

const _topicLabel = (topic) => topic?.topic_name || topic?.name || topic?.title || String(topic || '').trim();

const _extractSummary = (analysis, file) => {
    if (!analysis || typeof analysis !== 'object') {
        return {
            title: file?.filename || 'Selected file',
            summary: 'Open a file to see a summary and start teaching mode.',
            keyPoints: [],
            suggestedQuestions: QUICK_PROMPTS,
        };
    }

    const subjects = Array.isArray(analysis.subjects) ? analysis.subjects : [];
    const firstSubject = subjects[0] || {};
    const allTopics = subjects.flatMap((subject) =>
        (subject.units || []).flatMap((unit) => (unit.topics || []).map((topic) => ({
            subject: subject.subject || file?.subject || '',
            unit: unit.unit_name || unit.unit || '',
            topic: _topicLabel(topic),
        })))
    );

    const summaryText = _cleanText(
        analysis.summary ||
        analysis.overview ||
        analysis.tldr ||
        analysis.description ||
        firstSubject.summary ||
        firstSubject.overview ||
        `This file contains ${allTopics.length || 0} extracted topic(s) and is ready for guided study.`
    );

    const keyPoints = Array.isArray(analysis.key_points)
        ? analysis.key_points.filter(Boolean)
        : allTopics.slice(0, 5).map((item) => `${item.subject}${item.unit ? ` / ${item.unit}` : ''}${item.topic ? ` / ${item.topic}` : ''}`);

    const suggestedQuestions = Array.isArray(analysis.suggested_questions)
        ? analysis.suggested_questions.filter(Boolean)
        : [
            `What is the main idea of ${file?.filename || 'this file'}?`,
            'Explain the most important section like a teacher.',
            'Give me likely exam questions from this PDF.',
        ];

    return {
        title: analysis.subject_name || analysis.subject || file?.filename || 'Selected file',
        summary: summaryText,
        keyPoints,
        suggestedQuestions: suggestedQuestions.slice(0, 5),
    };
};

const StudyTutor = () => {
    const [subjects, setSubjects] = useState([]);
    const [selectedSubject, setSelectedSubject] = useState('');
    const [files, setFiles] = useState([]);
    const [selectedFile, setSelectedFile] = useState(null);
    const [analysis, setAnalysis] = useState(null);
    const [previewUrl, setPreviewUrl] = useState('');
    const [loadingSubjects, setLoadingSubjects] = useState(false);
    const [loadingFiles, setLoadingFiles] = useState(false);
    const [loadingAnalysis, setLoadingAnalysis] = useState(false);
    const [loadingChat, setLoadingChat] = useState(false);
    const [question, setQuestion] = useState('');
    const [conversation, setConversation] = useState([]);
    const [status, setStatus] = useState('Select a PDF from your uploaded syllabus files to begin.');
    const previewRef = useRef(null);

    const summary = useMemo(() => _extractSummary(analysis, selectedFile), [analysis, selectedFile]);

    useEffect(() => {
        return () => {
            if (previewUrl) URL.revokeObjectURL(previewUrl);
        };
    }, [previewUrl]);

    useEffect(() => {
        const load = async () => {
            setLoadingSubjects(true);
            try {
                const token = getAuthToken();
                const subjectRes = await agentAPI.listSubjects(token);
                const subjectList = Array.isArray(subjectRes?.subjects) ? subjectRes.subjects : [];
                setSubjects(subjectList);
                const initialSubject = subjectList[0]?.name || '';
                setSelectedSubject(initialSubject);
            } catch {
                setSubjects([]);
            } finally {
                setLoadingSubjects(false);
            }
        };
        load();
    }, []);

    useEffect(() => {
        const loadFiles = async () => {
            if (!selectedSubject) return;
            setLoadingFiles(true);
            try {
                const token = getAuthToken();
                const res = await agentAPI.listFiles(selectedSubject, token);
                const list = Array.isArray(res?.files) ? res.files : [];
                setFiles(list);
                if (!list.some((file) => file.id === selectedFile?.id) && list.length > 0) {
                    setSelectedFile(list[0]);
                }
            } catch {
                setFiles([]);
            } finally {
                setLoadingFiles(false);
            }
        };
        loadFiles();
    }, [selectedSubject]);

    useEffect(() => {
        const loadSelectedFile = async () => {
            if (!selectedFile?.id) return;
            setLoadingAnalysis(true);
            setStatus(`Loading ${selectedFile.filename}...`);
            if (previewUrl) {
                URL.revokeObjectURL(previewUrl);
                setPreviewUrl('');
            }
            try {
                const [analysisRes, fileUrl] = await Promise.all([
                    agentAPI.getFileAnalysis(selectedFile.id),
                    agentAPI.getFileBlobUrl(selectedFile.id),
                ]);
                if (analysisRes?.status === 'ready') {
                    setAnalysis(analysisRes.analysis || null);
                } else {
                    setAnalysis(analysisRes || null);
                }
                setPreviewUrl(fileUrl);
                setConversation([]);
                setQuestion('');
                setStatus(`Studying ${selectedFile.filename}`);
            } catch {
                setAnalysis(null);
                setPreviewUrl('');
                setStatus('Preview unavailable for this file.');
            } finally {
                setLoadingAnalysis(false);
            }
        };
        loadSelectedFile();
    }, [selectedFile]);

    const sendQuestion = async (e) => {
        e.preventDefault();
        const cleaned = question.trim();
        if (!cleaned || !selectedFile?.id || loadingChat) return;
        setLoadingChat(true);
        setConversation((prev) => [...prev, { role: 'user', text: cleaned }]);
        setQuestion('');
        try {
            const token = getAuthToken();
            const res = await agentAPI.chatWithBot({ question: cleaned, material_id: selectedFile.id }, token);
            setConversation((prev) => [...prev, {
                role: 'assistant',
                text: res?.answer || 'I could not produce an answer for that file.',
                suggestions: Array.isArray(res?.suggested_questions) ? res.suggested_questions : [],
                sources: Array.isArray(res?.sources) ? res.sources : [],
            }]);
        } catch (err) {
            setConversation((prev) => [...prev, {
                role: 'assistant',
                text: 'The tutor could not answer right now. Try again once the file is indexed.',
            }]);
        } finally {
            setLoadingChat(false);
        }
    };

    const selectFile = (file) => {
        setSelectedFile(file);
        setStatus(`Studying ${file.filename}`);
    };

    return (
        <DashboardLayout>
            <div className="space-y-6">
                <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="space-y-2">
                    <div className="inline-flex items-center gap-2 rounded-full bg-primary-50 px-3 py-1 text-primary-700 text-sm font-medium">
                        <BookOpen className="w-4 h-4" /> Study Tutor
                    </div>
                    <h1 className="text-3xl font-bold text-gray-900">Dedicated study space</h1>
                    <p className="text-gray-600 max-w-3xl">
                        Pick one uploaded PDF, read its summary, ask questions, and keep the document open on the right while you study.
                    </p>
                </motion.div>

                <div className="grid xl:grid-cols-[320px_minmax(0,1fr)_460px] gap-6 items-start">
                    <div className="card space-y-4 sticky top-24">
                        <div>
                            <div className="flex items-center justify-between gap-3 mb-2">
                                <h2 className="font-bold text-gray-800">Uploaded PDFs</h2>
                                <ChevronDown className="w-4 h-4 text-gray-400" />
                            </div>
                            <p className="text-xs text-gray-500">Choose a subject and then a file.</p>
                        </div>

                        <select
                            value={selectedSubject}
                            onChange={(e) => setSelectedSubject(e.target.value)}
                            className="input-field text-sm"
                        >
                            {loadingSubjects && <option>Loading subjects...</option>}
                            {!loadingSubjects && subjects.length === 0 && <option value="">No subjects yet</option>}
                            {subjects.map((subject) => (
                                <option key={subject.name} value={subject.name}>{subject.name}</option>
                            ))}
                        </select>

                        <div className="space-y-2 max-h-[540px] overflow-y-auto pr-1">
                            {loadingFiles ? (
                                <div className="text-sm text-gray-400 animate-pulse">Loading files...</div>
                            ) : files.length === 0 ? (
                                <div className="text-sm text-gray-400">No files found for this subject.</div>
                            ) : (
                                files.map((file) => (
                                    <button
                                        key={file.id}
                                        type="button"
                                        onClick={() => selectFile(file)}
                                        className={`w-full text-left rounded-xl border px-3 py-3 transition ${selectedFile?.id === file.id ? 'border-primary-300 bg-primary-50' : 'border-gray-200 bg-white hover:border-gray-300'}`}
                                    >
                                        <div className="flex items-start gap-3">
                                            <FileText className="w-4 h-4 text-primary-500 mt-0.5 flex-shrink-0" />
                                            <div className="min-w-0 flex-1">
                                                <p className="text-sm font-medium text-gray-800 truncate">{file.filename}</p>
                                                <p className="text-xs text-gray-500 mt-1 truncate">{file.unitName || file.unit_name || 'General'} · {file.topicCount || 0} topics</p>
                                            </div>
                                            <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />
                                        </div>
                                    </button>
                                ))
                            )}
                        </div>
                    </div>

                    <div className="space-y-6">
                        <div className="card space-y-4">
                            <div className="flex items-center justify-between gap-3">
                                <div>
                                    <h2 className="font-bold text-gray-800">Summary</h2>
                                    <p className="text-xs text-gray-500 mt-1">Teacher-style overview of the selected file</p>
                                </div>
                                {selectedFile?.id && (
                                    <button
                                        type="button"
                                        onClick={() => agentAPI.openFile(selectedFile.id, selectedFile.filename).catch(() => {})}
                                        className="text-sm text-primary-600 hover:text-primary-700 font-medium"
                                    >
                                        Open original
                                    </button>
                                )}
                            </div>

                            {loadingAnalysis ? (
                                <div className="flex items-center gap-2 text-sm text-gray-500 animate-pulse"><Loader2 className="w-4 h-4 animate-spin" /> Building summary...</div>
                            ) : selectedFile ? (
                                <>
                                    <div className="rounded-2xl bg-gradient-to-br from-primary-50 to-blue-50 border border-primary-100 p-4">
                                        <p className="text-xs font-semibold uppercase tracking-wide text-primary-700 mb-1">{summary.title}</p>
                                        <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{summary.summary}</p>
                                    </div>

                                    {summary.keyPoints.length > 0 && (
                                        <div>
                                            <div className="flex items-center gap-2 mb-2 text-gray-700 font-medium text-sm">
                                                <Sparkles className="w-4 h-4 text-primary-500" /> Key points
                                            </div>
                                            <ul className="space-y-2">
                                                {summary.keyPoints.slice(0, 6).map((point, index) => (
                                                    <li key={index} className="text-sm text-gray-700 bg-gray-50 border border-gray-100 rounded-xl px-3 py-2">
                                                        {point}
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                </>
                            ) : (
                                <p className="text-sm text-gray-400">Select a file to see the summary.</p>
                            )}
                        </div>

                        <div className="card space-y-4">
                            <div className="flex items-center justify-between gap-3">
                                <div>
                                    <h2 className="font-bold text-gray-800">Ask the Tutor</h2>
                                    <p className="text-xs text-gray-500 mt-1">Questions stay scoped to this PDF.</p>
                                </div>
                            </div>

                            <div className="flex flex-wrap gap-2">
                                {summary.suggestedQuestions.slice(0, 3).map((item) => (
                                    <button
                                        key={item}
                                        type="button"
                                        onClick={() => setQuestion(item)}
                                        className="text-xs px-3 py-1.5 rounded-full bg-primary-50 text-primary-700 border border-primary-100 hover:bg-primary-100 transition"
                                    >
                                        {item}
                                    </button>
                                ))}
                            </div>

                            <div className="space-y-3 max-h-[420px] overflow-y-auto pr-1">
                                {conversation.length === 0 ? (
                                    <div className="rounded-2xl border border-dashed border-gray-200 bg-gray-50 p-4 text-sm text-gray-500">
                                        Ask a question and the tutor will explain this PDF like a teacher.
                                    </div>
                                ) : conversation.map((msg, index) => (
                                    <div key={index} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                                        <div className={`max-w-[90%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap ${msg.role === 'user' ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-800'}`}>
                                            {msg.text}
                                            {msg.suggestions?.length > 0 && (
                                                <div className="mt-3 pt-2 border-t border-gray-200 space-y-2">
                                                    <p className="text-xs font-semibold text-gray-500">Suggested follow-up questions</p>
                                                    <div className="flex flex-wrap gap-2">
                                                        {msg.suggestions.slice(0, 3).map((suggestion) => (
                                                            <button
                                                                key={suggestion}
                                                                type="button"
                                                                onClick={() => setQuestion(suggestion)}
                                                                className="text-[11px] px-2.5 py-1 rounded-full bg-white border border-gray-200 text-gray-700 hover:border-primary-300 hover:text-primary-700 transition"
                                                            >
                                                                {suggestion}
                                                            </button>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>

                            <form onSubmit={sendQuestion} className="space-y-3">
                                <textarea
                                    value={question}
                                    onChange={(e) => setQuestion(e.target.value)}
                                    placeholder="Ask about this PDF..."
                                    className="input-field min-h-[110px]"
                                />
                                <div className="flex items-center justify-between gap-3">
                                    <p className="text-xs text-gray-500">{status}</p>
                                    <button
                                        type="submit"
                                        disabled={!selectedFile?.id || loadingChat || !question.trim()}
                                        className="btn-primary inline-flex items-center gap-2 disabled:opacity-60"
                                    >
                                        {loadingChat ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                                        <span>{loadingChat ? 'Thinking...' : 'Ask tutor'}</span>
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>

                    <div className="card sticky top-24 min-h-[760px] space-y-4">
                        <div className="flex items-center justify-between gap-3">
                            <div>
                                <h2 className="font-bold text-gray-800">PDF Reader</h2>
                                <p className="text-xs text-gray-500 mt-1">Scroll the file while you study</p>
                            </div>
                        </div>
                        {!selectedFile ? (
                            <div className="h-[680px] rounded-2xl border border-dashed border-gray-200 flex items-center justify-center text-gray-400 text-sm">
                                Pick a file to load the reader.
                            </div>
                        ) : previewUrl ? (
                            <iframe
                                ref={previewRef}
                                title={selectedFile.filename}
                                src={previewUrl}
                                className="w-full h-[680px] rounded-2xl border border-gray-200 bg-white"
                            />
                        ) : (
                            <div className="h-[680px] rounded-2xl border border-dashed border-gray-200 flex items-center justify-center text-gray-400 text-sm">
                                Preview unavailable for this file.
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </DashboardLayout>
    );
};

export default StudyTutor;
