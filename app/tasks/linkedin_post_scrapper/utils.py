import re
from collections import deque

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


