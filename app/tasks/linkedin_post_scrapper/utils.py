from collections import defaultdict
import re
from collections import deque

import yaml
import logging
from typing import Dict, List, Tuple

from collections import defaultdict

def build_all_queries(self) -> Dict[str, List[Tuple[str, int, bool]]]:
    result = defaultdict(list)
    logging.info("Building queries for all enabled search configurations...")

    for search in self.config['searches']:
        enabled = search.get("enabled", True)
        if not enabled:
            logging.info(f"Skipping disabled search: {search['name']}")
            continue

        sort_option = search.get("sort_by_latest_option", 0)
        sort_flags = {
            0: [False],
            1: [True],
            2: [False, True]
        }.get(sort_option, [False])  # default to [False] if undefined

        queries = []
        base_query = self.build_base_query(search)
        logging.debug(f"Base query for '{search['name']}': {base_query}")

        if 'locations' in search:
            for location in search['locations']:
                for sort_flag in sort_flags:
                    location_query = f'{base_query} AND "{location}"'
                    queries.append((location_query, search.get('max_results', 10), sort_flag))
        else:
            for sort_flag in sort_flags:
                queries.append((base_query, search.get('max_results', 10), sort_flag))

        result[search['name']].extend(queries)
        logging.info(f"Built {len(queries)} queries for search '{search['name']}'")
    return result


# Configure logging
logging.basicConfig(level=logging.INFO,
					format="%(asctime)s - %(levelname)s - %(message)s")


class LinkedInQueryBuilder:
	def __init__(self, yaml_path: str):
		logging.info(f"Loading configuration from: {yaml_path}")
		try:
			with open(yaml_path, 'r') as f:
				self.config = yaml.safe_load(f)
			logging.info("Configuration loaded successfully.")
		except Exception as e:
			logging.error(f"Failed to load YAML: {e}")
			raise

		self.validate_config()

	def validate_config(self):
		if 'searches' not in self.config:
			raise ValueError("YAML config must contain 'searches' section")
		for search in self.config['searches']:
			if 'name' not in search:
				raise ValueError("Each search must have a 'name' field")
			if 'parameters' not in search:
				raise ValueError(
					f"Search '{search.get('name', '[unknown]')}' must have 'parameters' section")
		logging.info("Configuration validation passed.")


	def build_all_queries(self) -> Dict[str, List[Tuple[str, int, bool]]]:
		result = defaultdict(list)
		logging.info("Building queries for all enabled search configurations...")

		for search in self.config['searches']:
			enabled = search.get("enabled", True)
			if not enabled:
				logging.info(f"Skipping disabled search: {search['name']}")
				continue

			sort_option = search.get("sort_by_latest_option", 0)
			sort_flags = {
				0: [False],
				1: [True],
				2: [False, True]
			}.get(sort_option, [False])  # default to [False] if undefined

			queries = []
			base_query = self.build_base_query(search)
			logging.debug(f"Base query for '{search['name']}': {base_query}")

			if 'locations' in search:
				for location in search['locations']:
					for sort_flag in sort_flags:
						location_query = f'{base_query} AND "{location}"'
						queries.append(
							(location_query, search.get('max_results', 10), sort_flag))
			else:
				for sort_flag in sort_flags:
					queries.append(
						(base_query, search.get('max_results', 10), sort_flag))

			result[search['name']].extend(queries)
			logging.info(
				f"Built {len(queries)} queries for search '{search['name']}'")
		return result


	def build_base_query(self, search_config: Dict) -> str:
		components = []

		includes = search_config['parameters'].get('includes', {})
		include_components = []

		if 'keywords' in includes:
			include_components.extend(includes['keywords'])

		if 'exact_phrases' in includes:
			include_components.extend(
				f'"{phrase}"' for phrase in includes['exact_phrases'])

		if 'groups' in includes:
			for group in includes['groups']:
				include_components.append(self.process_group(group))

		if 'industries' in search_config:
			industries = [f'"{ind}"' for ind in search_config['industries']]
			include_components.append(f"({' OR '.join(industries)})")

		if include_components:
			components.append(' AND '.join(include_components))

		excludes = search_config['parameters'].get('excludes', {})
		exclude_components = []

		if 'keywords' in excludes:
			exclude_components.extend(excludes['keywords'])

		if 'exact_phrases' in excludes:
			exclude_components.extend(
				f'"{phrase}"' for phrase in excludes['exact_phrases'])

		if 'groups' in excludes:
			for group in excludes['groups']:
				exclude_components.append(self.process_group(group))

		if exclude_components:
			components.append('NOT ' + ' NOT '.join(exclude_components))

		return ' '.join(components)

	def process_group(self, group: Dict, level: int = 0) -> str:
		operator = group['operator']
		terms = []

		for term in group['terms']:
			if isinstance(term, dict) and 'group' in term:
				terms.append(self.process_group(term['group'], level+1))
			else:
				terms.append(str(term))

		if len(terms) > 1 or level > 0:
			return f"({f' {operator} '.join(terms)})"
		return f' {operator} '.join(terms)


