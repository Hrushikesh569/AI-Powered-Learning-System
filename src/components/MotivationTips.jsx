
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { agentAPI, getAuthToken } from '../api';
import { Sparkles } from 'lucide-react';


const MotivationTips = () => {
    const [tips, setTips] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        const fetchTips = async () => {
            setLoading(true);
            setError('');
            try {
                const token = getAuthToken();
                const res = await agentAPI.getMotivationTips(token);
                setTips(res.tips || []);
            } catch (err) {
                setError('Failed to load motivation tips.');
            } finally {
                setLoading(false);
            }
        };
        fetchTips();
    }, []);

    return (
        <div className="card">
            <div className="flex items-center space-x-2 mb-4">
                <Sparkles className="w-6 h-6 text-primary-600" />
                <h2 className="text-xl font-bold text-gray-800">Today&apos;s Study Tip</h2>
            </div>
            {loading && <div className="text-primary-600 text-sm">Loading...</div>}
            {error && <div className="text-red-600 text-sm">{error}</div>}
            {!loading && !error && (() => {
                if (!tips.length) return null;
                // Pick one tip per day using day-of-year as a stable index
                const doy = Math.floor((Date.now() - new Date(new Date().getFullYear(), 0, 0)) / 86400000);
                const item = tips[doy % tips.length];
                const text = typeof item === 'string' ? item : (item.tip || item.text || item.intervention || JSON.stringify(item));
                const icon = typeof item === 'object' ? (item.icon || '\u{1F4A1}') : '\u{1F4A1}';
                const category = typeof item === 'object' ? (item.category || 'Tip') : 'Tip';
                return (
                    <motion.div
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        className="flex items-start space-x-3 p-4 bg-gradient-to-r from-primary-50 to-blue-50 rounded-xl">
                        <span className="text-3xl flex-shrink-0">{icon}</span>
                        <div>
                            <p className="text-xs font-semibold text-primary-600 mb-1 uppercase tracking-wide">{category}</p>
                            <p className="text-sm text-gray-700 leading-relaxed">{text}</p>
                        </div>
                    </motion.div>
                );
            })()}
        </div>
    );
};

export default MotivationTips;
