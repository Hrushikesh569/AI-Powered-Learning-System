
import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import DashboardLayout from '../layouts/DashboardLayout';
import Modal from '../components/Modal';
import AchievementCard from '../components/AchievementCard';
import MotivationTips from '../components/MotivationTips';
import ShapExplanation from '../components/ShapExplanation';
import { agentAPI } from '../api';
import { CheckCircle, Clock, AlertCircle, TrendingUp, Calendar, Sparkles, Trophy, FileText, RefreshCw } from 'lucide-react';


const formatDate = (date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
};

const _cleanTopicName = (value) =>
    String(value || '').replace(/ — Day \d+$/, '').replace(/^\[Review\] /, '').trim();

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

const _buildMixedScheduleFromBackend = async ({
    todayIso,
    preferredTopics = [],
    hiddenSubjects = [],
}) => {
    let rows = [];
    try {
        const rowsRes = await agentAPI.queryScheduledTopics({});
        rows = rowsRes?.topics || [];
    } catch (_) {
        rows = [];
    }

    if (!rows.length) return [];

    const hiddenSet = new Set((hiddenSubjects || []).filter(Boolean));
    const preferredSet = new Set((preferredTopics || []).map(_cleanTopicName).filter(Boolean));
    if (hiddenSet.size) rows = rows.filter((r) => !hiddenSet.has(r.subject || 'General'));
    if (!rows.length) return [];

    const diffRank = { easy: 1, basic: 2, intermediate: 3, medium: 3, hard: 4, advanced: 5 };

    return [...rows]
        .sort((a, b) => {
            const aPreferred = preferredSet.has(_cleanTopicName(a.topic_name));
            const bPreferred = preferredSet.has(_cleanTopicName(b.topic_name));
            if (aPreferred !== bPreferred) return aPreferred ? -1 : 1;

            const aDate = a.rescheduled_date || a.scheduled_date || todayIso;
            const bDate = b.rescheduled_date || b.scheduled_date || todayIso;
            if (aDate !== bDate) return aDate.localeCompare(bDate);

            const da = diffRank[String(a.difficulty || '').toLowerCase()] || 3;
            const db = diffRank[String(b.difficulty || '').toLowerCase()] || 3;
            if (db !== da) return db - da;

            return Number(b.estimated_hours || 1) - Number(a.estimated_hours || 1);
        })
        .map((t, index) => {
            let hrs = Number(t.estimated_hours || 1);
            if (!Number.isFinite(hrs) || hrs <= 0) hrs = 1;
            hrs = Math.max(0.5, Math.min(2.5, hrs));
            return {
                id: t.id,
                scheduled_topic_id: t.id,
                date: (t.rescheduled_date || t.scheduled_date || todayIso).slice(0, 10),
                time: `Task ${index + 1}`,
                subject: t.subject || 'General',
                unit: t.unit_name || '',
                topic: t.topic_name || 'Study Topic',
                difficulty: diffRank[String(t.difficulty || '').toLowerCase()] || 3,
                difficultyLabel: t.difficulty || 'Intermediate',
                estimated_hours: hrs,
                duration: hrs < 1 ? `${Math.round(hrs * 60)} min` : `${hrs.toFixed(1)} hour${hrs === 1 ? '' : 's'}`,
                key_concepts: [],
                is_foundational: false,
                status: t.status || 'pending',
                completed_date: t.completed_date || null,
            };
        });
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
    const [topicPicker, setTopicPicker] = useState(false); // show "add topic today" modal
    const [topicPickerSubject, setTopicPickerSubject] = useState(''); // selected subject in picker
    const [topicPickerUnit, setTopicPickerUnit] = useState(''); // selected unit in picker
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
    const [hiddenSubjects, setHiddenSubjects] = useState(() => {
        try {
            const raw = localStorage.getItem('hiddenSubjects') || '[]';
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
        } catch (_) {
            return [];
        }
    });
    const [rebuildingSchedule, setRebuildingSchedule] = useState(false);
    const [customTopicName, setCustomTopicName] = useState('');
    const [customTopicSubject, setCustomTopicSubject] = useState('');
    const [customTopicDuration, setCustomTopicDuration] = useState('1');
    const [customTopicLoading, setCustomTopicLoading] = useState(false);

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

    useEffect(() => {
        try { localStorage.setItem('preferredTopics', JSON.stringify(preferredTopics)); } catch (_) {}
    }, [preferredTopics]);

    useEffect(() => {
        try { localStorage.setItem('hiddenSubjects', JSON.stringify(hiddenSubjects)); } catch (_) {}
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

                let hierarchy = [];
                try {
                    const hierarchyRes = await _withTimeout(agentAPI.getSubjectHierarchy(), 8000, { hierarchy: [] });
                    hierarchy = hierarchyRes?.hierarchy || [];
                    setSubjectHierarchy(hierarchy);
                } catch (_) {
                    setSubjectHierarchy([]);
                }

                let backendTasks = [];
                try {
                    backendTasks = await _withTimeout(_buildMixedScheduleFromBackend({
                        todayIso,
                        preferredTopics,
                        hiddenSubjects,
                    }), 12000, []);
                } catch (_) {}

                let storedCustomTasks = [];
                try {
                    const raw = JSON.parse(localStorage.getItem('generatedSchedule') || '[]');
                    storedCustomTasks = Array.isArray(raw)
                        ? raw.filter((task) => task.user_override === true)
                        : [];
                } catch (_) {
                    storedCustomTasks = [];
                }

                const syllabusExists = hierarchy.length > 0 || backendTasks.length > 0;
                const freshTasks = syllabusExists ? backendTasks : [];
                const combined = _applyStatuses([
                    ...freshTasks,
                    ...storedCustomTasks.filter((task) => !hiddenSubjects.includes(task.subject || '')),
                ]);
                const pastPending = combined.filter((t) => t.date < todayIso && (t.status || 'pending') === 'pending');
                if (pastPending.length > 0) {
                    const s = _loadStatuses();
                    pastPending.forEach((t) => { s[_taskKey(t)] = 'missed'; });
                    localStorage.setItem('taskStatuses', JSON.stringify(s));
                }
                const finalTasks = combined.map((t) =>
                    pastPending.some((p) => _taskKey(p) === _taskKey(t)) ? { ...t, status: 'missed' } : t,
                );
                const merged = mergeWithPastHistory(finalTasks);
                setTasks(merged);
                try { localStorage.setItem('generatedSchedule', JSON.stringify(merged)); } catch (_) {}

                if (!syllabusExists && storedCustomTasks.length === 0) {
                    try {
                        localStorage.setItem('generatedSchedule', JSON.stringify(merged.filter((task) => task.user_override === true)));
                    } catch (_) {}
                }

                // Fetch progress dashboard data from backend
                const progressRes = await _withTimeout(agentAPI.getProgressDashboard(), 8000, null);
                const safeProgress = progressRes || {};
                setWeeklyProgress(safeProgress.weeklyProgress || { percentage: 0, completedHours: 0, totalHours: 0, streak: 0 });
                // Fetch AI suggestions from backend
                setAiSuggestions(safeProgress.suggestions || []);
                // Fetch motivational quotes and achievements
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

    // Ensure selectedDate always belongs to the current month (default to today or first day)
    useEffect(() => {
        if (!calendarDays.length) return;
        if (calendarDays.includes(selectedDate)) return;
        const todayInMonth = calendarDays.find((d) => d === todayIso);
        setSelectedDate(todayInMonth || calendarDays[0]);
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
            const total = completedTopics.length + missedTopics.length;
            const performanceScore = total > 0 ? completedTopics.length / total : 0.7;

            const res = await agentAPI.getAdaptiveSchedule({
                completed_topics: completedTopics,
                missed_topics: missedTopics,
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

    const getDifficultyBadge = (task) => {
        if (!task.difficulty) return null;
        const color = DIFF_COLORS[task.difficulty] || 'bg-gray-100 text-gray-600';
        const label = task.difficultyLabel || ['', 'Easy', 'Basic', 'Intermediate', 'Hard', 'Advanced'][task.difficulty] || '';
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
        const usedSlots = new Set(
            tasks.filter((t) => t.date === todayIso).map((t) => t.time)
        );
        const fallbackSlots = ['09:00 AM', '11:00 AM', '02:00 PM', '05:00 PM', '08:00 PM'];
        const freeSlot = fallbackSlots.find((s) => !usedSlots.has(s)) || '12:00 PM';
        const diff = difficulty || 3;
        const hours = estimatedHours || (diff <= 2 ? 0.5 : diff <= 3 ? 1.0 : 2.0);
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
        setTopicPickerSubject('');
        setTopicPickerUnit('');
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
            unit: 'Self added',
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

                const moved = { ...next[idx], date: selectedDate, time: freeSlot, user_override: true };
                next[idx] = moved;
                _saveStatus(moved, moved.status || 'pending');
            }

            next = next.filter((t) => !hiddenSubjects.includes(t.subject || ''));
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

    const openTopicPicker = async () => {
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
    const getTasksForDateWithinHours = (dateStr, maxHours) => {
        const candidates = tasks.filter(
            (task) => task.date === dateStr && !hiddenSubjects.includes(task.subject || ''),
        );
        let accum = 0;
        const result = [];
        for (const t of candidates) {
            const hrs = Math.max(0.5, Math.min(2.5, Number(t.estimated_hours) || 1));
            if (accum + hrs <= maxHours) {
                result.push(t);
                accum += hrs;
            } else if (result.length === 0) {
                result.push(t);
                break;
            }
        }
        return result;
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
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <select
                                            value={preferredTopicDraft}
                                            onChange={(e) => setPreferredTopicDraft(e.target.value)}
                                            className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white min-w-[220px]"
                                            title="Select subjects or topics to prioritize in your schedule"
                                        >
                                            <option value="">Select subject or topic</option>
                                            {preferredTopicOptions.map((option) => (
                                                <option key={option.value} value={option.value}>{option.label}</option>
                                            ))}
                                        </select>
                                        <button
                                            onClick={() => {
                                                if (!preferredTopicDraft || preferredTopics.includes(preferredTopicDraft)) return;
                                                setPreferredTopics((prev) => [...prev, preferredTopicDraft]);
                                                setPreferredTopicDraft('');
                                            }}
                                            disabled={!preferredTopicDraft || preferredTopics.includes(preferredTopicDraft)}
                                            className="px-3 py-2 text-sm border border-primary-200 text-primary-700 rounded-lg hover:bg-primary-50 disabled:opacity-50 font-medium"
                                        >
                                            Add
                                        </button>
                                        <div className="flex items-center gap-2">
                                            <select
                                                value={hiddenSubjects.length > 0 ? 'configured' : ''}
                                                onChange={(e) => {
                                                    if (e.target.value === 'configure') {
                                                        const available = hiddenSubjectOptions.filter(s => !hiddenSubjects.includes(s));
                                                        const hidden = hiddenSubjectOptions.filter(s => hiddenSubjects.includes(s));
                                                        const input = prompt(
                                                            hidden.length > 0 
                                                                ? `Currently hidden: ${hidden.join(', ')}\n\nAvailable to hide: ${available.join(', ')}\n\nEnter subject names to hide (comma-separated):`
                                                                : `Available subjects: ${hiddenSubjectOptions.join(', ')}\n\nEnter subject names to hide (comma-separated):`,
                                                            hiddenSubjects.join(', ')
                                                        );
                                                        if (input !== null) {
                                                            setHiddenSubjects(input.split(',').map(s => s.trim()).filter(Boolean));
                                                        }
                                                    }
                                                }}
                                                className="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white flex-1"
                                                title="Manage hidden subjects"
                                            >
                                                <option value="">
                                                    {hiddenSubjects.length === 0 
                                                        ? 'Show all subjects' 
                                                        : hiddenSubjects.length === 1
                                                        ? `Hide: ${hiddenSubjects[0]}`
                                                        : `Hide ${hiddenSubjects.length} subjects`}
                                                </option>
                                                <option value="configure">→ Change</option>
                                            </select>
                                        </div>
                                        <button
                                            onClick={rebuildMixedScheduleNow}
                                            disabled={rebuildingSchedule}
                                            className="px-2.5 py-1.5 text-sm border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50 inline-flex items-center gap-1"
                                            title="Refresh schedule from extracted topics"
                                        >
                                            <RefreshCw className={`w-3.5 h-3.5 ${rebuildingSchedule ? 'animate-spin' : ''}`} />
                                            Refresh
                                        </button>
                                    </div>
                                    {selectedDate === todayIso && (
                                        <button
                                            onClick={openTopicPicker}
                                            className="flex items-center gap-1 px-3 py-1.5 bg-primary-50 text-primary-700 border border-primary-200 rounded-lg text-sm hover:bg-primary-100 transition-colors"
                                            title="Add a topic you want to study today"
                                        >
                                            <span className="font-bold text-base leading-none">+</span> Add Topic
                                        </button>
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
                                                {task.user_override && (
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

                                            {topicResources[task.topic]?.length > 0 && (
                                                <div className="flex flex-wrap gap-1.5 mb-3">
                                                    {(() => {
                                                        const { web, video } = _pickResourceLinks(topicResources[task.topic]);
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
                                                className={`h-8 w-8 rounded-md flex items-center justify-center text-[11px] font-medium transition-colors border ${
                                                    isSelected
                                                        ? 'border-primary-600 ring-1 ring-primary-400'
                                                        : 'border-transparent'
                                                } ${baseIntensityClass}`}
                                            >
                                                {dayNumber}
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                            <p className="mt-3 text-xs text-gray-500">
                                Darker green means a heavier study day. Click a date to see that day's plan.
                            </p>
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
                const DIFF_LABELS = ['', 'Easy', 'Basic', 'Intermediate', 'Hard', 'Advanced'];

                return (
                    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center">
                        <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md mx-4">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-lg font-bold text-gray-800">Add Topic to Today</h3>
                                <button
                                    onClick={() => { setTopicPicker(false); setTopicPickerSubject(''); setTopicPickerUnit(''); }}
                                    className="text-gray-400 hover:text-gray-600 text-xl leading-none"
                                >×</button>
                            </div>
                            <p className="text-sm text-gray-500 mb-5">
                                Pick a syllabus topic or add any custom topic you want to study today.
                                Web Search and YouTube links will be attached automatically.
                            </p>

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

                            {/* Subject picker */}
                            <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">Subject</label>
                            <div className="flex flex-wrap gap-2 mb-4">
                                {subjects.length === 0 && (
                                    <p className="text-sm text-gray-400 italic">
                                        No subjects found. Upload a syllabus first.
                                    </p>
                                )}
                                {subjects.map((s) => {
                                    const code = getSubjectCode(s);
                                    return (
                                        <button
                                            key={s}
                                            onClick={() => { setTopicPickerSubject(s); setTopicPickerUnit(''); }}
                                            className={`px-3 py-1.5 rounded-lg border text-sm font-medium transition-colors ${
                                                topicPickerSubject === s
                                                    ? 'bg-primary-600 text-white border-primary-600'
                                                    : 'bg-gray-50 text-gray-700 border-gray-200 hover:bg-gray-100'
                                            }`}
                                        >
                                            {s}
                                            {code && <span className="ml-1 font-mono text-xs opacity-70">({code})</span>}
                                        </button>
                                    );
                                })}
                            </div>

                            {/* Unit picker */}
                            {topicPickerSubject && (
                                <>
                                    <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">Unit / Module</label>
                                    <div className="flex flex-wrap gap-2 mb-4">
                                        {units.map((u) => (
                                            <button
                                                key={u}
                                                onClick={() => setTopicPickerUnit(u)}
                                                className={`px-3 py-1.5 rounded-lg border text-sm font-medium transition-colors ${
                                                    topicPickerUnit === u
                                                        ? 'bg-indigo-600 text-white border-indigo-600'
                                                        : 'bg-gray-50 text-gray-700 border-gray-200 hover:bg-gray-100'
                                                }`}
                                            >
                                                {u}
                                            </button>
                                        ))}
                                    </div>
                                </>
                            )}

                            {/* Topic picker */}
                            {topicPickerUnit && (
                                <>
                                    <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">Topic</label>
                                    <div className="max-h-48 overflow-y-auto space-y-1 mb-4 pr-1">
                                        {topicsForUnit.map(({ name: topic, difficulty, est_hours }) => {
                                            const alreadyToday = tasks.some(
                                                (t) => t.date === todayIso && t.topic === topic && t.status !== 'later'
                                            );
                                            return (
                                                <button
                                                    key={topic}
                                                    disabled={alreadyToday}
                                                    onClick={() =>
                                                        addTopicToToday({
                                                            subject: topicPickerSubject,
                                                            subjectCode: getSubjectCode(topicPickerSubject),
                                                            unit: topicPickerUnit,
                                                            topic,
                                                            difficulty,
                                                            estimatedHours: est_hours,
                                                        })
                                                    }
                                                    className={`w-full text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                                                        alreadyToday
                                                            ? 'bg-gray-50 text-gray-400 border-gray-100 cursor-not-allowed'
                                                            : 'bg-white text-gray-700 border-gray-200 hover:bg-primary-50 hover:border-primary-200 hover:text-primary-700'
                                                    }`}
                                                >
                                                    <span className="font-medium">{topic}</span>
                                                    <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${
                                                        difficulty >= 4 ? 'bg-orange-100 text-orange-700' :
                                                        difficulty >= 3 ? 'bg-yellow-100 text-yellow-700' :
                                                        'bg-green-100 text-green-700'
                                                    }`}>{DIFF_LABELS[difficulty] || 'Intermediate'}</span>
                                                    <span className="ml-1 text-xs text-gray-400">{est_hours < 1 ? `${Math.round(est_hours*60)}min` : `${est_hours}h`}</span>
                                                    {alreadyToday && <span className="ml-2 text-xs text-gray-400">(already today)</span>}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </>
                            )}

                            <div className="border-t border-gray-100 pt-4 mt-4 space-y-3">
                                <div>
                                    <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">Custom Topic</label>
                                    <input
                                        type="text"
                                        value={customTopicName}
                                        onChange={(e) => setCustomTopicName(e.target.value)}
                                        placeholder="Example: Backpropagation intuition"
                                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">Subject Label</label>
                                    <input
                                        type="text"
                                        value={customTopicSubject}
                                        onChange={(e) => setCustomTopicSubject(e.target.value)}
                                        placeholder="Optional subject name"
                                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">Planned Time</label>
                                    <select
                                        value={customTopicDuration}
                                        onChange={(e) => setCustomTopicDuration(e.target.value)}
                                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                                    >
                                        <option value="0.5">30 minutes</option>
                                        <option value="1">1 hour</option>
                                        <option value="1.5">1.5 hours</option>
                                        <option value="2">2 hours</option>
                                    </select>
                                </div>
                                <button
                                    onClick={addCustomTopicToToday}
                                    disabled={!_cleanTopicName(customTopicName) || customTopicLoading}
                                    className="w-full px-4 py-2 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 disabled:opacity-50"
                                >
                                    {customTopicLoading ? 'Adding resources...' : 'Add Custom Topic'}
                                </button>
                            </div>

                            <button
                                onClick={() => {
                                    setTopicPicker(false);
                                    setTopicPickerSubject('');
                                    setTopicPickerUnit('');
                                    setCustomTopicName('');
                                    setCustomTopicSubject('');
                                    setCustomTopicDuration('1');
                                }}
                                className="w-full px-4 py-2 border border-gray-300 text-gray-600 rounded-lg text-sm hover:bg-gray-50 transition-colors"
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                );
            })()}
        </DashboardLayout>
    );
};

export default Dashboard;
