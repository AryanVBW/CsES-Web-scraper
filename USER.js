import mongoose from 'mongoose';

const userSchema = new mongoose.Schema({
    username: String,
    solved_problems: [{
        name: String,
        link: String,
        section: String,
        timestamp: { type: Date, default: Date.now }
    }],
    unsolved_problems: [{
        name: String,
        link: String,
        section: String
    }],
    stats: {
        solved_count: { type: Number, default: 0 },
        total_count: { type: Number, default: 0 },
        last_updated: { type: Date, default: Date.now }
    }
});

export default mongoose.model('User', userSchema);
