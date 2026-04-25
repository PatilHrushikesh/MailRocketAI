"""LinkedIn search query builder + small helpers used by the scraper."""
from __future__ import annotations

import logging
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

logger = logging.getLogger(__name__)


_EMAIL_PATTERN = re.compile(
    r"""
    (?xi)
    (?:
        [a-z0-9!#$%&'*+/=?^_`{|}~-]+
        (?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*
    |
        "(?:(?:\\[\x00-\x7f])|[^\\"])+"
    )
    @
    (?:
        (?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+
        [a-z0-9][a-z0-9-]{0,61}[a-z0-9]
    |
        \[
            (?:(?:25[0-5]|2[0-4]\d|1?\d{1,2})\.){3}
            (?:25[0-5]|2[0-4]\d|1?\d{1,2})
        \]
    )
    """,
    re.VERBOSE,
)


def contains_email(text: str) -> bool:
    """True if the text contains anything that looks like an email address."""
    return bool(text and _EMAIL_PATTERN.search(text))


class FixedSizeStore:
    """FIFO store of strings with bounded capacity (used for deduping recent posts)."""

    def __init__(self, size: int):
        if size <= 0:
            raise ValueError("Size must be positive")
        self.size = size
        self._data: deque[str] = deque()

    def insert(self, item: str) -> None:
        if not isinstance(item, str):
            raise TypeError("Only strings can be inserted")
        self._data.append(item)
        if len(self._data) > self.size:
            self._data.popleft()

    def find(self, item: str) -> bool:
        return item in self._data

    def __repr__(self) -> str:
        return f"FixedSizeStore(size={self.size}, items={list(self._data)})"


class LinkedInQueryBuilder:
    """Builds LinkedIn search query strings from a YAML config."""

    def __init__(self, yaml_path: Path | str):
        path = Path(yaml_path)
        logger.info("Loading search-queries config from %s", path)
        with path.open("r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self._validate()

    def _validate(self) -> None:
        if "searches" not in self.config:
            raise ValueError("YAML config must contain 'searches' section")
        for search in self.config["searches"]:
            if "name" not in search:
                raise ValueError("Each search must have a 'name' field")
            if "parameters" not in search:
                raise ValueError(
                    f"Search '{search.get('name', '[unknown]')}' must have 'parameters' section"
                )

    def build_all_queries(self) -> Dict[str, List[Tuple[str, int, bool]]]:
        result: Dict[str, List[Tuple[str, int, bool]]] = defaultdict(list)
        for search in self.config["searches"]:
            if not search.get("enabled", True):
                logger.info("Skipping disabled search: %s", search["name"])
                continue

            sort_option = search.get("sort_by_latest_option", 0)
            sort_flags = {0: [False], 1: [True], 2: [False, True]}.get(sort_option, [False])

            base_query = self._build_base_query(search)
            queries: List[Tuple[str, int, bool]] = []
            if "locations" in search:
                for location in search["locations"]:
                    for sort_flag in sort_flags:
                        queries.append(
                            (f'{base_query} AND "{location}"', search.get("max_results", 10), sort_flag)
                        )
            else:
                for sort_flag in sort_flags:
                    queries.append((base_query, search.get("max_results", 10), sort_flag))

            result[search["name"]].extend(queries)
            logger.info("Built %d queries for search '%s'", len(queries), search["name"])
        return result

    def _build_base_query(self, search_config: Dict) -> str:
        components: list[str] = []

        includes = search_config["parameters"].get("includes", {})
        include_components: list[str] = []
        if "keywords" in includes:
            include_components.extend(includes["keywords"])
        if "exact_phrases" in includes:
            include_components.extend(f'"{p}"' for p in includes["exact_phrases"])
        if "groups" in includes:
            for group in includes["groups"]:
                include_components.append(self._process_group(group))
        if "industries" in search_config:
            industries = [f'"{ind}"' for ind in search_config["industries"]]
            include_components.append(f"({' OR '.join(industries)})")
        if include_components:
            components.append(" AND ".join(include_components))

        excludes = search_config["parameters"].get("excludes", {})
        exclude_components: list[str] = []
        if "keywords" in excludes:
            exclude_components.extend(excludes["keywords"])
        if "exact_phrases" in excludes:
            exclude_components.extend(f'"{p}"' for p in excludes["exact_phrases"])
        if "groups" in excludes:
            for group in excludes["groups"]:
                exclude_components.append(self._process_group(group))
        if exclude_components:
            components.append("NOT " + " NOT ".join(exclude_components))

        return " ".join(components)

    def _process_group(self, group: Dict, level: int = 0) -> str:
        operator = group["operator"]
        terms: list[str] = []
        for term in group["terms"]:
            if isinstance(term, dict) and "group" in term:
                terms.append(self._process_group(term["group"], level + 1))
            else:
                terms.append(str(term))
        if len(terms) > 1 or level > 0:
            return f"({f' {operator} '.join(terms)})"
        return f" {operator} ".join(terms)


def read_queries_from_file(file_path: Path | str) -> List[Tuple[str, int, bool]]:
    """Read enabled queries and return a flat list of (query, max_results, sort_by_latest)."""
    builder = LinkedInQueryBuilder(file_path)
    queries_by_name = builder.build_all_queries()
    flat: List[Tuple[str, int, bool]] = []
    for query_list in queries_by_name.values():
        flat.extend(query_list)
    return flat
