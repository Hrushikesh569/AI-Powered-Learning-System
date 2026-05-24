
import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import DashboardLayout from '../layouts/DashboardLayout';
import Modal from '../components/Modal';
import AchievementCard from '../components/AchievementCard';
import MotivationTips from '../components/MotivationTips';
import ShapExplanation from '../components/ShapExplanation';
import { agentAPI, getAuthToken } from '../api';
import { CheckCircle, Clock, AlertCircle, TrendingUp, Calendar, Sparkles, Trophy, FileText, RefreshCw, Trash2 } from 'lucide-react';


const formatDate = (date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
};

const _cleanTopicName = (value) =>
    String(value || '').replace(/ — Day \d+$/, '').replace(/^\[Review\] /, '').trim();

const _normalizeDeadlineItems = (items = []) => {
    const seen = new Set();
    return (Array.isArray(items) ? items : [])
        .map((item) => ({ ...item }))
        .filter((item) => {
            const key = item.id ?? `${String(item.due_date || '')}|${String(item.subject || '')}|${String(item.title || '')}|${String(item.source_text || '')}`;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        })
        .sort((left, right) => {
            const leftDate = left.due_date ? new Date(left.due_date).getTime() : Number.MAX_SAFE_INTEGER;
            const rightDate = right.due_date ? new Date(right.due_date).getTime() : Number.MAX_SAFE_INTEGER;
            return leftDate - rightDate;
        });
};

// ── Persistent task-status helpers (survive page reloads) ─────────────────────
// Key = "date|cleanTopic" — stable across schedule regenerations.
const _taskKey = (t) =>
    `${t.date || ''}|${_cleanTopicName(t.topic || '')}`;

const _loadStatuses = () => {
    try { return JSON.parse(localStorage.getItem('taskStatuses') || '{}'); } catch (_) { return {}; }
};

const _saveStatus = (task, status) => {
    try {
        const s = _loadStatuses();
        s[_taskKey(task)] = status;
        localStorage.setItem('taskStatuses', JSON.stringify(s));
    } catch (_) {}
};

// Re-apply persisted statuses on top of a freshly generated schedule list.
const _applyStatuses = (list) => {
    const s = _loadStatuses();
    return list.map(t => ({ ...t, status: s[_taskKey(t)] || t.status || 'pending' }));
};

const _pickResourceLinks = (resources = []) => {
    const web = resources.find((r) => (r.type || '').toLowerCase() !== 'video');
    const video = resources.find((r) => (r.type || '').toLowerCase() === 'video');
    return { web, video };
};

const _buildFallbackResourceLinks = (topic, subject = '') => {
    const cleanTopic = String(topic || '').trim();
    if (!cleanTopic) return [];
    const query = [cleanTopic, String(subject || '').trim()].filter(Boolean).join(' ');
    const encoded = encodeURIComponent(query);
    return [
        {
            title: `Web Search: ${cleanTopic}`,
            url: `https://www.google.com/search?q=${encoded}`,
            type: 'web',
            icon: '🔍',
        },
        {
            title: `YouTube Videos: ${cleanTopic}`,
            url: `https://www.youtube.com/results?search_query=${encoded}`,
            type: 'video',
            icon: '▶️',
        },
    ];
};

const _buildSlotsInWindow = (start = '09:00', end = '21:00', maxSlots = 8) => {
    const toMinutes = (v) => {
        const [h, m] = String(v || '00:00').split(':').map((x) => Number(x || 0));
        return (h * 60) + m;
    };
    const toLabel = (mins) => {
        const h24 = Math.floor(mins / 60) % 24;
        const mm = String(mins % 60).padStart(2, '0');
        const ampm = h24 >= 12 ? 'PM' : 'AM';
        const h12 = h24 % 12 || 12;
        return `${String(h12).padStart(2, '0')}:${mm} ${ampm}`;
    };

    let a = toMinutes(start);
    let b = toMinutes(end);
    if (!Number.isFinite(a) || !Number.isFinite(b)) {
        a = 9 * 60;
        b = 21 * 60;
    }
    if (b <= a) b = a + 180;

    const span = b - a;
    const step = Math.max(45, Math.floor(span / Math.max(1, maxSlots)));
    const slots = [];
    for (let t = a; t < b && slots.length < maxSlots; t += step) {
        slots.push(toLabel(t));
    }
    return slots.length ? slots : ['09:00 AM', '11:00 AM', '02:00 PM', '05:00 PM'];
};

const _defaultTimeSlots = _buildSlotsInWindow('09:00', '21:00', 5);

const _normalizeHiddenEntry = (entry) => {
    if (typeof entry === 'string') {
        const subject = String(entry || '').trim();
        return subject ? { subject, unit: '', topic: '', scope: 'subject' } : null;
    }
    if (!entry || typeof entry !== 'object') return null;
    const subject = String(entry.subject || '').trim();
    if (!subject) return null;
    const unit = String(entry.unit || '').trim();
    const topic = _cleanTopicName(entry.topic || '').trim();
    const scope = entry.scope || (topic ? 'topic' : unit ? 'unit' : 'subject');
    return { subject, unit, topic, scope };
};

const _loadHiddenEntries = () => {
    try {
        const raw = JSON.parse(localStorage.getItem('hiddenStudyItems') || '[]');
        const normalized = Array.isArray(raw) ? raw.map(_normalizeHiddenEntry).filter(Boolean) : [];
        if (normalized.length) return normalized;
    } catch (_) {}

    try {
        const legacy = JSON.parse(localStorage.getItem('hiddenSubjects') || '[]');
        if (!Array.isArray(legacy)) return [];
        return legacy.map((subject) => _normalizeHiddenEntry(subject)).filter(Boolean);
    } catch (_) {
        return [];
    }
};

const _hiddenEntryKey = (entry) => {
    const item = _normalizeHiddenEntry(entry);
    if (!item) return '';
    return `${item.subject}|||${item.unit || ''}|||${item.topic || ''}`;
};

const _taskMatchesHiddenEntry = (task, hiddenEntry) => {
    const item = _normalizeHiddenEntry(hiddenEntry);
    if (!item) return false;
    const taskSubject = String(task?.subject || '').trim();
    const taskUnit = String(task?.unit || '').trim();
    const taskTopic = _cleanTopicName(task?.topic || '').trim();
    if (!taskSubject || taskSubject !== item.subject) return false;
    if (item.unit && taskUnit !== item.unit) return false;
    if (item.topic && taskTopic !== item.topic) return false;
    return true;
};

const _isTaskHidden = (task, hiddenEntries = []) =>
    (hiddenEntries || []).some((entry) => _taskMatchesHiddenEntry(task, entry));

const _removeHiddenEntriesForSelection = (hiddenEntries, selection) => {
    const selected = _normalizeHiddenEntry(selection);
    if (!selected) return hiddenEntries;
    return hiddenEntries.filter((entry) => {
        const item = _normalizeHiddenEntry(entry);
        if (!item || item.subject !== selected.subject) return true;
        if (selected.topic) return !( (!item.unit || item.unit === selected.unit) && (!item.topic || item.topic === selected.topic) );
        if (selected.unit) return !( !item.unit || item.unit === selected.unit );
        return false;
    });
};

const _groupHiddenEntries = (entries = []) => {
    const grouped = {};
    (entries || []).map(_normalizeHiddenEntry).filter(Boolean).forEach((entry) => {
        if (!grouped[entry.subject]) grouped[entry.subject] = { subject: entry.subject, units: {} };
        const unitName = entry.unit || 'General';
        if (!grouped[entry.subject].units[unitName]) grouped[entry.subject].units[unitName] = [];
        grouped[entry.subject].units[unitName].push(entry);
    });
    return Object.values(grouped).map((subject) => ({
        ...subject,
        units: Object.entries(subject.units).map(([unitName, items]) => ({ unitName, items })),
    }));
};

