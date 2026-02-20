import { motion } from 'framer-motion';
import DashboardLayout from '../layouts/DashboardLayout';
import { studyGroups, forumPosts } from '../data/mockData';
import { Users, MessageSquare, ThumbsUp, Plus, Search } from 'lucide-react';

const Community = () => {
    return (
        <DashboardLayout>
            <div className="space-y-6">
                <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
                    <h1 className="text-3xl font-bold text-gray-900">Community</h1>
                    <p className="text-gray-600 mt-1">Connect with fellow learners</p>
                </motion.div>

                {/* Study Groups */}
                <div className="card">
                    <div className="flex items-center justify-between mb-6">
                        <h2 className="text-xl font-bold text-gray-800">Suggested Study Groups</h2>
                        <button className="btn-primary flex items-center space-x-2">
                            <Plus className="w-4 h-4" />
                            <span>Create Group</span>
                        </button>
                    </div>
                    <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {studyGroups.map((group, index) => (
                            <motion.div
                                key={group.id}
                                initial={{ opacity: 0, scale: 0.95 }}
                                animate={{ opacity: 1, scale: 1 }}
                                transition={{ delay: index * 0.1 }}
                                className="p-4 bg-gradient-to-br from-primary-50 to-blue-50 rounded-lg border border-primary-100 hover:shadow-md transition-shadow"
                            >
                                <div className="flex items-start justify-between mb-3">
                                    <div className="w-12 h-12 bg-primary-600 rounded-lg flex items-center justify-center">
                                        <Users className="w-6 h-6 text-white" />
                                    </div>
                                    <span className="text-xs bg-white px-2 py-1 rounded-full text-gray-600">
                                        {group.members} members
                                    </span>
                                </div>
                                <h3 className="font-semibold text-gray-800 mb-2">{group.name}</h3>
                                <p className="text-sm text-gray-600 mb-3">{group.description}</p>
                                <div className="flex items-center justify-between">
                                    <span className="text-xs text-gray-500">{group.nextSession}</span>
                                    <button className="px-3 py-1 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 transition-colors">
                                        Join
                                    </button>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </div>

                {/* Discussion Forum */}
                <div className="card">
                    <div className="flex items-center justify-between mb-6">
                        <h2 className="text-xl font-bold text-gray-800">Discussion Forum</h2>
                        <div className="flex space-x-3">
                            <div className="relative">
                                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                                <input
                                    type="text"
                                    placeholder="Search discussions..."
                                    className="pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                                />
                            </div>
                            <button className="btn-primary flex items-center space-x-2">
                                <Plus className="w-4 h-4" />
                                <span>New Post</span>
                            </button>
                        </div>
                    </div>

                    <div className="space-y-4">
                        {forumPosts.map((post, index) => (
                            <motion.div
                                key={post.id}
                                initial={{ opacity: 0, x: -20 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: index * 0.1 }}
                                className="p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                            >
                                <div className="flex items-start space-x-4">
                                    <div className="w-12 h-12 bg-primary-600 rounded-full flex items-center justify-center text-white font-bold flex-shrink-0">
                                        {post.avatar}
                                    </div>
                                    <div className="flex-1">
                                        <div className="flex items-center justify-between mb-2">
                                            <div>
                                                <h3 className="font-semibold text-gray-800">{post.title}</h3>
                                                <p className="text-sm text-gray-600">
                                                    by {post.author} • {post.timeAgo}
                                                </p>
                                            </div>
                                        </div>
                                        <p className="text-gray-700 mb-3">{post.content}</p>
                                        <div className="flex items-center space-x-4">
                                            <button className="flex items-center space-x-1 text-gray-600 hover:text-primary-600 transition-colors">
                                                <ThumbsUp className="w-4 h-4" />
                                                <span className="text-sm">{post.upvotes}</span>
                                            </button>
                                            <button className="flex items-center space-x-1 text-gray-600 hover:text-primary-600 transition-colors">
                                                <MessageSquare className="w-4 h-4" />
                                                <span className="text-sm">{post.comments} comments</span>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </div>

                {/* Peer Matching */}
                <div className="card bg-gradient-to-r from-primary-500 to-blue-600 text-white">
                    <div className="flex items-center justify-between">
                        <div>
                            <h2 className="text-2xl font-bold mb-2">Find Your Study Buddy</h2>
                            <p className="text-primary-100">
                                Get matched with peers who share your learning goals and schedule
                            </p>
                        </div>
                        <button className="px-6 py-3 bg-white text-primary-600 rounded-lg font-medium hover:bg-primary-50 transition-colors">
                            Start Matching
                        </button>
                    </div>
                </div>
            </div>
        </DashboardLayout>
    );
};

export default Community;
