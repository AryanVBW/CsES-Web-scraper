import express from 'express';
import puppeteer from 'puppeteer';
import dotenv from 'dotenv';
import mongoose from 'mongoose';
import User from './USER.js';

// Load environment variables
dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware to parse JSON
app.use(express.json());

// Add CORS middleware
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept');
    next();
});

// Add error handling middleware
app.use((err, req, res, next) => {
    console.error('Error:', err);
    res.status(500).json({
        error: 'Internal Server Error',
        message: err.message
    });
});

// MongoDB connection with better error handling
const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://localhost:27017/cses_scraper';

console.log('Connecting to MongoDB...');
mongoose.connect(MONGODB_URI)
    .then(() => {
        console.log('Connected to MongoDB successfully');
    })
    .catch((err) => {
        console.error('MongoDB connection error:', err);
        process.exit(1);
    });

// Function to scrape CSES problems
async function scrapeCsesProblems(username, password) {
    console.log(`Starting scraping for user: ${username}`);
    
    const browser = await puppeteer.launch({
        headless: "new",
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    
    const page = await browser.newPage();
    
    try {
        console.log('Going to login page...');
        await page.goto('https://cses.fi/login', { 
            waitUntil: 'networkidle0',
            timeout: 30000
        });

        console.log('Typing credentials...');
        await page.type('#nick', username);
        await page.type('input[type="password"]', password);

        console.log('Submitting login...');
        await Promise.all([
            page.click('input[type="submit"]'),
            page.waitForNavigation({ waitUntil: 'networkidle0', timeout: 30000 })
        ]);

        // Check if login was successful
        const loginError = await page.$('.error');
        if (loginError) {
            throw new Error('Login failed - Invalid credentials');
        }

        console.log('Going to problemset...');
        await page.goto('https://cses.fi/problemset/', {
            waitUntil: 'networkidle0',
            timeout: 30000
        });

        console.log('Waiting for table...');
        await page.waitForSelector('table', { timeout: 30000 });

        console.log('Extracting problems...');
        const problems = await page.evaluate(() => {
            const rows = document.querySelectorAll('table tr');
            const problemList = [];
            let currentSection = 'Unknown';
            
            rows.forEach(row => {
                // Check if this is a section header
                const sectionCell = row.querySelector('td.task-title');
                if (sectionCell && !row.querySelector('a')) {
                    currentSection = sectionCell.textContent.trim();
                    return;
                }

                const link = row.querySelector('a');
                const solved = row.querySelector('span.task-score.icon.full');
                
                if (link) {
                    problemList.push({
                        name: link.textContent.trim(),
                        link: link.href,
                        section: currentSection,
                        solved: !!solved
                    });
                }
            });
            
            return problemList;
        });

        console.log(`Found ${problems.length} problems`);
        
        if (problems.length === 0) {
            throw new Error('No problems found - Possible scraping error');
        }

        return problems;

    } catch (error) {
        console.error('Scraping error:', error);
        throw error;
    } finally {
        await browser.close();
    }
}

// Route to trigger scraping
app.get('/scrape/:userNumber', async (req, res) => {
    console.log(`Received scrape request for user ${req.params.userNumber}`);
    
    const userNumber = req.params.userNumber;
    const username = process.env[`CF_USERNAME_${userNumber}`];
    const password = process.env[`CF_PASSWORD_${userNumber}`];

    if (!username || !password) {
        return res.status(400).json({ 
            error: 'User credentials not found',
            message: `Make sure CF_USERNAME_${userNumber} and CF_PASSWORD_${userNumber} are set in .env file`
        });
    }

    try {
        console.log(`Starting scrape for user: ${username}`);
        const problems = await scrapeCsesProblems(username, password);
        
        // Separate solved and unsolved problems
        const solved = problems.filter(p => p.solved).map(({solved, ...rest}) => rest);
        const unsolved = problems.filter(p => !p.solved).map(({solved, ...rest}) => rest);

        console.log(`Found ${solved.length} solved and ${unsolved.length} unsolved problems`);

        // Update or create user in database
        const user = await User.findOneAndUpdate(
            { username },
            {
                username,
                solved_problems: solved,
                unsolved_problems: unsolved,
                stats: {
                    solved_count: solved.length,
                    total_count: problems.length,
                    last_updated: new Date()
                }
            },
            { upsert: true, new: true }
        );

        res.json({
            username,
            stats: user.stats,
            solved_count: solved.length,
            total_count: problems.length,
            message: 'Scraping completed successfully'
        });

    } catch (error) {
        console.error('Error:', error);
        res.status(500).json({ 
            error: 'Failed to scrape problems',
            message: error.message
        });
    }
});

// Route to get user stats
app.get('/users', async (req, res) => {
    console.log('Received request for users');
    try {
        const users = await User.find({});
        console.log(`Found ${users.length} users`);
        
        if (!users || users.length === 0) {
            return res.json({
                message: 'No users found. Try scraping some data first using /scrape/1 or /scrape/2',
                users: []
            });
        }
        
        res.json({
            message: `Found ${users.length} users`,
            users: users.map(user => ({
                username: user.username,
                stats: user.stats,
                solved_count: user.solved_problems.length,
                total_problems: user.solved_problems.length + user.unsolved_problems.length
            }))
        });
    } catch (error) {
        console.error('Error fetching users:', error);
        res.status(500).json({ 
            error: 'Failed to fetch users',
            message: error.message
        });
    }
});

// Home route
app.get('/', (req, res) => {
    console.log('Received request for home page');
    res.json({
        message: 'CSES Problem Scraper API',
        endpoints: {
            scrape: '/scrape/:userNumber (1 or 2)',
            users: '/users'
        },
        users: {
            1: process.env.CF_USERNAME_1,
            2: process.env.CF_USERNAME_2
        }
    });
});

// Start server only after MongoDB connects
mongoose.connection.once('open', () => {
    app.listen(PORT, () => {
        console.log('='.repeat(50));
        console.log(`Server running on http://localhost:${PORT}`);
        console.log('Available routes:');
        console.log('  - GET /              : Show API info');
        console.log('  - GET /scrape/1      : Scrape problems for user 1');
        console.log('  - GET /scrape/2      : Scrape problems for user 2');
        console.log('  - GET /users         : Get all users data');
        console.log('='.repeat(50));
    });
});