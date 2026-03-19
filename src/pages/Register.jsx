import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Mail, Lock, User, Target, Brain } from 'lucide-react';
import { agentAPI, setAuthToken } from '../api';

const Register = () => {
    const navigate = useNavigate();
    const [formData, setFormData] = useState({
        name: '',
        email: '',
        password: '',
        confirmPassword: '',
        studyHours: 5,
        learningGoal: '',
        grade: '',
        course: '',
    });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (formData.password !== formData.confirmPassword) {
            setError('Passwords do not match.');
            return;
        }

        setLoading(true);
        setError('');
        try {
            const res = await agentAPI.register({
                name: formData.name,
                email: formData.email,
                password: formData.password,
                studyHoursPerDay: Number(formData.studyHours),
                learningGoal: formData.learningGoal,
                grade: formData.grade,
                course: formData.course,
            });

            // Store JWT from response
            setAuthToken(res.access_token);
            
            // Clear old user data
            localStorage.removeItem('taskStatuses');
            localStorage.removeItem('preferredTopics');
            localStorage.removeItem('hiddenSubjects');
            localStorage.removeItem('generatedSchedule');
            localStorage.removeItem('completedSubjects');
            localStorage.removeItem('completedTopics');
            localStorage.removeItem('missedTopics');
            localStorage.removeItem('activityMap');
            localStorage.removeItem('scheduleOverrides');
            localStorage.removeItem('preferredSubjectToday');
            
            // Set new user data
            localStorage.setItem('userName', res.name || formData.name);
            localStorage.setItem('userEmail', res.email || formData.email);
            localStorage.setItem(
                'learningPreferences',
                JSON.stringify({
                    studyHours: Number(formData.studyHours),
                    learningGoal: formData.learningGoal,
                    grade: formData.grade,
                    course: formData.course,
                }),
            );

            navigate('/profiling');
        } catch (_err) {
            setError('Registration failed. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-primary-50 to-blue-50 flex items-center justify-center px-6 py-12">
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-md"
            >
                <div className="text-center mb-8">
                    <div className="flex items-center justify-center space-x-2 mb-4">
                        <Brain className="w-10 h-10 text-primary-600" />
                        <span className="text-3xl font-bold text-gray-800">AI Scheduler</span>
                    </div>
                    <h2 className="text-2xl font-bold text-gray-800">Create Account</h2>
                    <p className="text-gray-600 mt-2">Start your personalized learning journey</p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">Full Name</label>
                        <div className="relative">
                            <User className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                            <input
                                type="text"
                                value={formData.name}
                                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                className="input-field pl-10"
                                placeholder="John Doe"
                                required
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
                                placeholder="your.email@example.com"
                                required
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">Password</label>
                        <div className="relative">
                            <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                            <input
                                type="password"
                                value={formData.password}
                                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                                className="input-field pl-10"
                                placeholder="••••••••"
                                required
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">Confirm Password</label>
                        <div className="relative">
                            <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                            <input
                                type="password"
                                value={formData.confirmPassword}
                                onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                                className="input-field pl-10"
                                placeholder="••••••••"
                                required
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Study Hours Per Day: {formData.studyHours}
                        </label>
                        <input
                            type="range"
                            min="1"
                            max="12"
                            value={formData.studyHours}
                            onChange={(e) => setFormData({ ...formData, studyHours: e.target.value })}
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
                            placeholder="e.g., 10, 12, B.Tech Year 2"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">Course / Stream</label>
                        <input
                            type="text"
                            value={formData.course}
                            onChange={(e) => setFormData({ ...formData, course: e.target.value })}
                            className="input-field"
                            placeholder="e.g., Computer Science, Engineering"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">Learning Goal</label>
                        <div className="relative">
                            <Target className="absolute left-3 top-3 w-5 h-5 text-gray-400" />
                            <textarea
                                value={formData.learningGoal}
                                onChange={(e) => setFormData({ ...formData, learningGoal: e.target.value })}
                                className="input-field pl-10 min-h-[80px]"
                                placeholder="What do you want to achieve?"
                                required
                            />
                        </div>
                    </div>

                    <button type="submit" className="btn-primary w-full">
                        {loading ? 'Creating Account...' : 'Create Account'}
                    </button>

                    {error && <p className="text-sm text-red-600">{error}</p>}
                </form>

                <p className="text-center text-sm text-gray-600 mt-6">
                    Already have an account?{' '}
                    <Link to="/login" className="text-primary-600 hover:text-primary-700 font-medium">
                        Sign in
                    </Link>
                </p>
            </motion.div>
        </div>
    );
};

export default Register;
