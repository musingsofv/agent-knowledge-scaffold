"""Pure exact filtering and literal text matching.

Text is NFKC-normalized, case-folded, then split into Unicode word/mark runs
and individual non-whitespace punctuation tokens. Whitespace is insignificant
between tokens; punctuation is literal. Thus ``C++`` cannot match ``C``, while
the token ``C`` can occur within ``C++``. Exact language identity belongs in
the language filter, not in a special text-search heuristic.

Catalog labels and aliases offer direct phrase alternatives. Replacement does
not infer facets, follow catalog relationships, or recursively expand aliases.
Each metadata field/list entry and the supplied body is a separate surface;
phrases never bridge those surfaces. The caller owns Markdown interpretation
and physical line mapping; this module receives only text and typed values.

Prepare a query once when searching several documents. Prepared values are
immutable and retain only direct substitutions relevant to the query. No
catalog scan, alias expansion or query normalization happens per candidate.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from unicodedata import category, normalize

from agent_knowledge.domain.catalog import Catalog
from agent_knowledge.domain.models import KnowledgeDocument, SearchQuery, TextQuery

Tokens = tuple[str, ...]
Transition = tuple[int, Tokens]


@dataclass(frozen=True, slots=True)
class _PreparedPhrase:
    transitions: tuple[tuple[Transition, ...], ...]


@dataclass(frozen=True, slots=True)
class TextOccurrence:
    """One phrase's inclusive physical line span; phrase indices are zero-based."""

    group: str
    phrase_index: int
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class PreparedTextQuery:
    """Reuse normalized phrase transitions across independent candidate surfaces."""

    any: tuple[_PreparedPhrase, ...]
    all: tuple[_PreparedPhrase, ...]

    def matches(self, surfaces: tuple[str, ...]) -> bool:
        normalized = tuple(normalize_tokens(surface) for surface in surfaces)

        def found(phrase: _PreparedPhrase) -> bool:
            return any(_contains_phrase(surface, phrase) for surface in normalized)

        return (not self.any or any(found(phrase) for phrase in self.any)) and all(
            found(phrase) for phrase in self.all
        )

    def occurrences(self, lines: tuple[tuple[int, str], ...]) -> tuple[TextOccurrence, ...]:
        """Locate each contributing phrase without requiring the full query here.

        Callers supply one rendered text value per physical line. Phrases may
        span adjacent lines, including blank lines, but never a gap between line
        numbers. Repeated token matches sharing a phrase and line span coalesce.
        The result sorts by start line, end line, group and phrase index.
        """
        spans: set[tuple[int, int, str, int]] = set()
        for tokens, line_numbers in _tokenized_line_runs(lines):
            for group, phrases in (("any", self.any), ("all", self.all)):
                for phrase_index, phrase in enumerate(phrases):
                    for start, end in _phrase_spans(tokens, phrase):
                        spans.add((line_numbers[start], line_numbers[end - 1], group, phrase_index))
        return tuple(
            TextOccurrence(group, phrase_index, start, end)
            for start, end, group, phrase_index in sorted(spans)
        )


@dataclass(frozen=True, slots=True)
class PreparedQuery:
    """A reusable query snapshot with no catalog reference or mutable cache."""

    query: SearchQuery
    text: PreparedTextQuery | None

    def facets_match(self, document: KnowledgeDocument) -> bool:
        """Check metadata applicability before callers render a candidate's body."""
        return _matches_facets(document, self.query)

    def matches(self, document: KnowledgeDocument) -> bool:
        if not self.facets_match(document):
            return False
        if self.text is None:
            return True
        metadata = document.metadata
        return self.text.matches(
            (
                metadata.title,
                metadata.description,
                *metadata.aliases,
                *metadata.terms,
                document.body,
            )
        )


def normalize_tokens(text: str) -> Tokens:
    """Normalize literal text without regex syntax, stemming or fuzzy expansion."""
    tokens: list[str] = []
    word: list[str] = []
    for character in normalize("NFKC", text).casefold():
        if character.isalnum() or character == "_" or category(character).startswith("M"):
            word.append(character)
            continue
        if word:
            tokens.append("".join(word))
            word = []
        if not character.isspace():
            tokens.append(character)
    if word:
        tokens.append("".join(word))
    return tuple(tokens)


