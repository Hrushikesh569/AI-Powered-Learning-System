
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import DashboardLayout from '../layouts/DashboardLayout';
import { agentAPI, clearAuthToken } from '../api';
import { userProfile as fallbackUserProfile, scheduleData as fallbackScheduleData } from '../data/mockData';
import { User, Mail, Clock, Target, Award, Calendar, LogOut } from 'lucide-react';


const Profile = () => {
    const navigate = useNavigate();
    const [formData, setFormData] = useState({ name: '', email: '', studyHoursPerDay: 0, learningGoal: '', grade: '', course: '' });
    const [userProfile, setUserProfile] = useState({ name: '', email: '', learnerType: '', joinedDate: '', totalStudyHours: 0, completedSessions: 0, grade: '', course: '', branch: '' });
    const [completedArchive, setCompletedArchive] = useState([]);
    const [hiddenArchive, setHiddenArchive] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        const fetchProfile = async () => {
            setLoading(true);
            setError('');
            try {
                const [res, archiveRes] = await Promise.all([
                    agentAPI.getMe(),
                    agentAPI.getCompletedTopics().catch(() => ({ topics: [] })),
                ]);
                setUserProfile({
                    ...res,
                    branch: res.branch || res.course || '',
                });
                setFormData({
                    name: res.name || '',
                    email: res.email || '',
                    studyHoursPerDay: res.studyHoursPerDay || 0,
                    learningGoal: res.learningGoal || '',
                    grade: res.grade || '',
                    course: res.course || ''
                });

                const grouped = {};
                (archiveRes.topics || []).forEach((topic) => {
                    const subject = topic.subject || 'General';
                    const unit = topic.unit_name || 'General Unit';
                    if (!grouped[subject]) grouped[subject] = { subject, units: {} };
                    if (!grouped[subject].units[unit]) grouped[subject].units[unit] = [];
                    grouped[subject].units[unit].push(topic);
                });
                setCompletedArchive(Object.values(grouped).map((subject) => ({
                    ...subject,
                    units: Object.entries(subject.units).map(([unitName, topics]) => ({ unitName, topics })),
                })));

                try {
                    const rawHidden = JSON.parse(localStorage.getItem('hiddenStudyItems') || '[]');
                    const items = Array.isArray(rawHidden) ? rawHidden : [];
                    const fallbackSubjects = JSON.parse(localStorage.getItem('hiddenSubjects') || '[]');
                    const merged = [
                        ...items,
                        ...(Array.isArray(fallbackSubjects)
                            ? fallbackSubjects.map((subject) => ({ subject, unit: '', topic: '', scope: 'subject' }))
                            : []),
                    ].filter(Boolean);

                    const hiddenGrouped = {};
                    merged.forEach((entry) => {
                        const subject = entry.subject || 'General';
                        const unit = entry.unit || 'General Unit';
                        if (!hiddenGrouped[subject]) hiddenGrouped[subject] = { subject, units: {} };
                        if (!hiddenGrouped[subject].units[unit]) hiddenGrouped[subject].units[unit] = [];
                        hiddenGrouped[subject].units[unit].push(entry);
                    });
                    setHiddenArchive(Object.values(hiddenGrouped).map((subject) => ({
                        ...subject,
                        units: Object.entries(subject.units).map(([unitName, items]) => ({ unitName, items })),
                    })));
                } catch (_) {
                    setHiddenArchive([]);
                }
            } catch (err) {
                setUserProfile({
                    name: fallbackUserProfile.name,
                    email: fallbackUserProfile.email,
                    learnerType: fallbackUserProfile.learnerType,
                    joinedDate: fallbackUserProfile.joinedDate,
                    totalStudyHours: fallbackUserProfile.totalStudyHours,
                    completedSessions: fallbackUserProfile.completedSessions,
                    grade: 'Demo',
                    course: 'Computer Science',
                    branch: 'Computer Science',
                    learningGoal: fallbackUserProfile.learningGoal,
                    studyHoursPerDay: fallbackUserProfile.studyHoursPerDay,
                });
                setFormData({
                    name: fallbackUserProfile.name,
                    email: fallbackUserProfile.email,
                    studyHoursPerDay: fallbackUserProfile.studyHoursPerDay,
                    learningGoal: fallbackUserProfile.learningGoal,
                    grade: 'Demo',
                    course: 'Computer Science',
                });
                setCompletedArchive([
                    {
                        subject: 'Demo Learning',
                        units: [
                            {
                                unitName: 'Weekly Progress',
                                topics: fallbackScheduleData.map((item, index) => ({
                                    id: index + 1,
                                    subject: item.subject,
                                    unit_name: 'Weekly Progress',
                                    topic_name: item.topic,
                                    status: item.status,
                                })),
                            },
                        ],
                    },
                ]);
                setHiddenArchive([]);
                setError('');
            } finally {
                setLoading(false);
            }
        };
        fetchProfile();
    }, []);

    const [saving, setSaving] = useState(false);
    const [saveMsg, setSaveMsg] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSaving(true);
        setSaveMsg('');
        try {
            await agentAPI.updateMe({
                name: formData.name,
                studyHoursPerDay: Number(formData.studyHoursPerDay),
                learningGoal: formData.learningGoal,
                grade: formData.grade,
                course: formData.course,
            });
            setUserProfile((p) => ({ ...p, ...formData }));
            setSaveMsg('Profile saved successfully!');
        } catch (err) {
            setSaveMsg('Failed to save profile. Please try again.');
        } finally {
            setSaving(false);
        }
    };

    const handleLogout = () => {
        clearAuthToken();
        // Clear all user-specific localStorage data
        localStorage.removeItem('userName');
        localStorage.removeItem('userEmail');
        localStorage.removeItem('taskStatuses');
        localStorage.removeItem('preferredTopics');
        localStorage.removeItem('hiddenSubjects');
        localStorage.removeItem('hiddenStudyItems');
        localStorage.removeItem('generatedSchedule');
        localStorage.removeItem('learningPreferences');
        localStorage.removeItem('completedSubjects');
        localStorage.removeItem('completedTopics');
        localStorage.removeItem('missedTopics');
        localStorage.removeItem('activityMap');
        localStorage.removeItem('scheduleOverrides');
        localStorage.removeItem('preferredSubjectToday');
        navigate('/');
    };

    if (loading) return <div className="text-center text-primary-600 mt-8">Loading profile...</div>;
    if (error) return <div className="text-center text-red-600 mt-8">{error}</div>;

    return (
        <DashboardLayout>
            <div className="space-y-6">
                <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
                    <h1 className="text-3xl font-bold text-gray-900">Profile</h1>
                    <p className="text-gray-600 mt-1">Manage your account settings</p>
                </motion.div>

                <div className="grid lg:grid-cols-3 gap-6">
                    {/* Profile Summary */}
                    <motion.div
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        className="lg:col-span-1 space-y-4"
                    >
                        <div className="card text-center">
                            <div className="w-24 h-24 bg-gradient-to-br from-primary-500 to-blue-600 rounded-full flex items-center justify-center mx-auto mb-4">
                                <span className="text-3xl font-bold text-white">
                                    {(userProfile.name || 'User')
                                        .split(' ')
                                        .filter(Boolean)
                                        .map((n) => n[0])
                                        .join('')}
                                </span>
                            </div>
                            <h2 className="text-xl font-bold text-gray-800">{userProfile.name}</h2>
                            <p className="text-gray-600">{userProfile.email}</p>
                            <div className="mt-4 inline-flex items-center space-x-2 px-4 py-2 bg-primary-100 text-primary-800 rounded-full">
                                <Award className="w-4 h-4" />
                                <span className="font-semibold">{userProfile.learnerType}</span>
                            </div>
                        </div>

                        <div className="card">
                            <h3 className="font-semibold text-gray-800 mb-4">About</h3>
                            <div className="space-y-3">
                                <div className="flex items-center justify-between gap-4">
                                    <span className="text-sm text-gray-600">Study Hours / Day</span>
                                    <span className="font-semibold text-gray-800">{userProfile.studyHoursPerDay || 0}h</span>
                                </div>
                                <div className="flex items-center justify-between gap-4">
                                    <span className="text-sm text-gray-600">Grade / Year</span>
                                    <span className="font-semibold text-gray-800 text-right max-w-[55%]">{userProfile.grade || 'Not set'}</span>
                                </div>
                                <div className="flex items-center justify-between gap-4">
                                    <span className="text-sm text-gray-600">Branch / Course</span>
                                    <span className="font-semibold text-gray-800 text-right max-w-[55%]">{userProfile.branch || userProfile.course || 'Not set'}</span>
                                </div>
                                <div className="flex items-center justify-between gap-4">
                                    <span className="text-sm text-gray-600">Learning Goal</span>
                                    <span className="font-semibold text-gray-800 text-right max-w-[55%]">{userProfile.learningGoal || 'Not set'}</span>
                                </div>
                                <div className="flex items-center justify-between gap-4">
                                    <span className="text-sm text-gray-600">Member Since</span>
                                    <span className="font-semibold text-gray-800">
                                        {userProfile.joinedDate 
                                            ? new Date(userProfile.joinedDate).toLocaleDateString('en-US', { 
                                                year: 'numeric', 
                                                month: 'long', 
                                                day: 'numeric' 
                                              })
                                            : 'Today'}
                                    </span>
                                </div>
                            </div>
                        </div>

                        <div className="card">
                            <h3 className="font-semibold text-gray-800 mb-1">Learning Stats</h3>
                            <p className="text-xs text-gray-500 mb-4">Derived from progress logs in the backend, not manual inputs.</p>
                            <div className="space-y-3">
                                <div className="flex items-center justify-between gap-4">
                                    <span className="text-sm text-gray-600">Total Hours</span>
                                    <span className="font-semibold text-gray-800">{userProfile.totalStudyHours}h</span>
                                </div>
                                <div className="flex items-center justify-between gap-4">
                                    <span className="text-sm text-gray-600">Logged Sessions</span>
                                    <span className="font-semibold text-gray-800">{userProfile.completedSessions}</span>
                                </div>
                            </div>
                        </div>
                    </motion.div>

                    {/* Edit Form */}
                    <motion.div
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        className="lg:col-span-2"
                    >
                        <div className="card">
                            <h2 className="text-xl font-bold text-gray-800 mb-6">Edit Profile</h2>
                            <form onSubmit={handleSubmit} className="space-y-6">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">Full Name</label>
                                    <div className="relative">
                                        <User className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                                        <input
                                            type="text"
                                            value={formData.name}
                                            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                            className="input-field pl-10"
                                        />
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">Email</label>
                                    <div className="relative">
                                        <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                                        <input
                                            type="email"
                                            value={formData.email}
                                            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                                            className="input-field pl-10"
                                        />
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Study Hours Per Day: {formData.studyHoursPerDay}
                                    </label>
                                    <input
                                        type="range"
                                        min="1"
                                        max="12"
                                        value={formData.studyHoursPerDay}
                                        onChange={(e) =>
                                            setFormData({ ...formData, studyHoursPerDay: e.target.value })
                                        }
                                        className="w-full"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">Grade / Year</label>
                                    <input
                                        type="text"
                                        value={formData.grade}
                                        onChange={(e) => setFormData({ ...formData, grade: e.target.value })}
                                        className="input-field"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">Branch / Course</label>
                                    <input
                                        type="text"
                                        value={formData.course}
                                        onChange={(e) => setFormData({ ...formData, course: e.target.value })}
                                        className="input-field"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Learning Goal
                                    </label>
                                    <div className="relative">
                                        <Target className="absolute left-3 top-3 w-5 h-5 text-gray-400" />
                                        <textarea
                                            value={formData.learningGoal}
                                            onChange={(e) => setFormData({ ...formData, learningGoal: e.target.value })}
                                            className="input-field pl-10 min-h-[100px]"
                                        />
                                    </div>
                                </div>

                                <div className="flex space-x-4">
                                    <button type="submit" className="btn-primary flex-1" disabled={saving}>
                                        {saving ? 'Saving...' : 'Save Changes'}
                                    </button>
                                    <button type="button" className="btn-secondary flex-1">
                                        Cancel
                                    </button>
                                </div>
                                {saveMsg && (
                                    <p className={`text-sm mt-2 ${
                                        saveMsg.includes('Failed') ? 'text-red-600' : 'text-green-600'
                                    }`}>{saveMsg}</p>
                                )}
                            </form>
                        </div>

                        <div className="card mt-6 border-2 border-red-200">
                            <h3 className="text-lg font-semibold text-gray-800 mb-4">Danger Zone</h3>
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="font-medium text-gray-800">Logout from your account</p>
                                    <p className="text-sm text-gray-600">You can sign back in anytime</p>
                                </div>
                                <button
                                    onClick={handleLogout}
                                    className="flex items-center space-x-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                                >
                                    <LogOut className="w-4 h-4" />
                                    <span>Logout</span>
                                </button>
                            </div>
                        </div>
                    </motion.div>
                </div>

                <div className="card">
                    <h3 className="text-lg font-semibold text-gray-800 mb-4">Completed Topics Archive</h3>
                    {completedArchive.length === 0 ? (
                        <p className="text-sm text-gray-500">No completed topics yet.</p>
                    ) : (
                        <div className="space-y-4">
                            {completedArchive.map((subject) => (
                                <div key={subject.subject} className="rounded-xl border border-gray-200 p-4">
                                    <div className="flex items-center justify-between mb-3">
                                        <h4 className="font-semibold text-gray-800">{subject.subject}</h4>
                                        <span className="text-xs text-gray-500">
                                            {subject.units.reduce((sum, unit) => sum + unit.topics.length, 0)} completed
                                        </span>
                                    </div>
                                    <div className="space-y-3">
                                        {subject.units.map((unit) => (
                                            <div key={unit.unitName}>
                                                <p className="text-sm font-medium text-gray-700 mb-2">{unit.unitName}</p>
                                                <div className="flex flex-wrap gap-2">
                                                    {unit.topics.map((topic) => (
                                                        <span key={topic.id} className="text-xs px-2 py-1 rounded-full bg-green-50 text-green-700 border border-green-100">
                                                            {topic.topic_name}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                <div className="card">
                    <h3 className="text-lg font-semibold text-gray-800 mb-4">Hidden Topics Archive</h3>
                    {hiddenArchive.length === 0 ? (
                        <p className="text-sm text-gray-500">No hidden topics yet.</p>
                    ) : (
                        <div className="space-y-4">
                            {hiddenArchive.map((subject) => (
                                <div key={subject.subject} className="rounded-xl border border-gray-200 p-4">
                                    <div className="flex items-center justify-between mb-3">
                                        <h4 className="font-semibold text-gray-800">{subject.subject}</h4>
                                        <span className="text-xs text-gray-500">
                                            {subject.units.reduce((sum, unit) => sum + unit.items.length, 0)} hidden
                                        </span>
                                    </div>
                                    <div className="space-y-3">
                                        {subject.units.map((unit) => (
                                            <div key={unit.unitName}>
                                                <p className="text-sm font-medium text-gray-700 mb-2">{unit.unitName}</p>
                                                <div className="flex flex-wrap gap-2">
                                                    {unit.items.map((item, index) => (
                                                        <span
                                                            key={`${subject.subject}-${unit.unitName}-${item.topic || 'subject'}-${index}`}
                                                            className="text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-700 border border-gray-200"
                                                        >
                                                            {item.topic || item.unit || subject.subject}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </DashboardLayout>
    );
};

export default Profile;