const _buildMixedScheduleFromBackend = async ({
    todayIso,
    preferredTopics = [],
    hiddenSubjects = [],
    hoursPerDay = 3,
    fallbackHierarchy = [],
}) => {
    try {
        const token = localStorage.getItem('authToken');
        const intelligent = await agentAPI.getIntelligentSchedule({
            hours_per_day: Number(hoursPerDay) || 3,
            num_days: 60,
            cross_subject: true,
        }, token);
        const schedule = intelligent?.schedule || [];
        if (schedule.length) {
            const preferredSet = new Set((preferredTopics || []).map(_cleanTopicName).filter(Boolean));
            const filtered = schedule
                .filter((row) => !_isTaskHidden(row, hiddenSubjects))
                .sort((a, b) => {
                    const aDate = String(a.date || todayIso).slice(0, 10);
                    const bDate = String(b.date || todayIso).slice(0, 10);
                    if (aDate !== bDate) return aDate.localeCompare(bDate);
                    const aUnitIndex = Number.isFinite(Number(a.unit_number)) ? Number(a.unit_number) : Number(a.unit_index ?? 0);
                    const bUnitIndex = Number.isFinite(Number(b.unit_number)) ? Number(b.unit_number) : Number(b.unit_index ?? 0);
                    if (aUnitIndex !== bUnitIndex) return aUnitIndex - bUnitIndex;
                    const aTopicIndex = Number.isFinite(Number(a.topic_index)) ? Number(a.topic_index) : 0;
                    const bTopicIndex = Number.isFinite(Number(b.topic_index)) ? Number(b.topic_index) : 0;
                    if (aTopicIndex !== bTopicIndex) return aTopicIndex - bTopicIndex;
                    const aPreferred = preferredSet.has(_cleanTopicName(a.topic));
                    const bPreferred = preferredSet.has(_cleanTopicName(b.topic));
                    if (aPreferred !== bPreferred) return aPreferred ? -1 : 1;
                    const aSubject = String(a.subject || '');
                    const bSubject = String(b.subject || '');
                    if (aSubject !== bSubject) return aSubject.localeCompare(bSubject);
                    return String(a.time || '').localeCompare(String(b.time || ''));
                })
                .map((item) => ({
                    id: item.id,
                    scheduled_topic_id: item.id,
                    date: String(item.date || todayIso).slice(0, 10),
                    time: item.time || _defaultTimeSlots[0],
                    subject: item.subject || 'General',
                    subject_code: item.subject_code || '',
                    unit: item.unit || item.unit_name || '',
                    topic: item.topic || item.topic_name || 'Study Topic',
                    unit_number: Number.isFinite(Number(item.unit_number)) ? Number(item.unit_number) : Number(item.unit_index ?? 0),
                    difficulty: item.difficulty,
                    difficultyLabel: item.difficultyLabel || item.difficulty_label || '',
                    estimated_hours: Number(item.estimated_hours || 1),
                    duration: item.duration || (Number(item.estimated_hours || 1) < 1 ? `${Math.round(Number(item.estimated_hours || 1) * 60)} min` : `${Number(item.estimated_hours || 1).toFixed(1)} hour${Number(item.estimated_hours || 1) === 1 ? '' : 's'}`),
                    key_concepts: item.key_concepts || [],
                    is_foundational: Boolean(item.is_foundational),
                    status: item.status || 'pending',
                    completed_date: item.completed_date || null,
                    unit_index: Number.isFinite(Number(item.unit_index)) ? Number(item.unit_index) : Number(item.unit_number ?? 0),
                    topic_index: Number.isFinite(Number(item.topic_index)) ? Number(item.topic_index) : 0,
                    user_override: Boolean(item.custom_added),
                    custom_added: Boolean(item.custom_added),
                }));
            if (filtered.length) return filtered;
        }
    } catch (_) {}

    let rows = [];
    try {
        const rowsRes = await agentAPI.queryScheduledTopics({});
        rows = rowsRes?.topics || [];
    } catch (_) {
        rows = [];
    }

    if (!rows.length && Array.isArray(fallbackHierarchy) && fallbackHierarchy.length) {
        rows = fallbackHierarchy.flatMap((subject) =>
            (subject.units || []).flatMap((unit) =>
                (unit.topics || []).map((topic) => ({
                    id: `${subject.subject_name || 'subject'}-${unit.unit_name || 'unit'}-${topic.name || 'topic'}`,
                    subject: subject.subject_name || 'General',
                    subject_code: subject.subject_code || '',
                    unit_name: unit.unit_name || '',
                    topic_name: topic.name || 'Study Topic',
                    estimated_hours: topic.est_hours || topic.estimated_hours || 1,
                    difficulty: topic.difficulty || 3,
                    status: 'pending',
                })),
            ),
        );
    }

    if (!rows.length) return [];

    const uniqueSubjects = [...new Set(rows.map((row) => row.subject || 'General'))];
    const hierarchySubjects = Array.isArray(fallbackHierarchy)
        ? [...new Set(fallbackHierarchy.map((subject) => subject.subject_name).filter(Boolean))]
        : [];
    if (rows.length > 0 && uniqueSubjects.length <= 1 && hierarchySubjects.length > 1) {
        rows = fallbackHierarchy.flatMap((subject) =>
            (subject.units || []).flatMap((unit) =>
                (unit.topics || []).map((topic) => ({
                    id: `${subject.subject_name || 'subject'}-${unit.unit_name || 'unit'}-${topic.name || 'topic'}`,
                    subject: subject.subject_name || 'General',
                    subject_code: subject.subject_code || '',
                    unit_name: unit.unit_name || '',
                    topic_name: topic.name || 'Study Topic',
                    estimated_hours: topic.est_hours || topic.estimated_hours || 1,
                    difficulty: topic.difficulty || 3,
                    status: 'pending',
                })),
            ),
        );
    }

    if (Array.isArray(hiddenSubjects) && hiddenSubjects.length) rows = rows.filter((row) => !_isTaskHidden(row, hiddenSubjects));
    if (!rows.length) return [];

    const diffRank = { easy: 1, basic: 2, intermediate: 3, medium: 3, hard: 4, advanced: 5 };
    const diffLabelByRank = ['', 'Easy', 'Basic', 'Intermediate', 'Hard', 'Advanced'];
    const dayBudget = Math.max(1, Number(hoursPerDay) || 3);
    const clampHours = (value) => {
        let hrs = Number(value || 1);
        if (!Number.isFinite(hrs) || hrs <= 0) hrs = 1;
        return Math.max(0.5, Math.min(2.5, hrs));
    };

    const normalizedDifficulty = (value) => {
        if (typeof value === 'number') return Math.max(1, Math.min(5, value));
        const mapped = diffRank[String(value || '').toLowerCase()];
        return mapped || 3;
    };

    const buildItem = (t, assignedDate, slotIndex, queueIndex = 0, queueTotal = 1) => {
        const difficultyValue = normalizedDifficulty(t.difficulty);
        const hrs = clampHours(t.estimated_hours);
        const rawDifficultyLabel = String(t.difficultyLabel || '').trim();
        const fallbackDifficultyLabel = diffLabelByRank[difficultyValue] || String(t.difficulty || 'Intermediate');
        return {
            id: t.id,
            scheduled_topic_id: t.id,
            date: assignedDate,
            time: _defaultTimeSlots[slotIndex % _defaultTimeSlots.length],
            subject: t.subject || 'General',
            unit: t.unit_name || '',
            topic: t.topic_name || 'Study Topic',
            difficulty: difficultyValue,
            difficultyLabel: rawDifficultyLabel || fallbackDifficultyLabel,
            estimated_hours: hrs,
            duration: hrs < 1 ? `${Math.round(hrs * 60)} min` : `${hrs.toFixed(1)} hour${hrs === 1 ? '' : 's'}`,
            key_concepts: [],
            is_foundational: false,
            status: t.status || 'pending',
            completed_date: t.completed_date || null,
            user_override: Boolean(t.custom_added),
        };
    };

    const explicitRows = rows.filter((row) => row.rescheduled_date || row.scheduled_date);
    const flexRows = rows.filter((row) => !(row.rescheduled_date || row.scheduled_date));
    const explicitDates = explicitRows
        .map((row) => String(row.rescheduled_date || row.scheduled_date || todayIso).slice(0, 10))
        .filter(Boolean)
        .sort();
    const startDate = new Date(`${(explicitDates.at(-1) || todayIso)}T00:00:00`);
    if (!explicitDates.length || startDate < new Date(`${todayIso}T00:00:00`)) {
        startDate.setTime(new Date(`${todayIso}T00:00:00`).getTime());
    } else {
        startDate.setDate(startDate.getDate() + 1);
    }

    const scheduled = explicitRows
        .sort((a, b) => {
            const aDate = String(a.rescheduled_date || a.scheduled_date || todayIso).slice(0, 10);
            const bDate = String(b.rescheduled_date || b.scheduled_date || todayIso).slice(0, 10);
            if (aDate !== bDate) return aDate.localeCompare(bDate);
            const da = normalizedDifficulty(a.difficulty);
            const db = normalizedDifficulty(b.difficulty);
            if (db !== da) return db - da;
            return Number(b.estimated_hours || 1) - Number(a.estimated_hours || 1);
        })
        .map((t, index) => buildItem(t, String(t.rescheduled_date || t.scheduled_date || todayIso).slice(0, 10), index));

    const subjectQueues = new Map();
    for (const row of flexRows) {
        const subject = row.subject || 'General';
        if (!subjectQueues.has(subject)) subjectQueues.set(subject, []);
        subjectQueues.get(subject).push(row);
    }

    const subjectNames = [...subjectQueues.keys()];

    for (const [subject, queue] of subjectQueues.entries()) {
        subjectQueues.set(subject, queue);
    }

    const mixedSchedule = [];
    let cursorDate = startDate;
    let dayIndex = 0;

    while (subjectNames.some((subject) => (subjectQueues.get(subject) || []).length)) {
        let dailyRemaining = dayBudget;
        let slotIndex = 0;
        const rotationStart = subjectNames.length ? dayIndex % subjectNames.length : 0;

        for (let offset = 0; offset < subjectNames.length; offset += 1) {
            const subject = subjectNames[(rotationStart + offset) % subjectNames.length];
            const queue = subjectQueues.get(subject) || [];
            if (!queue.length) continue;

            const candidate = queue[0];
            const hrs = clampHours(candidate.estimated_hours);
            if (hrs > dailyRemaining && dailyRemaining >= 0.5) continue;

            queue.shift();
            mixedSchedule.push(buildItem(candidate, formatDate(cursorDate), slotIndex));
            dailyRemaining -= hrs;
            slotIndex += 1;
        }

        let madeProgress = true;
        while (dailyRemaining >= 0.5 && madeProgress) {
            madeProgress = false;
            for (let offset = 0; offset < subjectNames.length; offset += 1) {
                const subject = subjectNames[(rotationStart + offset) % subjectNames.length];
                const queue = subjectQueues.get(subject) || [];
                if (!queue.length) continue;

                const candidate = queue[0];
                const hrs = clampHours(candidate.estimated_hours);
                if (hrs > dailyRemaining && dailyRemaining >= 0.5) continue;

                queue.shift();
                mixedSchedule.push(buildItem(candidate, formatDate(cursorDate), slotIndex));
                dailyRemaining -= hrs;
                slotIndex += 1;
                madeProgress = true;
                break;
            }
        }

        cursorDate.setDate(cursorDate.getDate() + 1);
        dayIndex += 1;
    }

    return [...scheduled, ...mixedSchedule];
};
const _withTimeout = async (promise, ms = 12000, fallback = null) => {
    let timer;
    try {
        return await Promise.race([
            promise,
            new Promise((resolve) => {
                timer = setTimeout(() => resolve(fallback), ms);
            }),
        ]);
    } finally {
        if (timer) clearTimeout(timer);
    }
};

