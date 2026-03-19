import { useState } from 'react';
import { agentAPI } from '../api';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import Modal from '../components/Modal';
import { Brain, Clock, BookOpen, Zap, TrendingUp, CheckCircle } from 'lucide-react';

const PERFORMANCE_OPTIONS = [
    { value: 'excellent', label: 'Excellent',         desc: 'Consistently top scores, rarely struggle',       grades: ['A','A','A'] },
    { value: 'good',      label: 'Good',              desc: 'Above average, occasional difficulty',            grades: ['A','B','B'] },
    { value: 'average',   label: 'Average',           desc: 'Solid understanding, some knowledge gaps',        grades: ['B','B','C'] },
    { value: 'needs_work',label: 'Needs Improvement', desc: 'Struggling with several topics, need extra help', grades: ['C','C','C'] },
];

const Profiling = () => {
    const navigate = useNavigate();
    const [showModal, setShowModal] = useState(false);
    const [formData, setFormData] = useState({
        studyHours:   5,
        performance:  'good',
        attendance:   80,
        motivation:   7,
        learningStyle:'visual',
    });
    const [profileLabel, setProfileLabel] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');
        try {
            const selected = PERFORMANCE_OPTIONS.find(o => o.value === formData.performance) || PERFORMANCE_OPTIONS[1];

            const profilePayload = {
                grades:                selected.grades,
                studyHoursPerWeek:     Number(formData.studyHours) * 7,
                attendanceRate:        Number(formData.attendance),
                selfStudyHoursPerWeek: Math.round(Number(formData.studyHours) * 7 * 0.4),
                numSubjects:           3,
            };

            console.log('Sending profiling payload:', profilePayload);

            try {
                localStorage.setItem('learningPreferences', JSON.stringify(formData));
            } catch (_) {}

            // Import getAuthToken at top of file
            const token = localStorage.getItem('authToken');
            const res = await agentAPI.classifyProfile(profilePayload, token);
            console.log('Profile response:', res);
            setProfileLabel(res.profile_label || res.label || res.cluster || 'Learner');
            setShowModal(true);
            setTimeout(() => navigate('/dashboard'), 3000);
        } catch (err) {
            console.error('Profiling error:', err);
            setError(`Failed to generate profile: ${err.message || 'Unknown error'}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-primary-50 to-blue-50 py-12 px-6">
            <div className="max-w-5xl mx-auto">
                <motion.div initial={{ opacity:0, y:20 }} animate={{ opacity:1, y:0 }} className="text-center mb-12">
                    <Brain className="w-16 h-16 text-primary-600 mx-auto mb-4" />
                    <h1 className="text-4xl font-bold text-gray-900 mb-3">Build Your Learning Profile</h1>
                    <p className="text-lg text-gray-600">Tell us about yourself — no subjects required yet. We'll extract those from your syllabus.</p>
                </motion.div>

                <div className="grid lg:grid-cols-3 gap-8">
                    {/* Live Profile Summary */}
                    <motion.div initial={{ opacity:0, x:-20 }} animate={{ opacity:1, x:0 }} className="lg:col-span-1">
                        <div className="card sticky top-8 space-y-4">
                            <h3 className="text-lg font-bold text-gray-800">Your Profile</h3>

                            <div className="flex items-center space-x-3">
                                <Clock className="w-5 h-5 text-primary-600 flex-shrink-0" />
                                <div>
                                    <p className="text-xs text-gray-500">Daily Study Time</p>
                                    <p className="font-semibold">{formData.studyHours} hours/day</p>
                                </div>
                            </div>

                            <div className="flex items-center space-x-3">
                                <TrendingUp className="w-5 h-5 text-primary-600 flex-shrink-0" />
                                <div>
                                    <p className="text-xs text-gray-500">Academic Performance</p>
                                    <p className="font-semibold capitalize">
                                        {PERFORMANCE_OPTIONS.find(o => o.value === formData.performance)?.label || '—'}
                                    </p>
                                </div>
                            </div>

                            <div className="flex items-center space-x-3">
                                <CheckCircle className="w-5 h-5 text-primary-600 flex-shrink-0" />
                                <div>
                                    <p className="text-xs text-gray-500">Attendance</p>
                                    <p className="font-semibold">{formData.attendance}%</p>
                                </div>
                            </div>

                            <div className="flex items-center space-x-3">
                                <Zap className="w-5 h-5 text-primary-600 flex-shrink-0" />
                                <div>
                                    <p className="text-xs text-gray-500">Motivation Level</p>
                                    <p className="font-semibold">{formData.motivation}/10</p>
                                </div>
                            </div>

                            <div className="flex items-center space-x-3">
                                <BookOpen className="w-5 h-5 text-primary-600 flex-shrink-0" />
                                <div>
                                    <p className="text-xs text-gray-500">Learning Style</p>
                                    <p className="font-semibold capitalize">{formData.learningStyle}</p>
                                </div>
                            </div>

                            <div className="mt-4 p-3 bg-primary-50 rounded-lg text-sm text-primary-700">
                                After profiling, you can upload your syllabus PDFs and we'll extract your subjects automatically.
                            </div>
                        </div>
                    </motion.div>

                    {/* Questionnaire */}
                    <motion.div initial={{ opacity:0, x:20 }} animate={{ opacity:1, x:0 }} className="lg:col-span-2">
                        <div className="card">
                            <h3 className="text-xl font-bold text-gray-800 mb-6">Quick Questionnaire</h3>
                            <form onSubmit={handleSubmit} className="space-y-7">

                                {/* Study Hours */}
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        How many hours do you study per day?&nbsp;
                                        <span className="font-bold text-primary-600">{formData.studyHours}h</span>
                                    </label>
                                    <input type="range" min="1" max="12" step="0.5"
                                        value={formData.studyHours}
                                        onChange={e => setFormData({ ...formData, studyHours: e.target.value })}
                                        className="w-full" />
                                    <div className="flex justify-between text-xs text-gray-400 mt-1">
                                        <span>1h</span><span>6h</span><span>12h</span>
                                    </div>
                                </div>

                                {/* Overall Performance */}
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-3">
                                        How would you describe your overall academic performance?
                                    </label>
                                    <div className="grid sm:grid-cols-2 gap-3">
                                        {PERFORMANCE_OPTIONS.map(opt => (
                                            <label key={opt.value}
                                                className={`flex items-start space-x-3 p-4 rounded-xl border-2 cursor-pointer transition-all ${
                                                    formData.performance === opt.value
                                                        ? 'border-primary-500 bg-primary-50'
                                                        : 'border-gray-200 hover:border-gray-300'
                                                }`}
                                            >
                                                <input type="radio" name="performance" value={opt.value}
                                                    checked={formData.performance === opt.value}
                                                    onChange={e => setFormData({ ...formData, performance: e.target.value })}
                                                    className="mt-1 w-4 h-4 text-primary-600" />
                                                <div>
                                                    <p className="font-semibold text-gray-800">{opt.label}</p>
                                                    <p className="text-xs text-gray-500 mt-0.5">{opt.desc}</p>
                                                </div>
                                            </label>
                                        ))}
                                    </div>
                                </div>

                                {/* Attendance */}
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Attendance rate&nbsp;
                                        <span className="font-bold text-primary-600">{formData.attendance}%</span>
                                    </label>
                                    <input type="range" min="0" max="100" step="5"
                                        value={formData.attendance}
                                        onChange={e => setFormData({ ...formData, attendance: e.target.value })}
                                        className="w-full" />
                                    <div className="flex justify-between text-xs text-gray-400 mt-1">
                                        <span>Low</span><span>Average (75%)</span><span>Perfect</span>
                                    </div>
                                </div>

                                {/* Motivation */}
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        How motivated are you right now?&nbsp;
                                        <span className="font-bold text-primary-600">{formData.motivation}/10</span>
                                    </label>
                                    <input type="range" min="1" max="10"
                                        value={formData.motivation}
                                        onChange={e => setFormData({ ...formData, motivation: e.target.value })}
                                        className="w-full" />
                                    <div className="flex justify-between text-xs text-gray-400 mt-1">
                                        <span>Struggling</span><span>Neutral</span><span>Highly Motivated</span>
                                    </div>
                                </div>

                                {/* Learning Style */}
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-3">
                                        Preferred Learning Style
                                    </label>
                                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                        {[
                                            { value:'visual',      emoji:'👁️', desc:'Diagrams & charts' },
                                            { value:'auditory',    emoji:'🎧', desc:'Listen & discuss' },
                                            { value:'reading',     emoji:'📖', desc:'Notes & textbooks' },
                                            { value:'kinesthetic', emoji:'✍️', desc:'Practice & hands-on' },
                                        ].map(s => (
                                            <label key={s.value}
                                                className={`flex flex-col items-center p-3 rounded-xl border-2 cursor-pointer transition-all text-center ${
                                                    formData.learningStyle === s.value
                                                        ? 'border-primary-500 bg-primary-50'
                                                        : 'border-gray-200 hover:border-gray-300'
                                                }`}
                                            >
                                                <input type="radio" name="learningStyle" value={s.value}
                                                    checked={formData.learningStyle === s.value}
                                                    onChange={e => setFormData({ ...formData, learningStyle: e.target.value })}
                                                    className="sr-only" />
                                                <span className="text-2xl mb-1">{s.emoji}</span>
                                                <span className="font-semibold text-sm capitalize">{s.value}</span>
                                                <span className="text-xs text-gray-400 mt-0.5">{s.desc}</span>
                                            </label>
                                        ))}
                                    </div>
                                </div>

                                {error && <p className="text-red-600 text-sm">{error}</p>}

                                <button type="submit" disabled={loading}
                                    className="btn-primary w-full text-lg py-3 disabled:opacity-60">
                                    {loading ? 'Analysing your profile...' : '✨ Generate My AI Profile'}
                                </button>
                            </form>
                        </div>
                    </motion.div>
                </div>
            </div>

            <Modal isOpen={showModal} onClose={() => setShowModal(false)} title="Profile Generated!">
                <div className="text-center py-6">
                    <div className="w-20 h-20 bg-primary-100 rounded-full flex items-center justify-center mx-auto mb-4">
                        <Brain className="w-10 h-10 text-primary-600" />
                    </div>
                    <h3 className="text-2xl font-bold text-gray-800 mb-2">You are a</h3>
                    <p className="text-3xl font-bold text-primary-600 mb-4">{profileLabel || '...'}</p>
                    <p className="text-gray-600 text-sm">Redirecting to your personalised dashboard...</p>
                </div>
            </Modal>
        </div>
    );
};

export default Profiling;