def execute_search(query: str, max_results: int):
	logging.info(f"Executing search (limit: {max_results})")
	logging.debug(f"Query: {query}")
	print(f"\nExecuting search (limit: {max_results}):\nQuery: {query}")


			
class FixedSizeStore:
	"""
	A fixed-size storage for strings. Maintains the most recent `size` inserted items.
	When capacity is exceeded, removes the least recently inserted element (FIFO).
	"""
	def __init__(self, size: int):
		if size <= 0:
			raise ValueError("Size must be a positive integer")
		self.size = size
		self._data = deque()

	def insert(self, item: str) -> None:
		"""
		Insert a string into the store. If capacity is exceeded,
		removes the oldest inserted element.
		"""
		if not isinstance(item, str):
			raise TypeError("Only strings can be inserted")

		self._data.append(item)
		if len(self._data) > self.size:
			self._data.popleft()

	def find(self, item: str) -> bool:
		"""
		Returns True if the string exists in the current store, False otherwise.
		"""
		if not isinstance(item, str):
			raise TypeError("Find operation requires a string")

		return item in self._data

	def __repr__(self):
		return f"FixedSizeStore(size={self.size}, items={list(self._data)})"


def contains_email(text):
	"""
	Check if the provided text contains a valid email address.

	Returns:
		bool: True if an email is found, False otherwise.
	"""
	# Regex pattern for matching email addresses.
	# This pattern covers:
	#   - Normal unquoted local-parts (letters, digits, allowed special characters, dots)
	#   - Quoted local-parts
	#   - Domain names with subdomains and TLDs
	#   - Domains in IP address format (IPv4)
	email_pattern = re.compile(
		r"""
		(?xi)                             # Case-insensitive, verbose regex mode
		(?:                               # Non-capturing group for the whole email pattern
			(?:                           # Local part: unquoted
				[a-z0-9!#$%&'*+/=?^_`{|}~-]+
				(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*
			|
				"                         # OR quoted local part
				(?:(?:\\[\x00-\x7f])|[^\\"])+
				"
			)
			@                             # At symbol separating local and domain parts
			(?:
				(?:                       # Domain name parts: e.g. example.com, sub.example.co.uk
					[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.
				)+
				[a-z0-9][a-z0-9-]{0,61}[a-z0-9]
			|
				\[                        # OR literal IP address enclosed in brackets
					(?:
						(?:25[0-5]|2[0-4]\d|1?\d{1,2})
						\.
					){3}
					(?:25[0-5]|2[0-4]\d|1?\d{1,2})
				\]
			)
		)
	""",
		re.VERBOSE,
	)

	# Search the text for a match; return True if found.
	return re.search(email_pattern, text) is not None


def read_queries_from_file(file_path):
    """
    Read search queries from a text file.
    Returns list of (query_str, max_results, sort_by_latest) tuples.
    """
    builder = LinkedInQueryBuilder(file_path)
    queries = builder.build_all_queries()

    full_query_list = []
    for query_list in queries.values():
        full_query_list.extend(query_list)

    return full_query_list

if __name__ == "__main__":
	queries = read_queries_from_file(
		"D:\\Projects\\linkedin_mail_sender\\app\\tasks\\search_queries.yaml")
	for query in queries:
		print(query)