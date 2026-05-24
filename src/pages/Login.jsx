import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Mail, Lock, Brain } from 'lucide-react';
import { agentAPI, setAuthToken } from '../api';

const Login = () => {
    const navigate = useNavigate();
    const [formData, setFormData] = useState({
        email: '',
        password: '',
    });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const _parseDetail = (err) => {
        const text = err?.message ? String(err.message) : '';
        const match = text.match(/\{"detail":(.*)\}$/s);
        if (!match) return text;
        try {
            const parsed = JSON.parse(text);
            if (typeof parsed.detail === 'string') return parsed.detail;
            if (parsed.detail?.message) return parsed.detail.message;
            return JSON.stringify(parsed.detail);
        } catch {
            return text;
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');
        try {
            const res = await agentAPI.login({
                email: formData.email,
                password: formData.password,
            });

            // Keep UX flowing even when backend auth is in stub mode.
            const token = res?.access_token || res?.token || null;
            if (token) setAuthToken(token);
            
            // Clear old user data and set new user data
            localStorage.removeItem('taskStatuses');
            localStorage.removeItem('preferredTopics');
            localStorage.removeItem('hiddenSubjects');
            localStorage.removeItem('generatedSchedule');
            localStorage.removeItem('learningPreferences');
            localStorage.removeItem('completedSubjects');
            localStorage.removeItem('completedTopics');
            localStorage.removeItem('missedTopics');
            localStorage.removeItem('activityMap');
            localStorage.removeItem('scheduleOverrides');
            localStorage.removeItem('preferredSubjectToday');
            localStorage.setItem('userEmail', formData.email);
            if (res?.name) localStorage.setItem('userName', res.name);

            navigate('/dashboard');
        } catch (_err) {
            const detail = _parseDetail(_err);
            setError(detail || 'Login failed. Please check your credentials and try again.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-primary-50 to-blue-50 flex items-center justify-center px-6">
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-md"
            >
                <div className="text-center mb-8">
                    <div className="flex items-center justify-center space-x-2 mb-4">
                        <Brain className="w-10 h-10 text-primary-600" />
                        <div className="flex flex-col items-start">
                            <span className="inline-flex items-center rounded-full border border-primary-100 bg-primary-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-primary-700 mb-2">
                                Beta
                            </span>
                            <span className="text-3xl font-bold text-gray-800">AI Scheduler</span>
                        </div>
                    </div>

                    <h2 className="text-2xl font-bold text-gray-800">Welcome Back</h2>
                    <p className="text-gray-600 mt-2">Sign in to continue your learning journey</p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-6">
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

                    <div className="flex items-center justify-between">
                        <label className="flex items-center">
                            <input type="checkbox" className="w-4 h-4 text-primary-600 rounded" />
                            <span className="ml-2 text-sm text-gray-600">Remember me</span>
                        </label>
                        <a href="#" className="text-sm text-primary-600 hover:text-primary-700">
                            Forgot password?
                        </a>
                    </div>

                    <button type="submit" className="btn-primary w-full">
                        {loading ? 'Signing In...' : 'Sign In'}
                    </button>

                    {error && <p className="text-sm text-red-600 -mt-2">{error}</p>}

                    <p className="text-xs text-gray-500 text-center">Use your email and password to sign in.</p>
                </form>

                <p className="text-center text-sm text-gray-600 mt-6">
                    Don't have an account?{' '}
                    <Link to="/register" className="text-primary-600 hover:text-primary-700 font-medium">
                        Sign up
                    </Link>
                </p>
            </motion.div>
        </div>
    );
};

export default Login;
