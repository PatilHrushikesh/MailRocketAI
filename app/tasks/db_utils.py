import sqlite3
import json
import logging
from datetime import datetime
from tabulate import tabulate
import shutil
import os

# Configure logging
logging.basicConfig(level=logging.INFO,
					format='%(asctime)s - %(levelname)s - %(message)s')

linkedin_db_path = os.path.join(
	os.path.dirname(os.path.abspath(__file__)),
	"linkedin_posts.db"
)
print(linkedin_db_path)


def init_db(db_path=linkedin_db_path):
	"""
	Initialize the database with IST timestamp support and relationships.
	"""
	conn = sqlite3.connect(db_path)
	cursor = conn.cursor()
	cursor.execute("PRAGMA foreign_keys = ON;")

	cursor.execute("""
	CREATE TABLE IF NOT EXISTS linkedin_posts (
		uid INTEGER PRIMARY KEY AUTOINCREMENT,
		query TEXT,
		author_name TEXT,
		profile_url TEXT,
		post_link TEXT NOT NULL UNIQUE,
		post_text TEXT,
		post_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
		analysed BOOLEAN NOT NULL DEFAULT 0,
		other_data JSON,
		inserted_at TEXT DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%f', 'NOW', '+5 hours', '30 minutes'))
	);
	""")

	logging.info("Table 'linkedin_posts' created if not exists successfully.")

	cursor.execute("""
	CREATE TABLE IF NOT EXISTS post_analysis (
		analysis_id INTEGER PRIMARY KEY AUTOINCREMENT,
		post_uid INTEGER NOT NULL,
		experience_gap INTEGER,
		match_percentage INTEGER,
		contact_email TEXT,
		contact_number TEXT,
		application_link TEXT,
		company_name TEXT,
		should_apply BOOLEAN,
		subject TEXT,
		body TEXT,
		mail_sent INTEGER NOT NULL DEFAULT -1 CHECK (mail_sent IN (-1, 0, 1)),
		final_decision BOOLEAN NOT NULL DEFAULT 0,
		full_analysis_json JSON,
		model_used TEXT,
		inserted_at TEXT DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%f', 'NOW', '+5 hours', '30 minutes')),
		FOREIGN KEY (post_uid) REFERENCES linkedin_posts(uid) ON DELETE CASCADE
	);
	""")

	logging.info("Table 'post_analysis' created if not exists successfully.")
	conn.commit()
	cursor.close()
	conn.close()

def check_post_exists(post_link, db_path=linkedin_db_path):
	conn = sqlite3.connect(db_path)
	cursor = conn.cursor()
	cursor.execute("PRAGMA foreign_keys = ON;")

	try:
		cursor.execute("SELECT uid FROM linkedin_posts WHERE post_link = ?", (post_link,))
		uid = cursor.fetchone()
		return uid is not None
	except sqlite3.Error as error:
		logging.error("Database error checking post existence: %s", error)
		raise
	finally:
		cursor.close()
		conn.close()


def migrate_post_analysis_schema(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = OFF;")
    try:
        cursor.execute("BEGIN TRANSACTION;")

        # 1. Rename the existing table
        cursor.execute(
            "ALTER TABLE post_analysis RENAME TO post_analysis_old;")

        # 2. Create the new table with the updated schema
        cursor.execute("""
            CREATE TABLE post_analysis (
                analysis_id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_uid INTEGER NOT NULL,
                experience_gap INTEGER,
                match_percentage INTEGER,
                contact_email TEXT,
                contact_number TEXT,
                application_link TEXT,
                company_name TEXT,
                should_apply BOOLEAN,
                subject TEXT,
                body TEXT,
                mail_sent INTEGER NOT NULL DEFAULT -1 CHECK (mail_sent IN (-1, 0, 1)),
                full_analysis_json JSON,
                model_used TEXT,
                inserted_at TEXT DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%f', 'NOW', '+5 hours', '30 minutes')),
                FOREIGN KEY (post_uid) REFERENCES linkedin_posts(uid) ON DELETE CASCADE
            );
        """)

        # 3. Copy data from the old table to the new table, transforming mail_sent values
        cursor.execute("""
            INSERT INTO post_analysis (
                analysis_id, post_uid, experience_gap, match_percentage,
                contact_email, contact_number, application_link, company_name,
                should_apply, subject, body, mail_sent,
                full_analysis_json, model_used, inserted_at
            )
            SELECT
                analysis_id, post_uid, experience_gap, match_percentage,
                contact_email, contact_number, application_link, company_name,
                should_apply, subject, body,
                CASE mail_sent
                    WHEN 0 THEN -1
                    ELSE mail_sent
                END AS mail_sent,
                full_analysis_json, model_used, inserted_at
            FROM post_analysis_old;
        """)

        # 4. Drop the old table
        cursor.execute("DROP TABLE post_analysis_old;")

        cursor.execute("COMMIT;")
        logging.info("Schema migration completed successfully.")
    except sqlite3.Error as e:
        cursor.execute("ROLLBACK;")
        logging.error(f"Schema migration failed: {e}")
        raise
    finally:
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.close()
        conn.close()



def read_linkedin_posts(db_path, filters=None):

    if filters is None:
        filters = {}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        base_query = "SELECT * FROM linkedin_posts"
        conditions = []
        values = []

        for column, value in filters.items():
            conditions.append(f"{column} = ?")
            values.append(value)

        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)
            final_query = base_query + where_clause
        else:
            final_query = base_query

        cursor.execute(final_query, values)
        rows = cursor.fetchall()

        posts = [dict(row) for row in rows]

        return posts

    except sqlite3.Error as error:
        print("Error reading from database:", error)
        return []
    finally:
        cursor.close()
        conn.close()


