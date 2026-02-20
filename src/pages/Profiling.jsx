import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import Modal from '../components/Modal';
import { Brain, Clock, BookOpen, Zap } from 'lucide-react';

const Profiling = () => {
    const navigate = useNavigate();
    const [showModal, setShowModal] = useState(false);
    const [formData, setFormData] = useState({
        studyHours: 5,
        mathDifficulty: 'medium',
        physicsDifficulty: 'hard',
        chemistryDifficulty: 'easy',
        motivation: 7,
        learningStyle: 'visual',
    });

    const handleSubmit = (e) => {
        e.preventDefault();
        setShowModal(true);
        setTimeout(() => {
            navigate('/dashboard');
        }, 3000);
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-primary-50 to-blue-50 py-12 px-6">
            <div className="max-w-6xl mx-auto">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="text-center mb-12"
                >
                    <Brain className="w-16 h-16 text-primary-600 mx-auto mb-4" />
                    <h1 className="text-4xl font-bold text-gray-900 mb-4">Let's Build Your Profile</h1>
                    <p className="text-lg text-gray-600">Help us understand your learning preferences</p>
                </motion.div>

                <div className="grid lg:grid-cols-3 gap-8">
                    {/* Profile Summary */}
                    <motion.div
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        className="lg:col-span-1"
                    >
                        <div className="card sticky top-8">
                            <h3 className="text-xl font-bold text-gray-800 mb-6">Your Profile</h3>
                            <div className="space-y-4">
                                <div className="flex items-center space-x-3">
                                    <Clock className="w-5 h-5 text-primary-600" />
                                    <div>
                                        <p className="text-sm text-gray-500">Daily Study Time</p>
                                        <p className="font-semibold">{formData.studyHours} hours</p>
                                    </div>
                                </div>
                                <div className="flex items-center space-x-3">
                                    <Zap className="w-5 h-5 text-primary-600" />
                                    <div>
                                        <p className="text-sm text-gray-500">Motivation Level</p>
                                        <p className="font-semibold">{formData.motivation}/10</p>
                                    </div>
                                </div>
                                <div className="flex items-center space-x-3">
                                    <BookOpen className="w-5 h-5 text-primary-600" />
                                    <div>
                                        <p className="text-sm text-gray-500">Learning Style</p>
                                        <p className="font-semibold capitalize">{formData.learningStyle}</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </motion.div>

                    {/* Questionnaire */}
                    <motion.div
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        className="lg:col-span-2"
                    >
                        <div className="card">
                            <h3 className="text-xl font-bold text-gray-800 mb-6">Questionnaire</h3>
                            <form onSubmit={handleSubmit} className="space-y-6">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Daily Study Hours: {formData.studyHours}
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
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Mathematics Difficulty
                                    </label>
                                    <select
                                        value={formData.mathDifficulty}
                                        onChange={(e) => setFormData({ ...formData, mathDifficulty: e.target.value })}
                                        className="input-field"
                                    >
                                        <option value="easy">Easy</option>
                                        <option value="medium">Medium</option>
                                        <option value="hard">Hard</option>
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Physics Difficulty
                                    </label>
                                    <select
                                        value={formData.physicsDifficulty}
                                        onChange={(e) => setFormData({ ...formData, physicsDifficulty: e.target.value })}
                                        className="input-field"
                                    >
                                        <option value="easy">Easy</option>
                                        <option value="medium">Medium</option>
                                        <option value="hard">Hard</option>
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Chemistry Difficulty
                                    </label>
                                    <select
                                        value={formData.chemistryDifficulty}
                                        onChange={(e) => setFormData({ ...formData, chemistryDifficulty: e.target.value })}
                                        className="input-field"
                                    >
                                        <option value="easy">Easy</option>
                                        <option value="medium">Medium</option>
                                        <option value="hard">Hard</option>
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Motivation Level: {formData.motivation}/10
                                    </label>
                                    <input
                                        type="range"
                                        min="1"
                                        max="10"
                                        value={formData.motivation}
                                        onChange={(e) => setFormData({ ...formData, motivation: e.target.value })}
                                        className="w-full"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-3">
                                        Preferred Learning Style
                                    </label>
                                    <div className="space-y-2">
                                        {['visual', 'auditory', 'reading', 'kinesthetic'].map((style) => (
                                            <label key={style} className="flex items-center space-x-3 cursor-pointer">
                                                <input
                                                    type="radio"
                                                    name="learningStyle"
                                                    value={style}
                                                    checked={formData.learningStyle === style}
                                                    onChange={(e) => setFormData({ ...formData, learningStyle: e.target.value })}
                                                    className="w-4 h-4 text-primary-600"
                                                />
                                                <span className="capitalize">{style}</span>
                                            </label>
                                        ))}
                                    </div>
                                </div>

                                <button type="submit" className="btn-primary w-full">
                                    Generate My AI Profile
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
                    <h3 className="text-2xl font-bold text-gray-800 mb-2">You are categorized as:</h3>
                    <p className="text-3xl font-bold text-primary-600 mb-4">Fast Learner</p>
                    <p className="text-gray-600">Redirecting to your personalized dashboard...</p>
                </div>
            </Modal>
        </div>
    );
};

export default Profiling;
