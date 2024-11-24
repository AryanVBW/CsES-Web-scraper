from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from dotenv import load_dotenv
import os
import json
import time
from flask import Flask, jsonify, render_template_string
from pathlib import Path
from datetime import datetime
import random

# Load environment variables
load_dotenv()

# Base directory for all user data
BASE_DATA_DIR = Path("scraped_data")

# HTML template for leaderboard
LEADERBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>CSES Problem Solving Leaderboard</title>
    <style>
        body {
            font-family: 'Arial', sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .leaderboard {
            background: white;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
            padding: 20px;
        }
        .header {
            text-align: center;
            color: #2c3e50;
            margin-bottom: 30px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #3498db;
            color: white;
        }
        tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        tr:hover {
            background-color: #f1f1f1;
        }
        .progress-bar {
            width: 200px;
            height: 20px;
            background-color: #eee;
            border-radius: 10px;
            overflow: hidden;
        }
        .progress {
            height: 100%;
            background-color: #2ecc71;
            transition: width 0.5s ease-in-out;
        }
        .timestamp {
            color: #7f8c8d;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="leaderboard">
        <div class="header">
            <h1>CSES Problem Solving Leaderboard</h1>
            <p>Last updated: {{ timestamp }}</p>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Username</th>
                    <th>Solved Problems</th>
                    <th>Progress</th>
                    <th>Last Updated</th>
                </tr>
            </thead>
            <tbody>
                {% for user in users %}
                <tr>
                    <td>{{ loop.index }}</td>
                    <td>{{ user.username }}</td>
                    <td>{{ user.solved_count }} / {{ user.total_count }}</td>
                    <td>
                        <div class="progress-bar">
                            <div class="progress" style="width: {{ user.progress }}%"></div>
                        </div>
                    </td>
                    <td class="timestamp">{{ user.last_updated }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

def ensure_user_directory(username):
    """Create and return the user's data directory path"""
    user_dir = BASE_DATA_DIR / username
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir

app = Flask(__name__)

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-gpu')
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.implicitly_wait(10)
    return driver

def login_to_cses(driver, wait, username, password):
    """Handle CSES login process"""
    try:
        driver.get("https://cses.fi/login")
        time.sleep(random.uniform(2, 4))  # Random delay
        
        username_field = wait.until(EC.presence_of_element_located((By.NAME, "nick")))
        username_field.clear()
        username_field.send_keys(username)
        
        time.sleep(random.uniform(1, 2))  # Random delay
        
        password_field = wait.until(EC.presence_of_element_located((By.NAME, "pass")))
        password_field.clear()
        password_field.send_keys(password)
        
        time.sleep(random.uniform(1, 2))  # Random delay
        
        submit = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[type="submit"]')))
        submit.click()
        
        time.sleep(random.uniform(3, 5))  # Random delay
        
        if "Login" in driver.title:
            return False, "Login failed. Please check credentials."
        return True, "Login successful"
    except Exception as e:
        return False, f"Login error: {str(e)}"

def scrape_problem_data(driver, wait):
    """Scrape problem set data"""
    try:
        driver.get("https://cses.fi/problemset/list/")  # Changed URL to list view
        time.sleep(random.uniform(3, 5))  # Random delay
        
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "task-list")))
        
        solved_problems = []
        unsolved_problems = []
        
        # Find all task lists (sections)
        task_lists = driver.find_elements(By.CLASS_NAME, "task-list")
        
        for task_list in task_lists:
            try:
                section_name = task_list.find_element(By.TAG_NAME, "h2").text
                problems = task_list.find_elements(By.CLASS_NAME, "task")
                
                for problem in problems:
                    try:
                        problem_link = problem.find_element(By.TAG_NAME, "a")
                        name = problem_link.text
                        href = problem_link.get_attribute("href")
                        
                        # Check for the 'full' class which indicates a solved problem
                        classes = problem.get_attribute("class").split()
                        is_solved = any('full' in class_name for class_name in classes)
                        
                        problem_data = {
                            "name": name,
                            "link": href,
                            "section": section_name,
                            "solved": is_solved
                        }
                        
                        if is_solved:
                            solved_problems.append(problem_data)
                        else:
                            unsolved_problems.append(problem_data)
                            
                    except Exception as e:
                        print(f"Error processing problem: {str(e)}")
                        continue
                        
            except Exception as e:
                print(f"Error processing section: {str(e)}")
                continue
                
        if not solved_problems and not unsolved_problems:
            return False, "No problems found on the page"
            
        return True, {
            "solved": solved_problems,
            "unsolved": unsolved_problems,
            "total_solved": len(solved_problems),
            "total_problems": len(solved_problems) + len(unsolved_problems)
        }
    except Exception as e:
        return False, f"Scraping error: {str(e)}"

