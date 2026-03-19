import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import DashboardLayout from '../layouts/DashboardLayout';
import { agentAPI } from '../api';
import {
    Upload, FileText, Folder, FolderOpen, Trash2, Plus,
    ChevronRight, ChevronDown, ChevronUp, BookOpen, Calendar,
    RefreshCw, X, CheckCircle, Loader, ExternalLink, AlertTriangle,
} from 'lucide-react';

const DIFF_LABEL = ['', 'Easy', 'Basic', 'Intermediate', 'Hard', 'Advanced'];
const DIFF_COLOR = ['', 'bg-green-100 text-green-700', 'bg-blue-100 text-blue-700',
    'bg-yellow-100 text-yellow-700', 'bg-orange-100 text-orange-700', 'bg-red-100 text-red-700'];

const SUBJECT_ICONS = {
    'Mathematics':     '\u{1F4D0}',
    'Physics':         '\u{26A1}',
    'Chemistry':       '\u{1F9EA}',
    'Biology':         '\u{1F9EC}',
    'Computer Science':'\u{1F4BB}',
    'History':         '\u{1F3DB}',
    'Literature':      '\u{1F4DA}',
    'Economics':       '\u{1F4CA}',
    'General':         '\u{1F4C1}',
};

const subjectIcon = (name) => SUBJECT_ICONS[name] || '\u{1F4C1}';

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
const fileTypeBadge = (name = '') => {
    const ext = (name.split('.').pop() || '').toLowerCase();
    if (ext === 'pdf')                   return { label: 'PDF',  cls: 'bg-red-50 text-red-600 border-red-200' };
    if (ext === 'ppt' || ext === 'pptx') return { label: 'PPT',  cls: 'bg-orange-50 text-orange-600 border-orange-200' };
    if (ext === 'doc' || ext === 'docx') return { label: 'Word', cls: 'bg-blue-50 text-blue-600 border-blue-200' };
    return { label: ext.toUpperCase() || 'File', cls: 'bg-gray-100 text-gray-500 border-gray-200' };
};