def insert_linkedin_post(data, db_path=linkedin_db_path):
	conn = sqlite3.connect(db_path)
	cursor = conn.cursor()
	cursor.execute("PRAGMA foreign_keys = ON;")

	search_query = data.get("query")
	post_link = data.get("post_link")
	author_name = data.get("author_name")
	profile_url = data.get("profile_url")
	post_text = data.get("post_text")
	data["post_date"] = data.get("post_date").isoformat()
	post_date = data["post_date"]
	other_data_json = json.dumps(data)

	try:
		query = """
		INSERT INTO linkedin_posts (query, post_link, post_text, post_date, author_name, profile_url, other_data)
			VALUES (?, ?, ?, ?, ?, ?, ?); --INSERT INTO linkedin_posts (query, post_link, post_text, post_date,author_name, profile_url, other_data)
		"""
		cursor.execute(query, (search_query, post_link, post_text,
						post_date, author_name, profile_url,other_data_json))
		conn.commit()
		uid = cursor.lastrowid
		logging.info("Post inserted successfully with uid: %d", uid)
		return uid
	except sqlite3.IntegrityError as e:
		conn.rollback()
		logging.error("Integrity error (likely duplicate post_link): %s", e)
		raise sqlite3.IntegrityError(
			f"Duplicate post_link '{post_link}' detected") from e
	except sqlite3.Error as error:
		conn.rollback()
		logging.error("Database error inserting post: %s", error)
		raise
	finally:
		cursor.close()
		conn.close()


def insert_post_analysis(post_uid, analysis_data_list, model_used=None, db_path=linkedin_db_path):
	"""
	Insert multiple analysis records for a LinkedIn post into the database
	and mark the corresponding post as analysed.
	"""
	if not isinstance(analysis_data_list, list):
		raise ValueError("analysis_data must be a list of dictionaries.")

	conn = sqlite3.connect(db_path)
	cursor = conn.cursor()
	cursor.execute("PRAGMA foreign_keys = ON;")

	try:
		for analysis_data in analysis_data_list:
			query = """
			INSERT INTO post_analysis (
				post_uid,
				match_percentage,
				experience_gap,
				contact_email,
				contact_number,
				application_link,
				company_name,
				should_apply,
				subject,
				body,
				mail_sent,
				full_analysis_json,
				model_used
			) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
			"""
			if not model_used:
				model_used = analysis_data.get("model_name", "unknown")

			cursor.execute(query, (
				post_uid,
				analysis_data.get("match_percentage"),
				analysis_data.get("experience_gap"),
				json.dumps(analysis_data.get("contact_email")),
				json.dumps(analysis_data.get("contact_number")),
				json.dumps(analysis_data.get("application_link")),
				analysis_data.get("company_name"),
				analysis_data.get("should_apply"),
				analysis_data.get("message_content", {}).get("subject"),
				analysis_data.get("message_content", {}).get("body"),
				-1,
				json.dumps(analysis_data),
				model_used
			))

		# Mark the post as analysed
		update_query = "UPDATE linkedin_posts SET analysed = 1 WHERE uid = ?;"
		cursor.execute(update_query, (post_uid,))

		conn.commit()
		logging.info(
			f"Inserted {len(analysis_data_list)} analysis record(s) and marked post as analysed.")
		return True
	except sqlite3.IntegrityError as e:
		conn.rollback()
		logging.error("Integrity error in analysis insertion: %s", e)
		raise sqlite3.IntegrityError(
			f"Foreign key violation or constraint failed for post_uid {post_uid}. "
			f"Original error: {str(e)}"
		) from e
	except sqlite3.Error as error:
		conn.rollback()
		logging.error("Database error inserting analysis data: %s", error)
		raise
	finally:
		cursor.close()
		conn.close()


