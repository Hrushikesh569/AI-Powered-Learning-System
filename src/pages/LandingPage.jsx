import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { Brain, Calendar, Zap, Users, ArrowRight, CheckCircle } from 'lucide-react';

const LandingPage = () => {
    const features = [
        {
            icon: Brain,
            title: 'Intelligent Profiling',
            description: 'AI analyzes your learning style and creates a personalized study profile',
        },
        {
            icon: Calendar,
            title: 'Smart Scheduling',
            description: 'Automatically generates optimal study schedules based on your goals',
        },
        {
            icon: Zap,
            title: 'Adaptive Rescheduling',
            description: 'Dynamically adjusts your schedule when you miss sessions',
        },
        {
            icon: Users,
            title: 'Community Learning',
            description: 'Connect with study groups and peers for collaborative learning',
        },
    ];

    const steps = [
        { number: '01', title: 'Complete Profile', description: 'Tell us about your learning goals and preferences' },
        { number: '02', title: 'Get AI Schedule', description: 'Receive your personalized study plan' },
        { number: '03', title: 'Track Progress', description: 'Monitor your growth and achievements' },
    ];

    return (
        <div className="min-h-screen bg-gradient-to-br from-primary-50 via-white to-blue-50">
            {/* Navbar */}
            <nav className="fixed top-0 w-full bg-white/80 backdrop-blur-md shadow-sm z-50">
                <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
                    <div className="flex items-center space-x-2">
                        <Brain className="w-8 h-8 text-primary-600" />
                        <span className="text-2xl font-bold text-gray-800">AI Scheduler</span>
                    </div>
                    <div className="flex space-x-4">
                        <Link to="/login" className="px-6 py-2 text-primary-600 hover:text-primary-700 font-medium">
                            Login
                        </Link>
                        <Link to="/register" className="btn-primary">
                            Get Started
                        </Link>
                    </div>
                </div>
            </nav>

            {/* Hero Section */}
            <section className="pt-32 pb-20 px-6">
                <div className="max-w-7xl mx-auto text-center">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.6 }}
                    >
                        <h1 className="text-6xl font-bold text-gray-900 mb-6">
                            Your AI-Powered Personal
                            <span className="text-primary-600"> Study Mentor</span>
                        </h1>
                        <p className="text-xl text-gray-600 mb-8 max-w-3xl mx-auto">
                            Transform your learning journey with intelligent scheduling, adaptive planning,
                            and a supportive community. Let AI optimize your study time.
                        </p>
                        <div className="flex justify-center space-x-4">
                            <Link to="/register" className="btn-primary flex items-center space-x-2">
                                <span>Get Started Free</span>
                                <ArrowRight className="w-5 h-5" />
                            </Link>
                            <Link to="/login" className="btn-secondary">
                                Sign In
                            </Link>
                        </div>
                    </motion.div>
                </div>
            </section>

            {/* Features Section */}
            <section className="py-20 px-6 bg-white">
                <div className="max-w-7xl mx-auto">
                    <div className="text-center mb-16">
                        <h2 className="text-4xl font-bold text-gray-900 mb-4">Powerful Features</h2>
                        <p className="text-lg text-gray-600">Everything you need for effective learning</p>
                    </div>
                    <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
                        {features.map((feature, index) => (
                            <motion.div
                                key={index}
                                initial={{ opacity: 0, y: 20 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                transition={{ delay: index * 0.1 }}
                                className="card text-center"
                            >
                                <div className="w-16 h-16 bg-primary-100 rounded-full flex items-center justify-center mx-auto mb-4">
                                    <feature.icon className="w-8 h-8 text-primary-600" />
                                </div>
                                <h3 className="text-xl font-semibold text-gray-800 mb-2">{feature.title}</h3>
                                <p className="text-gray-600">{feature.description}</p>
                            </motion.div>
                        ))}
                    </div>
                </div>
            </section>

            {/* How It Works */}
            <section className="py-20 px-6">
                <div className="max-w-7xl mx-auto">
                    <div className="text-center mb-16">
                        <h2 className="text-4xl font-bold text-gray-900 mb-4">How It Works</h2>
                        <p className="text-lg text-gray-600">Get started in three simple steps</p>
                    </div>
                    <div className="grid md:grid-cols-3 gap-12">
                        {steps.map((step, index) => (
                            <motion.div
                                key={index}
                                initial={{ opacity: 0, x: -20 }}
                                whileInView={{ opacity: 1, x: 0 }}
                                transition={{ delay: index * 0.2 }}
                                className="relative"
                            >
                                <div className="text-6xl font-bold text-primary-100 mb-4">{step.number}</div>
                                <h3 className="text-2xl font-semibold text-gray-800 mb-2">{step.title}</h3>
                                <p className="text-gray-600">{step.description}</p>
                                {index < steps.length - 1 && (
                                    <ArrowRight className="hidden md:block absolute top-8 -right-6 w-8 h-8 text-primary-300" />
                                )}
                            </motion.div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Footer */}
            <footer className="bg-gray-900 text-white py-12 px-6">
                <div className="max-w-7xl mx-auto text-center">
                    <div className="flex items-center justify-center space-x-2 mb-4">
                        <Brain className="w-8 h-8 text-primary-400" />
                        <span className="text-2xl font-bold">AI Scheduler</span>
                    </div>
                    <p className="text-gray-400 mb-4">Your Personal Study Mentor</p>
                    <p className="text-sm text-gray-500">© 2026 AI Scheduler. All rights reserved.</p>
                </div>
            </footer>
        </div>
    );
};

export default LandingPage;
