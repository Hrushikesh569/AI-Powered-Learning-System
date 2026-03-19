import { motion } from 'framer-motion';

const ICON_MAP = {
    fire: '🔥',
    star: '⭐',
    trophy: '🏆',
    award: '🎖️',
    target: '🎯',
    lightbulb: '💡',
    book: '📚',
    check: '✅',
    rocket: '🚀',
    heart: '❤️',
};

const resolveIcon = (icon) => ICON_MAP[icon?.toLowerCase()] || icon || '🏅';

const AchievementCard = ({ achievement }) => {
    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            whileHover={{ scale: 1.05 }}
            className={`p-4 rounded-lg border-2 transition-all ${achievement.unlocked
                ? 'bg-gradient-to-br from-yellow-50 to-orange-50 border-yellow-300'
                : 'bg-gray-50 border-gray-200 opacity-60'
                }`}
        >
            <div className="flex items-start justify-between mb-2">
                <span className="text-3xl">{resolveIcon(achievement.icon)}</span>
                {achievement.unlocked && (
                    <span className="text-xs bg-green-500 text-white px-2 py-1 rounded-full">
                        Unlocked
                    </span>
                )}
            </div>
            <h3 className="font-semibold text-gray-800 mb-1">{achievement.title}</h3>
            <p className="text-sm text-gray-600 mb-2">{achievement.description}</p>
            {achievement.unlocked ? (
                achievement.unlockedDate && (
                    <p className="text-xs text-gray-500">
                        Unlocked on {new Date(achievement.unlockedDate).toLocaleDateString()}
                    </p>
                )
            ) : (
                achievement.progress !== undefined && (
                    <div>
                        <div className="flex justify-between text-xs text-gray-600 mb-1">
                            <span>Progress</span>
                            <span>{achievement.progress}/{achievement.total}</span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2">
                            <div
                                className="bg-primary-600 h-2 rounded-full transition-all"
                                style={{ width: `${(achievement.progress / achievement.total) * 100}%` }}
                            ></div>
                        </div>
                    </div>
                )
            )}
        </motion.div>
    );
};

export default AchievementCard;