def read_post_analysis(filters=None, db_path=linkedin_db_path):
	conn = sqlite3.connect(db_path)
	conn.row_factory = sqlite3.Row
	cursor = conn.cursor()

	query = "SELECT * FROM post_analysis"
	params = []

	allowed_columns = {
		"analysis_id", "post_uid", "match_percentage", "contact_email",
		"contact_number", "application_link", "company_name", "should_apply",
		"subject", "body", "mail_sent", "model_used"
	}

	if filters:
		conditions = []
		for key, value in filters.items():
			if key not in allowed_columns:
				raise ValueError(f"Invalid filter key: {key}")
			conditions.append(f"{key} = ?")
			params.append(value)
		query += " WHERE " + " AND ".join(conditions)

	cursor.execute(query, params)
	rows = cursor.fetchall()

	if rows:
		results = [dict(row) for row in rows]
		for result in results:
			for field in ["contact_email", "contact_number", "application_link", "full_analysis_json"]:
				if result.get(field):
					try:
						result[field] = json.loads(result[field])
					except json.JSONDecodeError:
						pass
		print(json.dumps(results, indent=4, sort_keys=True))
		# print(tabulate(results, headers="keys", tablefmt="grid"))
	else:
		print("No analysis records found.")

	cursor.close()
	conn.close()

def execute_query(query,db_path=linkedin_db_path):
	conn = sqlite3.connect(db_path)
	conn.row_factory = sqlite3.Row
	cursor = conn.cursor()
	cursor.execute(query)
	conn.commit()
	cursor.close()
	conn.close()	