// ─────────────────────────────────────────────────────────────────────────────
// FileBrowser — collapsible folder tree: Subject → Unit → Files → Topics
// ─────────────────────────────────────────────────────────────────────────────
const FileBrowser = ({ files, expandedFile, fileTopics, fileAnalysis, loadingTopics,
    onExpand, onDelete, onRetry, onUploadToUnit, onMarkComplete, onReschedule, selectedSubject }) => {

    const [openUnits, setOpenUnits] = useState({});
    const [openSubjects, setOpenSubjects] = useState({});
    const [openTopicUnits, setOpenTopicUnits] = useState({});
    const unitInputRefs = useRef({});
    const toggleUnit = (key) => setOpenUnits(prev => ({ ...prev, [key]: !prev[key] }));
    const toggleSubject = (key) => setOpenSubjects(prev => ({ ...prev, [key]: !prev[key] }));
    const toggleTopicUnit = (key) => setOpenTopicUnits(prev => ({ ...prev, [key]: !prev[key] }));

    // Group files by unitName
    const groups = {};
    files.forEach(f => {
        const g = f.unitName || '_general';
        if (!groups[g]) groups[g] = [];
        groups[g].push(f);
    });
    const unitKeys = Object.keys(groups).sort((a, b) => {
        if (a === '_general') return 1;   // General goes last
        if (b === '_general') return -1;
        return a.localeCompare(b);
    });

    // Auto-open all units on first render
    useEffect(() => {
        const init = {};
        unitKeys.forEach(k => { init[k] = true; });
        setOpenUnits(init);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [files.length]);

    const renderFile = (file) => {
        const isStuck = file.processing && file.createdAt &&
            (Date.now() - new Date(file.createdAt).getTime()) > 2 * 60 * 1000;
        const badge = fileTypeBadge(file.filename);
        const canExpand = !file.processing && !isStuck && (file.topicCount || 0) > 0;

        return (
            <div key={file.id} className="group">
                {/* ── File row ── */}
                <div
                    className={`flex items-center gap-2 py-1.5 px-2 rounded-lg transition ${canExpand ? 'hover:bg-gray-50 cursor-pointer' : 'hover:bg-gray-50'}`}
                    onClick={() => { if (canExpand) onExpand(file.id); }}
                    role={canExpand ? 'button' : undefined}
                    tabIndex={canExpand ? 0 : undefined}
                    onKeyDown={(e) => {
                        if (!canExpand) return;
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            onExpand(file.id);
                        }
                    }}
                >
                    <FileText className="w-4 h-4 text-gray-400 flex-shrink-0" />

                    {/* Filename + type badge together */}
                    <div className="flex items-center gap-1.5 flex-1 min-w-0">
                        <span className="text-sm text-gray-800 truncate">{file.filename}</span>
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                agentAPI.openFile(file.id, file.filename).catch(() => {});
                            }}
                            className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded border leading-none flex-shrink-0 cursor-pointer hover:opacity-80 transition inline-flex items-center gap-0.5 ${badge.cls}`}
                            title={`Open ${file.filename}`}
                        >
                            <ExternalLink className="w-2.5 h-2.5" />
                            {badge.label}
                        </button>
                    </div>

                    {/* Status chip */}
                    {isStuck ? (
                        <span className="text-[10px] text-orange-600 bg-orange-50 border border-orange-200 rounded px-1.5 py-0.5 inline-flex items-center gap-0.5 flex-shrink-0">
                            <AlertTriangle className="w-3 h-3" /> Timed out
                        </span>
                    ) : file.processing ? (
                        <span className="text-[10px] text-amber-600 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5 inline-flex items-center gap-0.5 flex-shrink-0">
                            <Loader className="w-3 h-3 animate-spin" /> Extracting…
                        </span>
                    ) : (
                        <span className="text-[10px] text-gray-400 flex-shrink-0">{file.topicCount} topics</span>
                    )}

                    {/* Expand topics */}
                    {canExpand && (
                        <span className="p-0.5 text-gray-400 flex-shrink-0" title="Show topics">
                            {expandedFile === file.id
                                ? <ChevronUp className="w-3.5 h-3.5" />
                                : <ChevronDown className="w-3.5 h-3.5" />}
                        </span>
                    )}

                    {/* Retry */}
                    {isStuck && (
                        <button onClick={(e) => { e.stopPropagation(); onRetry(file.id); }}
                            className="p-0.5 text-orange-500 hover:text-orange-700 transition flex-shrink-0" title="Retry">
                            <RefreshCw className="w-3.5 h-3.5" />
                        </button>
                    )}

                    {/* Delete */}
                    <button onClick={(e) => { e.stopPropagation(); onDelete(file.id); }}
                        className="p-0.5 text-gray-300 hover:text-red-500 transition flex-shrink-0 opacity-0 group-hover:opacity-100">
                        <Trash2 className="w-3.5 h-3.5" />
                    </button>
                </div>

                {/* ── Expanded topics — hierarchical display ── */}
                <AnimatePresence>
                    {expandedFile === file.id && (
                        <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="overflow-hidden ml-6 border-l-2 border-primary-100 pl-3 mb-1">
                            {loadingTopics[file.id] ? (
                                <p className="text-xs text-gray-400 animate-pulse py-2">Loading topics…</p>
                            ) : (
                                <div className="py-2 space-y-2">
                                    {/* Pending analysis */}
                                    {fileAnalysis[file.id] === 'pending' && (
                                        <div className="flex items-center gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                                            <Loader className="w-3 h-3 animate-spin flex-shrink-0" />
                                            <span>AI is organizing topics into units…</span>
                                        </div>
                                    )}
                                    {/* Hierarchical unit → topic tree (from AI analysis) */}
                                    {(() => {
                                        const hierarchy = fileTopics[file.id];
                                        if (
                                            hierarchy &&
                                            typeof hierarchy === 'object' &&
                                            Array.isArray(hierarchy.subjects) &&
                                            hierarchy.subjects.length > 0
                                        ) {
                                            return (
                                                <div className="space-y-3">
                                                    {hierarchy.subjects.map((subj, si) => (
                                                        <div key={si} className="border border-primary-100 rounded-lg overflow-hidden">
                                                            {(() => {
                                                                const subjKey = `${file.id}::${subj.subject || si}`;
                                                                const subjOpen = !!openSubjects[subjKey];
                                                                return (
                                                                    <>
                                                                        <button
                                                                            type="button"
                                                                            onClick={() => toggleSubject(subjKey)}
                                                                            className="w-full px-3 py-2 bg-primary-50 hover:bg-primary-100 flex items-center gap-2 text-left"
                                                                        >
                                                                            {subjOpen
                                                                                ? <FolderOpen className="w-3.5 h-3.5 text-primary-600 flex-shrink-0" />
                                                                                : <Folder className="w-3.5 h-3.5 text-primary-500 flex-shrink-0" />}
                                                                            <span className="text-xs font-semibold text-primary-800 flex-1">
                                                                                {subj.subject}
                                                                                {subj.subject_code ? ` (${subj.subject_code})` : ''}
                                                                            </span>
                                                                            <span className="text-[10px] text-primary-600">{(subj.units || []).length} units</span>
                                                                            {subjOpen
                                                                                ? <ChevronDown className="w-3.5 h-3.5 text-primary-600" />
                                                                                : <ChevronRight className="w-3.5 h-3.5 text-primary-600" />}
                                                                        </button>
                                                                        <AnimatePresence>
                                                                            {subjOpen && (
                                                                                <motion.div
                                                                                    initial={{ height: 0, opacity: 0 }}
                                                                                    animate={{ height: 'auto', opacity: 1 }}
                                                                                    exit={{ height: 0, opacity: 0 }}
                                                                                    className="overflow-hidden"
                                                                                >
                                                                                    <div className="p-2 space-y-2 bg-white">
                                                                                        {(subj.units || []).map((unit, ui) => {
                                                                                            const unitKey = `${file.id}::${subj.subject || si}::${unit.unit_name || ui}`;
                                                                                            const unitOpen = !!openTopicUnits[unitKey];
                                                                                            return (
                                                                                                <div key={ui} className="border border-gray-100 rounded-lg overflow-hidden">
                                                                                                    <button
                                                                                                        type="button"
                                                                                                        onClick={() => toggleTopicUnit(unitKey)}
                                                                                                        className="w-full px-3 py-1.5 bg-gray-50 hover:bg-gray-100 flex items-center gap-2 text-left"
                                                                                                    >
                                                                                                        {unitOpen
                                                                                                            ? <FolderOpen className="w-3.5 h-3.5 text-primary-400 flex-shrink-0" />
                                                                                                            : <Folder className="w-3.5 h-3.5 text-primary-400 flex-shrink-0" />}
                                                                                                        <span className="text-xs font-semibold text-gray-700 flex-1">{unit.unit_name}</span>
                                                                                                        <span className="text-[10px] text-gray-400">{(unit.topics || []).length} topics</span>
                                                                                                        {unitOpen
                                                                                                            ? <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
                                                                                                            : <ChevronRight className="w-3.5 h-3.5 text-gray-500" />}
                                                                                                    </button>
                                                                                                    <AnimatePresence>
                                                                                                        {unitOpen && (
                                                                                                            <motion.div
                                                                                                                initial={{ height: 0, opacity: 0 }}
                                                                                                                animate={{ height: 'auto', opacity: 1 }}
                                                                                                                exit={{ height: 0, opacity: 0 }}
                                                                                                                className="overflow-hidden"
                                                                                                            >
                                                                                                                <div className="divide-y divide-gray-50">
                                                                            {(unit.topics || []).map((t, ti) => {
                                                                                const name = t.topic_name || t.name || '';
                                                                                const difficulty = t.difficulty;
                                                                                return (
                                                                                    <div key={ti} className="flex items-center gap-2 px-3 py-1 group/topic hover:bg-gray-50">
                                                                                        <span className="w-1 h-1 rounded-full bg-gray-300 flex-shrink-0" />
                                                                                        <span className="text-xs text-gray-700 flex-1 min-w-0">{name}</span>
                                                                                        {t.status === 'completed' && (
                                                                                            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-100 text-green-700 flex-shrink-0">Completed</span>
                                                                                        )}
                                                                                        {t.status === 'rescheduled' && (
                                                                                            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 flex-shrink-0">Rescheduled</span>
                                                                                        )}
                                                                                        {difficulty && (
                                                                                            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-50 text-blue-700 flex-shrink-0">
                                                                                                {difficulty}
                                                                                            </span>
                                                                                        )}
                                                                                        <div className="flex items-center gap-1 opacity-0 group-hover/topic:opacity-100 transition-opacity">
                                                                                            {t.status !== 'completed' && (
                                                                                                <button
                                                                                                    type="button"
                                                                                                    onClick={() => onMarkComplete?.(file.id, t)}
                                                                                                    className="p-0.5 text-gray-400 hover:text-green-600"
                                                                                                    title="Mark complete"
                                                                                                >
                                                                                                    <CheckCircle className="w-3.5 h-3.5" />
                                                                                                </button>
                                                                                            )}
                                                                                            <button
                                                                                                type="button"
                                                                                                onClick={() => onReschedule?.(file.id, t)}
                                                                                                className="p-0.5 text-gray-400 hover:text-primary-600"
                                                                                                title="Reschedule"
                                                                                            >
                                                                                                <Calendar className="w-3.5 h-3.5" />
                                                                                            </button>
                                                                                        </div>
                                                                                    </div>
                                                                                );
                                                                            })}
                                                                                                                </div>
                                                                                                            </motion.div>
                                                                                                        )}
                                                                                                    </AnimatePresence>
                                                                                                </div>
                                                                                            );
                                                                                        })}
                                                                                    </div>
                                                                                </motion.div>
                                                                            )}
                                                                        </AnimatePresence>
                                                                    </>
                                                                );
                                                            })()}
                                                        </div>
                                                    ))}
                                                </div>
                                            );
                                        }

                                        const analysis = fileAnalysis[file.id];
                                        if (analysis && analysis !== 'pending' && analysis !== 'not_found' && typeof analysis === 'object') {
                                            const analysisUnits = analysis.units || [];
                                            if (analysisUnits.length > 0) return (
                                                <div className="space-y-2">
                                                    {analysis.overview && <p className="text-xs text-gray-500 italic mb-1">{analysis.overview}</p>}
                                                    {analysisUnits.map((unit, ui) => (
                                                        <div key={ui} className="border border-gray-100 rounded-lg overflow-hidden">
                                                            <div className="px-3 py-1.5 bg-gray-50 flex items-center gap-2">
                                                                <Folder className="w-3.5 h-3.5 text-primary-400 flex-shrink-0" />
                                                                <span className="text-xs font-semibold text-gray-700 flex-1">{unit.unit_name}</span>
                                                                <span className="text-[10px] text-gray-400">{(unit.topics || []).length} topics</span>
                                                            </div>
                                                            <div className="divide-y divide-gray-50">
                                                                {(unit.topics || []).map((t, ti) => {
                                                                    const name = typeof t === 'object' ? t.name : String(t);
                                                                    const diff = typeof t === 'object' ? t.difficulty : null;
                                                                    return (
                                                                        <div key={ti} className="flex items-center gap-2 px-3 py-1">
                                                                            <span className="w-1 h-1 rounded-full bg-gray-300 flex-shrink-0" />
                                                                            <span className="text-xs text-gray-700 flex-1 min-w-0">{name}</span>
                                                                            {diff && (
                                                                                <span className={`text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0 ${DIFF_COLOR[diff] || ''}`}>
                                                                                    {DIFF_LABEL[diff] || ''}
                                                                                </span>
                                                                            )}
                                                                        </div>
                                                                    );
                                                                })}
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            );
                                        }
                                        /* Fallback: raw topics in a clean scrollable list */
                                        const topics = fileTopics[file.id] || [];
                                        if (topics.length === 0) return <p className="text-xs text-gray-400">No topics extracted.</p>;
                                        return (
                                            <div>
                                                <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1">
                                                    {topics.length} extracted topics
                                                </p>
                                                <div className="max-h-60 overflow-y-auto space-y-0.5">
                                                    {topics.map((t, i) => (
                                                        <div key={i} className="flex items-center gap-2 py-0.5 px-2 rounded hover:bg-gray-50">
                                                            <span className="w-1 h-1 rounded-full bg-gray-300 flex-shrink-0" />
                                                            <span className="text-xs text-gray-600">{t}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        );
                                    })()}
                                </div>
                            )}
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        );
    };

    return (
        <div className="space-y-1">
            {unitKeys.map(uKey => {
                const unitFiles = groups[uKey];
                const isGeneral = uKey === '_general';
                const isOpen = openUnits[uKey] ?? true;
                const unitLabel = isGeneral ? 'General' : uKey;
                const totalTopics = unitFiles.reduce((s, f) => s + (f.topicCount || 0), 0);

                return (
                    <div key={uKey}>
                        {/* ── Unit folder header ── */}
                        <div className="flex items-center gap-1">
                            <button
                                onClick={() => toggleUnit(uKey)}
                                className="flex-1 flex items-center gap-2 py-2 px-2 rounded-lg hover:bg-primary-50 transition text-left">
                                {isOpen
                                    ? <FolderOpen className="w-4 h-4 text-primary-500 flex-shrink-0" />
                                    : <Folder className="w-4 h-4 text-primary-400 flex-shrink-0" />}
                                <span className="text-sm font-semibold text-gray-700 flex-1">{unitLabel}</span>
                                <span className="text-[10px] text-gray-400">
                                    {unitFiles.length} file{unitFiles.length !== 1 ? 's' : ''} · {totalTopics} topics
                                </span>
                                {isOpen
                                    ? <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
                                    : <ChevronRight className="w-3.5 h-3.5 text-gray-400" />}
                            </button>
                            {/* Upload to this unit */}
                            <input
                                type="file"
                                accept=".pdf,.ppt,.pptx,.doc,.docx"
                                className="hidden"
                                ref={el => { unitInputRefs.current[uKey] = el; }}
                                onChange={(e) => {
                                    const f = e.target.files?.[0];
                                    if (f && onUploadToUnit) onUploadToUnit(f, isGeneral ? '' : uKey);
                                    e.target.value = '';
                                }}
                            />
                            <button
                                onClick={() => unitInputRefs.current[uKey]?.click()}
                                className="p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition flex-shrink-0"
                                title={`Upload to ${unitLabel}`}>
                                <Upload className="w-3.5 h-3.5" />
                            </button>
                        </div>

                        {/* ── Files inside this unit ── */}
                        <AnimatePresence>
                            {isOpen && (
                                <motion.div
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: 'auto', opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    className="overflow-hidden ml-3 border-l-2 border-gray-100 pl-2">
                                    {unitFiles.map(renderFile)}
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                );
            })}
        </div>
    );
};

const SyllabusManager = () => {
    const [subjects, setSubjects] = useState([]);
    const [selectedSubject, setSelectedSubject] = useState(null);
    const [files, setFiles] = useState([]);
    const [expandedFile, setExpandedFile] = useState(null);
    const [fileTopics, setFileTopics] = useState({});
    const [fileAnalysis, setFileAnalysis] = useState({});  // { [fileId]: analysis object | 'pending' | 'not_found' }
    const [loadingTopics, setLoadingTopics] = useState({});
    const [loadingSubjects, setLoadingSubjects] = useState(true);
    const [loadingFiles, setLoadingFiles] = useState(false);
    const [uploadingSchedule, setUploadingSchedule] = useState(false);
    const [uploadingMaterial, setUploadingMaterial] = useState(false);
    const [statusMsg, setStatusMsg] = useState('');
    const [statusType, setStatusType] = useState('info');
    const [processingIds, setProcessingIds] = useState([]);
    const [generatingSchedule, setGeneratingSchedule] = useState(false);
    const [schedulePreview, setSchedulePreview] = useState([]);
    const [newSubjectName, setNewSubjectName] = useState('');
    const [newUnitName, setNewUnitName] = useState('');
    const schedFileRef = useRef();
    const matFileRef = useRef();
    const pollRef = useRef(null);

    const loadSubjects = useCallback(async () => {
        setLoadingSubjects(true);
        try {
            const res = await agentAPI.listSubjects();
            setSubjects(res.subjects || []);
        } catch {
            setSubjects([]);
        } finally {
            setLoadingSubjects(false);
        }
    }, []);

    const loadFiles = useCallback(async (subjectName) => {
        setLoadingFiles(true);
        try {
            const res = await agentAPI.listFiles(subjectName);
            const fetched = res.files || [];
            setFiles(fetched);
            // Track any files still being processed
            const still = fetched.filter(f => f.processing).map(f => f.id);
            if (still.length > 0) setProcessingIds(ids => [...new Set([...ids, ...still])]);
        } catch {
            setFiles([]);
        } finally {
            setLoadingFiles(false);
        }
    }, []);

    // Poll processing files until topics arrive
    useEffect(() => {
        if (processingIds.length === 0) return;
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = setInterval(async () => {
            const remaining = [];
            for (const id of processingIds) {
                try {
                    const res = await agentAPI.getFileTopics(id);
                    if (!res.processing && res.topicCount > 0) {
                        // Update the file in the list
                        setFiles(prev => prev.map(f =>
                            f.id === id ? { ...f, topics: res.topics.slice(0, 100), topicCount: res.topicCount, processing: false } : f
                        ));
                        // Refresh subjects count
                        loadSubjects();
                        // Show success message
                        setStatusMsg(`Topics extracted: ${res.topicCount} topics ready!`);
                        setStatusType('success');
                        // Auto-fetch analysis
                        try {
                            const aRes = await agentAPI.getFileAnalysis(id);
                            if (aRes.status === 'ready') {
                                setFileAnalysis(prev => ({ ...prev, [id]: aRes.analysis }));
                            } else if (aRes.status === 'not_found') {
                                try { await agentAPI.triggerFileAnalysis(id); setFileAnalysis(prev => ({ ...prev, [id]: 'pending' })); } catch {}
                            }
                        } catch {}
                        // Auto-generate schedule if this is a syllabus
                        setTimeout(() => autoSaveSchedule(res.topics, null), 500);
                    } else if (!res.processing) {
                        // Extraction done but 0 topics — stop polling, update state so badge clears
                        setFiles(prev => prev.map(f =>
                            f.id === id ? { ...f, processing: false, topicCount: 0 } : f
                        ));
                        setStatusMsg('PDF processed — no topics found. Make sure it\'s a course syllabus and try re-uploading.');
                        setStatusType('warning');
                    } else {
                        remaining.push(id);
                    }
                } catch {
                    remaining.push(id);
                }
            }
            setProcessingIds(remaining);
            if (remaining.length === 0) clearInterval(pollRef.current);
        }, 3000);
        return () => clearInterval(pollRef.current);
    }, [processingIds, loadSubjects]);

    useEffect(() => { loadSubjects(); }, [loadSubjects]);

    useEffect(() => {
        if (selectedSubject) loadFiles(selectedSubject.name);
    }, [selectedSubject, loadFiles]);

    // After a syllabus is processed, save the intelligent schedule into localStorage
    // so the Dashboard can display it. Falls back to keyword schedule if no analysis yet.
    const autoSaveSchedule = async (_topics, _subjectName) => {
        try {
            let prefs = { studyHours: 3 };
            try { prefs = JSON.parse(localStorage.getItem('learningPreferences') || '{}'); } catch (_) {}
            const overrides = JSON.parse(localStorage.getItem('scheduleOverrides') || '{}');
            let res;
            try {
                res = await agentAPI.getIntelligentSchedule({
                    hours_per_day: Number(prefs.studyHours) || 3,
                    num_days: 30,
                    cross_subject: true,
                    user_overrides: overrides,
                });
            } catch (_) {}
            // Fall back to keyword schedule if intelligent not ready yet
            if (!res?.schedule?.length && _topics?.length > 0) {
                res = await agentAPI.generateSchedule({
                    subjects: [{ name: _subjectName || 'Study', topics: _topics.slice(0, 60), priority: 1 }],
                    num_days: 30,
                    hours_per_day: Number(prefs.studyHours) || 3,
                });
            }
            if (res?.schedule?.length > 0) {
                localStorage.setItem('generatedSchedule', JSON.stringify(res.schedule));
            }
        } catch (_) { /* silent */ }
    };

    const handleScheduleUpload = async (e) => {
        e.preventDefault();
        const file = schedFileRef.current?.files[0];
        if (!file) return;
        const fd = new FormData();
        fd.append('file', file);
        fd.append('subject', newSubjectName || selectedSubject?.name || '');
        fd.append('num_days', '30');
        fd.append('hours_per_day', '3');
        setUploadingSchedule(true);
        setStatusMsg('Saving file...');
        setStatusType('info');
        try {
            const res = await agentAPI.uploadScheduleDoc(fd);
            setStatusMsg(`File saved to "${res.subject}"! Topics being extracted in background — check back in a moment.`);
            setStatusType('info');
            if (res.processing) {
                setProcessingIds(ids => [...ids, res.id]);
            }
            // Select the new subject automatically
            await loadSubjects();
            setSelectedSubject({ name: res.subject, fileCount: 1, topicCount: 0 });
            if (schedFileRef.current) schedFileRef.current.value = '';
            setNewSubjectName('');
        } catch {
            setStatusMsg('Upload failed. Please try again.');
            setStatusType('error');
        } finally {
            setUploadingSchedule(false);
        }
    };

    const handleMaterialUpload = async (e) => {
        e.preventDefault();
        const file = matFileRef.current?.files[0];
        if (!file) return;
        const fd = new FormData();
        fd.append('file', file);
        fd.append('subject', newSubjectName || selectedSubject?.name || '');
        if (newUnitName.trim()) fd.append('unit', newUnitName.trim());
        setUploadingMaterial(true);
        setStatusMsg('Saving file...');
        setStatusType('info');
        try {
            const res = await agentAPI.uploadStudyMaterial(fd);
            setStatusMsg(`Saved to "${res.subject}"${newUnitName ? ` / ${newUnitName}` : ''}. Indexing for AI chat in background.`);
            setStatusType('success');
            if (res.processing) setProcessingIds(ids => [...ids, res.id]);
            await loadSubjects();
            if (selectedSubject) await loadFiles(selectedSubject.name);
            if (matFileRef.current) matFileRef.current.value = '';
        } catch {
            setStatusMsg('Upload failed. Please try again.');
            setStatusType('error');
        } finally {
            setUploadingMaterial(false);
        }
    };

    const handleDelete = async (fileId) => {
        if (!window.confirm('Delete this file?')) return;
        try {
            await agentAPI.deleteFile(fileId);
            setFiles(prev => prev.filter(f => f.id !== fileId));
            await loadSubjects();
            // Invalidate schedule cache so dashboard regenerates
            localStorage.removeItem('generatedSchedule');
        } catch {
            setStatusMsg('Could not delete file.');
            setStatusType('error');
        }
    };

    const handleGenerateSchedule = async () => {
        const allTopics = files.flatMap(f => f.topics || []);
        if (!allTopics.length) { setStatusMsg('No topics yet — wait for extraction to finish.'); setStatusType('info'); return; }
        setGeneratingSchedule(true);
        setSchedulePreview([]);
        try {
            let prefs = { studyHours: 3 };
            try { prefs = JSON.parse(localStorage.getItem('learningPreferences') || '{}'); } catch (_) {}
            const overrides = JSON.parse(localStorage.getItem('scheduleOverrides') || '{}');

            // Build a diverse multi-subject schedule directly from extracted ScheduledTopic rows.
            const preferredTodaySubject = (localStorage.getItem('preferredSubjectToday') || '').trim();
            const scheduledRows = await agentAPI.queryScheduledTopics({ status: 'pending' }).catch(() => ({ topics: [] }));
            const rows = scheduledRows.topics || [];

            if (rows.length > 0) {
                const hoursPerDay = Number(prefs.studyHours) || 3;
                const numDays = 30;
                const today = new Date();
                const slotLabels = ['09:00 AM', '11:00 AM', '02:00 PM', '05:00 PM', '08:00 PM'];
                const diffRank = { easy: 1, basic: 2, intermediate: 3, medium: 3, hard: 4, advanced: 5 };

                const bySubject = rows.reduce((acc, r) => {
                    const s = r.subject || 'General';
                    if (!acc[s]) acc[s] = [];
                    acc[s].push(r);
                    return acc;
                }, {});

                Object.keys(bySubject).forEach((s) => {
                    bySubject[s].sort((a, b) => {
                        const da = diffRank[String(a.difficulty || '').toLowerCase()] || 3;
                        const db = diffRank[String(b.difficulty || '').toLowerCase()] || 3;
                        if (db !== da) return db - da;
                        return (Number(b.estimated_hours || 1) - Number(a.estimated_hours || 1));
                    });
                });

                const subjects = Object.keys(bySubject);
                const hasAny = () => subjects.some((s) => bySubject[s].length > 0);
                let cursor = 0;
                let seq = 1;
                const mixed = [];

                for (let day = 0; day < numDays && hasAny(); day += 1) {
                    let remaining = hoursPerDay;
                    const dateObj = new Date(today);
                    dateObj.setDate(today.getDate() + day);
                    const date = dateObj.toISOString().slice(0, 10);
                    let slot = 0;

                    const addOne = (subjectName) => {
                        const q = bySubject[subjectName] || [];
                        if (!q.length) return false;
                        const t = q.shift();
                        let hrs = Number(t.estimated_hours || 1);
                        if (!Number.isFinite(hrs) || hrs <= 0) hrs = 1;
                        hrs = Math.max(0.5, Math.min(2.0, hrs));
                        if (hrs > remaining && remaining >= 0.5) hrs = remaining;
                        if (hrs > remaining) return false;

                        const rounded = hrs < 1 ? `${Math.round(hrs * 60)}min` : `${hrs.toFixed(1)}h`;
                        mixed.push({
                            id: Date.now() + seq,
                            date,
                            time: slotLabels[slot % slotLabels.length],
                            subject: subjectName,
                            unit: t.unit_name || '',
                            topic: t.topic_name || 'Study Topic',
                            difficulty: diffRank[String(t.difficulty || '').toLowerCase()] || 3,
                            difficultyLabel: t.difficulty || 'Intermediate',
                            estimated_hours: hrs,
                            duration: rounded,
                            key_concepts: [],
                            is_foundational: false,
                            status: 'pending',
                        });
                        remaining -= hrs;
                        slot += 1;
                        seq += 1;
                        return true;
                    };

                    // Optional user preference: ensure one task from preferred subject appears first today.
                    if (day === 0 && preferredTodaySubject && bySubject[preferredTodaySubject]?.length) {
                        addOne(preferredTodaySubject);
                    }

                    let guard = 0;
                    while (remaining >= 0.5 && hasAny() && guard < 200) {
                        guard += 1;
                        let placed = false;
                        for (let i = 0; i < subjects.length; i += 1) {
                            const s = subjects[(cursor + i) % subjects.length];
                            if (addOne(s)) {
                                cursor = (cursor + i + 1) % subjects.length;
                                placed = true;
                                break;
                            }
                        }
                        if (!placed) break;
                    }
                }

                if (mixed.length > 0) {
                    setSchedulePreview(mixed);
                    localStorage.setItem('generatedSchedule', JSON.stringify(mixed));
                    setStatusMsg(`Mixed schedule built: ${mixed.length} tasks across ${subjects.length} subjects.`);
                    setStatusType('success');
                    setGeneratingSchedule(false);
                    return;
                }
            }

            // Try intelligent (LLM-analyzed) schedule first
            let res;
            let source = 'intelligent';
            try {
                res = await agentAPI.getIntelligentSchedule({
                    hours_per_day: Number(prefs.studyHours) || 3,
                    num_days: 30,
                    cross_subject: true,
                    user_overrides: overrides,
                });
                if (!res?.schedule?.length) { res = null; source = 'keyword'; }
            } catch (_) { source = 'keyword'; }

            // Keyword fallback (analysis may still be in progress for newly uploaded files)
            if (!res) {
                res = await agentAPI.generateSchedule({
                    subjects: [{ name: selectedSubject?.name || 'Study', topics: allTopics.slice(0, 60), priority: 1 }],
                    num_days: 30,
                    hours_per_day: Number(prefs.studyHours) || 3,
                });
            }

            const schedule = res.schedule || [];
            setSchedulePreview(schedule);
            localStorage.setItem('generatedSchedule', JSON.stringify(schedule));
            if (source === 'intelligent') {
                const summary = res.summary || {};
                const relCount = res.crossSubjectRelations?.length || 0;
                setStatusMsg(
                    `\u2728 AI schedule built! ${summary.totalTopics || schedule.length} topics across ` +
                    `${Object.keys(summary.bySubject || {}).length} subject(s)` +
                    (relCount > 0 ? `, ${relCount} cross-subject link(s) detected.` : '.') +
                    ' Head to Dashboard to see it.'
                );
            } else {
                setStatusMsg('Schedule saved! (AI analysis still processing \u2014 re-run once analysis badge appears.)');
            }
            setStatusType('success');
        } catch {
            setStatusMsg('Failed to generate schedule.');
            setStatusType('error');
        } finally {
            setGeneratingSchedule(false);
        }
    };

    const loadAllTopics = async (fileId) => {
        if (fileTopics[fileId]) { setExpandedFile(expandedFile === fileId ? null : fileId); return; }
        setLoadingTopics(prev => ({ ...prev, [fileId]: true }));
        setExpandedFile(fileId);
        try {
            const hRes = await agentAPI.getFileTopicsHierarchical(fileId);
            if (hRes?.subjects?.length > 0) {
                setFileTopics(prev => ({ ...prev, [fileId]: hRes }));
            } else {
                const res = await agentAPI.getFileTopics(fileId);
                setFileTopics(prev => ({ ...prev, [fileId]: res.topics || [] }));
            }
        } catch {
            try {
                const res = await agentAPI.getFileTopics(fileId);
                setFileTopics(prev => ({ ...prev, [fileId]: res.topics || [] }));
            } catch {
                setFileTopics(prev => ({ ...prev, [fileId]: [] }));
            }
        } finally {
            setLoadingTopics(prev => ({ ...prev, [fileId]: false }));
        }
        // Auto-fetch or auto-trigger analysis
        if (!fileAnalysis[fileId] || fileAnalysis[fileId] === 'not_found') {
            try {
                const aRes = await agentAPI.getFileAnalysis(fileId);
                if (aRes.status === 'ready') {
                    setFileAnalysis(prev => ({ ...prev, [fileId]: aRes.analysis }));
                } else if (aRes.status === 'not_found') {
                    // Auto-trigger analysis silently
                    try {
                        await agentAPI.triggerFileAnalysis(fileId);
                        setFileAnalysis(prev => ({ ...prev, [fileId]: 'pending' }));
                    } catch {}
                } else {
                    setFileAnalysis(prev => ({ ...prev, [fileId]: aRes.status }));
                }
            } catch {
                // silent — analysis is optional
            }
        }
    };

    const handleMarkComplete = async (fileId, topic) => {
        if (!topic?.id) return;
        const notes = window.prompt('Completion note (optional):', '') || '';
        try {
            await agentAPI.markTopicComplete(topic.id, notes);
            setFileTopics(prev => {
                const current = prev[fileId];
                if (!current?.subjects) return prev;
                const next = {
                    ...current,
                    subjects: current.subjects.map(subj => ({
                        ...subj,
                        units: (subj.units || []).map(unit => ({
                            ...unit,
                            topics: (unit.topics || []).map(t =>
                                t.id === topic.id
                                    ? { ...t, status: 'completed', completed_date: new Date().toISOString() }
                                    : t
                            ),
                        })),
                    })),
                };
                return { ...prev, [fileId]: next };
            });
            setStatusMsg('Topic marked complete');
            setStatusType('success');
        } catch {
            setStatusMsg('Could not mark topic complete');
            setStatusType('error');
        }
    };

    const handleRescheduleTopic = async (fileId, topic) => {
        if (!topic?.id) return;
        const dateInput = window.prompt('New date-time (ISO), e.g. 2026-03-20T10:00:00', '2026-03-20T10:00:00');
        if (!dateInput) return;
        const reason = window.prompt('Reason (optional):', '') || '';
        try {
            await agentAPI.rescheduleTopics(topic.id, dateInput, reason);
            setFileTopics(prev => {
                const current = prev[fileId];
                if (!current?.subjects) return prev;
                const next = {
                    ...current,
                    subjects: current.subjects.map(subj => ({
                        ...subj,
                        units: (subj.units || []).map(unit => ({
                            ...unit,
                            topics: (unit.topics || []).map(t =>
                                t.id === topic.id
                                    ? {
                                        ...t,
                                        status: 'rescheduled',
                                        scheduled_date: dateInput,
                                        rescheduled_date: new Date().toISOString(),
                                    }
                                    : t
                            ),
                        })),
                    })),
                };
                return { ...prev, [fileId]: next };
            });
            setStatusMsg('Topic rescheduled');
            setStatusType('success');
        } catch {
            setStatusMsg('Could not reschedule topic');
            setStatusType('error');
        }
    };

    const statusBg = statusType === 'error' ? 'bg-red-50 border-red-200 text-red-800'
        : statusType === 'success' ? 'bg-green-50 border-green-200 text-green-800'
        : 'bg-blue-50 border-blue-200 text-blue-800';

    const hasTopics = files.some(f => (f.topicCount || 0) > 0);

    return (
        <DashboardLayout>
            <div className="space-y-6">
                <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
                    <h1 className="text-3xl font-bold text-gray-900">Syllabus &amp; Study Files</h1>
                    <p className="text-gray-600 mt-1">Upload your PDFs, PPTs and notes &mdash; topics are extracted automatically and your Dashboard schedule is built from them.</p>
                </motion.div>

                {statusMsg && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                        className={`flex items-center justify-between px-4 py-3 border rounded-xl text-sm ${statusBg}`}>
                        <span>{statusMsg}</span>
                        <button onClick={() => setStatusMsg('')}><X className="w-4 h-4" /></button>
                    </motion.div>
                )}

                {processingIds.length > 0 && (
                    <div className="flex items-center space-x-2 px-4 py-2.5 bg-amber-50 border border-amber-200 rounded-xl text-amber-800 text-sm">
                        <Loader className="w-4 h-4 animate-spin flex-shrink-0" />
                        <span>Extracting topics from {processingIds.length} file(s) in background&hellip; page updates automatically.</span>
                    </div>
                )}

                <div className="grid lg:grid-cols-4 gap-6">
                    {/* Subject Folder Panel */}
                    <div className="lg:col-span-1">
                        <div className="card h-full">
                            <div className="flex items-center justify-between mb-4">
                                <h2 className="font-bold text-gray-800">Subjects</h2>
                                <button onClick={() => { setSelectedSubject(null); setNewSubjectName(''); }}
                                    className="p-1 rounded-lg hover:bg-gray-100 text-primary-600 transition"
                                    title="New subject folder">
                                    <Plus className="w-5 h-5" />
                                </button>
                            </div>

                            {loadingSubjects ? (
                                <p className="text-sm text-gray-400 animate-pulse">Loading&hellip;</p>
                            ) : subjects.length === 0 ? (
                                <p className="text-sm text-gray-400">No subjects yet. Upload a file to get started.</p>
                            ) : (
                                <div className="space-y-1">
                                    {subjects.map(subj => (
                                        <div key={subj.name}>
                                        <button
                                            onClick={() => setSelectedSubject(subj)}
                                            className={`w-full flex items-center space-x-2 px-3 py-2.5 rounded-lg text-left transition-all ${
                                                selectedSubject?.name === subj.name
                                                    ? 'bg-primary-50 text-primary-700 font-medium'
                                                    : 'hover:bg-gray-50 text-gray-700'
                                            }`}>
                                            <span className="text-xl">{subjectIcon(subj.name)}</span>
                                            <div className="flex-1 min-w-0">
                                                <p className="text-sm font-medium truncate">{subj.name}</p>
                                                <p className="text-xs text-gray-400">
                                                    {subj.fileCount} file{subj.fileCount !== 1 ? 's' : ''} &middot; {subj.topicCount} topics
                                                </p>
                                            </div>
                                            {selectedSubject?.name === subj.name && <ChevronRight className="w-4 h-4 text-primary-500" />}
                                        </button>
                                        {/* Show unit folders when subject selected */}
                                        {selectedSubject?.name === subj.name && subj.units?.length > 0 && (
                                            <div className="ml-4 mt-1 space-y-0.5 border-l-2 border-primary-100 pl-2">
                                                {subj.units.map(u => (
                                                    <div key={u.unitName || '_default'} className="flex items-center space-x-1 py-1 text-xs text-gray-500">
                                                        <Folder className="w-3 h-3 text-primary-400 flex-shrink-0" />
                                                        <span className="truncate font-medium text-gray-700">{u.unitName || 'General'}</span>
                                                        <span className="text-gray-400 flex-shrink-0">· {u.topicCount} topics</span>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Main Content Panel */}
                    <div className="lg:col-span-3 space-y-6">

                        {/* Upload Zone */}
                        <div className="grid md:grid-cols-2 gap-4">
                            {/* Syllabus Upload */}
                            <div className="card">
                                <div className="flex items-center space-x-2 mb-3">
                                    <BookOpen className="w-5 h-5 text-primary-600" />
                                    <h2 className="font-bold text-gray-800">Upload Syllabus / Schedule</h2>
                                </div>
                                <p className="text-xs text-gray-500 mb-3">PDF preferred. Topics are extracted and used to auto-build your Dashboard schedule.</p>
                                <form onSubmit={handleScheduleUpload} className="space-y-3">
                                    <input value={newSubjectName}
                                        onChange={e => setNewSubjectName(e.target.value)}
                                        className="input-field text-sm"
                                        placeholder={selectedSubject ? `${selectedSubject.name} (type to change)` : 'Folder name (e.g. 3rd Year, AIML)'} />
                                    <input ref={schedFileRef} type="file"
                                        accept=".pdf,.ppt,.pptx,.doc,.docx"
                                        className="block w-full text-sm text-gray-700" />
                                    <button type="submit" disabled={uploadingSchedule}
                                        className="btn-primary w-full inline-flex items-center justify-center space-x-2 disabled:opacity-60">
                                        {uploadingSchedule ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                                        <span>{uploadingSchedule ? 'Saving...' : 'Upload Syllabus'}</span>
                                    </button>
                                </form>
                            </div>

                                {/* Study Material Upload */}
                            <div className="card">
                                <div className="flex items-center space-x-2 mb-3">
                                    <Folder className="w-5 h-5 text-primary-600" />
                                    <h2 className="font-bold text-gray-800">Upload Study Material</h2>
                                </div>
                                <p className="text-xs text-gray-500 mb-3">Lecture slides, notes, handouts. Stored in subject/unit folders and used by the AI chatbot.</p>
                                <form onSubmit={handleMaterialUpload} className="space-y-3">
                                    <input value={newSubjectName}
                                        onChange={e => setNewSubjectName(e.target.value)}
                                        className="input-field text-sm"
                                        placeholder={selectedSubject ? `${selectedSubject.name} (type to change)` : 'Folder name (e.g. 3rd Year, AIML)'} />
                                    <input
                                        value={newUnitName}
                                        onChange={e => setNewUnitName(e.target.value)}
                                        className="input-field text-sm"
                                        placeholder="Unit / Module name (e.g. Unit 1, Module 3 — optional)" />
                                    <input ref={matFileRef} type="file"
                                        accept=".pdf,.ppt,.pptx,.doc,.docx"
                                        className="block w-full text-sm text-gray-700" />
                                    <button type="submit" disabled={uploadingMaterial}
                                        className="btn-secondary w-full inline-flex items-center justify-center space-x-2 disabled:opacity-60">
                                        {uploadingMaterial ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                                        <span>{uploadingMaterial ? 'Uploading...' : 'Upload Material'}</span>
                                    </button>
                                </form>
                            </div>
                        </div>

                        {/* Schedule Preview */}
                        <AnimatePresence>
                            {schedulePreview.length > 0 && (
                                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                                    className="card">
                                    <div className="flex items-center justify-between mb-3">
                                        <div className="flex items-center space-x-2">
                                            <CheckCircle className="w-5 h-5 text-green-500" />
                                            <h3 className="font-bold text-gray-800">Schedule Preview ({schedulePreview.length} blocks over 30 days)</h3>
                                        </div>
                                        <button onClick={() => setSchedulePreview([])}
                                            className="p-1 hover:bg-gray-100 rounded text-gray-500"><X className="w-4 h-4" /></button>
                                    </div>
                                    <div className="max-h-64 overflow-y-auto space-y-1.5">
                                        {schedulePreview.slice(0, 30).map(task => (
                                            <div key={task.id}
                                                className="flex items-center justify-between text-sm py-2 px-3 bg-gray-50 rounded-lg">
                                                <div>
                                                    <p className="font-medium text-gray-800">{task.topic}</p>
                                                    <p className="text-xs text-gray-400">{task.date} &middot; {task.time} &middot; {task.duration}</p>
                                                </div>
                                                <span className="text-xs text-gray-500 bg-white px-2 py-0.5 rounded border">{task.subject}</span>
                                            </div>
                                        ))}
                                    </div>
                                    <p className="text-xs text-gray-400 mt-2 text-center">
                                        Schedule saved &mdash; visible on your Dashboard
                                    </p>
                                </motion.div>
                            )}
                        </AnimatePresence>

                        {/* File Browser */}
                        {selectedSubject && (
                            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card">
                                <div className="flex items-center justify-between mb-4">
                                    <div className="flex items-center space-x-2">
                                        <FolderOpen className="w-5 h-5 text-primary-600" />
                                        <h2 className="font-bold text-gray-800">
                                            {subjectIcon(selectedSubject.name)} {selectedSubject.name}
                                        </h2>
                                        <span className="text-xs text-gray-400 ml-2">
                                            {selectedSubject.fileCount} file{selectedSubject.fileCount !== 1 ? 's' : ''} &middot; {selectedSubject.topicCount} topics indexed
                                        </span>
                                    </div>
                                    {hasTopics && (
                                        <button onClick={handleGenerateSchedule} disabled={generatingSchedule}
                                            className="btn-primary text-sm inline-flex items-center space-x-2 disabled:opacity-60 py-2 px-3">
                                            {generatingSchedule
                                                ? <><RefreshCw className="w-4 h-4 animate-spin" /><span>Building...</span></>
                                                : <><Calendar className="w-4 h-4" /><span>Build Dashboard Schedule</span></>
                                            }
                                        </button>
                                    )}
                                </div>

                                {loadingFiles ? (
                                    <p className="text-sm text-gray-400 animate-pulse">Loading files...</p>
                                ) : files.length === 0 ? (
                                    <p className="text-sm text-gray-400">No files in this subject yet. Upload above to add files here.</p>
                                ) : (
                                    <FileBrowser
                                        files={files}
                                        expandedFile={expandedFile}
                                        fileTopics={fileTopics}
                                        fileAnalysis={fileAnalysis}
                                        loadingTopics={loadingTopics}
                                        processingIds={processingIds}
                                        selectedSubject={selectedSubject}
                                        onExpand={loadAllTopics}
                                        onDelete={handleDelete}
                                        onMarkComplete={handleMarkComplete}
                                        onReschedule={handleRescheduleTopic}
                                        onUploadToUnit={async (file, unitName) => {
                                            const fd = new FormData();
                                            fd.append('file', file);
                                            fd.append('subject', selectedSubject?.name || '');
                                            if (unitName) fd.append('unit', unitName);
                                            setStatusMsg('Uploading to ' + (unitName || 'General') + '…');
                                            setStatusType('info');
                                            try {
                                                const res = await agentAPI.uploadStudyMaterial(fd);
                                                setStatusMsg(`Saved! Indexing in background.`);
                                                setStatusType('success');
                                                if (res.processing) setProcessingIds(ids => [...ids, res.id]);
                                                await loadSubjects();
                                                await loadFiles(selectedSubject.name);
                                            } catch {
                                                setStatusMsg('Upload failed.');
                                                setStatusType('error');
                                            }
                                        }}
                                        onRetry={(id) => {
                                            setProcessingIds(ids => [...ids, id]);
                                            agentAPI.triggerFileAnalysis(id).catch(() => {});
                                        }}
                                    />
                                )}
                            </motion.div>
                        )}

                        {!selectedSubject && subjects.length > 0 && (
                            <div className="card text-center py-12 text-gray-400">
                                <Folder className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                                <p className="font-medium">Select a subject folder on the left to view its files</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </DashboardLayout>
    );
};

export default SyllabusManager;
