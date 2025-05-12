from flask import Flask, render_template, request, jsonify
from flask_session import Session
from flask import session 
from github import Github
from review_engine import CodeReviewer
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Add session configuration
app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY")
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)  # Initialize server-side sessions

# Initialize reviewer with selected LLM
reviewer = CodeReviewer(os.getenv("LLM_CHOICE", "openai")) 

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/review', methods=['POST'])
def review_code():
    if 'file' in request.files:
        code = request.files['file'].read().decode()
        session['last_code'] = code   # Store the uploaded or fetched code
    elif 'github_url' in request.form:
        g = Github(os.getenv("GITHUB_TOKEN"))
        repo = g.get_repo(request.form['github_url'].strip())
        # Get all files recursively
        contents = repo.get_contents("")
        code = ""
        while contents:
                content_file = contents.pop(0)
                if content_file.type == "dir":
                    # Add subdirectory contents to process
                    contents.extend(repo.get_contents(content_file.path))
                else:
                    # Append file content
                    code += f"\n// File: {content_file.path}\n"
                    code += content_file.decoded_content.decode() + "\n"
    else:
        return jsonify(error="No input provided"), 400
    
    # ✅ Save code in session for Q&A
    session['last_code'] = code

    review = reviewer.generate_review(code)
    suggestions = extract_code_blocks(review)
    # return jsonify(review=review)
    return jsonify({
        "review": review,
        "code_suggestions": suggestions
    })

@app.route('/pull_request_review', methods=['POST'])
def pull_request_review():
    if not session.get('authenticated'):
        return jsonify(error="Unauthorized"), 401
    data = request.json
    repo_name = data.get('repo_name')
    pr_number = data.get('pr_number')

    if not repo_name or not pr_number:
        return jsonify(error="Repository name and pull request number are required"), 400

    try:
        # Authenticate with GitHub
        g = Github(os.getenv("GITHUB_TOKEN"))
        repo = g.get_repo(repo_name)
        pull_request = repo.get_pull(int(pr_number))

        # Fetch the pull request diff
        files = pull_request.get_files()
        code_diff = ""
        for file in files:
            code_diff += f"\n// File: {file.filename}\n{file.patch}\n"

        # Generate review comments
        reviewer = CodeReviewer(os.getenv("LLM_CHOICE"))
        review_comments = reviewer.generate_review(code_diff)

        # Post comments to the pull request
        for comment in review_comments.split("\n\n"):
            pull_request.create_review_comment(body=comment, commit_id=pull_request.head.sha, path=file.filename, position=1)

        return jsonify(message="Review comments posted successfully")
    except Exception as e:
        return jsonify(error=str(e)), 500

# New endpoint for interactive Q&A
@app.route('/chat', methods=['POST'])
def handle_chat():
    data = request.json
    code_diff = data.get('code_diff', '').strip() or session.get('last_code', '')
    question = data.get('message', '').strip()
    
    # Initialize session-based conversation history
    if 'conversation' not in session:
        session['conversation'] = []
    
    reviewer = CodeReviewer(os.getenv("LLM_CHOICE"))
    
    try:
        # Get validated response
        response = reviewer.get_response(
            question=question,
            code_diff=code_diff,
            conversation_history=session['conversation']
        )
        
        # Extract suggested code blocks
        code_suggestions = extract_code_blocks(response)
        
        # Update conversation history (last 3 exchanges)
        session['conversation'].extend([
            {"role": "user", "content": question},
            {"role": "assistant", "content": response}
        ][-6:])  # Keep last 3 pairs
        
        return jsonify({
            "response": response,
            "code_suggestions": code_suggestions
        })
    except Exception as e:
        return jsonify(error=str(e)), 500

def extract_code_blocks(text):
    """Extract Markdown code blocks from response"""
    import re
    return re.findall(r"```(?:[\w+]*\n)?(.*?)```", text, re.DOTALL)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860)