def count_unsent_mail_posts_by_date(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
    WITH RECURSIVE last_20_days(day) AS (
        SELECT DATE('now', '-19 days')
        UNION ALL
        SELECT DATE(day, '+1 day')
        FROM last_20_days
        WHERE day < DATE('now')
    )
    SELECT 
        last_20_days.day AS insertion_date,
        COUNT(DISTINCT linkedin_posts.uid) AS unsent_mail_post_count
    FROM 
        last_20_days
    LEFT JOIN 
        linkedin_posts ON DATE(linkedin_posts.inserted_at) = last_20_days.day
    LEFT JOIN 
        post_analysis ON post_analysis.post_uid = linkedin_posts.uid AND post_analysis.mail_sent = -1
    GROUP BY 
        last_20_days.day
    ORDER BY 
        last_20_days.day DESC;
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    results = [dict(row) for row in rows]
    print(json.dumps(results, indent=4, sort_keys=True))

    cursor.close()
    conn.close()

def read_posts(filters=None, db_path=linkedin_db_path):
	conn = sqlite3.connect(db_path)
	conn.row_factory = sqlite3.Row
	cursor = conn.cursor()

	query = "SELECT * FROM linkedin_posts"
	params = []

	allowed_columns = {"uid", "query", "post_link",
					   "post_text", "analysed", "post_date"}

	if filters:
		conditions = []
		for key, value in filters.items():
			if key not in allowed_columns:
				raise ValueError(f"Invalid filter key: {key}")
			conditions.append(f"{key} = ?")
			params.append(value)
		query += " WHERE " + " AND ".join(conditions)

	cursor.execute(query, params)
	rows = cursor.fetchall()

	if rows:
		results = [dict(row) for row in rows]
		for result in results:
			if result.get("other_data"):
				try:
					result["other_data"] = json.loads(result["other_data"])
				except json.JSONDecodeError:
					pass
		print(json.dumps(results, indent=4, sort_keys=True))
	else:
		print("No posts found.")

	cursor.close()
	conn.close()


def remove_db(db_path=linkedin_db_path, backup=True):
	"""
	Remove a SQLite database file, optionally creating a backup first.
	"""
	if not os.path.exists(db_path):
		print(f"Database file {db_path} does not exist.")
		return

	if backup:
		timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
		backup_path = f"{db_path}.backup_{timestamp}"

		try:
			shutil.copy2(db_path, backup_path)
			print(f"Backup created at: {backup_path}")
		except Exception as e:
			print(f"Failed to create backup: {e}")
			return

	try:
		os.remove(db_path)
		print(f"Successfully removed database: {db_path}")
	except Exception as e:
		print(f"Failed to remove database: {e}")


def process_job_data(json_file_path):
	"""
	Process JSON data and insert into database tables
	"""
	# Load JSON data
	with open(json_file_path, 'r') as f:
		all_jobs = json.load(f)

	for job_entry in all_jobs[:]:
		# Process LinkedIn post data
		job_post = job_entry['job_post']

		# Add query text to post_text
		job_post['post_text']
		job_post['query'] = 'Python Contract'

		# convert this date string to datetime: 2025-04-05 13: 13: 00
		job_post['post_date'] = datetime.strptime(
			job_post['post_date'], '%Y-%m-%d %H:%M:%S')
		
		try:
			# Insert into LinkedIn posts table
			post_uid = insert_linkedin_post(job_post)
			logging.info(f"Inserted post with UID: {post_uid}")
		except sqlite3.IntegrityError as e:
			logging.warning(
				f"Skipping duplicate post: {job_post['post_link']}")
			continue
		except Exception as e:
			logging.error(f"Error inserting post: {str(e)}")
			continue

		# Process analysis results
		analysis_data = job_entry['result']

		# Remove original_job_text from all analysis entries
		clean_analysis = []
		for analysis in analysis_data:
			analysis.pop('original_job_text', None)

			# Convert null values to appropriate types
			# for key in ['salary', 'application_deadline', 'security_clearance',
			# 			'visa_sponsorship', 'remote_eligibility', 'travel_requirements']:
			# 	if key in analysis.get('additional_data', {}) and analysis['additional_data'][key] is None:
			# 		analysis['additional_data'][key] = ""

			clean_analysis.append(analysis)

		try:
			# Insert into analysis table
			insert_post_analysis(post_uid, clean_analysis)
			logging.info(f"Inserted analysis for post UID: {post_uid}")
		except sqlite3.IntegrityError as e:
			logging.error(
				f"Foreign key violation for post UID {post_uid}: {str(e)}")
		except Exception as e:
			logging.error(f"Error inserting analysis: {str(e)}")


def count_unsent_mails(db_path=linkedin_db_path):
	"""
	Count the number of entries in post_analysis where mail_sent is False.
	"""
	conn = sqlite3.connect(db_path)
	cursor = conn.cursor()

	try:
		cursor.execute("SELECT COUNT(*) FROM post_analysis WHERE mail_sent = 0;")
		result = cursor.fetchone()
		count = result[0] if result else 0
		print(f"Unsent mails count: {count}")
		return count
	except sqlite3.Error as e:
		print(f"Database error: {e}")
		return 0
	finally:
		cursor.close()
		conn.close()


def run_raw_sql_query(sql_query, db_path=linkedin_db_path):
	"""
	Execute a raw SQL query and return the results as a list of dictionaries.
	"""
	conn = sqlite3.connect(db_path)
	conn.row_factory = sqlite3.Row
	cursor = conn.cursor()

	try:
		cursor.execute(sql_query)
		rows = cursor.fetchall()
		results = [dict(row) for row in rows]
		print(json.dumps(results, indent=4, sort_keys=True))
		return results
	except sqlite3.Error as e:
		print(f"Error executing query: {e}")
		return []
	finally:
		cursor.close()
		conn.close()


def mark_mail_sent_if_url_matches(file_path="post_url.txt", db_path=linkedin_db_path):
	"""
	Marks `mail_sent = 1` in post_analysis table for entries whose post_link (in linkedin_posts)
	is found in the given text file (one link per line).
	"""
	# Read all post links from the file and strip whitespace
	try:
		with open(file_path, "r", encoding="utf-8") as f:
			urls_to_mark = set(line.strip() for line in f if line.strip())
	except FileNotFoundError:
		print(f"File {file_path} not found.")
		return

	if not urls_to_mark:
		print("No URLs to process.")
		return

	conn = sqlite3.connect(db_path)
	cursor = conn.cursor()
	cursor.execute("PRAGMA foreign_keys = ON;")

	print(f"Marking mail_sent = 1 for {len(urls_to_mark)} URLs...")
	try:
		# Find all post_uid values that match the URLs
		cursor.execute(
			f"""
			SELECT pa.post_uid FROM post_analysis pa
			JOIN linkedin_posts lp ON pa.post_uid = lp.uid
			WHERE lp.post_link IN ({','.join(['?'] * len(urls_to_mark))}) AND pa.mail_sent = 0
			""",
			list(urls_to_mark)
		)
		matching_post_uids = [row[0] for row in cursor.fetchall()]
		print(f"Found {len(matching_post_uids)} matching posts.")

		if not matching_post_uids:
			print("No matching posts found for the given URLs.")
			return

		# Update mail_sent = 1 in post_analysis for all matching post_uids
		cursor.execute(
			f"""
			UPDATE post_analysis
			SET mail_sent = 1
			WHERE post_uid IN ({','.join(['?'] * len(matching_post_uids))})
			""",
			matching_post_uids
		)

		conn.commit()
		print(
			f"Updated {cursor.rowcount} rows in post_analysis with mail_sent = 1.")

	except sqlite3.Error as e:
		conn.rollback()
		print(f"Database error: {e}")
	finally:
		cursor.close()
		conn.close()


# Usage
init_db()
if __name__ == "__main__":
	# remove_db()
	# init_db()


	# output = read_linkedin_posts(linkedin_db_path, {"analysed": 0})	
	# print(json.dumps(output, indent=4, sort_keys=True))
	# raw_sql_query = """
	# 				SELECT count(*)
	# 				FROM linkedin_posts
	# 				WHERE analysed = 0
	# 				"""
	# output = run_raw_sql_query(raw_sql_query)

	# count_unsent_mail_posts_by_date(linkedin_db_path)
	raw_sql_query = """
				SELECT 
					pa.mail_sent
				FROM 
					linkedin_posts lp
				JOIN 
					post_analysis pa ON lp.uid = pa.post_uid
				WHERE 
					lp.post_link = "https://www.linkedin.com/feed/update/urn:li:activity:7328417439023538176";

					"""
	output = run_raw_sql_query(raw_sql_query)

	# process_job_data(json_path)

	# # Display results
	# print("\nAll Posts:")
	# read_posts()

	# print("\nAll Analysis:")
	# read_post_analysis()
	# remove_db()
	# init_db()

	# sample_post = {
	# 	"author_name": "Jane Doe",
	# 	"query": "Python Hiring",
	# 	"profile_url": "https://linkedin.com/in/janedoe",
	# 	"post_date": datetime.now(),
	# 	"post_link": "https://linkedin.com/posts/98765454",
	# 	"post_text": "This is an example LinkedIn post using SQLite.",
	# 	"hashtags": ["example", "sqlite"],
	# 	"reactions": {"like": 15, "insightful": 3},
	# 	"comments": ["Nice post!", "Very informative."]
	# }

	# try:
	# 	uid = insert_linkedin_post(sample_post)
	# 	print(f"Post inserted successfully with uid: {uid}")
	# except Exception as e:
	# 	print(f"Error inserting post: {e}")

	# post_uid = 1

	# sample_analysis = [{
	# 	"match_percentage": 85,
	# 	"contact_email": ["hr@companyxyz.com"],
	# 	"contact_number": ["+1234567890"],
	# 	"application_link": ["https://companyxyz.com/careers"],
	# 	"company_name": "Company XYZ",
	# 	"should_apply": True,
	# 	"message_content": {
	# 		"subject": "Application for Software Engineer",
	# 		"body": "Dear HR, I am interested in the position..."
	# 	},
	# 	"additional_data": {
	# 		"employment_type": "Full-time",
	# 		"application_deadline": "2025-05-01",
	# 		"education_requirements": "Bachelor's in Computer Science",
	# 		"certifications": ["AWS Certified Developer"],
	# 		"visa_sponsorship": True
	# 	}
	# }]

	# try:
	# 	insert_post_analysis(post_uid, sample_analysis, model_used="gpt-4")
	# except Exception as e:
	# 	print(f"Error inserting analysis: {e}")

	# read_post_analysis(filters={})
	# read_posts(filters={"query": "Golang Contract"})
	# count_unsent_mails(linkedin_db_path)

	# add column final_desicion to post_analysis


	# mark_mail_sent_if_url_matches()