def prepare_text_query(query: TextQuery, catalog: Catalog) -> PreparedTextQuery:
    """Resolve direct aliases once, indexed only at positions in the original query."""
    phrases = tuple(normalize_tokens(phrase) for phrase in (*query.any, *query.all))
    choices: list[list[set[Transition]]] = [
        [{(1, (token,))} for token in phrase] for phrase in phrases
    ]
    starts: dict[str, list[tuple[int, int]]] = {}
    for phrase_index, phrase in enumerate(phrases):
        for token_index, token in enumerate(phrase):
            starts.setdefault(token, []).append((phrase_index, token_index))
    for record in catalog.records:
        labels = record.aliases + ((record.label,) if record.label is not None else ())
        forms = {tokens for label in labels if (tokens := normalize_tokens(label))}
        for form in forms:
            for phrase_index, token_index in starts.get(form[0], ()):
                if phrases[phrase_index][token_index : token_index + len(form)] == form:
                    choices[phrase_index][token_index].update(
                        (len(form), replacement) for replacement in forms - {form}
                    )
    prepared = tuple(
        _PreparedPhrase(tuple(tuple(sorted(transitions)) for transitions in phrase_choices))
        for phrase_choices in choices
    )
    return PreparedTextQuery(any=prepared[: len(query.any)], all=prepared[len(query.any) :])


def prepare_query(query: SearchQuery, catalog: Catalog) -> PreparedQuery:
    """Prepare once per query/catalog, then call ``matches`` on each candidate."""
    return PreparedQuery(
        query=query,
        text=prepare_text_query(query.text, catalog) if query.text is not None else None,
    )


def _contains_phrase(surface: Tokens, phrase: _PreparedPhrase) -> bool:
    return next(_phrase_spans(surface, phrase), None) is not None


def _phrase_spans(surface: Tokens, phrase: _PreparedPhrase) -> Iterator[tuple[int, int]]:
    """Yield token spans using bounded states rather than alias phrase products.

    Track one candidate start at a time so locating a match does not retain all
    possible starts for every query position across a large document.
    """
    if not phrase.transitions:
        return
    if all(len(choices) == 1 for choices in phrase.transitions):
        # No aliases: every choice is the original one-token transition. Avoid
        # allocating a state machine per literal hit in a repetitive body.
        literal = tuple(choices[0][1][0] for choices in phrase.transitions)
        for start, token in enumerate(surface):
            if token == literal[0] and surface[start : start + len(literal)] == literal:
                yield start, start + len(literal)
        return
    if len(phrase.transitions) == 1:
        for start in range(len(surface)):
            for _, replacement in phrase.transitions[0]:
                end = start + len(replacement)
                if surface[start:end] == replacement:
                    yield start, end
        return
    first_tokens = {replacement[0] for _, replacement in phrase.transitions[0]}
    for start, token in enumerate(surface):
        if token not in first_tokens:
            continue
        positions: list[set[int]] = [set() for _ in range(len(phrase.transitions) + 1)]
        positions[0].add(start)
        for phrase_index, surface_positions in enumerate(positions[:-1]):
            for consumed, replacement in phrase.transitions[phrase_index]:
                for surface_index in surface_positions:
                    end = surface_index + len(replacement)
                    if surface[surface_index:end] == replacement:
                        positions[phrase_index + consumed].add(end)
        for end in sorted(positions[-1]):
            yield start, end


def _tokenized_line_runs(
    lines: tuple[tuple[int, str], ...],
) -> Iterator[tuple[Tokens, tuple[int, ...]]]:
    tokens: list[str] = []
    line_numbers: list[int] = []
    previous_line: int | None = None
    for line_number, text in lines:
        if previous_line is not None and line_number != previous_line + 1:
            if tokens:
                yield tuple(tokens), tuple(line_numbers)
            tokens = []
            line_numbers = []
        normalized = normalize_tokens(text)
        tokens.extend(normalized)
        line_numbers.extend([line_number] * len(normalized))
        previous_line = line_number
    if tokens:
        yield tuple(tokens), tuple(line_numbers)


def text_matches(surfaces: tuple[str, ...], query: TextQuery, catalog: Catalog) -> bool:
    """Match one surface collection; use ``prepare_text_query`` for repeated calls."""
    return prepare_text_query(query, catalog).matches(surfaces)


def _matches_facets(document: KnowledgeDocument, query: SearchQuery) -> bool:
    metadata = document.metadata
    if query.sources is not None and document.source_id not in query.sources:
        return False
    if query.kind is not None and metadata.kind not in query.kind:
        return False
    for requested, applicable in (
        (query.scope, metadata.scope),
        (query.topics, metadata.topics),
        (query.entities, metadata.entities),
        (query.languages, metadata.languages),
        (query.technologies, metadata.technologies),
        (query.environments, metadata.environments),
    ):
        if requested is not None and not set(requested).intersection(applicable or ()):
            return False
    return True


def matches(document: KnowledgeDocument, query: SearchQuery, catalog: Catalog) -> bool:
    """Match one document; use ``prepare_query`` when scanning several candidates."""
    return _matches_facets(document, query) and prepare_query(query, catalog).matches(document)
