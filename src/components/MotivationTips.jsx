import { motion } from 'framer-motion';
import { motivationTips } from '../data/mockData';
import { Sparkles } from 'lucide-react';

const MotivationTips = () => {
    return (
        <div className="card">
            <div className="flex items-center space-x-2 mb-4">
                <Sparkles className="w-6 h-6 text-primary-600" />
                <h2 className="text-xl font-bold text-gray-800">Study Tips</h2>
            </div>
            <div className="space-y-3">
                {motivationTips.map((item, index) => (
                    <motion.div
                        key={item.id}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.1 }}
                        className="flex items-start space-x-3 p-3 bg-gradient-to-r from-primary-50 to-blue-50 rounded-lg"
                    >
                        <span className="text-2xl flex-shrink-0">{item.icon}</span>
                        <div>
                            <p className="text-xs font-semibold text-primary-600 mb-1">
                                {item.category}
                            </p>
                            <p className="text-sm text-gray-700">{item.tip}</p>
                        </div>
                    </motion.div>
                ))}
            </div>
        </div>
    );
};

export default MotivationTips;