const Dashboard = () => {
    const todayIso = formatDate(new Date());
    const [showRescheduleModal, setShowRescheduleModal] = useState(false);
    const [tasks, setTasks] = useState([]);
    const [calendarDays, setCalendarDays] = useState([]);
    const [selectedDate, setSelectedDate] = useState('');
    const [activityByDate, setActivityByDate] = useState({});
    const [userJoinDate, setUserJoinDate] = useState(null);
    const [currentMonth, setCurrentMonth] = useState(() => {
        const now = new Date();
        return new Date(now.getFullYear(), now.getMonth(), 1);
    });
    const [weeklyProgress, setWeeklyProgress] = useState({ percentage: 0, completedHours: 0, totalHours: 0, streak: 0 });
    const [aiSuggestions, setAiSuggestions] = useState([]);
    const [motivationalQuotes, setMotivationalQuotes] = useState([]);
    const [achievements, setAchievements] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [adaptiveMsg, setAdaptiveMsg] = useState(null);
    const [timeModal, setTimeModal] = useState(null); // { task, addAmount, addUnit } when open
    const [topicMaterials, setTopicMaterials] = useState({}); // topic → [{filename, page, ...}]
    const [topicResources, setTopicResources] = useState({}); // topic → [{title,url,type,...}]
    const [deadlineItems, setDeadlineItems] = useState([]);
    const [deadlineText, setDeadlineText] = useState('');
    const [deadlineTextSubject, setDeadlineTextSubject] = useState('');
    const [deadlineTextLoading, setDeadlineTextLoading] = useState(false);
    const [topicPicker, setTopicPicker] = useState(false); // show "add topic today" modal
    const [topicPickerMode, setTopicPickerMode] = useState('syllabus');
    const [topicPickerSubject, setTopicPickerSubject] = useState(''); // selected subject in picker
    const [topicPickerUnit, setTopicPickerUnit] = useState(''); // selected unit in picker
    const [topicPickerTopic, setTopicPickerTopic] = useState(''); // selected topic in picker
    const [subjectHierarchy, setSubjectHierarchy] = useState([]); // backend hierarchy for picker
    const [preferredTopics, setPreferredTopics] = useState(() => {
        try {
            const raw = localStorage.getItem('preferredTopics') || '[]';
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
        } catch (_) {
            return [];
        }
    });
    const [preferredTopicDraft, setPreferredTopicDraft] = useState('');
    const [hiddenSubjects, setHiddenSubjects] = useState(() => _loadHiddenEntries());
    const [rebuildingSchedule, setRebuildingSchedule] = useState(false);
    const [customTopicName, setCustomTopicName] = useState('');
    const [customTopicSubject, setCustomTopicSubject] = useState('');
    const [customTopicDuration, setCustomTopicDuration] = useState('1');
    const [customTopicLoading, setCustomTopicLoading] = useState(false);
    const [calendarInitialized, setCalendarInitialized] = useState(false);

    const mergeWithPastHistory = (freshList) => {
        let existing = [];
        try {
            existing = JSON.parse(localStorage.getItem('generatedSchedule') || '[]');
            if (!Array.isArray(existing)) existing = [];
        } catch (_) {
            existing = [];
        }
        const keepPast = existing.filter((t) => {
            const st = t.status || 'pending';
            return (t.date || '') < todayIso && ['completed', 'missed', 'skipped'].includes(st);
        });
        const keySet = new Set(freshList.map((t) => _taskKey(t)));
        const historicOnly = keepPast.filter((t) => !keySet.has(_taskKey(t)));
        return [...freshList, ...historicOnly].sort((a, b) => {
            if ((a.date || '') !== (b.date || '')) return (a.date || '').localeCompare(b.date || '');
            return String(a.time || '').localeCompare(String(b.time || ''));
        });
    };

    const carryForwardMissedTopics = (list) => {
        const base = list.map((task) => ({ ...task }));
        const fallbackSlots = ['09:00 AM', '11:00 AM', '02:00 PM', '05:00 PM', '08:00 PM'];
        const cloned = [];
        const seenCarry = new Set();

        const hasSameTopic = (items, candidate) => items.some((item) =>
            item.date === candidate.date &&
            _cleanTopicName(item.topic) === _cleanTopicName(candidate.topic) &&
            (item.subject || '') === (candidate.subject || '') &&
            (item.unit || '') === (candidate.unit || '') &&
            (item.status || 'pending') !== 'later'
        );

        const countOnDate = (items, date) => items.filter((item) => item.date === date && (item.status || 'pending') !== 'later').length;

        for (const task of base) {
            const isPastPending = task.date && task.date < todayIso && (task.status || 'pending') === 'pending';
            if (!isPastPending) continue;

            const carryKey = `${task.date}|${_cleanTopicName(task.topic)}|${task.subject || ''}|${task.unit || ''}`;
            if (seenCarry.has(carryKey)) continue;
            seenCarry.add(carryKey);

            _saveStatus(task, 'missed');
            task.status = 'missed';

            const sourceDate = new Date(`${task.date}T00:00:00`);
            let targetDate = new Date(sourceDate);
            targetDate.setDate(targetDate.getDate() + 1);
            let targetIso = formatDate(targetDate);
            for (let i = 0; i < 14; i += 1) {
                const candidateDate = new Date(sourceDate);
                candidateDate.setDate(candidateDate.getDate() + 1 + i);
                const candidateIso = formatDate(candidateDate);
                if (countOnDate([...base, ...cloned], candidateIso) < 5) {
                    targetIso = candidateIso;
                    break;
                }
            }

            const usedSlots = new Set([...base, ...cloned].filter((item) => item.date === targetIso).map((item) => item.time));
            const freeSlot = fallbackSlots.find((slot) => !usedSlots.has(slot)) || fallbackSlots[0];
            const clone = {
                ...task,
                id: Date.now() + cloned.length + 1,
                date: targetIso,
                time: freeSlot,
                status: 'pending',
                user_override: true,
                carriedForwardOf: carryKey,
            };
            _saveStatus(clone, 'pending');
            cloned.push(clone);
        }

        return [...base, ...cloned].sort((a, b) => {
            if ((a.date || '') !== (b.date || '')) return (a.date || '').localeCompare(b.date || '');
            return String(a.time || '').localeCompare(String(b.time || ''));
        });
    };

    useEffect(() => {
        try { localStorage.setItem('preferredTopics', JSON.stringify(preferredTopics)); } catch (_) {}
    }, [preferredTopics]);

    useEffect(() => {
        const normalized = (hiddenSubjects || []).map(_normalizeHiddenEntry).filter(Boolean);
        try { localStorage.setItem('hiddenStudyItems', JSON.stringify(normalized)); } catch (_) {}
        try {
            localStorage.setItem(
                'hiddenSubjects',
                JSON.stringify([...new Set(normalized.map((item) => item.subject).filter(Boolean))]),
            );
        } catch (_) {}
    }, [hiddenSubjects]);

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            setError('');

            // Hard safety: never keep spinner forever due to a stalled network request.
            const forceStop = setTimeout(() => {
                setLoading(false);
                setAdaptiveMsg('Some dashboard data timed out. Showing available data.');
                setTimeout(() => setAdaptiveMsg(null), 4000);
            }, 20000);

            try {
                // Load any stored per-day activity (in minutes)
                try {
                    const storedActivity = localStorage.getItem('activityMap');
                    if (storedActivity) {
                        setActivityByDate(JSON.parse(storedActivity));
                    }
                } catch (e) {
                    // ignore malformed storage
                }
                // Read learning preferences
                let prefs = { studyHours: 3 };
                try {
                    const stored = localStorage.getItem('learningPreferences');
                    if (stored) prefs = { ...prefs, ...JSON.parse(stored) };
                } catch (_) {}

                let storedSchedule = [];
                try {
                    const raw = JSON.parse(localStorage.getItem('generatedSchedule') || '[]');
                    storedSchedule = Array.isArray(raw) ? raw : [];
                } catch (_) {
                    storedSchedule = [];
                }

                if (storedSchedule.length > 0) {
                    const combined = _applyStatuses([...storedSchedule]);
                    const merged = carryForwardMissedTopics(mergeWithPastHistory(combined));
                    setTasks(merged);
                    try { localStorage.setItem('generatedSchedule', JSON.stringify(merged)); } catch (_) {}
                    setLoading(false);
                }

                const token = getAuthToken();
                const profileRes = await _withTimeout(agentAPI.getMe(token), 8000, null).catch(() => null);

                const studyHours = Math.max(
                    0.5,
                    Number(profileRes?.studyHoursPerDay ?? prefs.studyHours ?? 3) || 3,
                );
                prefs = { ...prefs, studyHours };
                try {
                    localStorage.setItem('learningPreferences', JSON.stringify({
                        ...prefs,
                        studyHours,
                        studyHoursPerDay: studyHours,
                    }));
                } catch (_) {}

                const [hierarchyRes, progressRes, deadlinesRes] = await Promise.all([
                    _withTimeout(agentAPI.getSubjectHierarchy(), 8000, { hierarchy: [] }).catch(() => ({ hierarchy: [] })),
                    _withTimeout(agentAPI.getProgressDashboard(token), 8000, null).catch(() => null),
                    _withTimeout(agentAPI.getDeadlines({}, token), 8000, { deadlines: [] }).catch(() => ({ deadlines: [] })),
                ]);

                const hierarchy = hierarchyRes?.hierarchy || [];
                setSubjectHierarchy(hierarchy);

                const backendTasks = await _withTimeout(_buildMixedScheduleFromBackend({
                    todayIso,
                    preferredTopics,
                    hiddenSubjects,
                    hoursPerDay: studyHours,
                    fallbackHierarchy: hierarchy,
                }), 12000, []);

                let progressTaskSource = [];

                if (backendTasks.length > 0) {
                    const combined = _applyStatuses([...backendTasks]);
                    const merged = carryForwardMissedTopics(mergeWithPastHistory(combined));
                    setTasks(merged);
                    try { localStorage.setItem('generatedSchedule', JSON.stringify(merged)); } catch (_) {}
                    progressTaskSource = merged;
                } else if (!storedSchedule.length) {
                    setTasks([]);
                } else {
                    progressTaskSource = carryForwardMissedTopics(mergeWithPastHistory(_applyStatuses([...storedSchedule])));
                }

                const safeProgress = progressRes || {};
                setWeeklyProgress(safeProgress.weeklyProgress || { percentage: 0, completedHours: 0, totalHours: 0, streak: 0 });
                setDeadlineItems(_normalizeDeadlineItems(deadlinesRes?.deadlines || []));
                setAiSuggestions(safeProgress.suggestions || []);
                setMotivationalQuotes(safeProgress.motivationalQuotes || []);
                setAchievements(safeProgress.achievements || []);
            } catch (err) {
                setError('Failed to load dashboard data.');
            } finally {
                clearTimeout(forceStop);
                setLoading(false);
            }
        };
        fetchData();
    }, [preferredTopics, hiddenSubjects]);

    useEffect(() => {
        const refreshLiveProgress = async () => {
            try {
                const token = getAuthToken();
                const [progressRes, deadlinesRes] = await Promise.all([
                    _withTimeout(agentAPI.getProgressDashboard(token), 8000, null).catch(() => null),
                    _withTimeout(agentAPI.getDeadlines({}, token), 8000, { deadlines: [] }).catch(() => ({ deadlines: [] })),
                ]);
                const safeProgress = progressRes || {};
                setWeeklyProgress(safeProgress.weeklyProgress || { percentage: 0, completedHours: 0, totalHours: 0, streak: 0 });
                setDeadlineItems(_normalizeDeadlineItems(deadlinesRes?.deadlines || []));
                setAiSuggestions(safeProgress.suggestions || []);
                setMotivationalQuotes(safeProgress.motivationalQuotes || []);
                setAchievements(safeProgress.achievements || []);
            } catch (_) {}
        };

        refreshLiveProgress();
        const intervalId = setInterval(refreshLiveProgress, 60000);
        return () => clearInterval(intervalId);
    }, []);

    // Recompute the list of days whenever the visible month changes
    useEffect(() => {
        const year = currentMonth.getFullYear();
        const month = currentMonth.getMonth();
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const days = [];
        for (let day = 1; day <= daysInMonth; day += 1) {
            const d = new Date(year, month, day);
            days.push(formatDate(d));
        }
        setCalendarDays(days);
    }, [currentMonth]);

    // Ensure selectedDate defaults to today and stays within the visible month.
    useEffect(() => {
        if (!calendarDays.length || calendarInitialized) return;

        const todayInMonth = calendarDays.find((d) => d === todayIso);
        if (todayInMonth) {
            setSelectedDate(todayInMonth);
        } else {
            setCurrentMonth(new Date(new Date(todayIso).getFullYear(), new Date(todayIso).getMonth(), 1));
            setSelectedDate(calendarDays[0] || todayIso);
        }
        setCalendarInitialized(true);
    }, [calendarDays, todayIso, calendarInitialized]);

    useEffect(() => {
        if (!calendarDays.length) return;
        if (calendarDays.includes(selectedDate)) return;

        const todayInMonth = calendarDays.find((d) => d === todayIso);
        if (todayInMonth) {
            setSelectedDate(todayInMonth);
            return;
        }

        setSelectedDate(calendarDays[0]);
    }, [calendarDays, selectedDate, todayIso]);

    const randomQuote = motivationalQuotes.length
        ? motivationalQuotes[0]
        : 'Keep going—consistent small steps lead to big progress.';

    const parseDurationToMinutes = (duration) => {
        if (!duration) return 0;
        const numeric = parseFloat(duration);
        if (Number.isNaN(numeric)) return 0;
        const low = String(duration).toLowerCase();
        if (low.includes('hour') || low.endsWith('h')) {
            return Math.round(numeric * 60);
        }
        if (low.includes('min')) {
            return Math.round(numeric);
        }
        return 0;
    };

    const markComplete = async (id) => {
        let topicToSync = null;
        setTasks((prevTasks) => {
            const target = prevTasks.find((t) => t.id === id);
            if (target) {
                if ((target.status || 'pending') === 'completed') return prevTasks;
                topicToSync = target;
                const minutes = parseDurationToMinutes(target.duration);
                if (minutes > 0 && target.date) {
                    setActivityByDate((prev) => {
                        const next = {
                            ...prev,
                            [target.date]: (prev[target.date] || 0) + minutes,
                        };
                        try {
                            localStorage.setItem('activityMap', JSON.stringify(next));
                        } catch (e) {
                            // ignore storage issues
                        }
                        return next;
                    });
                }
                // Track completed subject for analytics (not topic)
                const subject = target.subject || 'General';
                try {
                    const completedSubjects = JSON.parse(localStorage.getItem('completedSubjects') || '{}');
                    completedSubjects[subject] = (completedSubjects[subject] || 0) + 1;
                    localStorage.setItem('completedSubjects', JSON.stringify(completedSubjects));
                    // Also track for adaptive rescheduling with topics
                    const topicName = (target.topic || '').replace(/ — Day \d+$/, '').replace(/^\[Review\] /, '');
                    const done = JSON.parse(localStorage.getItem('completedTopics') || '[]');
                    if (topicName && !done.includes(topicName)) done.push(topicName);
                    localStorage.setItem('completedTopics', JSON.stringify(done));
                    // Persist status so it survives page reload
                    _saveStatus(target, 'completed');
                    // Trigger adaptive reschedule every 3 completions
                    if (done.length % 3 === 0) {
                        const missed = JSON.parse(localStorage.getItem('missedTopics') || '[]');
                        setTimeout(() => triggerAdaptiveReschedule(done, missed), 200);
                    }
                } catch (_) {}
            }
            return prevTasks.map((task) => (task.id === id ? { ...task, status: 'completed' } : task));
        });

        // Sync with backend so completion is reflected in syllabus folders and analytics.
        try {
            if (topicToSync?.scheduled_topic_id) {
                await agentAPI.markTopicComplete(topicToSync.scheduled_topic_id, 'Completed from dashboard');
            } else if (topicToSync?.subject && topicToSync?.topic) {
                const rows = await agentAPI.queryScheduledTopics({ subject: topicToSync.subject });
                const clean = String(topicToSync.topic || '').replace(/ — Day \d+$/, '').replace(/^\[Review\] /, '').trim().toLowerCase();
                const match = (rows?.topics || []).find((r) =>
                    String(r.topic_name || '').trim().toLowerCase() === clean &&
                    String(r.status || 'pending') !== 'completed'
                );
                if (match?.id) {
                    await agentAPI.markTopicComplete(match.id, 'Completed from dashboard');
                }
            }
        } catch (_) {
            // Keep local completion even if network sync fails.
        }

        // Refresh server-derived progress widgets.
        try {
            const progressRes = await agentAPI.getProgressDashboard();
            setWeeklyProgress(progressRes?.weeklyProgress || { percentage: 0, completedHours: 0, totalHours: 0, streak: 0 });
            setAchievements(progressRes?.achievements || []);
        } catch (_) {}
    };

    const markMissed = (id) => {
        setTasks((prevTasks) => {
            const target = prevTasks.find((t) => t.id === id);
            if (target) {
                const topicName = (target.topic || '').replace(/ — Day \d+$/, '').replace(/^\[Review\] /, '');
                try {
                    const missed = JSON.parse(localStorage.getItem('missedTopics') || '[]');
                    if (topicName && !missed.includes(topicName)) missed.push(topicName);
                    localStorage.setItem('missedTopics', JSON.stringify(missed));
                    // Persist status so it survives page reload
                    _saveStatus(target, 'missed');
                    const done = JSON.parse(localStorage.getItem('completedTopics') || '[]');
                    setTimeout(() => triggerAdaptiveReschedule(done, missed), 200);
                } catch (_) {}
            }
            return prevTasks.map((task) => (task.id === id ? { ...task, status: 'missed' } : task));
        });
    };

    const triggerAdaptiveReschedule = async (completedTopics = [], missedTopics = []) => {
        try {
            const prefs = JSON.parse(localStorage.getItem('learningPreferences') || '{}');
            const stressLevel = parseFloat(localStorage.getItem('stressLevel') || '0.3');
            const currentSchedule = JSON.parse(localStorage.getItem('generatedSchedule') || '[]');
            const skippedTopics = currentSchedule
                .filter((task) => String(task.status || '').toLowerCase() === 'skipped')
                .map((task) => task.topic || task.subject || task.name)
                .filter(Boolean);
            const doLaterTopics = currentSchedule
                .filter((task) => String(task.status || '').toLowerCase() === 'later')
                .map((task) => task.topic || task.subject || task.name)
                .filter(Boolean);
            const total = completedTopics.length + missedTopics.length;
            const performanceScore = total > 0 ? completedTopics.length / total : 0.7;

            const res = await agentAPI.getAdaptiveSchedule({
                completed_topics: completedTopics,
                missed_topics: missedTopics,
                skipped_topics: skippedTopics,
                do_later_topics: doLaterTopics,
                hours_per_day: Number(prefs.studyHours) || 3,
                num_days: 30,
                stress_level: stressLevel,
                performance_score: performanceScore,
                cross_subject: true,
            });

            if (res.schedule?.length > 0) {
                const adj = res.adjustments || {};
                const hoursChanged = adj.hours_per_day !== adj.original_hours;
                const msg = hoursChanged
                    ? `Study load updated to ${adj.hours_per_day}h/day. ${adj.adjustment_reason || ''}`
                    : `Progress recorded. ${missedTopics.length} missed topic(s) noted for future planning.`;
                setAdaptiveMsg(msg);
                setTimeout(() => setAdaptiveMsg(null), 6000);
            }
        } catch (_) {}
    };

    const getStatusBadge = (status) => {
        const badges = {
            completed: 'badge-completed',
            pending: 'badge-pending',
            missed: 'badge-missed',
            later: 'text-xs font-medium px-2 py-1 rounded-full bg-slate-100 text-slate-600',
            skipped: 'text-xs font-medium px-2 py-1 rounded-full bg-amber-100 text-amber-700',
        };
        return badges[status] || 'badge-pending';
    };

    const getStatusIcon = (status) => {
        const icons = {
            completed: <CheckCircle className="w-4 h-4" />,
            pending: <Clock className="w-4 h-4" />,
            missed: <AlertCircle className="w-4 h-4" />,
            later: <Clock className="w-4 h-4 text-slate-400" />,
            skipped: <Clock className="w-4 h-4 text-amber-400" />,
        };
        return icons[status] || <Clock className="w-4 h-4" />;
    };

    const DIFF_COLORS = {
        1: 'bg-green-100 text-green-700',
        2: 'bg-blue-100 text-blue-700',
        3: 'bg-yellow-100 text-yellow-700',
        4: 'bg-orange-100 text-orange-700',
        5: 'bg-red-100 text-red-700',
    };

    const _inferDifficultyFromTopic = (topicName = '') => {
        const n = String(topicName || '').toLowerCase();
        if (['proof', 'derivation', 'theorem', 'optimization', 'backpropagation', 'transformer', 'attention mechanism', 'bert', 'gpt', 'eigenvector', 'byzantine', 'paxos', 'raft', 'consensus', 'distributed consensus', 'variational', 'monte carlo', 'expectation maximization', 'hmm', 'conditional random field', 'crf', 'lstm', 'gru', 'gan'].some((k) => n.includes(k))) return 5;
        if (['neural network', 'deep learning', 'convolutional', 'recurrent', 'gradient descent', 'regularization', 'convolution', 'dependency parsing', 'word embeddings', 'word2vec', 'glove', 'transformer architecture', 'language model', 'cloud architecture', 'kubernetes', 'distributed', 'machine learning algorithm', 'reinforcement learning'].some((k) => n.includes(k))) return 4;
        if (['introduction', 'overview', 'basics', 'fundamentals', 'what is', 'history', 'motivation', 'simple', 'linear regression', 'classification', 'supervised', 'unsupervised', 'tokenization', 'stemming', 'lemmatization'].some((k) => n.includes(k))) return 2;
        if (['definition', 'prerequisites', 'course overview', 'syllabus review', 'setup', 'installation', 'getting started'].some((k) => n.includes(k))) return 1;
        return null;
    };

    const _normalizeDifficultyValue = (value) => {
        if (typeof value === 'number' && Number.isFinite(value)) {
            return Math.max(1, Math.min(5, Math.round(value)));
        }
        const mapped = {
            easy: 1,
            basic: 2,
            beginner: 2,
            intermediate: 3,
            medium: 3,
            hard: 4,
            advanced: 5,
        }[String(value || '').trim().toLowerCase()];
        return mapped || null;
    };

    const getDifficultyBadge = (task) => {
        const inferred = _inferDifficultyFromTopic(task.topic);
        const difficultyValue = inferred || _normalizeDifficultyValue(task.difficulty);
        if (!difficultyValue) return null;
        const color = DIFF_COLORS[difficultyValue] || 'bg-gray-100 text-gray-600';
        const rawLabel = String(task.difficultyLabel || '').trim();
        const fallbackLabel = ['', 'Easy', 'Basic', 'Intermediate', 'Hard', 'Advanced'][difficultyValue] || String(task.difficulty || '');
        const label = rawLabel === 'Intermediate' && inferred ? ['', 'Easy', 'Basic', 'Intermediate', 'Hard', 'Advanced'][inferred] : (rawLabel || fallbackLabel);
        return (
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${color}`}>
                {label}
            </span>
        );
    };

    const requestMoreTime = (task) => {
        setTimeModal({ task, addAmount: '30', addUnit: 'min' });
    };

    // "Do it later" — marks the topic dismissed and re-inserts it N days after today.
    const markDoLater = (id, daysLater = 2) => {
        setTasks((prevTasks) => {
            const target = prevTasks.find((t) => t.id === id);
            if (!target) return prevTasks;
            _saveStatus(target, 'later');

            // Find the earliest future date N days from now that has ≤ 3 tasks already
            const baseDate = new Date(todayIso);
            baseDate.setDate(baseDate.getDate() + daysLater);
            const futureDateCounts = {};
            prevTasks.forEach((t) => {
                if (t.date > todayIso && t.status !== 'later') {
                    futureDateCounts[t.date] = (futureDateCounts[t.date] || 0) + 1;
                }
            });
            let insertDate = formatDate(baseDate);
            // Try to find a lightly-loaded day within the next 7 days
            for (let i = 0; i < 7; i++) {
                const d = new Date(baseDate);
                d.setDate(d.getDate() + i);
                const ds = formatDate(d);
                if ((futureDateCounts[ds] || 0) < 3) { insertDate = ds; break; }
            }

            // Determine a time slot (use last slot of that day or default 05:00 PM)
            const slotsForDay = prevTasks
                .filter((t) => t.date === insertDate && t.status !== 'later')
                .map((t) => t.time);
            const fallbackSlots = ['09:00 AM', '11:00 AM', '02:00 PM', '05:00 PM', '08:00 PM'];
            const usedSlots = new Set(slotsForDay);
            const freeSlot = fallbackSlots.find((s) => !usedSlots.has(s)) || '05:00 PM';

            const newId = Date.now();
            const newTask = {
                ...target,
                id: newId,
                date: insertDate,
                time: freeSlot,
                status: 'pending',
            };

            // Persist the re-inserted task's status as pending
            _saveStatus(newTask, 'pending');

            return [
                ...prevTasks.map((t) => (t.id === id ? { ...t, status: 'later', laterInsertedId: newId } : t)),
                newTask,
            ];
        });
    };

    // Skip today — mark as skipped and carry forward to tomorrow.
    const markSkip = (id) => {
        setTasks((prevTasks) => {
            const target = prevTasks.find((t) => t.id === id);
            if (!target) return prevTasks;
            _saveStatus(target, 'skipped');

            const tomorrow = new Date(todayIso);
            tomorrow.setDate(tomorrow.getDate() + 1);
            const insertDate = formatDate(tomorrow);

            const slotsForDay = prevTasks
                .filter((t) => t.date === insertDate && !['later', 'skipped'].includes(t.status))
                .map((t) => t.time);
            const fallbackSlots = ['09:00 AM', '11:00 AM', '02:00 PM', '05:00 PM', '08:00 PM'];
            const usedSlots = new Set(slotsForDay);
            const freeSlot = fallbackSlots.find((s) => !usedSlots.has(s)) || '09:00 AM';

            const newId = Date.now();
            const newTask = { ...target, id: newId, date: insertDate, time: freeSlot, status: 'pending' };
            _saveStatus(newTask, 'pending');

            return [
                ...prevTasks.map((t) => (t.id === id ? { ...t, status: 'skipped', laterInsertedId: newId } : t)),
                newTask,
            ];
        });
    };

    // Undo a Skip or Do Later — removes the re-inserted copy and restores original to pending.
    const undoMove = (task) => {
        setTasks((prevTasks) => {
            const filtered = task.laterInsertedId
                ? prevTasks.filter((t) => t.id !== task.laterInsertedId)
                : prevTasks;
            return filtered.map((t) =>
                t.id === task.id ? { ...t, status: 'pending', laterInsertedId: undefined } : t
            );
        });
        _saveStatus(task, 'pending');
    };

    // Undo a Done task — marks as pending and removes from completed subjects count
    const undoComplete = (task) => {
        try {
            const subject = task.subject || 'General';
            const completedSubjects = JSON.parse(localStorage.getItem('completedSubjects') || '{}');
            if (completedSubjects[subject]) {
                completedSubjects[subject] = Math.max(0, completedSubjects[subject] - 1);
                localStorage.setItem('completedSubjects', JSON.stringify(completedSubjects));
            }
        } catch (_) {}
        setTasks((prevTasks) =>
            prevTasks.map((t) => (t.id === task.id ? { ...t, status: 'pending' } : t))
        );
        _saveStatus(task, 'pending');
    };

    // User override: add a specific subject/unit/topic to today's schedule
    const addTopicToToday = ({ subject, subjectCode, unit, topic, difficulty, estimatedHours, resources = [] }) => {
        const normalizedSelection = _normalizeHiddenEntry({ subject, unit, topic });
        if (normalizedSelection) {
            setHiddenSubjects((prev) => _removeHiddenEntriesForSelection(prev, normalizedSelection));
        }
        const usedSlots = new Set(
            tasks.filter((t) => t.date === todayIso).map((t) => t.time)
        );
        const fallbackSlots = ['09:00 AM', '11:00 AM', '02:00 PM', '05:00 PM', '08:00 PM'];
        const freeSlot = fallbackSlots.find((s) => !usedSlots.has(s)) || '12:00 PM';
        const diff = difficulty || 3;
        const hours = Math.max(0.5, Math.min(studyHoursPerDay, estimatedHours || (diff <= 2 ? 0.5 : diff <= 3 ? 1.0 : 2.0)));
        const durationStr = hours < 1 ? `${Math.round(hours * 60)}min` : `${hours}h`;
        const newTask = {
            id: Date.now(),
            date: todayIso,
            time: freeSlot,
            subject: subject || 'Custom',
            subject_code: subjectCode || '',
            unit: unit || '',
            topic: topic || 'Study Session',
            difficulty: diff,
            difficultyLabel: ['', 'Easy', 'Basic', 'Intermediate', 'Hard', 'Advanced'][diff] || 'Intermediate',
            estimated_hours: hours,
            duration: durationStr,
            key_concepts: [],
            is_foundational: false,
            status: 'pending',
            user_override: true,
        };
        _saveStatus(newTask, 'pending');
        setTasks((prev) => [...prev, newTask]);
        if (resources.length > 0) {
            setTopicResources((prev) => ({ ...prev, [topic]: resources }));
        }
        setTopicPicker(false);
        setTopicPickerMode('syllabus');
        setTopicPickerSubject('');
        setTopicPickerUnit('');
        setTopicPickerTopic('');
        setCustomTopicName('');
        setCustomTopicSubject('');
        setCustomTopicDuration('1');
    };

    const hideSelection = () => {
        if (!topicPickerSubject) return;
        const normalizedSelection = _normalizeHiddenEntry({
            subject: topicPickerSubject,
            unit: topicPickerUnit,
            topic: topicPickerTopic,
        });
        if (!normalizedSelection) return;

        setHiddenSubjects((prev) => {
            const normalizedPrev = (prev || []).map(_normalizeHiddenEntry).filter(Boolean);
            const next = [...normalizedPrev, normalizedSelection];
            const deduped = [...new Map(next.map((entry) => [_hiddenEntryKey(entry), entry])).values()];
            return deduped;
        });

        setTopicPicker(false);
        setTopicPickerMode('syllabus');
        setTopicPickerSubject('');
        setTopicPickerUnit('');
        setTopicPickerTopic('');
        setCustomTopicName('');
        setCustomTopicSubject('');
        setCustomTopicDuration('1');
    };

    const addCustomTopicToToday = async () => {
        const topic = _cleanTopicName(customTopicName);
        if (!topic) return;

        setCustomTopicLoading(true);
        let resources = [];
        try {
            const links = await agentAPI.getTopicResources(topic, customTopicSubject || 'Custom', 5);
            resources = links?.resources || [];
        } catch (_) {
            resources = [];
        } finally {
            setCustomTopicLoading(false);
        }

        addTopicToToday({
            subject: _cleanTopicName(customTopicSubject) || 'Custom Topic',
            subjectCode: '',
            unit: 'Custom Topic',
            topic,
            difficulty: 3,
            estimatedHours: Math.max(0.5, Number(customTopicDuration) || 1),
            resources,
        });
    };

    // User preference: bring one pending task per selected preferred topic into selected day.
    const applyPreferredSubjectsForSelectedDate = () => {
        if (!preferredTopics.length) return;

        setTasks((prev) => {
            let next = [...prev];
            const usedSlots = new Set(next.filter((t) => t.date === selectedDate).map((t) => t.time));
            const fallbackSlots = _buildSlotsInWindow('09:00', '21:00', 8);

            for (const preferred of preferredTopics) {
                const alreadyOnDay = next.some(
                    (t) => t.date === selectedDate && t.status === 'pending' && _cleanTopicName(t.topic) === preferred,
                );
                if (alreadyOnDay) continue;

                const idx = next.findIndex(
                    (t) => t.status === 'pending' && _cleanTopicName(t.topic) === preferred && t.date !== selectedDate,
                );
                if (idx < 0) continue;

                const freeSlot = fallbackSlots.find((s) => !usedSlots.has(s)) || fallbackSlots[0] || '12:00 PM';
                usedSlots.add(freeSlot);

                const moved = { ...next[idx], date: selectedDate, time: freeSlot, user_override: false, moved_by_user: true };
                next[idx] = moved;
                _saveStatus(moved, moved.status || 'pending');
            }

            next = next.filter((t) => !_isTaskHidden(t, hiddenSubjects));
            try { localStorage.setItem('generatedSchedule', JSON.stringify(next)); } catch (_) {}
            return next;
        });
    };

    const rebuildMixedScheduleNow = async () => {
        setRebuildingSchedule(true);
        try {
            const mixed = await _withTimeout(_buildMixedScheduleFromBackend({
                todayIso,
                preferredTopics,
                hiddenSubjects,
            }), 12000, []);

            if (!mixed.length) {
                setAdaptiveMsg('No syllabus topics found yet. Upload a syllabus or add a custom topic.');
                setTimeout(() => setAdaptiveMsg(null), 5000);
                return;
            }

            const withStatuses = _applyStatuses(mixed);
            const merged = mergeWithPastHistory(withStatuses);
            setTasks(merged);
            try { localStorage.setItem('generatedSchedule', JSON.stringify(merged)); } catch (_) {}
            setAdaptiveMsg(`Schedule refreshed from your extracted syllabus topics.`);
            setTimeout(() => setAdaptiveMsg(null), 5000);
        } catch (_) {
            setAdaptiveMsg('Could not refresh the schedule right now.');
            setTimeout(() => setAdaptiveMsg(null), 5000);
        } finally {
            setRebuildingSchedule(false);
        }
    };

    const openTopicPicker = async (mode = 'syllabus') => {
        setTopicPickerMode(mode);
        setTopicPicker(true);
        // Load backend hierarchy if not yet loaded
        if (subjectHierarchy.length === 0) {
            try {
                const res = await agentAPI.getSubjectHierarchy();
                if (res.hierarchy?.length > 0) setSubjectHierarchy(res.hierarchy);
            } catch (_) {}
        }
    };

    const confirmMoreTime = () => {
        if (!timeModal) return;
        const { task, addAmount, addUnit } = timeModal;
        const amt = parseFloat(addAmount) || 0;
        if (amt <= 0) { setTimeModal(null); return; }
        const addMins = addUnit === 'hr' ? amt * 60 : amt;
        setTasks(prev => prev.map(t => {
            if (t.id !== task.id) return t;
            const currentMins = parseDurationToMinutes(t.duration) || (t.estimated_hours ? Math.round(t.estimated_hours * 60) : 60);
            const newMins = currentMins + addMins;
            const newHrs = newMins / 60;
            const newDuration = newMins < 60
                ? `${Math.round(newMins)} min`
                : `${parseFloat(newHrs.toFixed(1))} hour${newHrs !== 1 ? 's' : ''}`;
            return { ...t, duration: newDuration, estimated_hours: parseFloat(newHrs.toFixed(2)) };
        }));
        try {
            const overrides = JSON.parse(localStorage.getItem('scheduleOverrides') || '{}');
            overrides[task.topic] = { ...(overrides[task.topic] || {}), extra_minutes: ((overrides[task.topic]?.extra_minutes || 0) + addMins) };
            localStorage.setItem('scheduleOverrides', JSON.stringify(overrides));
            localStorage.setItem('generatedSchedule', JSON.stringify(
                tasks.map((t) => (t.id === task.id ? {
                    ...t,
                    estimated_hours: parseFloat((((parseDurationToMinutes(t.duration) || 60) + addMins) / 60).toFixed(2)),
                } : t))
            ));
        } catch (_) {}
        setTimeModal(null);
    };

    // Fetch topic-page materials whenever selected date or tasks change
    useEffect(() => {
        if (!tasks.length) return;
        const todayTasks = tasks.filter(t => t.date === selectedDate);
        if (!todayTasks.length) return;
        const pairs = [...new Map(todayTasks.map(t => [
            `${t.topic || ''}|||${t.subject || ''}`,
            { topic: t.topic || '', subject: t.subject || '' },
        ])).values()];
        let cancelled = false;
        const fetchMaterials = async () => {
            const map = {};
            const rmap = {};
            await Promise.all(pairs.map(async ({ topic, subject }) => {
                if (!topic) return;
                try {
                    const token = localStorage.getItem('authToken');
                    const res = await agentAPI.getTopicPages(topic, subject, token);
                    if (!cancelled && res.materials?.length > 0) map[topic] = res.materials;
                } catch (_) {}
                try {
                    const token = localStorage.getItem('authToken');
                    const links = await agentAPI.getTopicResources(topic, subject, 5, token);
                    if (!cancelled && links.resources?.length > 0) rmap[topic] = links.resources;
                } catch (_) {}
            }));
            if (!cancelled) {
                setTopicMaterials(prev => ({ ...prev, ...map }));
                setTopicResources(prev => ({ ...prev, ...rmap }));
            }
        };
        fetchMaterials();
        return () => { cancelled = true; };
    }, [selectedDate, tasks]);

    // Limit tasks to fit within daily study hours, weighted by difficulty
    const getTasksForDateWithinHours = (dateStr) => {
        const budgetMinutes = Math.max(30, Math.round(studyHoursPerDay * 60));
        let usedMinutes = 0;
        const picked = [];

        for (const task of tasks
            .filter((task) => task.date === dateStr && !_isTaskHidden(task, hiddenSubjects))
            .sort((a, b) => {
                const aUnitIndex = Number.isFinite(Number(a.unit_number)) ? Number(a.unit_number) : Number(a.unit_index ?? 0);
                const bUnitIndex = Number.isFinite(Number(b.unit_number)) ? Number(b.unit_number) : Number(b.unit_index ?? 0);
                if (aUnitIndex !== bUnitIndex) return aUnitIndex - bUnitIndex;
                const aTopicIndex = Number.isFinite(Number(a.topic_index)) ? Number(a.topic_index) : 0;
                const bTopicIndex = Number.isFinite(Number(b.topic_index)) ? Number(b.topic_index) : 0;
                if (aTopicIndex !== bTopicIndex) return aTopicIndex - bTopicIndex;
                const aTime = String(a.time || '');
                const bTime = String(b.time || '');
                if (aTime !== bTime) return aTime.localeCompare(bTime);
                const aSubject = String(a.subject || '');
                const bSubject = String(b.subject || '');
                if (aSubject !== bSubject) return aSubject.localeCompare(bSubject);
                return String(a.topic || '').localeCompare(String(b.topic || ''));
            })) {
            const taskMinutes = Math.max(30, parseDurationToMinutes(task.duration) || Math.round(Number(task.estimated_hours || 1) * 60));
            if (picked.length > 0 && usedMinutes + taskMinutes > budgetMinutes) continue;

            usedMinutes += taskMinutes;
            picked.push(task);
            if (usedMinutes >= budgetMinutes) break;
        }

        return picked;
    };
    const studyHoursPerDay = (() => {
        try {
            const prefs = JSON.parse(localStorage.getItem('learningPreferences') || '{}');
            return Number(prefs.studyHours) || 3;
        } catch (_) { return 3; }
    })();
    const tasksForSelectedDate = getTasksForDateWithinHours(selectedDate, studyHoursPerDay);
    const preferredTopicOptions = [...new Map(
        subjectHierarchy.flatMap((subject) =>
            (subject.units || []).flatMap((unit) =>
                (unit.topics || []).map((topic) => {
                    const name = _cleanTopicName(topic.name);
                    return [
                        name,
                        {
                            value: name,
                            label: `${name} · ${subject.subject_name}${unit.unit_name ? ` · ${unit.unit_name}` : ''}`,
                        },
                    ];
                }),
            ),
        ),
    ).values()].sort((a, b) => a.label.localeCompare(b.label));
    const hiddenSubjectOptions = [
        ...new Set([
            ...tasks.map((t) => t.subject).filter(Boolean),
            ...subjectHierarchy.map((s) => s.subject_name).filter(Boolean),
        ]),
    ].sort((a, b) => a.localeCompare(b));

    const todayDateObj = new Date(todayIso);
    const deadlineByDate = {};
    deadlineItems.forEach((item) => {
        const key = String(item.due_date || '').slice(0, 10);
        if (!key) return;
        if (!deadlineByDate[key]) deadlineByDate[key] = [];
        deadlineByDate[key].push(item);
    });
    const deadlineSummary = deadlineItems.reduce((acc, item) => {
        const status = String(item.status || 'upcoming').toLowerCase();
        if (status === 'overdue') acc.overdue += 1;
        else if (status === 'due') acc.due += 1;
        else if (status !== 'done') acc.upcoming += 1;
        return acc;
    }, { overdue: 0, due: 0, upcoming: 0 });

    const refreshDeadlines = async () => {
        const token = getAuthToken();
        const res = await agentAPI.getDeadlines({}, token);
        setDeadlineItems(_normalizeDeadlineItems(res?.deadlines || []));
    };

    // Build intensity map per date (how "green" a box should be) for the current month
    const dateIntensityMap = {};
    const userJoinDateObj = userJoinDate ? new Date(userJoinDate) : null;
    calendarDays.forEach((date) => {
        const d = new Date(date);
        const isFuture = d > todayDateObj;
        const isBeforeJoinDate = userJoinDateObj && d < userJoinDateObj;
        const minutes = activityByDate[date] || 0;
        let level;
        if (isFuture) level = -1; // future stays gray
        else if (isBeforeJoinDate) level = -1; // before join date stays gray
        else if (minutes === 0) level = 0; // no activity
        else if (minutes < 60) level = 1;
        else if (minutes < 120) level = 2;
        else level = 3;
        dateIntensityMap[date] = { date, minutes, level };
    });

    // Build calendar cells like a traditional month view (date-picker style):
    // - Weeks start on Monday
    // - Leading days from previous month and trailing days from next month are shown, but faded.
    const firstDayOfMonth = new Date(
        currentMonth.getFullYear(),
        currentMonth.getMonth(),
        1,
    );
    // Convert JS Sunday-based index (0-6, Sun-Sat) to Monday-based (0-6, Mon-Sun)
    const firstDayWeekIndex = (firstDayOfMonth.getDay() + 6) % 7;

    const daysInPrevMonth = new Date(
        currentMonth.getFullYear(),
        currentMonth.getMonth(),
        0,
    ).getDate();

    const calendarCells = [];

    // Leading days from previous month
    for (let i = firstDayWeekIndex - 1; i >= 0; i -= 1) {
        const day = daysInPrevMonth - i;
        const dateObj = new Date(
            currentMonth.getFullYear(),
            currentMonth.getMonth() - 1,
            day,
        );
        calendarCells.push({
            date: formatDate(dateObj),
            inCurrentMonth: false,
        });
    }

    // Days in the current month
    calendarDays.forEach((d) => {
        calendarCells.push({
            date: d,
            inCurrentMonth: true,
        });
    });

    // Trailing days from next month to complete the final week
    let nextMonthDay = 1;
    while (calendarCells.length % 7 !== 0) {
        const dateObj = new Date(
            currentMonth.getFullYear(),
            currentMonth.getMonth() + 1,
            nextMonthDay,
        );
        calendarCells.push({
            date: formatDate(dateObj),
            inCurrentMonth: false,
        });
        nextMonthDay += 1;
    }

    const getIntensityClass = (level) => {
        switch (level) {
            case -1:
                return 'bg-gray-100 text-gray-400';
            case 0:
                return 'bg-gray-50 text-gray-500';
            case 1:
                return 'bg-green-100 text-green-800';
            case 2:
                return 'bg-green-300 text-green-900';
            case 3:
            default:
                return 'bg-green-600 text-white';
        }
    };

    if (loading) return (
        <DashboardLayout>
            <div className="flex items-center justify-center h-64">
                <div className="text-center">
                    <div className="w-10 h-10 border-4 border-primary-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                    <p className="text-gray-500 text-sm">Loading your dashboard...</p>
                </div>
            </div>
        </DashboardLayout>
    );
    if (error) return (
        <DashboardLayout>
            <div className="text-center text-red-600 mt-8">{error}</div>
        </DashboardLayout>
    );

    return (
        <DashboardLayout>
            <div className="space-y-6">
                {/* Header */}
                <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
                    <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
                    <p className="text-gray-600 mt-1">Track your learning progress</p>
                </motion.div>

                {/* Main Grid */}
                <div className="flex flex-col lg:flex-row gap-4 items-stretch w-full">
                    {/* Left: Daily Schedule — takes all remaining width */}
                    <div className="flex-1 min-w-0">
                        {/* Daily Schedule */}
                        <div className="card w-full">
                            <div className="flex items-center justify-between mb-6">
                                <div>
                                    <h2 className="text-xl font-bold text-gray-800">Daily Schedule</h2>
                                    {selectedDate && (
                                        <p className="text-sm text-gray-500">
                                            {selectedDate === todayIso ? 'Today • ' : 'Selected day • '}
                                            {new Date(selectedDate).toLocaleDateString(undefined, {
                                                weekday: 'long',
                                                day: 'numeric',
                                                month: 'short',
                                            })}
                                        </p>
                                    )}
                                </div>
                                <div className="flex items-center gap-2">
                                    {selectedDate === todayIso && (
                                        <>
                                            <button
                                                onClick={() => openTopicPicker('syllabus')}
                                                className="inline-flex items-center gap-1.5 px-3 py-2 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 transition-colors shadow-sm"
                                                title="Add a topic you want to study today"
                                            >
                                                <span className="font-bold text-base leading-none">+</span> Add Topic
                                            </button>
                                            <button
                                                onClick={() => openTopicPicker('hide')}
                                                className="inline-flex items-center gap-1.5 px-3 py-2 bg-white text-amber-700 border border-amber-200 rounded-lg text-sm font-medium hover:bg-amber-50 transition-colors shadow-sm"
                                                title="Hide a subject, unit, or topic you do not want to see right now"
                                            >
                                                Hide Topic
                                            </button>
                                        </>
                                    )}
                                    <Calendar className="w-6 h-6 text-primary-600" />
                                </div>
                            </div>
                            {preferredTopics.length > 0 && (
                                <div className="flex flex-wrap gap-2 mb-4">
                                    {preferredTopics.map((topic) => (
                                        <button
                                            key={topic}
                                            onClick={() => setPreferredTopics((prev) => prev.filter((item) => item !== topic))}
                                            className="text-xs px-2 py-1 rounded-full bg-primary-50 text-primary-700 border border-primary-100"
                                            title="Remove preferred topic"
                                        >
                                            {topic} ×
                                        </button>
                                    ))}
                                </div>
                            )}
                            <div className="space-y-3">
                                {tasksForSelectedDate.map((task, index) => (
                                    <motion.div
                                        key={task.id}
                                        initial={{ opacity: 0, x: -20 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ delay: index * 0.1 }}
                                        className={`rounded-xl border overflow-hidden transition-all ${
                                            task.status === 'skipped'
                                                ? 'bg-amber-50 border-amber-100 opacity-70'
                                                : task.status === 'later'
                                                ? 'bg-slate-50 border-slate-200 opacity-60'
                                                : task.status === 'completed'
                                                ? 'bg-green-50 border-green-200'
                                                : task.status === 'missed'
                                                ? 'bg-red-50 border-red-200'
                                                : 'bg-white border-gray-200 hover:border-gray-300 hover:shadow-sm'
                                        }`}
                                    >
                                        {/* Status stripe at top */}
                                        <div className={`h-1 ${
                                            task.status === 'completed' ? 'bg-green-400' :
                                            task.status === 'missed' ? 'bg-red-400' :
                                            task.status === 'later' ? 'bg-slate-300' :
                                            task.status === 'skipped' ? 'bg-amber-300' :
                                            'bg-primary-400'
                                        }`} />

                                        <div className="p-4">
                                            {/* Row 1: Time + Topic name + Status pill */}
                                            <div className="flex items-start justify-between gap-3 mb-2">
                                                <div className="flex items-baseline gap-2 min-w-0">
                                                    <h3 className="font-semibold text-gray-900 text-sm leading-snug">{task.topic}</h3>
                                                </div>
                                                <span className={`shrink-0 text-xs font-medium px-2.5 py-0.5 rounded-full ${
                                                    task.status === 'completed' ? 'bg-green-100 text-green-700' :
                                                    task.status === 'missed' ? 'bg-red-100 text-red-600' :
                                                    task.status === 'later' ? 'bg-slate-100 text-slate-500' :
                                                    task.status === 'skipped' ? 'bg-amber-100 text-amber-700' :
                                                    'bg-primary-50 text-primary-600'
                                                }`}>
                                                    {task.status === 'later' ? 'Do Later' : task.status === 'skipped' ? '→ Tomorrow' : task.status === 'pending' ? 'Pending' : task.status.charAt(0).toUpperCase() + task.status.slice(1)}
                                                </span>
                                            </div>

                                            {/* Row 2: Subject + code + unit */}
                                            <div className="flex items-center gap-1.5 mb-2.5 flex-wrap">
                                                <span className="text-xs text-gray-500 font-medium">{task.subject}</span>
                                                {task.subject_code && (
                                                    <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-600 border border-indigo-100">
                                                        {task.subject_code}
                                                    </span>
                                                )}
                                                {task.unit && (
                                                    <>
                                                        <span className="text-gray-300 text-xs">·</span>
                                                        <span className="text-xs text-gray-400">{task.unit}</span>
                                                    </>
                                                )}
                                                {task.user_override && task.custom_added && (
                                                    <span className="text-xs px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-600 border border-amber-100 ml-auto">My pick</span>
                                                )}
                                            </div>

                                            {/* Row 3: Difficulty · Duration · Foundational */}
                                            <div className="flex items-center gap-2 mb-2 flex-wrap">
                                                {getDifficultyBadge(task)}
                                                <span className="text-xs text-gray-400">{task.duration}</span>
                                                {task.is_foundational && (
                                                    <span className="text-xs px-2 py-0.5 rounded-full bg-purple-50 text-purple-600">Foundational</span>
                                                )}
                                            </div>

                                            {/* Row 4: Key concepts as plain text */}
                                            {task.key_concepts?.length > 0 && (
                                                <p className="text-xs text-gray-400 mb-3 leading-relaxed">
                                                    {task.key_concepts.slice(0, 3).join(' · ')}
                                                </p>
                                            )}

                                            {/* Row 5: Study materials — compact */}
                                            {topicMaterials[task.topic]?.length > 0 && (
                                                <div className="flex flex-wrap gap-1.5 mb-3">
                                                    {topicMaterials[task.topic].map((m, mi) => (
                                                        <span key={mi} className="text-xs text-blue-600 bg-blue-50 border border-blue-100 px-2 py-0.5 rounded-md">
                                                            {m.filename}{m.page ? ` p.${m.page}` : ''}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}

                                            {(topicResources[task.topic]?.length > 0 || task.topic) && (
                                                <div className="flex flex-wrap gap-1.5 mb-3">
                                                    {(() => {
                                                        const resourcesForTopic = topicResources[task.topic]?.length > 0
                                                            ? topicResources[task.topic]
                                                            : _buildFallbackResourceLinks(task.topic, task.subject);
                                                        const { web, video } = _pickResourceLinks(resourcesForTopic);
                                                        return (
                                                            <>
                                                                {web && (
                                                                    <a
                                                                        href={web.url}
                                                                        target="_blank"
                                                                        rel="noreferrer"
                                                                        className="text-xs px-2 py-0.5 rounded-md border text-indigo-700 bg-indigo-50 border-indigo-100"
                                                                    >
                                                                        Web Search
                                                                    </a>
                                                                )}
                                                                {video && (
                                                                    <a
                                                                        href={video.url}
                                                                        target="_blank"
                                                                        rel="noreferrer"
                                                                        className="text-xs px-2 py-0.5 rounded-md border text-red-700 bg-red-50 border-red-100"
                                                                    >
                                                                        YouTube
                                                                    </a>
                                                                )}
                                                            </>
                                                        );
                                                    })()}
                                                </div>
                                            )}

                                            {/* Row 6: Actions */}
                                            {task.status === 'pending' && (
                                                <div className="flex items-center gap-2 pt-2.5 border-t border-gray-100">
                                                    <button
                                                        onClick={() => markComplete(task.id)}
                                                        className="px-3 py-1.5 bg-primary-600 text-white text-xs font-medium rounded-lg hover:bg-primary-700 transition-colors"
                                                    >
                                                        Done
                                                    </button>
                                                    <button
                                                        onClick={() => markSkip(task.id)}
                                                        title="Move to tomorrow's schedule"
                                                        className="px-3 py-1.5 bg-white text-amber-600 border border-amber-200 text-xs font-medium rounded-lg hover:bg-amber-50 transition-colors"
                                                    >
                                                        Skip Tomorrow
                                                    </button>
                                                    <button
                                                        onClick={() => markDoLater(task.id, 2)}
                                                        title="Move to a less busy day (2+ days away)"
                                                        className="px-3 py-1.5 bg-white text-slate-500 border border-slate-200 text-xs font-medium rounded-lg hover:bg-slate-50 transition-colors"
                                                    >
                                                        Do Later
                                                    </button>
                                                    <button
                                                        onClick={() => requestMoreTime(task)}
                                                        className="ml-auto px-3 py-1.5 bg-white text-gray-500 border border-gray-200 text-xs font-medium rounded-lg hover:bg-gray-50 transition-colors"
                                                    >
                                                        + Time
                                                    </button>
                                                </div>
                                            )}
                                            {(task.status === 'later' || task.status === 'skipped') && (
                                                <div className="flex items-center gap-2 pt-2.5 border-t border-gray-100">
                                                    <button
                                                        onClick={() => undoMove(task)}
                                                        className="px-3 py-1.5 bg-white text-gray-600 border border-gray-300 text-xs font-medium rounded-lg hover:bg-gray-50 transition-colors"
                                                    >
                                                        Undo
                                                    </button>
                                                    <span className="text-xs text-gray-400">
                                                        {task.status === 'skipped' ? 'Added to tomorrow' : 'Moved to a later date'}
                                                    </span>
                                                </div>
                                            )}
                                            {task.status === 'completed' && (
                                                <div className="flex items-center gap-2 pt-2.5 border-t border-gray-100">
                                                    <button
                                                        onClick={() => undoComplete(task)}
                                                        className="px-3 py-1.5 bg-white text-gray-600 border border-gray-300 text-xs font-medium rounded-lg hover:bg-gray-50 transition-colors"
                                                    >
                                                        Undo
                                                    </button>
                                                    <span className="text-xs text-gray-400">Mark as pending</span>
                                                </div>
                                            )}
                                        </div>
                                    </motion.div>
                                ))}
                                {tasksForSelectedDate.length === 0 && (
                                    <div className="text-center py-8 text-gray-400">
                                        <Calendar className="w-10 h-10 mx-auto mb-2 opacity-30" />
                                        <p className="text-sm">
                                            {subjectHierarchy.length > 0 ? 'No tasks scheduled for this day.' : 'Upload a syllabus PDF to generate your schedule.'}
                                        </p>
                                        {selectedDate === todayIso && (
                                            <button
                                                onClick={openTopicPicker}
                                                className="mt-3 px-4 py-2 bg-primary-50 text-primary-700 border border-primary-200 rounded-lg text-sm hover:bg-primary-100 transition-colors"
                                            >
                                                + Add a topic to study
                                            </button>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>

                    </div>

                    {/* Right sidebar: Calendar on top, Weekly Progress below */}
                    <div className="flex flex-col gap-4 w-full lg:w-[300px] shrink-0">
                        <div className="card p-4 w-full">
                            <div className="flex items-center justify-between mb-4">
                                <div>
                                    <h2 className="text-xl font-bold text-gray-800">Study Calendar</h2>
                                    <p className="text-sm text-gray-500">
                                        {currentMonth.toLocaleDateString(undefined, {
                                            month: 'long',
                                            year: 'numeric',
                                        })}
                                    </p>
                                </div>
                                <div className="flex items-center space-x-2">
                                    <button
                                        type="button"
                                        onClick={() =>
                                            setCurrentMonth((prev) =>
                                                new Date(prev.getFullYear(), prev.getMonth() - 1, 1),
                                            )
                                        }
                                        className="h-8 w-8 flex items-center justify-center rounded-md border border-gray-200 text-gray-600 hover:bg-gray-100"
                                    >
                                        &#8249;
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() =>
                                            setCurrentMonth((prev) =>
                                                new Date(prev.getFullYear(), prev.getMonth() + 1, 1),
                                            )
                                        }
                                        className="h-8 w-8 flex items-center justify-center rounded-md border border-gray-200 text-gray-600 hover:bg-gray-100"
                                    >
                                        &#8250;
                                    </button>
                                    <Calendar className="w-6 h-6 text-primary-600" />
                                </div>
                            </div>
                            <div className="mt-2">
                                <div className="grid grid-cols-7 gap-x-1 gap-y-1 justify-items-center">
                                    {['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].map((day) => (
                                        <div
                                            key={day}
                                            className="h-7 w-7 flex items-center justify-center text-[11px] font-medium text-gray-400"
                                        >
                                            {day}
                                        </div>
                                    ))}
                                    {calendarCells.map((cell, index) => {
                                        const info = dateIntensityMap[cell.date] || { level: -1 };
                                        const dayNumber = new Date(cell.date).getDate();
                                        const isSelected = cell.date === selectedDate;
                                        const deadlinesForDay = deadlineByDate[cell.date] || [];
                                        const hasOverdue = deadlinesForDay.some((item) => item.status === 'overdue');
                                        const hasDue = deadlinesForDay.some((item) => item.status === 'due');
                                        const hasUpcoming = deadlinesForDay.some((item) => item.status === 'upcoming');
                                        const baseIntensityClass = cell.inCurrentMonth
                                            ? getIntensityClass(info.level)
                                            : 'bg-gray-100 text-gray-400';
                                        return (
                                            <button
                                                key={`${cell.date}-${index}`}
                                                type="button"
                                                onClick={() => {
                                                    setSelectedDate(cell.date);
                                                    if (!cell.inCurrentMonth) {
                                                        const dObj = new Date(cell.date);
                                                        setCurrentMonth(
                                                            new Date(
                                                                dObj.getFullYear(),
                                                                dObj.getMonth(),
                                                                1,
                                                            ),
                                                        );
                                                    }
                                                }}
                                                className={`h-8 w-8 rounded-md flex items-center justify-center text-[11px] font-medium transition-colors border relative ${
                                                    isSelected
                                                        ? 'border-primary-600 ring-1 ring-primary-400'
                                                        : 'border-transparent'
                                                } ${baseIntensityClass}`}
                                            >
                                                {dayNumber}
                                                {deadlinesForDay.length > 0 && (
                                                    <span
                                                        className={`absolute bottom-0.5 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full ${
                                                            hasOverdue ? 'bg-red-500' : hasDue ? 'bg-amber-500' : hasUpcoming ? 'bg-blue-500' : 'bg-gray-400'
                                                        }`}
                                                        title={`${deadlinesForDay.length} deadline${deadlinesForDay.length === 1 ? '' : 's'}`}
                                                    />
                                                )}
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                            <p className="mt-3 text-xs text-gray-500">
                                Darker green means a heavier study day. Click a date to see that day's plan.
                            </p>
                            <div className="mt-2 flex items-center gap-3 text-[11px] text-gray-500">
                                <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500" /> Overdue</span>
                                <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-500" /> Due today</span>
                                <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-500" /> Upcoming</span>
                            </div>
                            <div className="mt-4 border-t border-gray-100 pt-4">
                                <div className="flex items-center justify-between mb-2">
                                    <h3 className="text-sm font-semibold text-gray-800">Upcoming deadlines</h3>
                                </div>
                                <div className="space-y-2 max-h-44 overflow-auto pr-1">
                                    {(deadlineItems || [])
                                        .filter((item) => String(item.status || '').toLowerCase() !== 'done')
                                        .slice(0, 5)
                                        .map((item) => (
                                            <div key={item.id} className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
                                                <div className="flex items-start justify-between gap-2">
                                                    <div>
                                                        <p className="text-xs font-medium text-gray-800 line-clamp-2">{item.title || 'Deadline'}</p>
                                                        <p className="text-[11px] text-gray-500 mt-0.5">
                                                            {item.subject || 'General'}{item.due_date ? ` · ${new Date(item.due_date).toLocaleDateString()}` : ''}
                                                        </p>
                                                    </div>
                                                    <span className={`text-[10px] px-2 py-0.5 rounded-full ${item.status === 'overdue' ? 'bg-red-100 text-red-700' : item.status === 'due' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'}`}>
                                                        {item.status || 'upcoming'}
                                                    </span>
                                                </div>
                                                <div className="mt-2 flex items-center gap-2">
                                                    <button
                                                        type="button"
                                                        onClick={async () => {
                                                            try {
                                                                const token = getAuthToken();
                                                                await agentAPI.markDeadlineDone(item.id, token);
                                                                await refreshDeadlines();
                                                            } catch (_) {}
                                                        }}
                                                        className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700 hover:bg-emerald-100"
                                                    >
                                                        <CheckCircle className="h-3.5 w-3.5" />
                                                        Done
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={async () => {
                                                            try {
                                                                const token = getAuthToken();
                                                                await agentAPI.deleteDeadline(item.id, token);
                                                                await refreshDeadlines();
                                                            } catch (_) {}
                                                        }}
                                                        className="inline-flex items-center gap-1 rounded-full border border-red-200 bg-red-50 px-2.5 py-1 text-[11px] font-medium text-red-700 hover:bg-red-100"
                                                    >
                                                        <Trash2 className="h-3.5 w-3.5" />
                                                        Delete
                                                    </button>
                                                </div>
                                            </div>
                                        ))}
                                    {(!deadlineItems || deadlineItems.filter((item) => String(item.status || '').toLowerCase() !== 'done').length === 0) && (
                                        <p className="text-xs text-gray-400">No extracted deadlines yet.</p>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div className="card p-4 w-full">
                            <h3 className="text-sm font-semibold text-gray-800 mb-2">Paste Deadline Text</h3>
                            <p className="text-xs text-gray-500 mb-3">Paste a class message, announcement, or note to extract dated deadlines.</p>
                            <div className="space-y-3">
                                <input
                                    value={deadlineTextSubject}
                                    onChange={(e) => setDeadlineTextSubject(e.target.value)}
                                    className="input-field text-sm"
                                    placeholder="Optional subject label"
                                />
                                <textarea
                                    value={deadlineText}
                                    onChange={(e) => setDeadlineText(e.target.value)}
                                    className="w-full min-h-32 rounded-lg border border-gray-300 px-3 py-2 text-sm resize-y"
                                    placeholder="Paste deadline text here. Example: Assignment 2 due on 28 April 2026, quiz on 2 May 2026."
                                />
                                <button
                                    type="button"
                                    onClick={async () => {
                                        const text = deadlineText.trim();
                                        if (!text) return;
                                        setDeadlineTextLoading(true);
                                        try {
                                            const token = localStorage.getItem('authToken');
                                            const response = await agentAPI.extractDeadlinesFromText({ subject: deadlineTextSubject.trim(), text }, token);

                                            const loadDeadlines = async () => {
                                                const refreshed = await agentAPI.getDeadlines({}, token);
                                                setDeadlineItems(_normalizeDeadlineItems(refreshed?.deadlines || []));
                                                return refreshed?.deadlines || [];
                                            };

                                            if (response?.processing) {
                                                let attempts = 0;
                                                let deadlines = [];
                                                while (attempts < 8 && deadlines.length === 0) {
                                                    await new Promise((resolve) => setTimeout(resolve, 1000));
                                                    deadlines = await loadDeadlines();
                                                    attempts += 1;
                                                }
                                            } else {
                                                await loadDeadlines();
                                            }

                                            setDeadlineText('');
                                            setDeadlineTextSubject('');
                                        } catch (_) {
                                            setAdaptiveMsg('Could not extract deadlines from pasted text.');
                                            setTimeout(() => setAdaptiveMsg(null), 4000);
                                        } finally {
                                            setDeadlineTextLoading(false);
                                        }
                                    }}
                                    disabled={!deadlineText.trim() || deadlineTextLoading}
                                    className="w-full px-4 py-2.5 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 disabled:opacity-50"
                                >
                                    {deadlineTextLoading ? 'Extracting...' : 'Extract Deadlines'}
                                </button>
                            </div>
                        </div>

                        <div className="card p-4 w-full">
                            <h3 className="text-sm font-semibold text-gray-800 mb-3">Deadline Summary</h3>
                            <div className="grid grid-cols-3 gap-2 text-center">
                                {[
                                    { label: 'Overdue', value: deadlineSummary.overdue, tone: 'bg-red-50 text-red-700 border-red-100' },
                                    { label: 'Due Now', value: deadlineSummary.due, tone: 'bg-amber-50 text-amber-700 border-amber-100' },
                                    { label: 'Upcoming', value: deadlineSummary.upcoming, tone: 'bg-blue-50 text-blue-700 border-blue-100' },
                                ].map((item) => (
                                    <div key={item.label} className={`rounded-lg border px-2 py-2 ${item.tone}`}>
                                        <div className="text-lg font-bold">{item.value}</div>
                                        <div className="text-[11px]">{item.label}</div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className="card w-full px-4 py-4"
                        >
                            <h2 className="text-xl font-bold text-gray-800 mb-4 text-center">Weekly Progress</h2>
                            <div className="flex items-center justify-center mb-4">
                                <div className="relative w-32 h-32">
                                    <svg className="transform -rotate-90 w-32 h-32">
                                        <circle
                                            cx="64"
                                            cy="64"
                                            r="56"
                                            stroke="#e5e7eb"
                                            strokeWidth="8"
                                            fill="transparent"
                                        />
                                        <circle
                                            cx="64"
                                            cy="64"
                                            r="56"
                                            stroke="#22c55e"
                                            strokeWidth="8"
                                            fill="transparent"
                                            strokeDasharray={`${2 * Math.PI * 56}`}
                                            strokeDashoffset={`${2 * Math.PI * 56 * (1 - weeklyProgress.percentage / 100)}`}
                                            className="transition-all duration-1000"
                                        />
                                    </svg>
                                    <div className="absolute inset-0 flex items-center justify-center">
                                        <span className="text-2xl font-bold text-gray-800">
                                            {weeklyProgress.percentage}%
                                        </span>
                                    </div>
                                </div>
                            </div>
                            <div className="space-y-2">
                                <div className="flex justify-between text-sm">
                                    <span className="text-gray-600">Completed</span>
                                    <span className="font-semibold">{weeklyProgress.completedHours}h</span>
                                </div>
                                <div className="flex justify-between text-sm">
                                    <span className="text-gray-600">Total Goal</span>
                                    <span className="font-semibold">{weeklyProgress.totalHours}h</span>
                                </div>
                                <div className="flex justify-between text-sm">
                                    <span className="text-gray-600">Study Streak</span>
                                    <span className="font-semibold text-primary-600">
                                        {weeklyProgress.streak} days 🔥
                                    </span>
                                </div>
                            </div>
                        </motion.div>
                    </div>
                </div>

                {/* Achievements Section */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 }}
                >
                    <div className="card">
                        <div className="flex items-center space-x-2 mb-6">
                            <Trophy className="w-6 h-6 text-yellow-600" />
                            <h2 className="text-xl font-bold text-gray-800">Achievements</h2>
                        </div>
                        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {achievements.map((achievement) => (
                                <AchievementCard key={achievement.id} achievement={achievement} />
                            ))}
                        </div>
                    </div>
                </motion.div>

                {/* Motivation Tips */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.4 }}
                >
                    <MotivationTips />
                </motion.div>

                {/* SHAP AI Explanations */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.5 }}
                    className="grid grid-cols-1 lg:grid-cols-2 gap-4"
                >
                    <ShapExplanation agent="progress" />
                    <ShapExplanation agent="profile" />
                </motion.div>
            </div>

            {/* +Time Modal */}
            {timeModal && (() => {
                const amt = parseFloat(timeModal.addAmount) || 0;
                const addMins = timeModal.addUnit === 'hr' ? amt * 60 : amt;
                const currentMins = parseDurationToMinutes(timeModal.task.duration)
                    || (timeModal.task.estimated_hours ? Math.round(timeModal.task.estimated_hours * 60) : 0);
                const newMins = currentMins + addMins;
                const newHrs = newMins / 60;
                const newLabel = newMins < 60
                    ? `${Math.round(newMins)} min`
                    : `${parseFloat(newHrs.toFixed(1))} hour${newHrs !== 1 ? 's' : ''}`;
                const currentLabel = currentMins < 60 && currentMins > 0
                    ? `${currentMins} min`
                    : currentMins >= 60
                        ? `${parseFloat((currentMins / 60).toFixed(1))} hour${currentMins / 60 !== 1 ? 's' : ''}`
                        : timeModal.task.duration || 'Not set';
                return (
                    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center">
                        <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-sm mx-4">
                            <h3 className="text-lg font-bold text-gray-800 mb-1">Add Study Time</h3>
                            <p className="text-sm text-gray-600 mb-4 truncate">{timeModal.task.topic}</p>

                            <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 mb-4 flex items-center justify-between">
                                <span className="text-xs font-medium text-amber-700 uppercase tracking-wide">Currently allocated</span>
                                <span className="text-sm font-semibold text-amber-900">{currentLabel}</span>
                            </div>

                            <label className="block text-sm font-medium text-gray-700 mb-2">Time to add</label>
                            <div className="flex gap-2 mb-3">
                                <input
                                    type="number"
                                    min="1"
                                    max="480"
                                    value={timeModal.addAmount}
                                    onChange={e => setTimeModal(m => ({ ...m, addAmount: e.target.value }))}
                                    className="w-24 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
                                />
                                <select
                                    value={timeModal.addUnit}
                                    onChange={e => setTimeModal(m => ({ ...m, addUnit: e.target.value }))}
                                    className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
                                >
                                    <option value="min">minutes</option>
                                    <option value="hr">hours</option>
                                </select>
                            </div>

                            {amt > 0 && (
                                <div className="flex items-center gap-2 text-xs bg-green-50 border border-green-200 rounded-lg px-4 py-2.5 mb-4">
                                    <span className="text-green-700">{currentLabel}</span>
                                    <span className="text-green-400 font-bold">+{timeModal.addUnit === 'hr' ? `${amt}h` : `${amt}m`}</span>
                                    <span className="text-green-400">=</span>
                                    <span className="font-semibold text-green-800">{newLabel}</span>
                                </div>
                            )}

                            <div className="flex gap-2">
                                <button
                                    onClick={() => setTimeModal(null)}
                                    className="flex-1 px-4 py-2 border border-gray-300 text-gray-600 rounded-lg text-sm hover:bg-gray-50 transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={confirmMoreTime}
                                    disabled={amt <= 0}
                                    className="flex-1 px-4 py-2 bg-amber-500 text-white rounded-lg text-sm font-medium hover:bg-amber-600 disabled:opacity-40 transition-colors"
                                >
                                    Add Time
                                </button>
                            </div>
                        </div>
                    </div>
                );
            })()}

            {/* Reschedule Modal */}
            <Modal
                isOpen={showRescheduleModal}
                onClose={() => setShowRescheduleModal(false)}
                title="Adaptive Rescheduling"
            >
                <div className="space-y-4">
                    <p className="text-gray-700">
                        It looks like you have a few unfinished sessions. Let the AI suggest a better plan for the
                        next days?
                    </p>
                    <div className="flex space-x-3">
                        <button
                            onClick={() => {
                                setShowRescheduleModal(false);
                                const done   = JSON.parse(localStorage.getItem('completedTopics') || '[]');
                                const missed = JSON.parse(localStorage.getItem('missedTopics')    || '[]');
                                triggerAdaptiveReschedule(done, missed);
                            }}
                            className="btn-primary flex-1"
                        >
                            Auto Adjust
                        </button>
                        <button className="btn-secondary flex-1">Manual Adjust</button>
                    </div>
                </div>
            </Modal>

            {/* Adaptive reschedule toast */}
            {adaptiveMsg && (
                <div className="fixed bottom-6 right-6 bg-indigo-600 text-white px-5 py-3 rounded-xl shadow-xl z-50 max-w-sm text-sm leading-snug">
                    <span className="font-semibold">Schedule adapted</span>
                    <br />
                    {adaptiveMsg}
                </div>
            )}

            {/* Topic Picker Modal — "I want to study this today" */}
            {topicPicker && (() => {
                // Prefer backend subject hierarchy; fall back to schedule-derived data
                let subjects, getUnits, getTopics, getSubjectCode;

                if (subjectHierarchy.length > 0) {
                    subjects = subjectHierarchy.map((s) => s.subject_name);
                    getSubjectCode = (subj) =>
                        subjectHierarchy.find((s) => s.subject_name === subj)?.subject_code || '';
                    getUnits = (subj) =>
                        (subjectHierarchy.find((s) => s.subject_name === subj)?.units || []).map(
                            (u) => u.unit_name
                        );
                    getTopics = (subj, unit) => {
                        const unitObj = (subjectHierarchy.find((s) => s.subject_name === subj)?.units || [])
                            .find((u) => u.unit_name === unit);
                        return (unitObj?.topics || []).map((t) => ({
                            name: t.name,
                            difficulty: t.difficulty,
                            est_hours: t.est_hours,
                        }));
                    };
                } else {
                    // Derived from loaded schedule tasks
                    const subjectMap = {};
                    tasks.forEach((t) => {
                        if (!t.subject) return;
                        if (!subjectMap[t.subject]) subjectMap[t.subject] = {};
                        const unitKey = t.unit || 'General';
                        if (!subjectMap[t.subject][unitKey]) subjectMap[t.subject][unitKey] = [];
                        const topicName = (t.topic || '').replace(/ — Day \d+$/, '').replace(/^\[Review\] /, '').trim();
                        if (topicName && !subjectMap[t.subject][unitKey].some((x) => x.name === topicName)) {
                            subjectMap[t.subject][unitKey].push({ name: topicName, difficulty: t.difficulty || 3, est_hours: t.estimated_hours || 1 });
                        }
                    });
                    subjects = Object.keys(subjectMap);
                    getSubjectCode = (subj) => tasks.find((t) => t.subject === subj)?.subject_code || '';
                    getUnits = (subj) => Object.keys(subjectMap[subj] || {});
                    getTopics = (subj, unit) => subjectMap[subj]?.[unit] || [];
                }

                const units = topicPickerSubject ? getUnits(topicPickerSubject) : [];
                const topicsForUnit = topicPickerSubject && topicPickerUnit
                    ? getTopics(topicPickerSubject, topicPickerUnit) : [];
                const selectedTopicMeta = topicsForUnit.find((item) => item.name === topicPickerTopic) || null;
                const DIFF_LABELS = ['', 'Easy', 'Basic', 'Intermediate', 'Hard', 'Advanced'];

                return (
                    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center px-4">
                        <div className="bg-white rounded-xl shadow-xl p-5 w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-lg font-bold text-gray-800">
                                    {topicPickerMode === 'hide' ? 'Hide Topic' : 'Add Topic to Today'}
                                </h3>
                                <button
                                    onClick={() => { setTopicPicker(false); setTopicPickerMode('syllabus'); setTopicPickerSubject(''); setTopicPickerUnit(''); setTopicPickerTopic(''); setCustomTopicName(''); setCustomTopicSubject(''); setCustomTopicDuration('1'); }}
                                    className="text-gray-400 hover:text-gray-600 text-xl leading-none"
                                >×</button>
                            </div>
                            <p className="text-sm text-gray-500 mb-4">
                                Choose a syllabus topic with subject, unit, and topic dropdowns, or add a custom topic in the separate section below.
                            </p>

                            <div className="flex gap-2 mb-4 p-1 bg-gray-100 rounded-lg">
                                <button
                                    type="button"
                                    onClick={() => setTopicPickerMode('syllabus')}
                                    className={`flex-1 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                                        topicPickerMode === 'syllabus'
                                            ? 'bg-white text-primary-700 shadow-sm'
                                            : 'text-gray-600 hover:text-gray-800'
                                    }`}
                                >
                                    Syllabus Topic
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setTopicPickerMode('custom')}
                                    className={`flex-1 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                                        topicPickerMode === 'custom'
                                            ? 'bg-white text-primary-700 shadow-sm'
                                            : 'text-gray-600 hover:text-gray-800'
                                    }`}
                                >
                                    Custom Topic
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setTopicPickerMode('hide')}
                                    className={`flex-1 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                                        topicPickerMode === 'hide'
                                            ? 'bg-white text-amber-700 shadow-sm'
                                            : 'text-gray-600 hover:text-gray-800'
                                    }`}
                                >
                                    Hide Topic
                                </button>
                            </div>

                            {(topicPickerMode === 'syllabus' || topicPickerMode === 'hide') && (
                                <div className="space-y-3">
                                    <div>
                                        <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">Subject</label>
                                        <select
                                            value={topicPickerSubject}
                                            onChange={(e) => {
                                                setTopicPickerSubject(e.target.value);
                                                setTopicPickerUnit('');
                                                setTopicPickerTopic('');
                                            }}
                                            className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm bg-white"
                                        >
                                            <option value="">Select subject</option>
                                            {subjects.length === 0 && <option value="" disabled>No subjects found yet</option>}
                                            {subjects.map((s) => {
                                                const code = getSubjectCode(s);
                                                return (
                                                    <option key={s} value={s}>
                                                        {s}{code ? ` (${code})` : ''}
                                                    </option>
                                                );
                                            })}
                                        </select>
                                    </div>

                                    <div>
                                        <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">Unit</label>
                                        <select
                                            value={topicPickerUnit}
                                            onChange={(e) => {
                                                setTopicPickerUnit(e.target.value);
                                                setTopicPickerTopic('');
                                            }}
                                            disabled={!topicPickerSubject}
                                            className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm bg-white disabled:bg-gray-50 disabled:text-gray-400"
                                        >
                                            <option value="">Select unit</option>
                                            {units.map((unit) => (
                                                <option key={unit} value={unit}>{unit}</option>
                                            ))}
                                        </select>
                                    </div>

                                    <div>
                                        <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">Topic</label>
                                        <select
                                            value={topicPickerTopic}
                                            onChange={(e) => setTopicPickerTopic(e.target.value)}
                                            disabled={!topicPickerUnit}
                                            className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm bg-white disabled:bg-gray-50 disabled:text-gray-400"
                                        >
                                            <option value="">Select topic</option>
                                            {topicsForUnit.map(({ name: topic }) => (
                                                <option key={topic} value={topic}>{topic}</option>
                                            ))}
                                        </select>
                                    </div>

                                    {selectedTopicMeta && (
                                        <div className="flex items-center gap-2 text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
                                            <span className="font-medium text-gray-700">{selectedTopicMeta.name}</span>
                                            <span className="text-gray-400">·</span>
                                            <span>{selectedTopicMeta.est_hours < 1 ? `${Math.round(selectedTopicMeta.est_hours * 60)} min` : `${selectedTopicMeta.est_hours} h`}</span>
                                            <span className="text-gray-400">·</span>
                                            <span>{DIFF_LABELS[selectedTopicMeta.difficulty] || 'Intermediate'}</span>
                                        </div>
                                    )}

                                    <button
                                        type="button"
                                        onClick={() => {
                                            if (!topicPickerSubject) return;
                                            if (topicPickerMode === 'hide') {
                                                hideSelection();
                                                return;
                                            }
                                            if (!topicPickerUnit || !topicPickerTopic) return;
                                            addTopicToToday({
                                                subject: topicPickerSubject,
                                                subjectCode: getSubjectCode(topicPickerSubject),
                                                unit: topicPickerUnit,
                                                topic: topicPickerTopic,
                                                difficulty: selectedTopicMeta?.difficulty || 3,
                                                estimatedHours: selectedTopicMeta?.est_hours || 1,
                                            });
                                        }}
                                        disabled={
                                            !topicPickerSubject ||
                                            (topicPickerMode !== 'hide' && (!topicPickerUnit || !topicPickerTopic))
                                        }
                                        className={`w-full px-4 py-2.5 rounded-lg text-sm font-medium disabled:opacity-50 ${
                                            topicPickerMode === 'hide'
                                                ? 'bg-amber-600 text-white hover:bg-amber-700'
                                                : 'bg-primary-600 text-white hover:bg-primary-700'
                                        }`}
                                    >
                                        {topicPickerMode === 'hide' ? 'Hide Selected' : 'Add Topic'}
                                    </button>
                                </div>
                            )}

                            {topicPickerMode === 'custom' && (
                                <div className="space-y-3">
                                    <div>
                                        <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">Custom Topic</label>
                                        <input
                                            type="text"
                                            value={customTopicName}
                                            onChange={(e) => setCustomTopicName(e.target.value)}
                                            placeholder="Example: Backpropagation intuition"
                                            className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">Subject Label</label>
                                        <input
                                            type="text"
                                            value={customTopicSubject}
                                            onChange={(e) => setCustomTopicSubject(e.target.value)}
                                            placeholder="Optional subject name"
                                            className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">Planned Time</label>
                                        <select
                                            value={customTopicDuration}
                                            onChange={(e) => setCustomTopicDuration(e.target.value)}
                                            className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm bg-white"
                                        >
                                            <option value="0.5">30 minutes</option>
                                            <option value="1">1 hour</option>
                                            <option value="1.5">1.5 hours</option>
                                            <option value="2">2 hours</option>
                                        </select>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={addCustomTopicToToday}
                                        disabled={!_cleanTopicName(customTopicName) || customTopicLoading}
                                        className="w-full px-4 py-2.5 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 disabled:opacity-50"
                                    >
                                        {customTopicLoading ? 'Adding resources...' : 'Add Custom Topic'}
                                    </button>
                                </div>
                            )}

                            <div className="mt-4 pt-4 border-t border-gray-100 flex justify-end">
                                <button
                                    onClick={() => {
                                        setTopicPicker(false);
                                        setTopicPickerMode('syllabus');
                                        setTopicPickerSubject('');
                                        setTopicPickerUnit('');
                                        setTopicPickerTopic('');
                                        setCustomTopicName('');
                                        setCustomTopicSubject('');
                                        setCustomTopicDuration('1');
                                    }}
                                    className="px-4 py-2 border border-gray-300 text-gray-600 rounded-lg text-sm hover:bg-gray-50 transition-colors"
                                >
                                    Close
                                </button>
                            </div>
                        </div>
                    </div>
                );
            })()}
        </DashboardLayout>
    );
};

export default Dashboard;
