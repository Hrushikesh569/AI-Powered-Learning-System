import { useEffect, useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import DashboardLayout from '../layouts/DashboardLayout';
import { agentAPI } from '../api';
import {
    Users, MessageSquare, Heart, Plus, ArrowLeft, Trash2,
    Send, ChevronDown, ChevronUp, RefreshCw, Lightbulb, HelpCircle, MessageCircle,
} from 'lucide-react';

const TAG_STYLES = {
    question:   'bg-yellow-100 text-yellow-800',
    tip:        'bg-green-100 text-green-800',
    discussion: 'bg-blue-100 text-blue-800',
};

const TAG_ICONS = {
    question:   <HelpCircle className="w-3 h-3" />,
    tip:        <Lightbulb className="w-3 h-3" />,
    discussion: <MessageCircle className="w-3 h-3" />,
};

const GROUP_COLORS = [
    'from-purple-500 to-purple-700',
    'from-blue-500 to-blue-700',
    'from-green-500 to-green-700',
    'from-red-500 to-red-700',
    'from-yellow-500 to-orange-600',
];

function timeAgo(iso) {
    if (!iso) return '';
    const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
    if (diff < 60)  return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

function PostCard({ post, onLike, onToggleComments, openComments, onAddComment, onDelete }) {
    const [commentText, setCommentText] = useState('');
    const [comments, setComments]       = useState([]);
    const [loadingComments, setLoadingComments] = useState(false);
    const [posting, setPosting]         = useState(false);

    const loadComments = async () => {
        if (openComments) { onToggleComments(post.id); return; }
        setLoadingComments(true);
        try {
            const res = await agentAPI.getComments(post.id);
            setComments(res.comments || []);
        } catch { /* ignore */ }
        finally { setLoadingComments(false); }
        onToggleComments(post.id);
    };

    const submitComment = async (e) => {
        e.preventDefault();
        if (!commentText.trim()) return;
        setPosting(true);
        try {
            const newComment = await agentAPI.addComment(post.id, { content: commentText });
            setComments(prev => [...prev, newComment]);
            setCommentText('');
            onAddComment(post.id);
        } catch { /* ignore */ }
        finally { setPosting(false); }
    };

    const removeComment = async (commentId) => {
        try {
            await agentAPI.deleteComment(commentId);
            setComments(prev => prev.filter(c => c.id !== commentId));
            onAddComment(post.id);  // reuse to decrement count
        } catch { /* ignore */ }
    };

    return (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className="bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow overflow-hidden">
            <div className="p-4">
                <div className="flex items-start space-x-3">
                    <div className="w-9 h-9 rounded-full bg-gradient-to-br from-primary-500 to-blue-600 flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
                        {(post.author || 'A')[0].toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center space-x-2 flex-wrap">
                            <span className="font-semibold text-gray-900 text-sm">{post.author}</span>
                            <span className={`inline-flex items-center space-x-1 text-xs px-2 py-0.5 rounded-full font-medium ${TAG_STYLES[post.tag] || TAG_STYLES.discussion}`}>
                                {TAG_ICONS[post.tag]}
                                <span className="capitalize">{post.tag}</span>
                            </span>
                            <span className="text-xs text-gray-400 ml-auto">{timeAgo(post.createdAt)}</span>
                        </div>
                        <p className="mt-2 text-gray-800 text-sm leading-relaxed whitespace-pre-wrap">{post.content}</p>
                    </div>
                </div>
            </div>
            <div className="flex items-center space-x-4 px-4 py-2.5 border-t border-gray-50 bg-gray-50">
                <button onClick={() => onLike(post.id)}
                    className="flex items-center space-x-1.5 text-gray-500 hover:text-red-500 transition text-sm">
                    <Heart className={`w-4 h-4 ${post.liked ? 'fill-red-500 text-red-500' : ''}`} />
                    <span>{post.likes}</span>
                </button>
                <button onClick={loadComments}
                    className="flex items-center space-x-1.5 text-gray-500 hover:text-primary-600 transition text-sm">
                    {openComments ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    <MessageSquare className="w-4 h-4" />
                    <span>{post.commentCount} {openComments ? 'Hide' : 'Reply'}</span>
                </button>
                {post.isOwn && onDelete && (
                    <button onClick={() => onDelete(post.id)}
                        className="flex items-center space-x-1 text-gray-400 hover:text-red-500 hover:bg-red-50 transition text-sm ml-auto px-2 py-1 rounded-lg">
                        <Trash2 className="w-4 h-4" />
                    </button>
                )}
            </div>

            <AnimatePresence>
                {openComments && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden border-t border-gray-100">
                        {loadingComments ? (
                            <p className="text-xs text-gray-400 px-5 py-3 animate-pulse">Loading replies...</p>
                        ) : (
                            <div className="px-5 pt-3 pb-2 space-y-3">
                                {comments.map(c => (
                                    <div key={c.id} className="flex items-start space-x-2">
                                        <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center text-xs font-bold text-gray-600 flex-shrink-0">
                                            {(c.author || 'A')[0].toUpperCase()}
                                        </div>
                                        <div className="flex-1 bg-gray-50 rounded-xl px-3 py-2">
                                            <p className="text-xs font-semibold text-gray-700">{c.author}</p>
                                            <p className="text-sm text-gray-800 mt-0.5">{c.content}</p>
                                        </div>
                                        {c.isOwn && (
                                            <button onClick={() => removeComment(c.id)}
                                                className="p-1 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded transition flex-shrink-0 mt-1">
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                        )}
                                    </div>
                                ))}
                                <form onSubmit={submitComment} className="flex items-center space-x-2 pt-1">
                                    <input value={commentText} onChange={e => setCommentText(e.target.value)}
                                        placeholder="Write a reply..."
                                        className="flex-1 text-sm border border-gray-200 rounded-xl px-3 py-2 focus:ring-2 focus:ring-primary-300 outline-none" />
                                    <button type="submit" disabled={posting || !commentText.trim()}
                                        className="p-2 bg-primary-600 text-white rounded-xl hover:bg-primary-700 disabled:opacity-50 transition">
                                        <Send className="w-4 h-4" />
                                    </button>
                                </form>
                            </div>
                        )}
                    </motion.div>
                )}
            </AnimatePresence>
        </motion.div>
    );
}

const Community = () => {
    const [groups, setGroups]             = useState([]);
    const [activeGroup, setActiveGroup]   = useState(null);
    const [feed, setFeed]                 = useState([]);
    const [loadingGroups, setLoadingGroups] = useState(true);
    const [loadingFeed, setLoadingFeed]   = useState(false);
    const [postText, setPostText]         = useState('');
    const [postTag, setPostTag]           = useState('discussion');
    const [posting, setPosting]           = useState(false);
    const [openComments, setOpenComments] = useState({});
    const [error, setError]               = useState('');
    const pollRef                         = useRef(null);

    useEffect(() => {
        const load = async () => {
            setLoadingGroups(true);
            try {
                const res = await agentAPI.listStudyGroups();
                setGroups(res.groups || []);
            } catch { setError('Failed to load groups.'); }
            finally { setLoadingGroups(false); }
        };
        load();
    }, []);

    const enterGroup = async (group) => {
        setActiveGroup(group);
        setFeed([]);
        setOpenComments({});
        loadFeed(group.id);
        // Poll for new posts every 10 s
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = setInterval(() => loadFeed(group.id, true), 10000);
    };

    const leaveGroup = () => {
        setActiveGroup(null);
        setFeed([]);
        if (pollRef.current) clearInterval(pollRef.current);
    };

    useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

    const loadFeed = async (groupId, silent = false) => {
        if (!silent) setLoadingFeed(true);
        try {
            const res = await agentAPI.getGroupFeed(groupId);
            setFeed(res.posts || []);
        } catch { /* ignore polling errors */ }
        finally { if (!silent) setLoadingFeed(false); }
    };

    const handlePost = async (e) => {
        e.preventDefault();
        if (!postText.trim() || !activeGroup) return;
        setPosting(true);
        try {
            const newPost = await agentAPI.createPost(activeGroup.id, { content: postText, tag: postTag });
            setFeed(prev => [{ ...newPost, commentCount: 0 }, ...prev]);
            setPostText('');
        } catch { setError('Could not post. Please try again.'); }
        finally { setPosting(false); }
    };

    const handleLike = async (postId) => {
        try {
            const res = await agentAPI.likePost(postId);
            setFeed(prev => prev.map(p => p.id === postId ? { ...p, likes: res.likes, liked: true } : p));
        } catch { /* ignore */ }
    };

    const toggleComments = (postId) => {
        setOpenComments(prev => ({ ...prev, [postId]: !prev[postId] }));
    };

    const incrementCommentCount = (postId) => {
        // Called both on add (+1) and remove (-1 happens at source)
        // Reload feed silently to get accurate count
        loadFeed(activeGroup?.id, true);
    };

    const handleDelete = async (postId) => {
        try {
            await agentAPI.deletePost(postId);
            setFeed(prev => prev.filter(p => p.id !== postId));
        } catch { /* ignore */ }
    };

    // â”€â”€ Groups List view â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if (!activeGroup) {
        return (
            <DashboardLayout>
                <div className="space-y-6">
                    <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
                        <h1 className="text-3xl font-bold text-gray-900">Community</h1>
                        <p className="text-gray-600 mt-1">Join a study group and connect with peers who share your learning profile.</p>
                    </motion.div>

                    {error && <div className="text-red-600 text-sm">{error}</div>}

                    {loadingGroups ? (
                        <div className="text-center text-primary-600 mt-8 animate-pulse">Loading groups...</div>
                    ) : (
                        <div className="space-y-6">
                            {/* Recommended Group */}
                            {groups.length > 0 && groups[0].isMyGroup && (
                                <div>
                                    <div className="flex items-center space-x-2 mb-4">
                                        <Lightbulb className="w-5 h-5 text-primary-600" />
                                        <h2 className="text-lg font-bold text-gray-900">Recommended For You</h2>
                                    </div>
                                    <motion.div
                                        initial={{ opacity: 0, scale: 0.95 }}
                                        animate={{ opacity: 1, scale: 1 }}
                                        className="bg-white rounded-2xl shadow-md border-2 border-primary-200 overflow-hidden hover:shadow-lg transition-shadow cursor-pointer group"
                                        onClick={() => enterGroup(groups[0])}
                                    >
                                        <div className={`h-32 bg-gradient-to-r ${GROUP_COLORS[groups[0].id % GROUP_COLORS.length]} flex items-center justify-center relative`}>
                                            <Users className="w-14 h-14 text-white opacity-90" />
                                            <div className="absolute top-3 right-3 bg-primary-600 text-white text-xs font-bold px-3 py-1.5 rounded-full">
                                                ⭐ Best Match
                                            </div>
                                        </div>
                                        <div className="p-6">
                                            <h3 className="font-bold text-xl text-gray-900 mb-2">{groups[0].name}</h3>
                                            <p className="text-gray-600 text-sm mb-4">{groups[0].description}</p>
                                            <div className="flex gap-4 text-sm text-gray-500 mb-4">
                                                <span>👥 {groups[0].memberCount || 0} members</span>
                                                <span>💬 {groups[0].postCount || 0} posts</span>
                                            </div>
                                            <button className="w-full py-2.5 bg-primary-600 text-white font-medium rounded-xl hover:bg-primary-700 transition">
                                                Join Group &rarr;
                                            </button>
                                        </div>
                                    </motion.div>
                                </div>
                            )}

                            {/* All Groups */}
                            <div>
                                <h2 className="text-lg font-bold text-gray-900 mb-4">All Study Groups</h2>
                                <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
                                    {groups.map((group, idx) => (
                                        <motion.div key={group.id}
                                            initial={{ opacity: 0, scale: 0.95 }}
                                            animate={{ opacity: 1, scale: 1 }}
                                            transition={{ delay: idx * 0.07 }}
                                            className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden hover:shadow-md transition-shadow cursor-pointer group"
                                            onClick={() => enterGroup(group)}
                                        >
                                            <div className={`h-24 bg-gradient-to-r ${GROUP_COLORS[group.id % GROUP_COLORS.length]} flex items-center justify-center`}>
                                                <Users className="w-10 h-10 text-white opacity-80" />
                                            </div>
                                            <div className="p-4">
                                                <div className="flex items-center justify-between mb-1">
                                                    <h3 className="font-bold text-gray-900">{group.name}</h3>
                                                    {group.isMyGroup && (
                                                        <span className="text-xs bg-primary-100 text-primary-700 px-2 py-0.5 rounded-full font-medium">My Group</span>
                                                    )}
                                                </div>
                                                <p className="text-sm text-gray-500 mb-3">{group.description}</p>
                                                <div className="flex items-center justify-between text-xs text-gray-400">
                                                    <span>{group.memberCount || 0} members</span>
                                                    <span>{group.postCount || 0} posts</span>
                                                </div>
                                                <button className="mt-3 w-full py-2 bg-primary-50 text-primary-700 text-sm font-medium rounded-xl hover:bg-primary-100 transition group-hover:bg-primary-600 group-hover:text-white">
                                                    Enter Group &rarr;
                                                </button>
                                            </div>
                                        </motion.div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Peer Matching Banner */}
                    <div className="card bg-gradient-to-r from-primary-500 to-blue-600 text-white">
                        <div className="flex items-center justify-between">
                            <div>
                                <h2 className="text-xl font-bold mb-1">Find Your Study Buddy</h2>
                                <p className="text-primary-100 text-sm">Get matched with peers who share your schedule and goals.</p>
                            </div>
                            <Users className="w-12 h-12 text-primary-200 flex-shrink-0" />
                        </div>
                    </div>
                </div>
            </DashboardLayout>
        );
    }

    // â”€â”€ Group Feed view â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    return (
        <DashboardLayout>
            <div className="max-w-2xl mx-auto space-y-5">
                <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}
                    className="flex items-center space-x-3">
                    <button onClick={leaveGroup}
                        className="p-2 hover:bg-gray-100 rounded-xl transition text-gray-600">
                        <ArrowLeft className="w-5 h-5" />
                    </button>
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">{activeGroup.name}</h1>
                        <p className="text-sm text-gray-500">{activeGroup.description}</p>
                    </div>
                    <button onClick={() => loadFeed(activeGroup.id)}
                        className="ml-auto p-2 hover:bg-gray-100 rounded-xl transition text-gray-500">
                        <RefreshCw className="w-4 h-4" />
                    </button>
                </motion.div>

                {/* Post Composer */}
                <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
                    <form onSubmit={handlePost} className="space-y-3">
                        <textarea value={postText}
                            onChange={e => setPostText(e.target.value)}
                            placeholder={`Share something with ${activeGroup.name}...`}
                            rows={3}
                            className="w-full text-sm border border-gray-200 rounded-xl px-3 py-2.5 resize-none focus:ring-2 focus:ring-primary-300 outline-none" />
                        <div className="flex items-center justify-between">
                            <div className="flex space-x-2">
                                {['discussion','question','tip'].map(tag => (
                                    <button key={tag} type="button"
                                        onClick={() => setPostTag(tag)}
                                        className={`flex items-center space-x-1 text-xs px-3 py-1.5 rounded-full transition font-medium border ${
                                            postTag === tag
                                                ? `${TAG_STYLES[tag]} border-current`
                                                : 'border-gray-200 text-gray-500 hover:border-gray-300'
                                        }`}>
                                        {TAG_ICONS[tag]}<span className="capitalize">{tag}</span>
                                    </button>
                                ))}
                            </div>
                            <button type="submit" disabled={posting || !postText.trim()}
                                className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-xl hover:bg-primary-700 disabled:opacity-50 transition">
                                {posting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                                <span>Post</span>
                            </button>
                        </div>
                    </form>
                </div>

                {error && <div className="text-red-600 text-sm">{error}</div>}

                {/* Feed */}
                {loadingFeed ? (
                    <div className="text-center text-primary-600 animate-pulse py-8">Loading feed...</div>
                ) : feed.length === 0 ? (
                    <div className="text-center py-16 text-gray-400">
                        <MessageSquare className="w-12 h-12 mx-auto mb-3 text-gray-200" />
                        <p className="font-medium">No posts yet</p>
                        <p className="text-sm mt-1">Be the first to post something in this group!</p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {feed.map(post => (
                            <PostCard key={post.id} post={post}
                                onLike={handleLike}
                                onToggleComments={toggleComments}
                                openComments={!!openComments[post.id]}
                                onAddComment={incrementCommentCount}
                                onDelete={handleDelete} />
                        ))}
                    </div>
                )}
            </div>
        </DashboardLayout>
    );
};

export default Community;
