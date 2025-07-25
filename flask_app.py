from flask import Flask, render_template, request
import os, re
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from langchain.chains import create_sql_query_chain
from langchain_google_genai import GoogleGenerativeAI
from langchain_community.utilities.sql_database import SQLDatabase
from dotenv import load_dotenv

# --- Load env and init Flask ---
load_dotenv()
app = Flask(__name__)

# --- DB connection ---
db_user = "root"
db_password = quote_plus("your_password")
db_host = "localhost"
db_name = "chinook"
engine = create_engine(f"mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_name}")
db = SQLDatabase(engine, sample_rows_in_table_info=3)

# --- LLM setup ---
llm = GoogleGenerativeAI(model="gemini-2.5-pro", google_api_key=os.environ["GOOGLE_API_KEY"])
sql_chain = create_sql_query_chain(llm, db)

def execute_query(question):
    try:
        response = sql_chain.invoke({"question": question}).strip()
        match = re.search(r"(SELECT[\s\S]+?;)", response, re.IGNORECASE)
        if not match:
            return None, None, "Could not extract SQL query."
        cleaned_query = match.group(1).strip()

        with engine.connect() as conn:
            result_proxy = conn.execute(text(cleaned_query))
            rows = result_proxy.fetchall()
            columns = result_proxy.keys()

        result_data = [dict(zip(columns, row)) for row in rows]
        return cleaned_query, result_data, None
    except Exception as e:
        return None, None, str(e)

def format_result_to_markdown(result_list):
    if not result_list:
        return "No data found."
    headers = result_list[0].keys()
    md = "| " + " | ".join(headers) + " |\n"
    md += "| " + " | ".join(["---"] * len(headers)) + " |\n"
    for row in result_list:
        md += "| " + " | ".join(str(v) for v in row.values()) + " |\n"
    return md

def generate_summary(question, result_data):
    try:
        result_md = format_result_to_markdown(result_data)
        prompt = f"""
        You are a helpful assistant. A user asked:

        '{question}'

        Here is the result of the SQL query:

        {result_md}

        Please provide a clear and concise explanation in plain English.
        """
        return llm.invoke(prompt).strip()
    except Exception as e:
        return f"❌ Summary error: {e}"

# --- Routes ---
@app.route("/", methods=["GET", "POST"])
def index():
    question, sql_query, result_data, summary, error = "", "", [], "", ""
    if request.method == "POST":
        question = request.form["question"]
        sql_query, result_data, error = execute_query(question)
        if result_data:
            summary = generate_summary(question, result_data)
    return render_template("index.html", question=question, sql_query=sql_query, result=result_data, summary=summary, error=error)

# --- Run app ---
if __name__ == "__main__":
    app.run(debug=True)