@app.route('/scrape/<int:user_number>')
def scrape(user_number=1):
    driver = None
    try:
        driver = setup_driver()
        wait = WebDriverWait(driver, 20)
        
        username_key = f'CF_USERNAME_{user_number}'
        password_key = f'CF_PASSWORD_{user_number}'
        username = os.getenv(username_key)
        password = os.getenv(password_key)
        
        if not username or not password:
            return jsonify({'error': f'User {user_number} credentials not found'}), 404
            
        user_dir = ensure_user_directory(username)
        
        success, message = login_to_cses(driver, wait, username, password)
        if not success:
            return jsonify({'error': message}), 401
            
        success, problems_data = scrape_problem_data(driver, wait)
        if not success:
            return jsonify({'error': problems_data}), 500
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save solved problems
        solved_file = user_dir / f"solved_{timestamp}.json"
        with open(solved_file, 'w', encoding='utf-8') as f:
            json.dump({
                "total_solved": problems_data["total_solved"],
                "problems": problems_data["solved"]
            }, f, indent=4, ensure_ascii=False)
            
        # Save unsolved problems
        unsolved_file = user_dir / f"unsolved_{timestamp}.json"
        with open(unsolved_file, 'w', encoding='utf-8') as f:
            json.dump({
                "total_unsolved": len(problems_data["unsolved"]),
                "problems": problems_data["unsolved"]
            }, f, indent=4, ensure_ascii=False)
            
        # Save stats
        stats = {
            "username": username,
            "timestamp": timestamp,
            "solved_count": problems_data["total_solved"],
            "total_count": problems_data["total_problems"],
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sections": {}
        }
        
        # Calculate section-wise stats
        for problem in problems_data["solved"]:
            section = problem["section"]
            if section not in stats["sections"]:
                stats["sections"][section] = {"solved": 0, "total": 0}
            stats["sections"][section]["solved"] += 1
            
        for problem in problems_data["solved"] + problems_data["unsolved"]:
            section = problem["section"]
            if section not in stats["sections"]:
                stats["sections"][section] = {"solved": 0, "total": 0}
            stats["sections"][section]["total"] += 1
        
        stats_file = user_dir / "stats.json"
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=4, ensure_ascii=False)
        
        return jsonify({
            'status': 'success',
            'message': f'Data saved for user {username}',
            'solved_count': problems_data["total_solved"],
            'total_problems': problems_data["total_problems"],
            'files': {
                'solved': str(solved_file),
                'unsolved': str(unsolved_file),
                'stats': str(stats_file)
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if driver:
            driver.quit()

@app.route('/leaderboard')
def leaderboard():
    try:
        users_data = []
        for user_dir in BASE_DATA_DIR.iterdir():
            if user_dir.is_dir():
                stats_file = user_dir / "stats.json"
                if stats_file.exists():
                    with open(stats_file, 'r', encoding='utf-8') as f:
                        stats = json.load(f)
                        stats['progress'] = (stats['solved_count'] / stats['total_count']) * 100
                        users_data.append(stats)
        
        # Sort users by solved count (descending)
        users_data.sort(key=lambda x: x['solved_count'], reverse=True)
        
        return render_template_string(
            LEADERBOARD_TEMPLATE,
            users=users_data,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(port=3000, debug=True)
